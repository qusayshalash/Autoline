"""Which filters fit a vehicle: the configuration key, the import, and the lookup.

The real reference database is built from catalogue data kept out of the repository, so
these tests build a small one of their own from a two-row file in the merged format.
"""

import csv

import pytest

from app.config import settings
from app.services import fitment

# 49-107-66 in the registry: a 2009 Hyundai i30. Its key in the merged catalogue file is
# this exact value - the recipe was recovered from that file and then reproduced for all
# 4,114,487 registry vehicles; this pins it.
I30 = {
    "tozeret_cd": "0481",
    "sug_degem": "P",
    "degem_cd": "0791",
    "degem_manoa": "G4FC",
    "shnat_yitzur": "2009",
    "sug_delek_nm": "בנזין",
    "kvutzat_zihum": "15",
}
I30_KEY = "75aebcb996c5b5eac9e763f20ef0097eeffcf4ae8ba2e4585e2d85e8969bf6de"

COLUMNS = [
    "configuration_key", "vehicle_count", "vehicle_powertrain", "fitment_sources", "combined_fitment_coverage",
    "mann_match_status", "mann_match_method",
    "oil_filter_parts", "air_filter_parts", "fuel_filter_parts", "cabin_air_filter_parts",
    "ufi_direct_match_status", "ufi_direct_match_confidence",
    "ufi_direct_oil_filter_parts", "ufi_direct_air_filter_parts", "ufi_direct_fuel_filter_parts", "ufi_direct_cabin_air_filter_parts",
    "ufi_cross_reference_oil_filter_parts", "ufi_cross_reference_air_filter_parts",
    "ufi_cross_reference_fuel_filter_parts", "ufi_cross_reference_cabin_air_filter_parts",
    "jsfilter_match_status", "jsfilter_match_confidence",
    "jsfilter_oil_filter_parts", "jsfilter_air_filter_parts", "jsfilter_fuel_filter_parts", "jsfilter_cabin_air_filter_parts",
    "denckermann_match_status", "denckermann_match_confidence",
    "denckermann_oil_filter_parts", "denckermann_air_filter_parts", "denckermann_fuel_filter_parts", "denckermann_cabin_air_filter_parts",
]


@pytest.fixture
def reference(tmp_path, monkeypatch):
    """A reference built from small catalogue files: the i30's configuration, where MANN
    and JS Filter name the same oil filter (one shared Hyundai OE number) and different
    air filters (OE numbers that share nothing), and an uncovered configuration."""
    import sqlite3

    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    fitment.reset()
    outputs, dataprime = tmp_path / "outputs", tmp_path / "dataprime"
    outputs.mkdir()
    dataprime.mkdir()

    from scripts import build_fitment

    with (outputs / build_fitment.MERGED).open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS + ["tozeret_nm"])
        w.writeheader()
        w.writerow({
            "configuration_key": I30_KEY, "vehicle_count": "1244", "vehicle_powertrain": "combustion_or_hybrid",
            "tozeret_nm": "יונדאי קוריאה",
            "fitment_sources": "MANN-FILTER;JS Filter", "combined_fitment_coverage": "covered",
            "mann_match_status": "matched", "mann_match_method": "vin",
            "oil_filter_parts": "W811/80_MANN-FILTER", "air_filter_parts": "C2029_MANN-FILTER",
            "fuel_filter_parts": "LIFETIME-FILTER", "cabin_air_filter_parts": "CU2532_MANN-FILTER;CUK2532_MANN-FILTER",
            "ufi_cross_reference_oil_filter_parts": "23.139.00;23.461.00",
            "jsfilter_match_status": "matched_engine_model_year_body", "jsfilter_match_confidence": "safe_engine_model_year",
            "jsfilter_oil_filter_parts": "C304J", "jsfilter_air_filter_parts": "A9320",
            "denckermann_match_status": "not_matched",
        })
        w.writerow({"configuration_key": "0" * 64, "vehicle_count": "11", "combined_fitment_coverage": "uncovered",
                    "mann_match_status": "not_found", "mann_match_method": "vin"})
    (outputs / build_fitment.UFI_XREF).write_text("ufi_product_code,manufacturer,cross_code\n", encoding="utf-8")
    (outputs / "mann_filter_oem_references.csv").write_text(
        "mann_part_number,reference_manufacturer,reference_number\n"
        "W811/80,HYUNDAI,26300-35503\n"
        "C2029,HYUNDAI,28113-2H000\n",
        encoding="utf-8",
    )
    db = sqlite3.connect(dataprime / "dataset.db")
    db.execute("CREATE TABLE filter_part (filter_id INT, part_number TEXT)")
    db.execute("CREATE TABLE part_oe (filter_id INT, oe_brand TEXT, oe_part_no TEXT)")
    db.executemany("INSERT INTO filter_part VALUES (?, ?)", [(1, "C304J"), (2, "A9320")])
    db.executemany("INSERT INTO part_oe VALUES (?, ?, ?)", [(1, "HYUNDAI", "26300 35503"), (2, "HYUNDAI", "28113-1H000")])
    db.commit()
    db.close()
    db = sqlite3.connect(dataprime / "denckermann.db")
    db.execute("CREATE TABLE result (oe_query TEXT, part_no TEXT)")
    db.commit()
    db.close()
    (dataprime / "normalize.py").write_text(
        "def parse_manufacturer(s):\n    return ('Hyundai', 'Korea') if s and s.startswith('יונדאי') else None\n",
        encoding="utf-8",
    )

    result = build_fitment.build(outputs, dataprime)
    assert result["configurations"] == 2 and result["vehicles"] == 1255
    yield
    fitment.reset()


