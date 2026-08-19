"""Streaming exporters. All three formats read the result set in bounded batches
(or let DuckDB's own COPY stream straight to disk) so a multi-million-row export
never materializes fully in Python memory.
"""

from pathlib import Path

import arabic_reshaper
import xlsxwriter
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle

from app.config import settings
from app.db import catalog
from app.db.connection import datasets
from app.jobs import submit
from app.models.schemas import ExportRequest
from app.services import sql_utils
from app.services.pdf_fonts import data_font


def build_export_query(dataset_id: str, req: ExportRequest) -> tuple[str, list, list[str]]:
    table = sql_utils.resolve_source_table(dataset_id, req.source)
    columns = sql_utils.table_columns(dataset_id, table)
    valid = set(columns)

    where_clauses: list[str] = []
    params: list = []

    if req.scope == "current_view":
        if req.search:
            s_sql, s_params = sql_utils.build_search_sql(req.search, columns)
            where_clauses.append(s_sql)
            params.extend(s_params)
        if req.filters:
            f_sql, f_params = sql_utils.build_filter_sql(req.filters, valid)
            if f_sql:
                where_clauses.append(f_sql)
                params.extend(f_params)

    where_sql = " AND ".join(f"({c})" for c in where_clauses)

    order_sql = ""
    if req.scope == "current_view" and req.sort_by:
        order_sql = " ORDER BY " + sql_utils.build_order_sql(req.sort_by, req.sort_dir, valid)

    cols_sql = ", ".join(sql_utils.quote_ident(c) for c in columns)
    sql = (
        f"SELECT {cols_sql} FROM {sql_utils.quote_ident(table)}"
        + (f" WHERE {where_sql}" if where_sql else "")
        + order_sql
    )
    return sql, params, columns


def export_csv(dataset_id: str, req: ExportRequest, out_path: Path) -> None:
    # held for the whole write: exporting four million rows takes minutes, and the file
    # must not be replaced or closed underneath it
    with datasets.reading(dataset_id) as cur:
        sql, params, _columns = build_export_query(dataset_id, req)
        escaped = str(out_path).replace("'", "''")
        cur.execute(f"COPY ({sql}) TO '{escaped}' (FORMAT CSV, HEADER)", params)


def export_xlsx(dataset_id: str, req: ExportRequest, out_path: Path) -> None:
    with datasets.reading(dataset_id) as cur:
        _export_xlsx(cur, dataset_id, req, out_path)


def _export_xlsx(cur, dataset_id: str, req: ExportRequest, out_path: Path) -> None:
    sql, params, columns = build_export_query(dataset_id, req)
    cur.execute(sql, params)

    workbook = xlsxwriter.Workbook(str(out_path), {"constant_memory": True})
    sheet_index = 1
    row_limit = settings.xlsx_sheet_row_limit

    def new_sheet():
        ws = workbook.add_worksheet(f"Sheet{sheet_index}")
        for c, col in enumerate(columns):
            ws.write(0, c, col)
        return ws

    sheet = new_sheet()
    row_in_sheet = 1  # row 0 is the header

    while True:
        batch = cur.fetchmany(settings.xlsx_batch_rows)
        if not batch:
            break
        for record in batch:
            if row_in_sheet >= row_limit:
                sheet_index += 1
                sheet = new_sheet()
                row_in_sheet = 1
            for c, value in enumerate(record):
                sheet.write(row_in_sheet, c, "" if value is None else value)
            row_in_sheet += 1

    workbook.close()


def _fix_rtl(value) -> str:
    text = "" if value is None else str(value)
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def export_pdf(dataset_id: str, req: ExportRequest, out_path: Path) -> None:
    sql, params, columns = build_export_query(dataset_id, req)
    bounded_sql = sql + " LIMIT ?"
    with datasets.reading(dataset_id) as cur:
        rows = cur.execute(bounded_sql, [*params, settings.pdf_row_limit]).fetchall()

    header = [_fix_rtl(c) for c in columns]
    body = [[_fix_rtl(v) for v in row] for row in rows]
    data = [header] + body

    doc = SimpleDocTemplate(str(out_path), pagesize=landscape(A4))
    table = Table(data, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2b2b40")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                # without this every Hebrew value in the file prints as a .notdef box:
                # reportlab's built-in faces are Latin-1 only
                ("FONTNAME", (0, 0), (-1, -1), data_font()),
                ("FONTSIZE", (0, 0), (-1, -1), 6),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f7")]),
            ]
        )
    )
    doc.build([table])


def run_export_job(dataset_id: str, job_id: str, req: ExportRequest) -> None:
    try:
        catalog.update_job(job_id, status="running", progress="exporting")
        out_dir = settings.exports_dir / dataset_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{job_id}.{req.format}"

        if req.format == "csv":
            export_csv(dataset_id, req, out_path)
        elif req.format == "xlsx":
            export_xlsx(dataset_id, req, out_path)
        elif req.format == "pdf":
            export_pdf(dataset_id, req, out_path)
        else:
            raise ValueError(f"Unsupported export format: {req.format}")

        size_bytes = out_path.stat().st_size
        catalog.update_job(
            job_id,
            status="done",
            progress="ready",
            result_json={"filename": out_path.name, "size_bytes": size_bytes, "format": req.format},
        )
    except Exception as exc:  # noqa: BLE001
        catalog.update_job(job_id, status="error", error_message=str(exc))


def start_export(dataset_id: str, req: ExportRequest) -> str:
    job_id = catalog.create_job(dataset_id, "export")
    submit(run_export_job, dataset_id, job_id, req)
    return job_id
