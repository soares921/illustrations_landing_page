# Builds carrier sheet templates and turns them into PDFs.

# what sheet states comes from template tab in Google Sheet, live edits
# what sheet looks like lives here under SHEET_STYLE
# code only replaces bracketed fields

import html
import io
import logging
import re

from xhtml2pdf import pisa

import rules

logging.getLogger("xhtml2pdf").setLevel(logging.ERROR)  # hides harmless css warnings

# any [bracketed text] still left after filling is a field the code doesn't recognize
LEFTOVER_FIELD = re.compile(r"\[[^\[\]\n]+\]")

SHEET_STYLE = """
  @page { size: letter; margin: 0.6in; }
  body { font-family: Helvetica, Arial, sans-serif; font-size: 10pt; color: #000; }
  h1 { font-size: 16pt; margin: 0 0 2pt 0; }
  .subtitle { font-size: 10pt; color: #444; margin-bottom: 10pt; }
  h2 { font-size: 11pt; margin: 12pt 0 4pt 0; -pdf-keep-with-next: true; }
  p { margin: 0 0 6pt 0; }
  table { width: 100%; border-collapse: collapse; margin-bottom: 4pt; }
  td { border: 0.5pt solid #999; padding: 4pt 6pt; vertical-align: top; }
  td.label { width: 32%; font-weight: bold; background-color: #f0f0f0; }
"""

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
        "Income Start Age": str(p(["income_start_age"])),
        "Income End Age": str(rules.INCOME_END_AGE),
        "Face Instruction": request["face_instruction"],
    }

def fill_text(text, fields):
    """Fills the [Fields] in one Template value. Returns (html, unrecognized fields)."""
    filled = html.escape(text)  # so text like "S&P" displays correctly
    for name, value in fields.items():
        value = str(value).strip()
        if not value:
            filled = filled.replace(f"[{name}] ", "")  # e.g. a blank middle name leaves no gap
        filled = filled.replace(f"[{name}]", html.escape(value))
    unrecognized = LEFTOVER_FIELD.findall(filled)
    return filled.replace("\n", "<br>"), unrecognized  # Alt+Enter line breaks


def build_sheet_html(carrier, role, template_rows, fields):
    
    # lays out one carrier's rows from the template tab, in order
      # rows with no section go in the top block (no heading)
      # a new section name starts a new heading and table
      # rows with no label print as a plain paragraph
    
    rows = [r for r in template_rows if r["carrier"].lower() == carrier.lower()]
    if not rows:
        raise ValueError(f"The Template tab has no rows for {carrier}.")

    parts, problems = [], []
    current_section, table_open = None, False

    for row in rows:
        if row["section"] != current_section:
            if table_open:
                parts.append("</table>")
                table_open = False
            if row["section"]:
                parts.append(f"<h2>{html.escape(row['section'])}</h2>")
            current_section = row["section"]

        value, unrecognized = fill_text(row["value"], fields)
        for field in unrecognized:
            problems.append(f"{field} (row \"{row['label'] or row['value'][:30]}\")")

        if not row["label"]:
            if table_open:
                parts.append("</table>")
                table_open = False
            parts.append(f"<p>{value}</p>")
            continue

        if not table_open:
            parts.append("<table>")
            table_open = True
        label, _ = fill_text(row["label"], fields)
        parts.append(f'<tr><td class="label">{label}</td><td>{value}</td></tr>')

    if table_open:
        parts.append("</table>")

    if problems:
        raise ValueError(f"The Template tab for {carrier} uses fields the app doesn't recognize: "
                         + "; ".join(problems))

    return f"""<html><head><meta charset="utf-8"><style>{SHEET_STYLE}</style></head><body>
<h1>{html.escape(carrier)}: Submittal Illustration</h1>
<div class="subtitle">Simplicity Keystone &nbsp;|&nbsp; Capital Accumulation Plan &nbsp;|&nbsp; {role}</div>
{"".join(parts)}
</body></html>"""

def html_to_pdf(filled_html):
    buffer = io.BytesIO()
    result = pisa.CreatePDF(filled_html, dest=buffer, encoding="utf-8")
    if result.err:
        raise RuntimeError("PDF could not be generated.")
    return buffer.getvalue()

def build_benefit_sheet(request, request_id, template_rows):
    # returns (filled HTML, PDF bytes) for the benefit carrier's sheet
    fields = benefit_sheet_fields(request, request_id)
    filled = build_sheet_html(request["benefit_carrier"], "Benefit Policy", template_rows, fields)
    return filled, html_to_pdf(filled)

def sheet_filename(request, request_id, carrier):
    last = request["primary"]["last_name"] or "Insured"
    safe = re.sub(r"[^A-Za-z0-9]+", "_", f"{request_id}_{carrier}_{last}").strip("_")
    return f"{safe}.pdf"
