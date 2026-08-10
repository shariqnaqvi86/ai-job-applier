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
    verify_handshake_login, open_handshake_browser, global_bot,
    TAILORED_DOCS_DIR, UPLOADS_DIR
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
    else:
        st.warning("🟡 Handshake Session Idle")

    st.divider()
    st.subheader("🔑 Gemini AI Engine")
    gemini_key = st.text_input("Gemini API Key", value=os.environ.get("GEMINI_API_KEY", ""), type="password", key="sidebar_gemini_key")
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

# --- HEADER & WIZARD STEPS ---
st.title("🤝 Universal Handshake Autopilot Bot")
st.caption("Universal job application engine: upload your master resume & life markers, search Handshake manually in the browser, then click Start Auto Apply.")

# Step Progress Bar
st.markdown("""
<div class="step-banner">
    <div class="step-box">
        <div class="step-num">Step 1</div>
        <div class="step-title">📄 Master Resume & Life Markers</div>
    </div>
    <div class="step-box">
        <div class="step-num">Step 2</div>
        <div class="step-title">🌐 Open Browser & Search Jobs</div>
    </div>
    <div class="step-box">
        <div class="step-num">Step 3</div>
        <div class="step-title">🚀 Auto Apply Start / Stop</div>
    </div>
</div>
""", unsafe_allow_html=True)

# Main Navigation Tabs
tab_materials, tab_browser_search, tab_autopilot = st.tabs([
    "1️⃣ Master Resume & Life Markers",
    "2️⃣ 🌐 Handshake Browser & Search",
    "3️⃣ 🚀 Auto Apply Engine (Start / Stop)"
])

