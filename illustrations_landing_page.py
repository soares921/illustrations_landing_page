#CAP Illustration Request landing page

# this file is the form only. Business rules live in rules.py, carrier sheets in
# documents.py + templates, storage in storage.py, delivery in delivery.py.

import datetime
import json
import os
import streamlit as st
import delivery
import documents
import rules
import storage

st.set_page_config(page_title="CAP Illustration Request", layout="wide")

ROUTING_FILE = os.path.join(os.path.dirname(__file__), "config", "routing_rules.json")

US_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
             "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
             "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
             "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
             "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]


# SESSION STATE
# every widget key ends in the form version, so "Start a new request"
# can clear the whole form by bumping the version

if "form_version" not in st.session_state:
    st.session_state.form_version = 0
    st.session_state.preview = None      # {"request": ..., "signature": ...}
    st.session_state.submitted = None    # {"request_id": ..., "pdf": ..., ...}

def k(name):
    return f"{name}_{st.session_state.form_version}"

def start_new_request():
    st.session_state.form_version += 1
    st.session_state.preview = None
    st.session_state.submitted = None

# LOAD CONFIGURATION

@st.cache_data
def load_routing(_modified_time):
    # rereads automatically whenever the file changes
    return rules.load_routing_config(ROUTING_FILE)

try:
    routing_config = load_routing(os.path.getmtime(ROUTING_FILE))
    clients, client_source = storage.load_clients()
except Exception as e:
    st.error(f"The page couldn't load its configuration: {e}")
    st.stop()

active_clients = [c for c in clients if c["active"]]
client_names = [c["organization_name"] for c in active_clients]
today = rules.today() # EST

# FORM

st.title("CAP Illustration Request")
st.caption("MVP")

if client_source == "sample":
    st.warning(
        "Google Sheet not connected. Using the sample client list, and submitting is turned off."
        "Preview and PDF download still work."
    )

st.markdown("---")

# 1. REQUEST HEADER
st.subheader("Request Header")
col1, col2 = st.columns(2)
with col1:
    requestor_name = st.text_input("Requestor Name *", key=k("requestor_name"))
    requestor_email = st.text_input("Requestor Email *", key=k("requestor_email"))
    advisor_of_record = st.text_input("Advisor / Producer", key=k("advisor"))
with col2:
    date_needed = st.date_input("Date Needed *", value=None, min_value=today,
                                format="MM/DD/YYYY", key=k("date_needed"))
    case_reference = st.text_input("Case Reference", key=k("case_reference"))

st.markdown("---")

#2. CLIENT ORGANIZATION
st.subheader("Client Organization")
col1, col2 = st.columns(2)
with col1:
    org_name = st.selectbox("Organization *", options=[""] + client_names, key=k("org"))
    selected_client = next((c for c in active_clients if c["organization_name"] == org_name), None)

with col2:
    default_pct = selected_client["default_offset_pct"] if selected_client else 0.0
    override = st.checkbox("Override Standard Offset Percentage", key=k("override"))
    if override:
        # the key includes the organization so the field resets when it changes
        offset_pct = st.number_input("Employer Contribution / Offset (%) *", value=default_pct,
                                     min_value=0.0, max_value=100.0, step=0.5, format="%.2f",
                                     key=k(f"offset_{org_name}"))
        override_reason = st.text_area("Reason for Override *", key=k("override_reason"),
                                       help="Required when overriding the standard offset.")
    else:
        offset_pct = default_pct
        st.number_input("Employer Contribution / Offset (%)", value=default_pct, disabled=True,
                        format="%.2f", key=k(f"offset_locked_{org_name}"))
        override_reason = ""

st.markdown("---")

# 3. DESIGN TYPE
st.subheader("Design Type")
design_type = st.radio("Select Design Type *", ["Single life recovery", "Joint life recovery"],
                       horizontal=True, key=k("design_type"))
is_joint = design_type == "Joint life recovery"

st.markdown("---")

# 4 & 5. INSURED INFORMATION
def insured_fields(prefix, label):
    st.subheader(f"{label} Insured")
    values = {
        f"{prefix}_first": st.text_input(f"{label} First Name *", key=k(f"{prefix}_first")),
        f"{prefix}_middle": st.text_input(f"{label} Middle Name", key=k(f"{prefix}_middle")),
        f"{prefix}_last": st.text_input(f"{label} Last Name *", key=k(f"{prefix}_last")),
        f"{prefix}_gender": st.selectbox(f"{label} Gender *", ["", "Male", "Female"],
                                         key=k(f"{prefix}_gender")),
        f"{prefix}_dob": st.date_input(f"{label} Date of Birth *", value=None,
                                       min_value=datetime.date(today.year - rules.MAX_ISSUE_AGE - 1, 1, 1),
                                       max_value=today, format="MM/DD/YYYY", key=k(f"{prefix}_dob")),
        f"{prefix}_state": st.selectbox(f"{label} State *", [""] + US_STATES, key=k(f"{prefix}_state")),
        f"{prefix}_tobacco": st.radio(f"{label} Tobacco Status *", ["Non-Tobacco", "Tobacco"],
                                      key=k(f"{prefix}_tobacco")),
    }
    st.info(f"**Resolved Underwriting Class:** {rules.underwriting_class(values[f'{prefix}_tobacco'])}")
    if values[f"{prefix}_dob"]:
        age = rules.age_on(values[f"{prefix}_dob"], today)
        st.caption(f"Age today: {age} · Income start age: "
                   f"{rules.income_start_age(age) if age <= rules.MAX_ISSUE_AGE else 'n/a'}")
    return values

