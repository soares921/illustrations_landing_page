"""
Business rules for CAP illustration requests.

Everything here is a plain function with no Streamlit code, so the same rules
can be reused by the landing page, the tests, and a future census upload.

Rules are written by ROLE (benefit / recovery), never by carrier name.
Which carrier fills each role comes from config/routing_rules.json.
"""

import datetime
import json
import os
from decimal import Decimal, ROUND_HALF_UP

# ==========================================
# FIXED RULE VALUES (from Michael's spec)
# ==========================================

BENEFIT_SHARE = Decimal("0.85")         # share of total funding to the benefit policy
RECOVERY_SHARE = Decimal("0.15")        # share to EACH recovery carrier (not divided)
TARGET_PREMIUM_PCT = Decimal("0.32")    # target premium goal = benefit premium x 32%

MAX_ISSUE_AGE = 84
INCOME_END_AGE = 84

# (upper age limit inclusive, income start age), checked in order
INCOME_START_TABLE = [
    (61, 65),    # under 62        -> 65
    (65, 70),    # 62 through 65   -> 70
    (999, 75),   # 66 and older    -> 75
]

FACE_REDUCTION_DURATION_CUTOFF = 8  # durations of 8+ years keep the issue face
FACE_TEXT_NO_CHANGE = "No change after year 1. Run the issue face through maturity."
FACE_TEXT_REDUCE = (
    "Keep the issue face for years 1 through 7. Starting in year 8, "
    "reduce base face as far as the software allows, through maturity."
)


# ==========================================
# HELPERS
# ==========================================

def round_dollars(value):
    """Round to the nearest whole dollar, with .50 always rounding up."""
    return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_dollars(value):
    """85000 -> '$85,000' (no cents)."""
    return f"${round_dollars(value):,}"


def format_date(value):
    """date -> 'MM/DD/YYYY'."""
    return value.strftime("%m/%d/%Y")


def underwriting_class(tobacco_status):
    """Every case is illustrated at Preferred."""
    return "Preferred Tobacco" if tobacco_status == "Tobacco" else "Preferred Non-Tobacco"


# ==========================================
# AGE RULES
# ==========================================

def age_on(dob, as_of=None):
    """Age based on last birthday, as of the given date (default: today)."""
    as_of = as_of or datetime.date.today()
    had_birthday = (as_of.month, as_of.day) >= (dob.month, dob.day)
    return as_of.year - dob.year - (0 if had_birthday else 1)


def income_start_age(age):
    for upper_limit, start_age in INCOME_START_TABLE:
        if age <= upper_limit:
            return start_age
    raise ValueError(f"No income start age defined for age {age}")


# ==========================================
# PREMIUM RULES
# ==========================================

def calculate_premiums(participant_contribution, offset_pct):
    """
    Total funding = participant contribution x (1 + employer offset).
    Benefit premium = 85% of total. Each recovery carrier gets 15% of total.
    Target premium goal = 32% of the (rounded) benefit premium.
    """
    contribution = Decimal(str(participant_contribution))
    offset = Decimal(str(offset_pct)) / Decimal("100")

    total_funding = contribution * (Decimal("1") + offset)
    benefit_premium = round_dollars(total_funding * BENEFIT_SHARE)
    recovery_premium = round_dollars(total_funding * RECOVERY_SHARE)
    target_premium_goal = round_dollars(Decimal(benefit_premium) * TARGET_PREMIUM_PCT)

    return {
        "total_funding": round_dollars(total_funding),
        "benefit_premium": benefit_premium,
        "recovery_premium": recovery_premium,
        "target_premium_goal": target_premium_goal,
    }


# ==========================================
# FACE INSTRUCTION RULE
# ==========================================

def face_instruction(duration_years):
    """Depends only on duration. Reduction always starts in year 8 (7 pay rule)."""
    if duration_years >= FACE_REDUCTION_DURATION_CUTOFF:
        return FACE_TEXT_NO_CHANGE
    return FACE_TEXT_REDUCE


# ==========================================
# ROUTING (reads config/routing_rules.json)
# ==========================================

def load_routing_config(file_path):
    """Reads the routing file. Stops with a clear error if it is missing."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Routing file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def evaluate_routing(design_type, participant_contribution, total_funding, config):
    """
    Returns the benefit carrier, the recovery carriers, and the matched rule.
    The amount compared against each rule is set by "routing_basis" in the
    config: "participant_contribution" or "total_funding".
    """
    basis = config.get("routing_basis", "participant_contribution")
    amount = total_funding if basis == "total_funding" else participant_contribution

    for rule in config["recovery_rules"]:
        if rule["design_type"] != design_type:
            continue
        min_c = rule["min_contribution"]
        below_max = rule["below_contribution"] is None or amount < rule["below_contribution"]
        if amount >= min_c and below_max:
            return {
                "benefit_carrier": config["benefit"]["carrier"],
                "recovery_carriers": rule["recovery_carriers"],
                "rule": rule,
            }

    return {
        "benefit_carrier": config["benefit"]["carrier"],
        "recovery_carriers": [],
        "rule": None,
    }


# ==========================================
# BUILD A COMPLETE REQUEST
# ==========================================

def build_request(form, routing_config, as_of=None):
    """
    Turns raw form answers into one complete request: calculated premiums,
    ages, routing, and every value the carrier sheets need.

    `form` is a plain dict, so a census upload row can be passed in the same way.
    """
    as_of = as_of or datetime.date.today()
    premiums = calculate_premiums(form["participant_contribution"], form["offset_pct"])
    routing = evaluate_routing(
        form["design_type"],
        form["participant_contribution"],
        premiums["total_funding"],
        routing_config,
    )

    def insured_block(prefix):
        dob = form[f"{prefix}_dob"]
        age = age_on(dob, as_of)
        return {
            "first_name": form[f"{prefix}_first"].strip(),
            "middle_name": (form.get(f"{prefix}_middle") or "").strip(),
            "last_name": form[f"{prefix}_last"].strip(),
            "gender": form[f"{prefix}_gender"],
            "dob": dob,
            "age": age,
            "state": form[f"{prefix}_state"],
            "tobacco_status": form[f"{prefix}_tobacco"],
            "underwriting_class": underwriting_class(form[f"{prefix}_tobacco"]),
            "income_start_age": income_start_age(age),
        }

    is_joint = form["design_type"] == "Joint life recovery"

    return {
        "as_of": as_of,
        "requestor_name": form["requestor_name"].strip(),
        "requestor_email": form["requestor_email"].strip(),
        "advisor_of_record": form["advisor_of_record"].strip(),
        "date_needed": form["date_needed"],
        "case_reference": (form.get("case_reference") or "").strip(),
        "client_id": form.get("client_id"),
        "organization_name": form["organization_name"],
        "offset_pct": float(form["offset_pct"]),
        "offset_overridden": bool(form.get("offset_overridden")),
        "override_reason": (form.get("override_reason") or "").strip(),
        "design_type": form["design_type"],
        "primary": insured_block("p"),
        "secondary": insured_block("s") if is_joint else None,
        "participant_contribution": round_dollars(form["participant_contribution"]),
        "duration_years": int(form["duration_years"]),
        **premiums,
        "face_instruction": face_instruction(int(form["duration_years"])),
        "benefit_carrier": routing["benefit_carrier"],
        "recovery_carriers": routing["recovery_carriers"],
        "routing_rule_id": routing["rule"]["rule_id"] if routing["rule"] else None,
        "routing_note": routing["rule"].get("note", "") if routing["rule"] else "",
        "solve_target": None,  # placeholder: Michael is standardizing this by design type
    }