# ==============================================================================
# STEP 1: MASTER RESUME & LIFE MARKERS (UNIVERSAL / MULTI-USER)
# ==============================================================================
with tab_materials:
    st.header("Step 1: Upload Master Resume & Set Life Markers")
    st.caption("Anyone can use this app! Upload your master resume and add significant life markers (milestones) for AI cover letters.")

    col_m1, col_m2 = st.columns(2)

    with col_m1:
        st.subheader("📄 Upload Master Resume")
        uploaded_file = st.file_uploader("Upload PDF / DOCX / TXT Resume", type=["pdf", "docx", "doc", "txt"], key="resume_file_uploader")
        if uploaded_file is not None:
            filename = uploaded_file.name
            filepath = os.path.join(UPLOADS_DIR, f"{uuid.uuid4().hex[:6]}_{filename}")
            with open(filepath, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with st.spinner("Extracting skills & experience from master resume..."):
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
        c_fn = st.text_input("First Name", value=p_personal.get("first_name", ""), placeholder="e.g. Kelly", key="contact_first_name")
        c_ln = st.text_input("Last Name", value=p_personal.get("last_name", ""), placeholder="e.g. DeToy", key="contact_last_name")
        c_phone = st.text_input("Phone Number", value=p_personal.get("phone", ""), placeholder="615-555-0199", key="contact_phone_number")
        c_email = st.text_input("Email Address", value=p_personal.get("email", ""), placeholder="user@georgetown.edu", key="contact_email_str")
        c_loc = st.text_input("Location", value=f"{p_personal.get('city', '')}, {p_personal.get('state', '')}".strip(", "), placeholder="Baltimore, MD", key="contact_location_str")

        if st.button("💾 Save Profile Details", key="btn_save_contact"):
            p_personal["first_name"] = c_fn
            p_personal["last_name"] = c_ln
            p_personal["phone"] = c_phone
            p_personal["email"] = c_email
            loc_p = c_loc.split(",")
            p_personal["city"] = loc_p[0].strip() if loc_p else ""
            p_personal["state"] = loc_p[1].strip() if len(loc_p) > 1 else ""
            current_profile["personal"] = p_personal
            save_profile(current_profile)
            st.success("Candidate details updated!")

    st.divider()

    # LIFE MARKERS / MILESTONES
    st.subheader("💎 Significant Life Markers (Woven into Cover Letters)")
    st.caption("Add custom life milestones (e.g. Military Veteran, Georgetown MS, Career Pivot, Leadership Feat) for Gemini AI to weave into cover letters.")
    
    with st.expander("➕ Add New Life Marker", expanded=False):
        mk_title = st.text_input("Marker Title", placeholder="e.g. US Navy Squad Leader / Georgetown Policy Pivot", key="marker_title_input")
        mk_cat = st.selectbox("Category", ["Leadership & Military", "Academic Pivot", "Overcoming Challenge", "Public Health & Policy", "Technical Achievement"], key="marker_category_select")
        mk_desc = st.text_area("Narrative Context", placeholder="Describe experience, challenges faced, and achievements...", key="marker_desc_input")
        mk_takeaway = st.text_input("Key Takeaway for Employer", placeholder="e.g. High-stakes leadership, resilience under pressure", key="marker_takeaway_input")

        if st.button("➕ Add Milestone Marker", key="btn_add_milestone"):
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
# STEP 2: LAUNCH HANDSHAKE BROWSER & MANUAL SEARCH
# ==============================================================================
with tab_browser_search:
    st.header("Step 2: Open Handshake Browser & Perform Manual Search")
    st.caption("Click below to open a live Chromium window. Log in manually (Georgetown SSO / Duo 2FA) and perform your keyword search.")

    col_b1, col_b2 = st.columns([2, 1])

    with col_b1:
        st.subheader("🌐 Handshake Chromium Session")
        st.write("Click the button below to launch Chromium. You can log into Handshake manually and perform any job search or filter.")
        
        if st.button("🌐 Open Handshake Browser Window", key="btn_open_browser"):
            with st.spinner("Launching Chromium browser window..."):
                success, msg = open_handshake_browser()
                if success:
                    st.success(f"✅ {msg}")
                else:
                    st.error(f"Error launching browser: {msg}")

        st.divider()
        st.subheader("🔍 Select & Queue Target Positions")
        col_kw, col_lc, col_btn = st.columns([3, 2, 1.5])
        search_keywords = col_kw.text_input("Target Job Title / Keywords", value="Python Developer", placeholder="e.g. Data Analyst, Project Manager", key="job_search_keywords")
        search_location = col_lc.text_input("Location", value="Baltimore, MD", key="job_search_location")
        
        with col_btn:
            st.write("")
            st.write("")
            execute_search = st.button("🔍 Filter Jobs", key="btn_execute_search")

        if execute_search or "search_results" not in st.session_state:
            results = search_jobs(search_keywords, search_location, True)
            for r in results:
                r["handshake_direct"] = True
            st.session_state["search_results"] = results

        jobs_found = st.session_state.get("search_results", [])
        st.subheader(f"Handshake Jobs Found ({len(jobs_found)} positions)")

        selected_jobs = []
        for idx, job in enumerate(jobs_found):
            with st.container():
                col_j1, col_j2 = st.columns([4, 1])
                with col_j1:
                    is_checked = st.checkbox(
                        f"**{job.get('title')}** — {job.get('company')}",
                        value=True,
                        key=f"job_chk_{job.get('id', idx)}"
                    )
                    if is_checked:
                        selected_jobs.append(job)
                    st.caption(f"📍 {job.get('location')} | 💰 {job.get('salary')} | <span class='badge-handshake'>Handshake Apply</span>", unsafe_allow_html=True)
                    st.write(job.get("description")[:220] + "...")
                with col_j2:
                    st.metric("ATS Match", f"{job.get('match_score', 92)}%")
                st.divider()

        st.session_state["queued_jobs"] = selected_jobs

    with col_b2:
        st.subheader("📋 Instructions")
        st.info("""
        1. Click **Open Handshake Browser Window**.
        2. Log into Handshake in the opened window (enter Georgetown NetID & complete Duo 2FA push on phone).
        3. Navigate to **Jobs**, search/filter positions.
        4. Select queued positions and proceed to **Step 3** to Start Auto Apply!
        """)

# ==============================================================================
# STEP 3: AUTO APPLY ENGINE (START / STOP CONTROLS)
# ==============================================================================
with tab_autopilot:
    st.header("Step 3: Auto Apply Campaign (Start / Stop Controls)")
    st.caption("Control the automated applying loop. The bot will generate tailored ATS resumes & cover letters using your uploaded profile and submit applications.")

    queued_jobs = st.session_state.get("queued_jobs", [])
    st.info(f"📋 **{len(queued_jobs)} Handshake jobs queued** for automated application.")

    col_ctrl1, col_ctrl2, col_ctrl3 = st.columns(3)
    wpm_speed = col_ctrl1.slider("Human Typing Speed (WPM)", 40, 100, 65, key="slider_wpm_speed")
    mouse_jitter = col_ctrl2.checkbox("Enable Mouse Jitter & Curves", value=True, key="chk_mouse_jitter")
    delay_min, delay_max = col_ctrl3.slider("Random Delay Between Steps (sec)", 1, 10, (2, 5), key="slider_random_delay")

    st.divider()
    col_start, col_stop, col_pause = st.columns(3)

    with col_start:
        start_clicked = st.button("🚀 START AUTO APPLY", key="btn_start_auto_apply")
    with col_stop:
        stop_clicked = st.button("🛑 STOP AUTO APPLY", key="btn_stop_auto_apply")
    with col_pause:
        pause_clicked = st.button("⏸️ PAUSE / RESUME", key="btn_pause_auto_apply")

    if stop_clicked:
        global_bot.stop()
        st.warning("🛑 Auto Apply engine stopped by user command.")

    if pause_clicked:
        is_paused = global_bot.pause()
        st.info("⏸️ Engine Paused" if is_paused else "▶️ Engine Resumed")

    if start_clicked:
        if not queued_jobs:
            st.error("No jobs selected. Please go to Step 2 and select jobs.")
        else:
            job_ids = [j.get("id") for j in queued_jobs if j.get("id")]
            started, msg = global_bot.start_apply_campaign(
                job_ids=job_ids,
                profile=current_profile,
                humanizer_settings={
                    "typing_wpm": wpm_speed,
                    "mouse_jitter": mouse_jitter,
                    "min_delay": delay_min,
                    "max_delay": delay_max
                }
            )
            if started:
                st.success("🚀 Auto Apply Engine Started!")
            else:
                st.info(f"Bot Status: {msg}")

    # Live Status & Log Viewer
    st.subheader("📊 Live Execution Progress & Logs")
    if global_bot.is_running:
        st.write(f"**Current Action:** `{global_bot.current_step}`")
    
    if global_bot.logs:
        st.text_area("Live Terminal Output Logs", value="\n".join(global_bot.logs[-25:]), height=300, key="live_log_output_area")
    else:
        st.caption("No log activity yet. Click *START AUTO APPLY* to begin processing applications.")
        st.divider()
