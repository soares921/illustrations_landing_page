"""
Google Sheet storage.

The spreadsheet "CAP Illustration Requests" has two tabs:
  Clients  - the Client Key (one row per organization)
  Requests - one row per submitted request; also the source of Request IDs

Connection details live in Streamlit secrets, never in this code.
If the sheet is not connected yet, the client list falls back to
config/clients_seed.csv so the form can still be tested, and submitting is
turned off.
"""

import csv
import datetime
import json
import os

import streamlit as st

CLIENTS_TAB = "Clients"
REQUESTS_TAB = "Requests"
SEED_FILE = os.path.join(os.path.dirname(__file__), "config", "clients_seed.csv")

CLIENT_COLUMNS = ["client_id", "organization_name", "default_offset_pct", "active"]

REQUEST_COLUMNS = [
    "request_id", "submitted_at", "status",
    "requestor_name", "requestor_email", "advisor_of_record", "date_needed", "case_reference",
    "client_id", "organization_name", "offset_pct", "offset_overridden", "override_reason",
    "design_type",
    "primary_first", "primary_middle", "primary_last", "primary_gender", "primary_dob",
    "primary_age", "primary_state", "primary_underwriting_class", "primary_income_start_age",
    "secondary_first", "secondary_middle", "secondary_last", "secondary_gender", "secondary_dob",
    "secondary_age", "secondary_state", "secondary_underwriting_class",
    "participant_contribution", "duration_years", "total_funding",
    "benefit_premium", "recovery_premium", "target_premium_goal",
    "benefit_carrier", "recovery_carriers", "routing_rule_id",
    "request_json",
]


# ==========================================
# CONNECTION
# ==========================================

def is_connected():
    try:
        return "gcp_service_account" in st.secrets and "google_sheet" in st.secrets
    except Exception:
        return False  # no secrets file at all


@st.cache_resource
def _spreadsheet():
    import gspread
    client = gspread.service_account_from_dict(dict(st.secrets["gcp_service_account"]))
    return client.open_by_key(st.secrets["google_sheet"]["spreadsheet_id"])


# ==========================================
# CLIENTS
# ==========================================

def _parse_pct(value):
    """Accepts 15, '15', or '15%' and returns 15.0."""
    text = str(value).strip().replace("%", "")
    return float(text) if text else 0.0


def _parse_active(value):
    return str(value).strip().upper() in ("TRUE", "YES", "Y", "1", "")


def _clean_clients(rows):
    clients = []
    for row in rows:
        name = str(row.get("organization_name", "")).strip()
        if not name:
            continue
        clients.append({
            "client_id": str(row.get("client_id", "")).strip(),
            "organization_name": name,
            "default_offset_pct": _parse_pct(row.get("default_offset_pct", 0)),
            "active": _parse_active(row.get("active", "TRUE")),
        })
    return sorted(clients, key=lambda c: c["organization_name"].lower())


@st.cache_data(ttl=60)  # new rows in the Clients tab show up within a minute
def load_clients():
    """Returns (clients, source) where source is 'sheet' or 'sample'."""
    if is_connected():
        rows = _spreadsheet().worksheet(CLIENTS_TAB).get_all_records()
        missing = [c for c in CLIENT_COLUMNS if rows and c not in rows[0]]
        if missing:
            raise ValueError(f"The {CLIENTS_TAB} tab is missing columns: {', '.join(missing)}")
        return _clean_clients(rows), "sheet"

    with open(SEED_FILE, newline="", encoding="utf-8") as f:
        return _clean_clients(list(csv.DictReader(f))), "sample"


# ==========================================
# REQUESTS
# ==========================================

def _next_request_id(worksheet, year):
    """CAP-YYYY-0001, counting up within each year."""
    prefix = f"CAP-{year}-"
    numbers = [
        int(value[len(prefix):])
        for value in worksheet.col_values(1)
        if value.startswith(prefix) and value[len(prefix):].isdigit()
    ]
    return f"{prefix}{(max(numbers) + 1 if numbers else 1):04d}"


def _request_row(request, request_id):
    p, s = request["primary"], request["secondary"] or {}

    def fmt(d):
        return d.strftime("%m/%d/%Y") if d else ""

    values = {
        "request_id": request_id,
        "submitted_at": datetime.datetime.now().strftime("%m/%d/%Y %I:%M %p"),
        "status": "Submitted",
        "requestor_name": request["requestor_name"],
        "requestor_email": request["requestor_email"],
        "advisor_of_record": request["advisor_of_record"],
        "date_needed": fmt(request["date_needed"]),
        "case_reference": request["case_reference"],
        "client_id": request["client_id"] or "",
        "organization_name": request["organization_name"],
        "offset_pct": request["offset_pct"],
        "offset_overridden": "Yes" if request["offset_overridden"] else "No",
        "override_reason": request["override_reason"],
        "design_type": request["design_type"],
        "primary_first": p["first_name"], "primary_middle": p["middle_name"],
        "primary_last": p["last_name"], "primary_gender": p["gender"],
        "primary_dob": fmt(p["dob"]), "primary_age": p["age"], "primary_state": p["state"],
        "primary_underwriting_class": p["underwriting_class"],
        "primary_income_start_age": p["income_start_age"],
        "secondary_first": s.get("first_name", ""), "secondary_middle": s.get("middle_name", ""),
        "secondary_last": s.get("last_name", ""), "secondary_gender": s.get("gender", ""),
        "secondary_dob": fmt(s.get("dob")), "secondary_age": s.get("age", ""),
        "secondary_state": s.get("state", ""),
        "secondary_underwriting_class": s.get("underwriting_class", ""),
        "participant_contribution": request["participant_contribution"],
        "duration_years": request["duration_years"],
        "total_funding": request["total_funding"],
        "benefit_premium": request["benefit_premium"],
        "recovery_premium": request["recovery_premium"],
        "target_premium_goal": request["target_premium_goal"],
        "benefit_carrier": request["benefit_carrier"],
        "recovery_carriers": ", ".join(request["recovery_carriers"]),
        "routing_rule_id": request["routing_rule_id"] or "",
        "request_json": json.dumps(request, default=str),
    }
    return [values[c] for c in REQUEST_COLUMNS]


def submit_request(request):
    """Assigns the next Request ID, saves the request as a new row, returns the ID."""
    worksheet = _spreadsheet().worksheet(REQUESTS_TAB)
    if not worksheet.row_values(1):
        worksheet.append_row(REQUEST_COLUMNS, value_input_option="RAW")

    request_id = _next_request_id(worksheet, request["as_of"].year)
    worksheet.append_row(_request_row(request, request_id), value_input_option="RAW")
    return request_id