col_primary, col_secondary = st.columns(2)
with col_primary:
    primary_values = insured_fields("p", "Primary")
secondary_values = {}
if is_joint:
    with col_secondary:
        secondary_values = insured_fields("s", "Secondary")

st.markdown("---")

# 6. CONTRIBUTION & CARRIER ROUTING
st.subheader("Contribution Information & Carrier Routing")
col1, col2 = st.columns(2)
with col1:
    participant_contribution = st.number_input(
        "Participant Annual Contribution ($) *", value=None, min_value=0, step=5000,
        key=k("contribution"),
        help="The participant's own contribution only. The employer offset is added automatically.",
    )
    duration_years = st.number_input("Estimated Contribution Duration (Years) *", value=None,
                                     min_value=1, max_value=50, step=1, key=k("duration"))

with col2:
    if participant_contribution:
        premiums = rules.calculate_premiums(participant_contribution, offset_pct)
        routing = rules.evaluate_routing(design_type, participant_contribution,
                                         premiums["total_funding"], routing_config)
        st.markdown("**Funding**")
        st.markdown(
            f"* Total annual funding (with {offset_pct:g}% offset): "
            f"**{rules.format_dollars(premiums['total_funding'])}**\n"
            f"* Benefit premium (85%): **{rules.format_dollars(premiums['benefit_premium'])}**\n"
            f"* Recovery premium, each carrier (15%): **{rules.format_dollars(premiums['recovery_premium'])}**"
        )
        st.markdown("**Assigned Carrier Routing**")
        st.markdown(
            f"* Benefit policy: `{routing['benefit_carrier']}`\n"
            f"* Recovery policies: `{', '.join(routing['recovery_carriers']) or 'None matched'}`"
        )
        if routing["rule"] and routing["rule"].get("note"):
            st.caption(routing["rule"]["note"])
        if not routing["recovery_carriers"]:
            st.warning("No routing rule matches this request. Check config/routing_rules.json.")
    else:
        st.caption("Enter the participant contribution to see funding and carrier routing.")

st.markdown("---")

# VALIDATION

def validate():
    errors = []
    if not requestor_name.strip() or not date_needed:
        errors.append("Complete all required fields in Request Header.")
    email = requestor_email.strip()
    if not email or "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Enter a valid requestor email.")
    if not selected_client:
        errors.append("Select a client organization.")
    if override and not override_reason.strip():
        errors.append("An override reason is required when overriding the offset.")

    for prefix, label, values in [("p", "Primary", primary_values)] + (
            [("s", "Secondary", secondary_values)] if is_joint else []):
        missing = [name for name, key in [("first name", "first"), ("last name", "last"),
                                          ("gender", "gender"), ("date of birth", "dob"),
                                          ("state", "state")]
                   if not values[f"{prefix}_{key}"] or (isinstance(values[f"{prefix}_{key}"], str)
                                                        and not values[f"{prefix}_{key}"].strip())]
        if missing:
            errors.append(f"{label} Insured is missing: {', '.join(missing)}.")
        dob = values[f"{prefix}_dob"]
        if dob and rules.age_on(dob, today) > rules.MAX_ISSUE_AGE:
            errors.append(f"{label} Insured is over the maximum age of {rules.MAX_ISSUE_AGE}.")

    if not participant_contribution:
        errors.append("Enter the participant annual contribution.")
    if not duration_years:
        errors.append("Enter the contribution duration.")
    return errors


def current_form():
    return {
        "requestor_name": requestor_name, "requestor_email": requestor_email,
        "advisor_of_record": advisor_of_record, "date_needed": date_needed,
        "case_reference": case_reference,
        "client_id": selected_client["client_id"] if selected_client else None,
        "organization_name": org_name, "offset_pct": offset_pct,
        "offset_overridden": override, "override_reason": override_reason,
        "design_type": design_type,
        **primary_values, **secondary_values,
        "participant_contribution": participant_contribution,
        "duration_years": duration_years,
    }


def signature(request):
    return json.dumps(request, default=str, sort_keys=True)

# 7. REVIEW & SUBMIT