def test_the_configuration_key_is_the_catalogue_file_s_own():
    assert fitment.config_key(I30) == I30_KEY
    # every field counts: the same car with another engine is another configuration
    assert fitment.config_key({**I30, "degem_manoa": "G4FA"}) != I30_KEY


def test_part_lists_split_into_part_and_brand():
    assert fitment.parse_parts("CU2532_MANN-FILTER;CUK2532_MANN-FILTER") == [
        {"part": "CU2532", "brand": "MANN-FILTER"},
        {"part": "CUK2532", "brand": "MANN-FILTER"},
    ]
    assert fitment.parse_parts("C304J") == [{"part": "C304J", "brand": None}]
    assert fitment.parse_parts("") == [] and fitment.parse_parts(None) == []


def test_every_source_is_reported_separately(reference):
    out = fitment.lookup(I30)
    assert out["found"] and out["covered"] and out["vehicles"] == 1244
    assert out["matches"]["mann"] == {"status": "matched", "detail": "vin"}
    assert [p["part"] for p in out["filters"]["oil"]["mann"]] == ["W811/80"]
    assert [p["part"] for p in out["filters"]["oil"]["jsfilter"]] == ["C304J"]
    assert [p["part"] for p in out["filters"]["oil"]["ufi_xref"]] == ["23.139.00", "23.461.00"]
    assert len(out["filters"]["cabin"]["mann"]) == 2  # alternatives, not a contradiction
    assert "denckermann" not in out["filters"]["oil"]


def test_catalogues_agree_only_on_a_shared_original_number(reference):
    """MANN W811/80 and JS C304J answer to the same Hyundai OE number, spelled two ways;
    the air filters answer to two different ones, which is a contradiction to show."""
    verdicts = fitment.lookup(I30)["verdicts"]
    assert verdicts["oil"] == {"verdict": "agree", "clashes": []}
    assert verdicts["air"] == {"verdict": "disagree", "clashes": ["jsfilter|mann"]}
    assert verdicts["cabin"]["verdict"] == "single"  # MANN alone, alternatives and all
    assert "fuel" not in verdicts  # "lifetime" is a statement, not a part to compare


def test_nothing_is_inferred_for_a_vehicle_the_catalogues_do_not_cover(reference):
    unknown = fitment.lookup({**I30, "degem_cd": "9999"})
    assert unknown["found"] is False and unknown["filters"] == {}


def test_without_the_reference_database_the_lookup_says_so(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "data_dir", tmp_path)
    fitment.reset()
    assert fitment.available() is False
    assert fitment.lookup(I30) is None
