import os
import sys
import time
import streamlit as st
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options

# Import engine logic and helpers
from bot_engine import (
    run_bot_logic,
    test_gemini_api_key,
    extract_text_from_file,
    generate_summary_from_resume
)

# 1. Page configuration - wide layout
st.set_page_config(
    page_title="Auto Job Applier AI",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for modern styling
st.markdown("""
<style>
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.5rem;
    }
    .sub-header {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .stButton button[kind="primary"] {
        background-color: #2563EB;
        color: white;
        font-weight: 600;
        border-radius: 8px;
        padding: 0.5rem 1rem;
    }
    .upload-box {
        border: 1px dashed #CBD5E1;
        border-radius: 8px;
        padding: 0.5rem;
        margin-bottom: 1rem;
        background-color: #F8FAFC;
    }
</style>
""", unsafe_allow_html=True)

# Helper function for resolving API key (same strategy as AI Debate)
def resolve_gemini_api_key(ui_key):
    if ui_key and ui_key.strip():
        return ui_key.strip()
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key and len(env_key) > 25 and not env_key.startswith("your_"):
        return env_key
    try:
        if "GEMINI_API_KEY" in st.secrets:
            sec_key = str(st.secrets["GEMINI_API_KEY"]).strip()
            if sec_key:
                return sec_key
    except Exception:
        pass
    return ""

# Session state initialization
if "user_data" not in st.session_state:
    st.session_state["user_data"] = {
        "api_key": "",
        "selected_model": "gemini-3.6-flash",
        "full_name": "",
        "email": "",
        "phone": "",
        "location": "",
        "full_resume": "",
        "resume_summary": "",
        "max_applications": 10
    }

# 2. Sidebar for User Profile & API Key
st.sidebar.title("👤 User Profile & Settings")
st.sidebar.markdown("---")

api_key_input = st.sidebar.text_input(
    "Gemini API Key",
    type="password",
    value=st.session_state["user_data"].get("api_key", ""),
    help="Enter your Gemini API key from Google AI Studio (aistudio.google.com)"
)

# Models match AI Debate Coach options
model_options = ["gemini-3.6-flash", "gemini-3.5-flash-lite", "gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash"]
selected_model = st.sidebar.selectbox(
    "Gemini Model",
    options=model_options,
    index=0,
    help="Select the Gemini model version (matching AI Debate Coach settings)."
)

effective_api_key = resolve_gemini_api_key(api_key_input)

# API Key Validation Button
if st.sidebar.button("🔌 Test API Key", use_container_width=True):
    if not effective_api_key:
        st.sidebar.warning("Please enter your Gemini API Key above. You can get a key at https://aistudio.google.com")
    else:
        with st.sidebar.spinner(f"Testing API Key with {selected_model}..."):
            is_valid, message = test_gemini_api_key(effective_api_key, model_name=selected_model)
            if is_valid:
                st.sidebar.success(f"✅ {message}")
            else:
                st.sidebar.error(f"❌ {message}")

st.sidebar.markdown("---")

full_name = st.sidebar.text_input(
    "Full Name",
    value=st.session_state["user_data"].get("full_name", ""),
    placeholder="e.g. Jane Doe"
)

email = st.sidebar.text_input(
    "Email",
    value=st.session_state["user_data"].get("email", ""),
    placeholder="e.g. jane@example.com"
)

phone = st.sidebar.text_input(
    "Phone",
    value=st.session_state["user_data"].get("phone", ""),
    placeholder="e.g. 555-0199"
)

location = st.sidebar.text_input(
    "Location",
    value=st.session_state["user_data"].get("location", ""),
    placeholder="e.g. Baltimore, MD"
)

st.sidebar.markdown("---")
st.sidebar.info(
    "🔒 **Privacy & Data Security Notice**\n\n"
    "No personal information, contact details, resume content, or API keys are stored externally. "
    "All inputs remain strictly in your active local browser session (`st.session_state`) "
    "and are used solely during your active automation run."
)

# Main Title Section
st.markdown('<div class="main-header">🤖 AI Job Application Bot</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Configure your profile, upload your resume/cover letter documents, test your API key, and launch the automated applier.</div>', unsafe_allow_html=True)

# 3. Main panel: side-by-side columns for Resume and Summary
col1, col2 = st.columns(2)

with col1:
    st.markdown("### 📄 Full Resume")
    uploaded_resume = st.file_uploader(
        "Upload Full Resume (.pdf, .docx, .doc, .txt)",
        type=["pdf", "docx", "doc", "txt"],
        key="full_resume_uploader"
    )

    if uploaded_resume is not None:
        extracted = extract_text_from_file(uploaded_resume)
        if extracted and not extracted.startswith("Error"):
            st.session_state["user_data"]["full_resume"] = extracted
            st.success(f"Successfully imported text from {uploaded_resume.name}")
        elif extracted:
            st.error(extracted)

    full_resume = st.text_area(
        "Full Resume Content",
        height=300,
        value=st.session_state["user_data"].get("full_resume", ""),
        placeholder="Paste or upload your complete detailed resume here (Work history, Education, Skills, Clearances)..."
    )

with col2:
    st.markdown("### 📝 Resume Summary")
    uploaded_summary = st.file_uploader(
        "Upload Resume Summary / Cover Letter (.pdf, .docx, .doc, .txt)",
        type=["pdf", "docx", "doc", "txt"],
        key="summary_uploader"
    )

    if uploaded_summary is not None:
        extracted_sum = extract_text_from_file(uploaded_summary)
        if extracted_sum and not extracted_sum.startswith("Error"):
            st.session_state["user_data"]["resume_summary"] = extracted_sum
            st.success(f"Successfully imported text from {uploaded_summary.name}")
        elif extracted_sum:
            st.error(extracted_sum)

    # Auto-generate summary with Gemini AI
    if st.button("✨ Auto-Generate Summary with AI", use_container_width=True):
        if not full_resume:
            st.warning("Please provide or upload Full Resume text first.")
        elif not effective_api_key:
            st.warning("Please enter your Gemini API Key in the sidebar.")
        else:
            with st.spinner(f"Summarizing resume using {selected_model}..."):
                ok, sum_text = generate_summary_from_resume(full_resume, effective_api_key, model_name=selected_model)
                if ok:
                    st.session_state["user_data"]["resume_summary"] = sum_text
                    st.success("Generated summary using Gemini AI!")
                    st.rerun()
                else:
                    st.error(sum_text)

    resume_summary = st.text_area(
        "Resume Summary Content",
        height=300,
        value=st.session_state["user_data"].get("resume_summary", ""),
        placeholder="Paste, upload, or auto-generate a concise summary of your resume..."
    )

# Keep session_state updated
st.session_state["user_data"]["api_key"] = api_key_input
st.session_state["user_data"]["selected_model"] = selected_model
st.session_state["user_data"]["full_name"] = full_name
st.session_state["user_data"]["email"] = email
st.session_state["user_data"]["phone"] = phone
st.session_state["user_data"]["location"] = location
st.session_state["user_data"]["full_resume"] = full_resume
st.session_state["user_data"]["resume_summary"] = resume_summary

# 4. Number input for Max Applications per run
max_applications = st.number_input(
    "Max Applications per run",
    min_value=1,
    max_value=100,
    value=int(st.session_state["user_data"].get("max_applications", 10)),
    step=1
)
st.session_state["user_data"]["max_applications"] = max_applications

st.markdown("---")

# Helper function to check if browser driver is still alive
def is_driver_alive(driver):
    try:
        driver.title
        return True
    except Exception:
        return False

# 5. Primary button: Launch Browser & Log In
btn_col1, btn_col2 = st.columns([1, 2])

with btn_col1:
    launch_clicked = st.button("Launch Browser & Log In", type="primary", use_container_width=True)

if launch_clicked:
    st.info("Launching Chrome browser...")

    try:
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        chromedriver_path = '/usr/bin/chromedriver'
        if os.path.exists(chromedriver_path):
            service = Service(chromedriver_path)
        else:
            service = Service()

        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        })

        # Navigate to Handshake login page
        driver.get("https://app.joinhandshake.com/login")

        # Save driver & session state
        st.session_state["driver"] = driver
        st.success("Browser launched successfully! Handshake login page opened.")
        st.rerun()

    except Exception as e:
        st.error(f"Failed to launch browser: {e}")

