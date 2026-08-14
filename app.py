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
    page_title="Handshake AI Job Applier",
    page_icon="🤝",
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
    .status-card {
        border-left: 4px solid #2563EB;
        background-color: #F8FAFC;
        padding: 1rem;
        border-radius: 6px;
        margin-bottom: 1rem;
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

# Pre-Flight Validation Check for Handshake Job Search URL
def validate_handshake_url(url: str) -> tuple:
    """Check if driver is currently on a valid Handshake job search page."""
    if not url:
        return False, "Driver URL is empty or inaccessible."

    url_lower = url.lower()

    if "joinhandshake.com" not in url_lower:
        return False, f"The open browser is currently at '{url}'. Please navigate to your school's Handshake domain (*.joinhandshake.com)."

    if "/login" in url_lower and "job" not in url_lower:
        return False, "The browser is still on the Handshake Login page. Please log in first and navigate to your Job Search page."

    valid_paths = ["/job-search", "/stu/jobs", "/jobs", "/explore/jobs"]
    if any(path in url_lower for path in valid_paths):
        return True, f"Valid Handshake Job Search page detected: {url}"

    return False, (
        f"Current browser URL is '{url}'. "
        "Please navigate your open browser to your Handshake Job Search page "
        "(e.g. https://[your-school].joinhandshake.com/stu/jobs or /job-search) before clicking 'Start Applying'."
    )

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
st.markdown('<div class="main-header">🤝 Handshake AI Job Application Bot</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">Human-in-the-Loop Architecture: Launch browser -> Log in & search manually -> Trigger AI application run.</div>', unsafe_allow_html=True)

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
        height=280,
        value=st.session_state["user_data"].get("full_resume", ""),
        placeholder="Paste or upload your complete detailed resume here..."
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
        height=280,
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

# ==============================================================================
# HUMAN-IN-THE-LOOP ARCHITECTURE
# ==============================================================================
st.markdown("## 🛑 Human-in-the-Loop Execution Control")

btn_col1, btn_col2 = st.columns([1, 2])

# STEP 1: PERSIST THE BROWSER
with btn_col1:
    launch_clicked = st.button("Step 1: Launch Browser & Log In", type="primary", use_container_width=True)

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

        # PERSIST BROWSER: Store in st.session_state["driver"]
        st.session_state["driver"] = driver
        
        # YIELD CONTROL: Script stops here and waits for user manual interaction
        st.success("Browser launched successfully! Handshake login page opened.")
        st.rerun()

    except Exception as e:
        st.error(f"Failed to launch browser: {e}")

# STEP 2: THE PAUSE MECHANISM
driver_active = ("driver" in st.session_state 
                 and st.session_state["driver"] is not None 
                 and is_driver_alive(st.session_state["driver"]))

if driver_active:
    current_browser = st.session_state["driver"]
    try:
        active_url = current_browser.current_url
    except Exception:
        active_url = "Unknown"

    st.markdown(
        f"""
        <div class="status-card">
            <h4>⏸️ Step 2: The Pause Mechanism (Dormant Mode)</h4>
            <p><strong>Active Browser URL:</strong> <code>{active_url}</code></p>
            <p>The bot is currently dormant. Please perform the following steps in your open Chrome browser window:</p>
            <ol>
                <li>Log in to your school's Handshake portal.</li>
                <li>Search for your desired jobs using location/keyword filters.</li>
                <li>Ensure your browser is sitting on the <strong>Job Search Results page</strong>.</li>
                <li>Then click <strong>"Step 3: 🚀 Start Applying"</strong> below.</li>
            </ol>
        </div>
        """,
        unsafe_allow_html=True
    )

    # STEP 3: THE TRIGGER & PRE-FLIGHT CHECK (VALIDATION)
    start_applying = st.button("Step 3: 🚀 Start Applying", use_container_width=True)

    if start_applying:
        active_driver = st.session_state["driver"]
        
        # 1. Fetch current URL for Pre-Flight Check
        try:
            current_url = active_driver.current_url
        except Exception as err_url:
            st.error(f"🛑 Pre-Flight Check Failed: Could not read browser URL ({err_url}). Ensure the Chrome browser is open.")
            st.stop()

        # 2. Execute Pre-Flight Validation Check
        is_valid_page, validation_message = validate_handshake_url(current_url)

        if not is_valid_page:
            st.error(f"🛑 **Pre-Flight Check Failed**: {validation_message}")
            st.warning("⚠️ Execution halted. Please navigate your open browser to your Handshake Job Search page before clicking 'Start Applying'.")
            st.stop()

        # 3. Validation Passed -> Proceed with Scraping & Applying
        st.success(f"✅ **Pre-Flight Check Passed**: {validation_message}")

        # Build contact string from location, email, and phone
        user_contact_parts = [p for p in [location, email, phone] if p.strip()]
        user_contact = " | ".join(user_contact_parts)

        st.info("🤖 Bot processing current page DOM job cards using Gemini AI...")

        with st.spinner(f"Processing jobs with {selected_model}..."):
            try:
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
else:
    st.warning("👈 Please click **'Step 1: Launch Browser & Log In'** to initialize the open Chrome browser.")
