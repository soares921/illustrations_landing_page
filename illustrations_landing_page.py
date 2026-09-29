import streamlit as st
import json
import datetime
import uuid
import os

# Page configuration
st.set_page_config(page_title="CAP Illustration Request", layout="wide")

# ==========================================
# 1. DATA LOADERS & ROUTING ENGINE
# ==========================================

@st.cache_data
def load_client_key(file_path="client_key.json"):
    """Reads the Client Key registry file."""
    if not os.path.exists(file_path):
        st.error(f"File not found: {file_path}")
        return []
    with open(file_path, "r") as f:
        return json.load(f)

@st.cache_data
def load_routing_rules(file_path="routing_rules.json"):
    #Reads the Carrier Routing configuration file
    if not os.path.exists(file_path):
        st.error(f"File not found: {file_path}")
        return {"benefit_policy_default": "Allianz Life", "routing_rules": []}
    with open(file_path, "r") as f:
        return json.load(f)

def evaluate_routing(design_type, contribution_amount, config):
    #Evaluates dynamic rules from the loaded routing configuration
    benefit_carrier = config.get("benefit_policy_default", "Allianz Life")
    recovery_carriers = []
    
    for rule in config.get("routing_rules", []):
        if rule["design_type"] == design_type:
            min_c = rule["min_contribution"]
            max_c = rule["max_contribution"]
            
            # check contribution boundaries (null/None represents infinity)
            if contribution_amount >= min_c and (max_c is None or contribution_amount <= max_c):
                recovery_carriers = rule["recovery_carriers"]
                break
                
    return benefit_carrier, recovery_carriers

# Load JSON Configurations
clients = load_client_key()
routing_config = load_routing_rules()

client_names = [c["organization_name"] for c in clients if c.get("active", True)]

US_STATES = ["AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA", 
             "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD", 
             "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ", 
             "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC", 
             "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY"]

# ==========================================
# 2. UI FORM BUILD
# ==========================================

st.title("CAP Illustration Request")
st.caption("MVP")

st.markdown("---")

# --- SECTION 1: REQUEST HEADER ---
st.subheader("Request Header")
col1, col2 = st.columns(2)
with col1:
    requestor_name = st.text_input("Requestor Name *")
    requestor_email = st.text_input("Requestor Email *")
    advisor_of_record = st.text_input("Advisor / Producer *")
with col2:
    date_needed = st.date_input("Date Needed *", min_value=datetime.date.today(), format="MM/DD/YYYY")
    case_reference = st.text_input("Case Reference")

st.markdown("---")

# --- SECTION 2: CLIENT ORGANIZATION ---
st.subheader("Client Organization")
col1, col2 = st.columns(2)

with col1:
    selected_org_name = st.selectbox("Organization *", options=[""] + client_names)
    selected_client = next((c for c in clients if c["organization_name"] == selected_org_name), None)

with col2:
    default_pct = selected_client["default_offset_pct"] if selected_client else 0.0
    
    override_check = st.checkbox("Override Standard Offset Percentage")
    
    if override_check:
        offset_pct = st.number_input(
            "Employer Contribution / Offset (%) *", 
            value=default_pct, 
            step=0.5, 
            format="%.2f"
        )
        override_reason = st.text_area("Reason for Override *", help="Required when overriding standard offset.")
    else:
        offset_pct = st.number_input(
            "Employer Contribution / Offset (%)", 
            value=default_pct, 
            disabled=True, 
            format="%.2f"
        )
        override_reason = ""

st.markdown("---")

# --- SECTION 3: DESIGN TYPE ---
st.subheader("Design Type")
design_type = st.radio(
    "Select Design Type *",
    options=["Single life recovery", "Joint life recovery"],
    horizontal=True
)

st.markdown("---")

# --- SECTION 4 & 5: INSURED INFORMATION ---
col_primary, col_secondary = st.columns(2)
is_joint = (design_type == "Joint life recovery")

with col_primary:
    st.subheader("Primary Insured")
    p_first = st.text_input("Primary First Name *")
    p_middle = st.text_input("Primary Middle Name")
    p_last = st.text_input("Primary Last Name *")
    p_gender = st.selectbox("Primary Gender *", ["Male", "Female"])
    p_dob = st.date_input("Primary Date of Birth *", min_value=datetime.date(1930, 1, 1), format="MM/DD/YYYY")
    p_state = st.selectbox("Primary State *", options=[""] + US_STATES)
    p_tobacco = st.radio("Primary Tobacco Status *", ["Non-tobacco", "Tobacco"], key="p_tob")
    
    p_underwriting = f"Preferred {p_tobacco}"
    st.info(f"**Resolved Underwriting Class:** {p_underwriting}")

