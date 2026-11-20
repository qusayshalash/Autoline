"""Reading a chassis number against the registry's record of the vehicle.

The rules per prefix are measured on the registry (scripts/build_vin_table.py); these
tests stand in a small table of their own, so they say what the reader does with a rule,
not which makers the real registry happened to show.
"""

import pytest

from app.services import vin

TABLE = {
    "KMH": {"cars": 1000, "makes": ["יונדאי קוריאה"], "year_code": True, "model_code": True, "check_digit": False},
    "JTD": {"cars": 1000, "makes": ["טויוטה יפן"], "year_code": False, "model_code": False, "check_digit": False},
    "1M8": {"cars": 1000, "makes": ["מוטור קואץ' ארהב"], "year_code": True, "model_code": False, "check_digit": True},
    "WDB": {"cars": 1000, "makes": ["מרצדס בנץ גרמנ"], "year_code": False, "model_code": False, "check_digit": False},
}


@pytest.fixture(autouse=True)
def small_table(monkeypatch):
    monkeypatch.setattr(vin, "table", lambda: TABLE)


def car(chassis, make="יונדאי קוריאה", model="DB51D", year="2009"):
    return {"misgeret": chassis, "tozeret_nm": make, "degem_nm": model, "shnat_yitzur": year}


def test_a_real_number_that_agrees_with_its_record():
    """49-107-66 in the real registry: a 2009 Hyundai i30."""
    out = vin.read(car("KMHDB51DP9U143756"))
    assert out["verdict"] == "ok"
    assert (out["maker"]["state"], out["model"]["state"], out["year"]["state"]) == ("match", "match", "match")
    assert out["year"]["decoded"] == 2009 and out["serial"] == "143756"


def test_another_make_than_the_prefix_is_bad():
    out = vin.read(car("KMHDB51DP9U143756", make="קיה קוריאה"))
    assert out["verdict"] == "bad" and out["maker"]["state"] == "mismatch"


def test_the_make_is_compared_by_brand_not_by_plant():
    """One WMI covers several plants; an Austrian-built G-Class is still a Mercedes."""
    assert vin.read(car("WDB4632021X203975", make="מרצדס-בנץ אוסט", model="463.202", year="2012"))["verdict"] == "ok"


def test_a_year_one_off_is_normal_and_two_off_is_worth_a_look():
    assert vin.read(car("KMHDB51DP9U143756", year="2008"))["year"]["state"] == "near"
    assert vin.read(car("KMHDB51DP9U143756", year="2008"))["verdict"] == "ok"
    far = vin.read(car("KMHDB51DP9U143756", year="2006"))
    assert far["year"]["state"] == "mismatch" and far["verdict"] == "warn"


def test_a_rule_a_maker_does_not_follow_is_not_applied():
    """Toyota does not put the year in character 10 for cars sold here."""
    out = vin.read(car("JTDBR32E000000002", make="טויוטה יפן", model="X", year="1995"))
    assert out["year"]["state"] == "unchecked" and out["model"]["state"] == "unchecked"
    assert out["verdict"] == "ok"


def test_the_check_digit_where_the_maker_uses_it():
    """1M8GDM9AXKP042788 is the standard's own worked example: its check digit is X."""
    good = vin.read(car("1M8GDM9AXKP042788", make="מוטור קואץ' ארהב", model="", year="1989"))
    assert good["check_digit"]["state"] == "valid" and good["verdict"] == "ok"
    typo = vin.read(car("1M8GDM9A1KP042788", make="מוטור קואץ' ארהב", model="", year="1989"))
    assert typo["check_digit"]["state"] == "invalid" and typo["verdict"] == "warn"


def test_numbers_that_cannot_be_read():
    assert vin.read(car("")) is None
    assert vin.read(car("ABC12345"))["verdict"] == "nonstandard"  # older, not 17 characters
    assert vin.read(car("KMHDB51DO9U143756"))["verdict"] == "nonstandard"  # O is never used
    assert vin.read(car("ZZZDB51DP9U143756"))["verdict"] == "unknown"  # prefix too rare to judge


@pytest.mark.parametrize("code,near,year", [("A", 2012, 2010), ("A", 1985, 1980), ("9", 2009, 2009), ("Y", 2028, 2030), ("U", 2010, None)])
def test_the_year_code_reads_the_nearer_of_its_two_cycles(code, near, year):
    assert vin.model_year(code, near) == year


def test_the_measured_table_ships_with_the_app():
    """The reader is only as good as its table; it must be there and cover the commonest makers."""
    import json

    data = json.loads(vin.TABLE.read_text(encoding="utf-8"))
    for prefix in ("KMH", "KNA", "TMB", "NMT", "JTD"):
        assert prefix in data["prefixes"], prefix
    assert data["prefixes"]["KMH"]["year_code"] is True
    assert data["prefixes"]["NMT"]["year_code"] is False  # Toyota Turkey: no year in character 10
