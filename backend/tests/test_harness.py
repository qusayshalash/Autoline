"""Proves the harness itself: isolation, a live app, and a fully imported dataset."""

from pathlib import Path

from app.config import settings


def test_data_dir_is_a_throwaway(tmp_path_factory):
    assert "csvstudio-test-data-" in str(settings.data_dir)


def test_health(api):
    assert api.get("/api/health").json() == {"status": "ok"}


def test_dataset_imported_every_row(dataset, oracle, admin):
    r = admin.get(f"/api/datasets/{dataset}")
    assert r.status_code == 200, r.text
    assert r.json()["row_count_raw"] == len(oracle)