def show_summary(request):
    p, s = request["primary"], request["secondary"]

    def insured_lines(i):
        name = " ".join(x for x in [i["first_name"], i["middle_name"], i["last_name"]] if x)
        return (f"* **Name:** {name}\n* **Gender:** {i['gender']}\n"
                f"* **DOB:** {rules.format_date(i['dob'])} (age {i['age']})\n"
                f"* **State:** {i['state']}\n* **Class:** {i['underwriting_class']}\n"
                f"* **Income ages:** {i['income_start_age']} to {rules.INCOME_END_AGE}")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**Request**")
        st.markdown(
            f"* **Requestor:** {request['requestor_name']} ({request['requestor_email']})\n"
            f"* **Advisor:** {request['advisor_of_record']}\n"
            f"* **Date needed:** {rules.format_date(request['date_needed'])}\n"
            f"* **Case reference:** {request['case_reference'] or 'None'}\n"
            f"* **Organization:** {request['organization_name']}\n"
            f"* **Offset:** {request['offset_pct']:g}%"
            + (f" (override: {request['override_reason']})" if request["offset_overridden"] else "")
            + f"\n* **Design:** {request['design_type']}"
        )
    with c2:
        st.markdown("**Primary Insured**")
        st.markdown(insured_lines(p))
        if s:
            st.markdown("**Secondary Insured**")
            st.markdown(insured_lines(s))
    with c3:
        st.markdown("**Money & Routing**")
        st.markdown(
            f"* **Participant contribution:** {rules.format_dollars(request['participant_contribution'])}"
            f" × {request['duration_years']} years\n"
            f"* **Total funding:** {rules.format_dollars(request['total_funding'])}\n"
            f"* **Benefit premium:** {rules.format_dollars(request['benefit_premium'])}\n"
            f"* **Recovery premium (each):** {rules.format_dollars(request['recovery_premium'])}\n"
            f"* **Target premium goal:** {rules.format_dollars(request['target_premium_goal'])}\n"
            f"* **Benefit carrier:** {request['benefit_carrier']}\n"
            f"* **Recovery carriers:** {', '.join(request['recovery_carriers'])}"
        )

st.subheader("Review & Submit")
submitted = st.session_state.submitted

if submitted:
    # AFTER SUBMIT 
    st.success(f"Request submitted. Request ID: **{submitted['request_id']}**")
    st.download_button("Download Submittal PDF", data=submitted["pdf"],
                       file_name=submitted["filename"], mime="application/pdf", type="primary")
    with st.expander("View submitted sheet"):
        st.iframe(submitted["html"], height=1300)
    st.button("Start a New Request", on_click=start_new_request)

else:
    if st.button("Preview"):
        errors = validate()
        if errors:
            st.session_state.preview = None
            for err in errors:
                st.error(err)
        else:
            try:
                request = rules.build_request(current_form(), routing_config, today)
                if not request["recovery_carriers"]:
                    st.error("No routing rule matches this request, so it can't be previewed.")
                else:
                    st.session_state.preview = {"request": request, "signature": signature(request)}
            except Exception as e:
                st.error(f"Preview failed: {e}")

    preview = st.session_state.preview
    if preview:
        # has anything changed since the preview was made?
        current = None
        if not validate():
            current = rules.build_request(current_form(), routing_config, today)
        if current is None or signature(current) != preview["signature"]:
            st.warning("The form has changed since this preview. Click **Preview** again before submitting.")
        else:
            request = preview["request"]
            show_summary(request)

            try:
                draft_html, draft_pdf = documents.build_benefit_sheet(request, "DRAFT", routing_config)
            except Exception as e:
                st.error(f"The {request['benefit_carrier']} sheet couldn't be built: {e}")
                st.stop()

            st.markdown(f"**{request['benefit_carrier']} Submittal Sheet (Preview)**")
            st.iframe(draft_html, height=1300)

            col_a, col_b = st.columns([1, 3])
            with col_a:
                st.download_button(
                    "Download PDF (Draft)", data=draft_pdf,
                    file_name=documents.sheet_filename(request, "DRAFT", request["benefit_carrier"]),
                    mime="application/pdf",
                )
            with col_b:
                if storage.is_connected():
                    if st.button("Submit Illustration Request", type="primary"):
                        try:
                            request_id = storage.submit_request(request)
                            final_html, final_pdf = documents.build_benefit_sheet(
                                request, request_id, routing_config)
                            filename = documents.sheet_filename(
                                request, request_id, request["benefit_carrier"])
                            delivery.deliver(request, request_id,
                                             [(request["benefit_carrier"], filename, final_pdf)])
                            st.session_state.submitted = {
                                "request_id": request_id, "html": final_html,
                                "pdf": final_pdf, "filename": filename,
                            }
                            st.rerun()
                        except Exception as e:
                            st.error(f"Submission failed: {e}")
                else:
                    st.button("Submit Illustration Request", type="primary", disabled=True,
                              help="Submitting turns on once the Google Sheet is connected.")
