"""
Fills carrier sheet templates and turns them into PDFs.

Each carrier sheet is an HTML file in /templates. The code only replaces the
bracketed fields; all fixed text lives in the template.
"""

import html
import io
import logging
import os
import re

from xhtml2pdf import pisa

import rules

logging.getLogger("xhtml2pdf").setLevel(logging.ERROR)  # hides harmless CSS warnings

TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), "templates")
LEFTOVER_FIELD = re.compile(r"\[[A-Z][A-Za-z0-9 +]*\]")


def benefit_sheet_fields(request, request_id):
    """Values for every bracketed field on a benefit policy sheet."""
    p = request["primary"]  # the benefit sheet is always the primary insured
    n = request["duration_years"]
    return {
        "Request ID": request_id,
        "Date Needed": rules.format_date(request["date_needed"]),
        "Client Organization": request["organization_name"],
        "Requestor Name": request["requestor_name"],
        "Requestor Email": request["requestor_email"],
        "State": p["state"],
        "First Name": p["first_name"],
        "Middle Name": p["middle_name"],  # blank middle names simply disappear
        "Last Name": p["last_name"],
        "Date of Birth": rules.format_date(p["dob"]),
        "Gender": p["gender"],
        "Underwriting Class": p["underwriting_class"],
        "Benefit Premium": rules.format_dollars(request["benefit_premium"]),
        "N": str(n),
        "N+1": str(n + 1),
        "Target Premium Goal": rules.format_dollars(request["target_premium_goal"]),
        "Income Start Age": str(p["income_start_age"]),
        "Face Instruction": request["face_instruction"],
    }


def fill_template(template_name, fields):
    """Replaces each [Field] in the template. Stops if any field is left unfilled."""
    path = os.path.join(TEMPLATE_DIR, template_name)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Carrier template not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()

    for name, value in fields.items():
        value = str(value).strip()
        if not value:
            text = text.replace(f"[{name}] ", "")  # e.g. a blank middle name leaves no gap
        text = text.replace(f"[{name}]", html.escape(value))

    leftover = LEFTOVER_FIELD.findall(text)
    if leftover:
        raise ValueError(f"{template_name} has fields with no value: {', '.join(sorted(set(leftover)))}")
    return text


def html_to_pdf(filled_html):
    buffer = io.BytesIO()
    result = pisa.CreatePDF(filled_html, dest=buffer, encoding="utf-8")
    if result.err:
        raise RuntimeError("PDF could not be generated.")
    return buffer.getvalue()


def build_benefit_sheet(request, request_id, routing_config):
    """Returns (filled HTML, PDF bytes) for the benefit carrier's sheet."""
    carrier = request["benefit_carrier"]
    template = routing_config["carrier_templates"]["benefit"].get(carrier)
    if not template:
        raise ValueError(f"No benefit sheet template is set up for {carrier}.")
    filled = fill_template(template, benefit_sheet_fields(request, request_id))
    return filled, html_to_pdf(filled)


def sheet_filename(request, request_id, carrier):
    last = request["primary"]["last_name"] or "Insured"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{request_id}_{carrier}_{last}").strip("_")
    return f"{safe}.pdf"