# Check browser status in session_state
driver_active = ("driver" in st.session_state 
                 and st.session_state["driver"] is not None 
                 and is_driver_alive(st.session_state["driver"]))

if driver_active:
    st.markdown("### 🌐 Browser Session Active")
    st.info("Chrome browser is open at Handshake login page. Log in, search for jobs, then click 'Start Applying'.")

    # 6. Second button: Start Applying
    start_applying = st.button("🚀 Start Applying", use_container_width=True)

    if start_applying:
        # Build contact string from location, email, and phone
        user_contact_parts = [p for p in [location, email, phone] if p.strip()]
        user_contact = " | ".join(user_contact_parts)

        st.warning("⚠️ Application bot engine is now running. Do not close the open Chrome browser.")

        with st.spinner(f"🤖 Bot processing current page using {selected_model}..."):
            try:
                active_driver = st.session_state["driver"]
                submitted_count = run_bot_logic(
                    driver_arg=active_driver,
                    api_key_arg=effective_api_key,
                    user_full_resume=full_resume,
                    user_resume_summary=resume_summary,
                    user_name=full_name,
                    user_contact=user_contact,
                    max_applications=max_applications,
                    model_name=selected_model
                )
                st.success(f"🎉 Application run complete! Total applications submitted in this run: {submitted_count}")
            except Exception as err:
                st.error(f"An error occurred during bot execution: {err}")
