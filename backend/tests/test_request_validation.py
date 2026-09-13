"""A request the server does not understand is refused, not quietly reinterpreted.

Pydantic drops unknown fields by default. On a cleaning request that behaved far worse
than it sounds: a body naming only fields that do not exist parsed into a config of all
defaults, rebuilt the cleaned table with no cleaning in it, and returned 200. The caller
was told it had worked. It had undone the previous run.
"""

import json
import re

import pytest
from conftest import wait_for_job
from pydantic import BaseModel

from app.main import app
from app.models import schemas


# ---- the defect ----------------------------------------------------------------------

@pytest.fixture(scope="module")
def messy(admin, tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("strict") / "dupes.csv"
    path.write_text(
        "plate,make,year\n1,Toyota,2015\n1,Toyota,2015\n2,Kia,2019\n3,Ford,2020\n",
        encoding="utf-8",
    )
    with open(path, "rb") as f:
        up = admin.post("/api/datasets/upload", files={"file": ("dupes.csv", f, "text/csv")})
    assert up.status_code == 200, up.text
    dataset_id = up.json()["dataset_id"]
    started = admin.post(
        f"/api/datasets/{dataset_id}/import",
        json={"encoding": "utf-8", "delimiter": ",", "has_header": True},
    )
    assert wait_for_job(admin, started.json()["id"])["status"] == "done"
    return dataset_id


def cleaned_rows(admin, dataset_id: str):
    return admin.get(f"/api/datasets/{dataset_id}").json()["row_count_cleaned"]


def test_a_cleaning_request_of_unknown_fields_is_refused(admin, messy):
    r = admin.post(
        f"/api/datasets/{messy}/clean",
        json={"remove_duplicates": True, "trim_whitespace": True},
    )
    assert r.status_code == 422, r.text
    assert "remove_duplicates" in r.text, "the refusal should name the field it did not know"


def test_a_refused_cleaning_does_not_undo_the_last_one(admin, messy):
    """The heart of it. The call used to succeed and silently revert the previous run."""
    applied = admin.post(f"/api/datasets/{messy}/clean", json={"dedupe": True})
    assert applied.status_code == 200, applied.text
    assert applied.json()["duplicates_removed"] >= 1
    before = cleaned_rows(admin, messy)

    refused = admin.post(f"/api/datasets/{messy}/clean", json={"remove_duplicates": True})
    assert refused.status_code == 422

    assert cleaned_rows(admin, messy) == before, "the earlier cleaning was undone"


def test_a_misspelt_field_beside_correct_ones_is_still_refused(admin, messy):
    """The dangerous shape is the half-right request, not the entirely wrong one."""
    r = admin.post(
        f"/api/datasets/{messy}/clean", json={"dedupe": True, "dedup_key_columns": ["plate"]}
    )
    assert r.status_code == 422, r.text
    assert "dedup_key_columns" in r.text


def test_an_unknown_field_is_refused_across_the_endpoints(admin, messy):
    for path, body in [
        (f"/api/datasets/{messy}/data", {"page": 1, "bogus": 1}),
        (f"/api/datasets/{messy}/export", {"format": "csv", "bogus": 1}),
        (f"/api/datasets/{messy}/group", {"column": "make", "bogus": 1}),
        ("/api/users", {"username": "x_qa", "password": "abcdef1", "role": "viewer", "bogus": 1}),
        ("/api/roles", {"name": "QA Bogus", "permissions": [], "bogus": 1}),
        ("/api/auth/login", {"username": "a", "password": "b", "bogus": 1}),
        ("/api/admin/activity/purge", {"older_than_days": 3650, "bogus": 1}),
    ]:
        r = admin.post(path, json=body)
        assert r.status_code == 422, (path, r.status_code, r.text[:160])


def test_an_unknown_field_nested_in_a_filter_is_refused(admin, messy):
    """A typo three levels down is exactly as quiet as one at the top."""
    r = admin.post(
        f"/api/datasets/{messy}/data",
        json={"page": 1, "filters": [{"column": "make", "op": "eq", "value": "Kia", "negate": True}]},
    )
    assert r.status_code == 422, r.text
    assert "negate" in r.text


def test_a_rename_cannot_smuggle_a_second_field(admin, messy):
    r = admin.patch(f"/api/datasets/{messy}", json={"name": "ok.csv", "row_count_raw": 99})
    assert r.status_code == 422, r.text


# ---- the other half: what the interface sends must still be accepted -------------------

def test_the_payloads_the_interface_sends_are_accepted(admin, messy, dataset):
    """Tightening validation is only half a fix if it refuses the real client. These are
    the bodies the frontend builds, field for field."""
    rules = [{"column": "tozeret_nm", "op": "eq", "value": "קיה ישראל"}]
    for path, body in [
        (f"/api/datasets/{dataset}/data",
         {"page": 1, "page_size": 25, "sort_by": None, "sort_dir": "asc", "search": None,
          "search_columns": None, "filters": [], "source": "cleaned"}),
        (f"/api/datasets/{dataset}/group",
         {"column": "tozeret_nm", "page": 1, "page_size": 100, "search": None,
          "search_columns": None, "filters": [], "source": "cleaned"}),
        (f"/api/datasets/{dataset}/export",
         {"format": "csv", "scope": "current_view", "source": "cleaned", "search": None,
          "search_columns": None, "filters": [], "sort_by": None, "sort_dir": "asc"}),
        (f"/api/datasets/{messy}/clean",
         {"keep_columns": ["plate", "make"], "dedupe": False,
          "dedupe_key_columns": None, "filters": []}),
        (f"/api/datasets/{dataset}/statistics",
         {"group_by": "tozeret_nm", "filters": [], "search": None, "source": "cleaned",
          "limit": 50, "sort": "count", "granularity": "year", "bins": 20}),
        (f"/api/datasets/{dataset}/pivot",
         {"row_column": "tozeret_nm", "column_column": "sug_delek_nm", "filters": [],
          "search": None, "source": "cleaned", "row_limit": 25, "column_limit": 12,
          "row_granularity": "year", "column_granularity": "year"}),
        (f"/api/datasets/{dataset}/statistics/export",
         {"format": "csv", "title": "t", "subtitle": "s", "headers": ["a", "b", "c"],
          "rows": [{"label": "Kia", "count": 5, "percentage": 12.5}],
          "total_label": "Total", "total": 5}),
    ]:
        r = admin.post(path, json=body)
        assert r.status_code not in (400, 422), (path, r.status_code, r.text[:200])

    r = admin.post(f"/api/datasets/{dataset}/data", json={"page": 1, "filters": rules})
    assert r.status_code == 200, r.text


def test_optional_fields_may_still_be_left_out(admin, messy):
    """Forbidding unknown fields must not have turned optional ones into required ones."""
    assert admin.post(f"/api/datasets/{messy}/data", json={}).status_code == 200
    assert admin.post(f"/api/datasets/{messy}/clean", json={}).status_code == 200


# ---- the structural guard -------------------------------------------------------------

def _refs(blob) -> set[str]:
    return set(re.findall(r"#/components/schemas/([A-Za-z0-9_]+)", json.dumps(blob)))


def request_model_names() -> set[str]:
    """Every schema a request body parses into, read from the published OpenAPI.

    Taken from the spec rather than from FastAPI's route objects: the internals moved
    between versions, and this is the same description the clients are written against.
    Nested schemas are followed, since a filter rule is as much a request body as the
    query holding it.
    """
    spec = app.openapi()
    names: set[str] = set()
    for operations in spec.get("paths", {}).values():
        for operation in operations.values():
            body = (operation or {}).get("requestBody")
            if body:
                names |= _refs(body)

    components = spec.get("components", {}).get("schemas", {})
    pending = list(names)
    while pending:
        nested = _refs(components.get(pending.pop(), {})) - names
        names |= nested
        pending.extend(nested)

    # FastAPI generates its own model for the multipart upload; it is not ours to set.
    return {n for n in names if not n.startswith("Body_")}


def request_models() -> list:
    return [getattr(schemas, name) for name in sorted(request_model_names())
            if isinstance(getattr(schemas, name, None), type)
            and issubclass(getattr(schemas, name), BaseModel)]


def test_the_scan_finds_the_request_models():
    found = {m.__name__ for m in request_models()}
    assert len(found) >= 15, found
    for expected in ("CleaningConfig", "DataQuery", "FilterRule", "CreateUserRequest",
                     "StatisticsExportRow"):
        assert expected in found, f"the scan missed {expected}"


def test_every_request_model_refuses_unknown_fields():
    """The guard that matters: a request model added later inherits BaseModel by habit
    and is loose again. Naming them individually here would have the same problem, so
    the list comes from the routes themselves."""
    loose = sorted(
        m.__name__ for m in request_models() if m.model_config.get("extra") != "forbid"
    )
    assert not loose, (
        f"these parse a request body but ignore unknown fields: {', '.join(loose)} - "
        "they should inherit schemas.Incoming"
    )


def test_responses_are_left_alone():
    """Only what clients send is strict. Responses are built in this codebase, and
    tightening them would buy nothing while risking a 500 on a field we added."""
    assert schemas.DataPage.model_config.get("extra") != "forbid"
    assert schemas.UserOut.model_config.get("extra") != "forbid"
