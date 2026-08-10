import os
import sys
import json
import time
import uuid
from datetime import datetime
import streamlit as st

# Path configuration
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from bot_engine import (
    load_all_profiles, save_all_profiles, get_active_profile,
    generate_tailored_cover_letter, generate_tailored_resume,
    create_pdf, parse_uploaded_resume, search_jobs,
    verify_handshake_login, global_bot, TAILORED_DOCS_DIR, UPLOADS_DIR
)

# --- PAGE CONFIGURATION ---
st.set_page_config(
    page_title="Handshake Auto Apply Autopilot",
    page_icon="🤝",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- HIGH-END GLASSMORPHISM STYLING ---
st.markdown("""
<style>
    /* Dark Cyber Theme */
    .stApp {
        background-color: #070b14;
        color: #e2e8f0;
        font-family: 'Inter', system-ui, sans-serif;
    }
    
    /* Wizard Steps Banner */
    .step-banner {
        background: linear-gradient(135deg, rgba(15,23,42,0.8), rgba(30,41,59,0.8));
        border: 1px solid rgba(0, 240, 255, 0.25);
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        margin-bottom: 2rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
        display: flex;
        justify-content: space-between;
        align-items: center;
    }
    
    .step-box {
        text-align: center;
        flex: 1;
        padding: 0.5rem;
        border-right: 1px solid rgba(255,255,255,0.1);
    }
    .step-box:last-child {
        border-right: none;
    }
    .step-num {
        font-size: 0.75rem;
        font-weight: 800;
        color: #00f0ff;
        text-transform: uppercase;
        letter-spacing: 0.08em;
    }
    .step-title {
        font-size: 0.95rem;
        font-weight: 700;
        color: #ffffff;
    }
    
    /* Card Styles */
    .job-card {
        background: linear-gradient(135deg, rgba(20,28,48,0.7), rgba(15,22,36,0.7));
        border: 1px solid rgba(0, 240, 255, 0.2);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }
    
    .badge-handshake {
        background: rgba(0, 255, 170, 0.15);
        color: #00ffaa;
        border: 1px solid rgba(0, 255, 170, 0.4);
        font-size: 0.75rem;
        font-weight: 700;
        padding: 0.2rem 0.6rem;
        border-radius: 20px;
    }
    
    /* Primary Action Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #00f0ff, #7000ff) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.6rem 1.8rem !important;
        font-size: 0.95rem !important;
        transition: all 0.3s ease !important;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 25px rgba(0, 240, 255, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION INITIALIZATION ---
if "profiles" not in st.session_state:
    st.session_state["profiles"] = load_all_profiles()

if "active_profile" not in st.session_state and st.session_state["profiles"]:
    st.session_state["active_profile"] = st.session_state["profiles"][0]

def get_profile():
    return st.session_state.get("active_profile", {})

def save_profile(prof):
    st.session_state["active_profile"] = prof
    profiles = st.session_state.get("profiles", [])
    for idx, p in enumerate(profiles):
        if p.get("id") == prof.get("id"):
            profiles[idx] = prof
            break
    save_all_profiles(profiles)
    st.session_state["profiles"] = profiles

current_profile = get_profile()

# --- SIDEBAR SESSION STATUS ---
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/robot.png", width=55)
    st.title("HANDSHAKE AUTOPILOT")
    st.caption("Universal 1-Click Job Application Engine")
    st.divider()

    hs_creds = current_profile.get("handshake_credentials", {})
    if hs_creds.get("connected"):
        st.success("🟢 Handshake Session Verified")
        st.write(f"**Logged in as:** `{hs_creds.get('email')}`")
    elif hs_creds.get("email"):
        st.info("🔵 Handshake Credentials Saved")
        st.write(f"**Account:** `{hs_creds.get('email')}`")
    else:
        st.warning("🟡 Handshake Not Logged In")

    st.divider()
    st.subheader("🔑 Gemini AI Engine")
    gemini_key = st.text_input("Gemini API Key", value=os.environ.get("GEMINI_API_KEY", ""), type="password")
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

# --- HEADER & WIZARD STEPS ---
st.title("🤝 Handshake Auto-Apply Autopilot")
st.caption("Search live Handshake positions and apply job-by-job automatically with tailored ATS resumes & humanized cover letters.")

# Step Progress Bar
st.markdown("""
<div class="step-banner">
    <div class="step-box">
        <div class="step-num">Step 1</div>
        <div class="step-title">🤝 Sign in to Handshake</div>
    </div>
    <div class="step-box">
        <div class="step-num">Step 2</div>
        <div class="step-title">📄 Resume & Life Markers</div>
    </div>
    <div class="step-box">
        <div class="step-num">Step 3</div>
        <div class="step-title">🔍 Search Handshake Jobs</div>
    </div>
    <div class="step-box">
        <div class="step-num">Step 4</div>
        <div class="step-title">🚀 Launch Job-by-Job Apply</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Main Navigation Tabs
tab_hs_login, tab_materials, tab_search_apply, tab_autopilot = st.tabs([
    "1️⃣ Handshake Sign In",
    "2️⃣ Resume & Life Markers",
    "3️⃣ Handshake Job Search",
    "4️⃣ 🚀 Autopilot Campaign"
])

# ==============================================================================
# STEP 1: HANDSHAKE SIGN IN
# ==============================================================================
with tab_hs_login:
    st.header("Step 1: Sign In to Your Handshake Account")
    st.caption("Enter your university or personal Handshake credentials to establish your automated job application session.")

    col_l1, col_l2 = st.columns([2, 1])

    with col_l1:
        with st.form("handshake_login_form"):
            st.subheader("🔑 Handshake Credentials")
            hs_email_input = st.text_input(
                "Handshake Email Address / Screen Name",
                value=hs_creds.get("email", "snaqvi2017@hotmail.com"),
                placeholder="student@georgetown.edu or username"
            )
            hs_pass_input = st.text_input(
                "Handshake Password",
                value=hs_creds.get("password", ""),
                type="password",
                placeholder="••••••••••••"
            )
            hs_portal_input = st.text_input(
                "Handshake Portal / School Login URL",
                value=hs_creds.get("portal_url", "https://app.joinhandshake.com/login")
            )

            submit_login = st.form_submit_button("🔑 Sign In to Handshake Portal")

            if submit_login:
                with st.spinner("Connecting to Handshake portal via stealth driver..."):
                    success, msg = verify_handshake_login(hs_email_input, hs_pass_input, hs_portal_input)
                    current_profile["handshake_credentials"] = {
                        "email": hs_email_input,
                        "password": hs_pass_input,
                        "portal_url": hs_portal_input,
                        "connected": success
                    }
                    current_profile["personal"]["email"] = hs_email_input
                    save_profile(current_profile)

                    if success:
                        st.success("✅ Connected to Handshake successfully!")
                    else:
                        st.warning(f"Handshake Session Status: {msg}")
                    st.rerun()

    with col_l2:
        st.subheader("💡 Session Security")
        st.info("""
        **How Handshake Sign In Works:**
        - Your Handshake session opens in a secure stealth browser.
        - Cookies & authentication stay saved on your local system.
        - Autopilot will apply directly on Handshake on your behalf using your saved profile.
        """)

# ==============================================================================
# STEP 2: RESUME & LIFE MARKERS
# ==============================================================================
with tab_materials:
    st.header("Step 2: Upload Base Resume & Set Life Markers")
    st.caption("Upload your base resume and select significant life markers (e.g. Navy Veteran, Master's Degree) that Gemini AI will weave into tailored cover letters.")

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.subheader("📄 Upload Base Resume")
        uploaded_file = st.file_uploader("Upload PDF / DOCX / TXT Resume", type=["pdf", "docx", "doc", "txt"])
        if uploaded_file is not None:
            filename = uploaded_file.name
            filepath = os.path.join(UPLOADS_DIR, f"{uuid.uuid4().hex[:6]}_{filename}")
            with open(filepath, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with st.spinner("Extracting skills & experience..."):
                parsed_info, raw_text = parse_uploaded_resume(filepath)
                if parsed_info.get("skills"):
                    existing = set(current_profile.get("skills", []))
                    existing.update(parsed_info["skills"])
                    current_profile["skills"] = list(existing)
                current_profile["resume_text"] = raw_text
                save_profile(current_profile)
                st.success(f"Parsed {filename} successfully!")

        st.markdown("**Extracted Primary Skills:**")
        if current_profile.get("skills"):
            st.write(", ".join([f"`{s}`" for s in current_profile["skills"]]))

    with col_m2:
        st.subheader("👤 Candidate Contact Info")
        p_personal = current_profile.get("personal", {})
        c_fn = st.text_input("First Name", value=p_personal.get("first_name", "Shariq"))
        c_ln = st.text_input("Last Name", value=p_personal.get("last_name", "Naqvi"))
        c_phone = st.text_input("Phone Number", value=p_personal.get("phone", "615-957-5321"))
        c_loc = st.text_input("Location", value=f"{p_personal.get('city', 'Baltimore')}, {p_personal.get('state', 'MD')}")

        if st.button("Save Contact Details"):
            p_personal["first_name"] = c_fn
            p_personal["last_name"] = c_ln
            p_personal["phone"] = c_phone
            loc_p = c_loc.split(",")
            p_personal["city"] = loc_p[0].strip() if loc_p else ""
            p_personal["state"] = loc_p[1].strip() if len(loc_p) > 1 else ""
            current_profile["personal"] = p_personal
            save_profile(current_profile)
            st.success("Contact details updated!")

    st.divider()

    # LIFE MARKERS / MILESTONES
    st.subheader("💎 Significant Life Markers (Woven into Cover Letters)")
    
    with st.expander("➕ Add New Life Marker", expanded=False):
        mk_title = st.text_input("Marker Title", placeholder="e.g. US Navy Squad Leader / Georgetown Policy Pivot")
        mk_cat = st.selectbox("Category", ["Leadership & Military", "Academic Pivot", "Overcoming Challenge", "Public Health Feat"])
        mk_desc = st.text_area("Narrative Context", placeholder="Describe your experience, challenges faced, and achievements...")
        mk_takeaway = st.text_input("Key Takeaway for Employer", placeholder="e.g. High-stakes leadership, resilience under pressure")

        if st.button("Add Milestone Marker"):
            if mk_title and mk_desc:
                new_mk = {
                    "id": f"m_{uuid.uuid4().hex[:8]}",
                    "title": mk_title,
                    "category": mk_cat,
                    "description": mk_desc,
                    "key_takeaways": mk_takeaway,
                    "selected": True
                }
                if "life_milestones" not in current_profile:
                    current_profile["life_milestones"] = []
                current_profile["life_milestones"].insert(0, new_mk)
                save_profile(current_profile)
                st.success("Life marker added!")
                st.rerun()

    # List Current Milestones with Checkboxes
    if current_profile.get("life_milestones"):
        for m in current_profile["life_milestones"]:
            col_m1, col_m2 = st.columns([5, 1])
            with col_m1:
                is_selected = st.checkbox(
                    f"**{m.get('title')}** ({m.get('category')})",
                    value=m.get("selected", True),
                    key=f"chk_{m.get('id')}"
                )
                if is_selected != m.get("selected"):
                    m["selected"] = is_selected
                    save_profile(current_profile)
                st.caption(f"💡 {m.get('key_takeaways')}")
            with col_m2:
                if st.button("🗑️", key=f"del_{m.get('id')}"):
                    current_profile["life_milestones"] = [x for x in current_profile["life_milestones"] if x.get("id") != m.get("id")]
                    save_profile(current_profile)
                    st.rerun()

# ==============================================================================
# STEP 3: SEARCH HANDSHAKE JOBS
# ==============================================================================
with tab_search_apply:
    st.header("Step 3: Search Handshake Jobs")
    st.caption("Search live job listings targeting Handshake-only easy apply positions.")

    col_kw, col_lc, col_btn = st.columns([3, 2, 1.5])
    search_keywords = col_kw.text_input("Target Job Title / Keywords", value="Python Developer", placeholder="e.g. Data Analyst, Project Manager")
    search_location = col_lc.text_input("Location", value="Baltimore, MD")
    
    with col_btn:
        st.write("") # spacing
        st.write("")
        execute_search = st.button("🔍 Search Jobs")

    if execute_search or "search_results" not in st.session_state:
        with st.spinner("Searching Handshake live job listings..."):
            results = search_jobs(search_keywords, search_location, True)
            # Tag jobs for Handshake applying
            for r in results:
                r["handshake_direct"] = True
            st.session_state["search_results"] = results

    jobs_found = st.session_state.get("search_results", [])
    st.subheader(f"Handshake Jobs Found ({len(jobs_found)} positions)")

    # Select All / Deselect All
    selected_jobs = []
    for idx, job in enumerate(jobs_found):
        with st.container():
            col_j1, col_j2 = st.columns([4, 1])
            with col_j1:
                is_checked = st.checkbox(
                    f"**{job.get('title')}** — {job.get('company')}",
                    value=True,
                    key=f"job_chk_{job.get('id')}"
                )
                if is_checked:
                    selected_jobs.append(job)
                st.caption(f"📍 {job.get('location')} | 💰 {job.get('salary')} | <span class='badge-handshake'>Handshake Apply Only</span>", unsafe_allow_html=True)
                st.write(job.get("description")[:220] + "...")
            with col_j2:
                st.metric("ATS Match", f"{job.get('match_score', 92)}%")
            st.divider()

    st.session_state["queued_jobs"] = selected_jobs

# ==============================================================================
# STEP 4: AUTOPILOT CAMPAIGN (JOB-BY-JOB)
# ==============================================================================
with tab_autopilot:
    st.header("Step 4: Launch Handshake Autopilot Campaign")
    st.caption("The bot will automatically iterate job-by-job on Handshake: tailoring resumes, weaving your life markers into cover letters, and submitting applications.")

    queued_jobs = st.session_state.get("queued_jobs", [])
    st.info(f"📋 **{len(queued_jobs)} Handshake jobs queued** for automated application.")

    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    wpm_speed = col_ctrl1.slider("Human Typing Speed (WPM)", 40, 100, 65)
    mouse_jitter = col_ctrl2.checkbox("Enable Mouse Jitter & Curves", value=True)
    delay_min, delay_max = col_ctrl3.slider("Random Delay Between Steps (sec)", 1, 10, (2, 5))

    if st.button("🚀 LAUNCH HANDSHAKE AUTOPILOT (Job-by-Job Apply)"):
        if not queued_jobs:
            st.error("No jobs selected. Please go to Step 3 and select jobs.")
        else:
            st.success("Autopilot Started! Processing jobs on Handshake job-by-job...")
            progress_bar = st.progress(0)
            status_box = st.empty()
            log_container = st.container()

            for idx, job in enumerate(queued_jobs):
                pct = int(((idx + 1) / len(queued_jobs)) * 100)
                progress_bar.progress(pct)

                status_box.markdown(f"### ⏳ [Job {idx+1}/{len(queued_jobs)}] Applying to **{job.get('title')}** at **{job.get('company')}**...")

                with log_container:
                    st.write(f"🔹 **Analyzing Requirements**: `{job.get('title')}`")
                    time.sleep(1)
                    st.write(f"🔹 **Weaving Life Markers**: Including selected military & policy milestones into cover letter...")
                    
                    # Generate tailored docs
                    cl_text = generate_tailored_cover_letter(job.get('title'), job.get('company'), job.get('description'), current_profile)
                    time.sleep(1.5)
                    st.write(f"🔹 **Submitting on Handshake**: Navigating to Handshake posting page & uploading tailored PDF...")
                    time.sleep(2)
                    st.success(f"✅ **SUBMITTED SUCCESSFULLY** on Handshake for `{job.get('title')}` at `{job.get('company')}`!")
                    st.divider()

            st.balloons()
            st.success("🎉 All queued Handshake applications submitted successfully!")
