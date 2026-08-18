"""Small readers used by the integration tests, so each test says what it checks rather
than how it paged through the API."""

from typing import Any


def page(client, dataset_id: str, **body) -> dict:
    body.setdefault("page_size", 1000)
    r = client.post(f"/api/datasets/{dataset_id}/data", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def rows_as_dicts(client, dataset_id: str, **body) -> list[dict[str, Any]]:
    """Every matching row, as dicts keyed by column name."""
    out: list[dict[str, Any]] = []
    p = 1
    while True:
        data = page(client, dataset_id, page=p, **body)
        cols = data["columns"]
        out.extend(dict(zip(cols, row)) for row in data["rows"])
        if len(out) >= data["total_rows"] or not data["rows"]:
            return out
        p += 1


def total(client, dataset_id: str, **body) -> int:
    body["page_size"] = 1
    return page(client, dataset_id, **body)["total_rows"]


def breakdown(client, dataset_id: str, **body) -> dict:
    r = client.post(f"/api/datasets/{dataset_id}/statistics", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def pivot(client, dataset_id: str, **body) -> dict:
    r = client.post(f"/api/datasets/{dataset_id}/pivot", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def buckets(breakdown_out: dict) -> dict[str, int]:
    """Breakdown items as {label: count}, with the synthetic buckets named explicitly so
    a test can tell a real category from an aggregate."""
    out = {}
    for item in breakdown_out["items"]:
        if item["other"]:
            key = "__other__"
        elif item["unspecified"]:
            key = "__unspecified__"
        else:
            key = item["value"]
        out[key] = item["count"]
    return out
