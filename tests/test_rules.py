"""
Michael's Allianz test cases. Run with:  python -m pytest
Ages are calculated as of 11/04/2026, the date the test cases were written for.
"""

import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import documents  # noqa: E402
import rules      # noqa: E402

AS_OF = datetime.date(2026, 11, 4)
ROUTING = rules.load_routing_config(
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "config", "routing_rules.json"))


def make_form(dob, contribution, duration, offset, design="Single life recovery", **extra):
    form = {
        "requestor_name": "Test Requestor", "requestor_email": "test@example.com",
        "advisor_of_record": "Test Advisor", "date_needed": datetime.date(2026, 12, 1),
        "case_reference": "", "client_id": "ORG-TEST", "organization_name": "Test Org",
        "offset_pct": offset, "offset_overridden": True, "override_reason": "Test",
        "design_type": design,
        "p_first": "John", "p_middle": "", "p_last": "Smith", "p_gender": "Male",
        "p_dob": dob, "p_state": "GA", "p_tobacco": "Non-Tobacco",
        "participant_contribution": contribution, "duration_years": duration,
    }
    form.update(extra)
    return form


# (dob, contribution, duration, offset, age, benefit, target, recovery, income start, reduce face?)
CASES = [
    (datetime.date(1985, 10, 20), 85000, 10, 10, 41, 79475, 25432, 14025, 65, False),
    (datetime.date(1976, 1, 10), 60000, 7, 15, 50, 58650, 18768, 10350, 65, True),
    (datetime.date(1963, 3, 15), 50000, 10, 0, 63, 42500, 13600, 7500, 70, False),
    (datetime.date(1959, 6, 1), 100000, 5, 20, 67, 102000, 32640, 18000, 75, True),
]


@pytest.mark.parametrize("dob,contrib,dur,offset,age,benefit,target,recovery,income,reduce", CASES)
def test_michaels_cases(dob, contrib, dur, offset, age, benefit, target, recovery, income, reduce):
    req = rules.build_request(make_form(dob, contrib, dur, offset), ROUTING, AS_OF)
    assert req["primary"]["age"] == age
    assert req["benefit_premium"] == benefit
    assert req["target_premium_goal"] == target
    assert req["recovery_premium"] == recovery
    assert req["primary"]["income_start_age"] == income
    expected_face = rules.FACE_TEXT_REDUCE if reduce else rules.FACE_TEXT_NO_CHANGE
    assert req["face_instruction"] == expected_face
    assert req["benefit_carrier"] == "Allianz Life"


@pytest.mark.parametrize("age,expected", [(61, 65), (62, 70), (65, 70), (66, 75), (84, 75)])
def test_income_age_boundaries(age, expected):
    assert rules.income_start_age(age) == expected


def test_age_uses_last_birthday():
    dob = datetime.date(1964, 11, 5)
    assert rules.age_on(dob, datetime.date(2026, 11, 4)) == 61  # day before birthday
    assert rules.age_on(dob, datetime.date(2026, 11, 5)) == 62  # on the birthday


@pytest.mark.parametrize("duration,reduce", [(5, True), (7, True), (8, False), (10, False)])
def test_face_instruction_cutoff(duration, reduce):
    expected = rules.FACE_TEXT_REDUCE if reduce else rules.FACE_TEXT_NO_CHANGE
    assert rules.face_instruction(duration) == expected


@pytest.mark.parametrize("design,amount,carriers", [
    ("Single life recovery", 500000, ["John Hancock", "Symetra"]),
    ("Joint life recovery", 199999, ["Penn Mutual", "National Life"]),
    ("Joint life recovery", 199999.50, ["Penn Mutual", "National Life"]),
    ("Joint life recovery", 200000, ["Penn Mutual", "National Life", "Lincoln Financial"]),
])
def test_routing(design, amount, carriers):
    result = rules.evaluate_routing(design, amount, amount, ROUTING)
    assert result["recovery_carriers"] == carriers


def test_john_smith_sheet_has_every_field_filled():
    req = rules.build_request(make_form(datetime.date(1985, 10, 20), 85000, 10, 10), ROUTING, AS_OF)
    html, pdf = documents.build_benefit_sheet(req, "DRAFT", ROUTING)
    for text in ["John Smith", "10/20/1985", "$79,475", "years 1 through 10",
                 "years 11 to maturity", "$25,432", "Age 65 through age 84",
                 "Preferred Non-Tobacco", "No change after year 1"]:
        assert text in html, text
    assert pdf.startswith(b"%PDF")


def test_secondary_insured_never_on_benefit_sheet():
    form = make_form(datetime.date(1985, 10, 20), 85000, 10, 10, design="Joint life recovery",
                     s_first="Jane", s_middle="", s_last="Doe", s_gender="Female",
                     s_dob=datetime.date(1987, 2, 2), s_state="GA", s_tobacco="Non-Tobacco")
    req = rules.build_request(form, ROUTING, AS_OF)
    html, _ = documents.build_benefit_sheet(req, "DRAFT", ROUTING)
    assert "Jane" not in html and "Doe" not in html