if is_joint:
    with col_secondary:
        st.subheader("Secondary Insured")
        s_first = st.text_input("Secondary First Name")
        s_middle = st.text_input("Secondary Middle Name")
        s_last = st.text_input("Secondary Last Name")
        s_gender = st.selectbox("Secondary Gender", ["Male", "Female"])
        s_dob = st.date_input("Secondary Date of Birth", min_value=datetime.date(1930, 1, 1), format="MM/DD/YYYY")
        s_state = st.selectbox("Secondary State", options=[""] + US_STATES)
        s_tobacco = st.radio("Secondary Tobacco Status", ["Non-tobacco", "Tobacco"], key="s_tob")
        
        s_underwriting = f"Preferred {s_tobacco}"
        st.info(f"**Resolved Underwriting Class:** {s_underwriting}")
else:
    s_first = s_middle = s_last = s_gender = s_dob = s_state = s_tobacco = s_underwriting = None

st.markdown("---")

# --- SECTION 6: CONTRIBUTION INFORMATION & LIVE ROUTING ---
st.subheader("Contribution Information & Carrier Routing")

col1, col2 = st.columns(2)

with col1:
    annual_contrib = st.number_input("Estimated Annual Contribution ($) *", min_value=0.0, step=5000.0, value=50000.0)
    contrib_duration = st.number_input("Estimated Contribution Duration (Years) *", min_value=1, max_value=50, value=10)

# pass the loaded routing_config dictionary to the engine
benefit_carrier, recovery_carriers = evaluate_routing(design_type, annual_contrib, routing_config)

with col2:
    st.markdown("**Assigned Carrier Routing**")
    st.markdown(f"* **Benefit Policy Carrier:** `{benefit_carrier}`")
    st.markdown(f"* **Recovery Policy Carriers:** `{', '.join(recovery_carriers)}`")
    
    if design_type == "Joint life recovery" and annual_contrib >= 200000:
        st.caption("*Lincoln Financial automatically added for Joint Life requests over $200,000*")

st.markdown("---")

# --- SECTION 7: REVIEW AND SUBMIT ---
st.subheader("Review & Submit")

if st.button("Submit Illustration Request", type="primary"):
    # Simple Validation Checks
    errors = []
    if not requestor_name or not requestor_email or not advisor_of_record:
        errors.append("Please complete all required fields in the 'Request Header' section.")
    if not selected_org_name:
        errors.append("Please select a client organization.")
    if override_check and not override_reason:
        errors.append("An override reason is required when overriding the employer contribution offset.")
    if not p_first or not p_last or not p_state:
        errors.append("Please complete required Primary Insured fields for Single Life.")
    if is_joint and (not s_first or not s_last or not s_state):
        errors.append("Please complete required Secondary Insured fields for Joint Life.")
        
    if errors:
        for err in errors:
            st.error(err)
    else:
        req_id = f"REQ-{datetime.date.today().strftime('%Y%m%d')}-{str(uuid.uuid4())[:4].upper()}"
        
        # Package Phase 2 Contract Payload
        payload = {
            "request_id": req_id,
            "created_at": datetime.datetime.now().isoformat(),
            "header": {
                "requestor_name": requestor_name,
                "requestor_email": requestor_email,
                "advisor_of_record": advisor_of_record,
                "date_needed": str(date_needed),
                "case_reference": case_reference
            },
            "client_organization": {
                "client_id": selected_client["client_id"] if selected_client else None,
                "organization_name": selected_org_name,
                "employer_offset_percentage": offset_pct,
                "is_overridden": override_check,
                "override_reason": override_reason if override_check else None
            },
            "design_type": design_type,
            "primary_insured": {
                "first_name": p_first,
                "middle_name": p_middle,
                "last_name": p_last,
                "gender": p_gender,
                "dob": str(p_dob),
                "state": p_state,
                "tobacco_status": p_tobacco,
                "resolved_underwriting_class": p_underwriting
            },
            "secondary_insured": {
                "first_name": s_first,
                "middle_name": s_middle,
                "last_name": s_last,
                "gender": s_gender,
                "dob": str(s_dob),
                "state": s_state,
                "tobacco_status": s_tobacco,
                "resolved_underwriting_class": s_underwriting
            } if is_joint else None,
            "contribution_info": {
                "estimated_annual_contribution": annual_contrib,
                "duration_years": contrib_duration
            },
            "assigned_routing": {
                "benefit_carrier": benefit_carrier,
                "recovery_carriers": recovery_carriers
            }
        }
        
        st.success(f"Request Submitted Successfully! Request ID: **{req_id}**")
        st.json(payload)