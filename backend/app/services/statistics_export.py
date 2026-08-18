"""Writes a finished breakdown to CSV, XLSX or PDF.

Unlike the row exporter next door, these files are tiny - fifty rows at most - so they
are built in memory and returned on the same request instead of going through the job
queue and leaving a file on disk. That also keeps the exports folder for what it is
meant to hold: full data extracts.

Arabic and Hebrew need the same reshape/bidi treatment the PDF row export already uses,
because reportlab draws glyphs in logical order and would otherwise print RTL text
reversed and disconnected.
"""

import csv
import io

import arabic_reshaper
import xlsxwriter
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from app.models.schemas import StatisticsExportRequest
from app.services.pdf_fonts import data_font

MEDIA_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


def build(req: StatisticsExportRequest) -> bytes:
    if req.format == "csv":
        return _csv(req)
    if req.format == "xlsx":
        return _xlsx(req)
    return _pdf(req)


def _csv(req: StatisticsExportRequest) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if req.title:
        writer.writerow([req.title])
    if req.subtitle:
        writer.writerow([req.subtitle])
    if req.title or req.subtitle:
        writer.writerow([])
    writer.writerow(req.headers)
    for row in req.rows:
        writer.writerow([row.label, row.count, f"{row.percentage:.2f}"])
    writer.writerow([req.total_label, req.total, ""])
    # BOM so Excel opens the file as UTF-8 instead of mangling Hebrew and Arabic
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def _xlsx(req: StatisticsExportRequest) -> bytes:
    buf = io.BytesIO()
    book = xlsxwriter.Workbook(buf, {"in_memory": True})
    sheet = book.add_worksheet("Statistics")
    sheet.right_to_left()

    title_fmt = book.add_format({"bold": True, "font_size": 14})
    sub_fmt = book.add_format({"font_color": "#666666"})
    head_fmt = book.add_format(
        {"bold": True, "bg_color": "#eef0ff", "border": 1, "border_color": "#d6d9e6"}
    )
    num_fmt = book.add_format({"num_format": "#,##0"})
    pct_fmt = book.add_format({"num_format": "0.00%"})
    total_fmt = book.add_format({"bold": True, "top": 1})
    total_num_fmt = book.add_format({"bold": True, "top": 1, "num_format": "#,##0"})

    r = 0
    if req.title:
        sheet.write(r, 0, req.title, title_fmt)
        r += 1
    if req.subtitle:
        sheet.write(r, 0, req.subtitle, sub_fmt)
        r += 1
    if r:
        r += 1

    for c, header in enumerate(req.headers):
        sheet.write(r, c, header, head_fmt)
    r += 1

    for row in req.rows:
        sheet.write(r, 0, row.label)
        sheet.write_number(r, 1, row.count, num_fmt)
        # stored as a real fraction so Excel's own percentage formatting applies and the
        # cell can be charted or summed like a number rather than parsed from text
        sheet.write_number(r, 2, row.percentage / 100.0, pct_fmt)
        r += 1

    sheet.write(r, 0, req.total_label, total_fmt)
    sheet.write_number(r, 1, req.total, total_num_fmt)

    sheet.set_column(0, 0, 34)
    sheet.set_column(1, 2, 16)
    book.close()
    return buf.getvalue()


def _rtl(value: object) -> str:
    text = "" if value is None else str(value)
    try:
        return get_display(arabic_reshaper.reshape(text))
    except Exception:  # noqa: BLE001 - never let presentation break an export
        return text


def _pdf(req: StatisticsExportRequest) -> bytes:
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=req.title or "Statistics")
    font = data_font()

    story = []
    if req.title:
        story.append(
            Paragraph(
                _rtl(req.title),
                ParagraphStyle("t", fontName=font, fontSize=15, leading=19, alignment=2),
            )
        )
    if req.subtitle:
        story.append(
            Paragraph(
                _rtl(req.subtitle),
                ParagraphStyle(
                    "s",
                    fontName=font,
                    fontSize=9,
                    leading=13,
                    alignment=2,
                    textColor=colors.grey,
                ),
            )
        )
    story.append(Spacer(1, 14))

    data = [[_rtl(h) for h in req.headers]]
    data += [[_rtl(r.label), f"{r.count:,}", f"{r.percentage:.2f}%"] for r in req.rows]
    data.append([_rtl(req.total_label), f"{req.total:,}", ""])

    table = Table(data, repeatRows=1, colWidths=[260, 110, 90])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef0ff")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#3730a3")),
                ("FONTNAME", (0, 0), (-1, -1), font),
                ("FONTSIZE", (0, 0), (-1, -1), 8.5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#d6d9e6")),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f7f8fa")]),
                ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#f0f1f5")),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.HexColor("#9ca3af")),
            ]
        )
    )
    story.append(table)
    doc.build(story)
    return buf.getvalue()
