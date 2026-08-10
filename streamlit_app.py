import os
import sys
import json
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
    page_title="Handshake Auto Apply - AI Career & Job Suite",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM GLASSMORPHISM STYLING ---
st.markdown("""
<style>
    /* Dark Theme Core */
    .stApp {
        background-color: #0a0f1a;
        color: #e2e8f0;
    }
    
    /* Header & Titles */
    h1, h2, h3 {
        font-family: 'Inter', -apple-system, sans-serif;
        font-weight: 800 !important;
        color: #ffffff !important;
    }
    
    /* Custom Metric Card */
    .metric-card {
        background: linear-gradient(135deg, rgba(20,28,48,0.7), rgba(15,22,36,0.7));
        border: 1px solid rgba(0, 240, 255, 0.2);
        border-radius: 12px;
        padding: 1.2rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37);
        backdrop-filter: blur(8px);
        margin-bottom: 1rem;
    }
    .metric-val {
        font-size: 2rem;
        font-weight: 900;
        color: #00f0ff;
    }
    .metric-lbl {
        font-size: 0.85rem;
        color: #94a3b8;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Milestone Card */
    .milestone-box {
        background: rgba(15, 23, 42, 0.6);
        border: 1px solid rgba(112, 0, 255, 0.3);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    
    /* Buttons */
    .stButton>button {
        background: linear-gradient(135deg, #00f0ff, #7000ff) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        border: none !important;
        border-radius: 8px !important;
        padding: 0.5rem 1.5rem !important;
        transition: all 0.3s ease !important;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 20px rgba(0, 240, 255, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# --- SESSION STATE INITIALIZATION ---
if "profiles" not in st.session_state:
    st.session_state["profiles"] = load_all_profiles()

if "active_profile_id" not in st.session_state and st.session_state["profiles"]:
    st.session_state["active_profile_id"] = st.session_state["profiles"][0].get("id")

def get_current_profile():
    profiles = st.session_state.get("profiles", [])
    active_id = st.session_state.get("active_profile_id")
    for p in profiles:
        if p.get("id") == active_id:
            return p
    return profiles[0] if profiles else None

def save_current_profile(updated_profile):
    profiles = st.session_state.get("profiles", [])
    for idx, p in enumerate(profiles):
        if p.get("id") == updated_profile.get("id"):
            profiles[idx] = updated_profile
            break
    save_all_profiles(profiles)
    st.session_state["profiles"] = profiles

current_profile = get_current_profile()

# --- SIDEBAR ---
with st.sidebar:
    st.image("https://img.icons8.com/isometric/100/robot.png", width=60)
    st.title("HANDSHAKE AUTO APPLY")
    st.caption("AI Career Autopilot & Life Milestone Tailorer")
    st.divider()

    # Active Profile Selector
    st.subheader("👤 Active Candidate")
    profile_names = {p.get("id"): f"{p['personal'].get('first_name', '')} {p['personal'].get('last_name', '')}" for p in st.session_state["profiles"]}
    selected_p_id = st.selectbox(
        "Select Candidate Profile",
        options=list(profile_names.keys()),
        format_func=lambda x: profile_names[x],
        index=list(profile_names.keys()).index(st.session_state["active_profile_id"]) if st.session_state["active_profile_id"] in profile_names else 0
    )
    if selected_p_id != st.session_state["active_profile_id"]:
        st.session_state["active_profile_id"] = selected_p_id
        st.rerun()

    st.divider()

    # Handshake Account Credentials
    st.subheader("🤝 Handshake Login Credentials")
    hs_creds = current_profile.get("handshake_credentials", {}) if current_profile else {}
    
    hs_email = st.text_input("Handshake Email / Username", value=hs_creds.get("email", ""), placeholder="student@georgetown.edu")
    hs_password = st.text_input("Handshake Password", value=hs_creds.get("password", ""), type="password", placeholder="••••••••••••")
    hs_portal = st.text_input("Portal / School Login URL", value=hs_creds.get("portal_url", "https://app.joinhandshake.com/login"))

    col_hs1, col_hs2 = st.columns(2)
    with col_hs1:
        if st.button("💾 Save Credentials"):
            if current_profile:
                current_profile["handshake_credentials"] = {
                    "email": hs_email,
                    "password": hs_password,
                    "portal_url": hs_portal,
                    "connected": bool(hs_email)
                }
                save_current_profile(current_profile)
                st.success("Handshake credentials saved!")
                st.rerun()

    with col_hs2:
        if st.button("🔌 Verify Login"):
            with st.spinner("Connecting to Handshake..."):
                success, msg = verify_handshake_login(hs_email, hs_password, hs_portal)
                if success:
                    st.success("✅ Handshake Verified!")
                else:
                    st.warning(f"Handshake Status: {msg}")

    # Connection Status Badge
    if hs_creds.get("connected"):
        st.success("🟢 Handshake Session Connected")
    elif hs_creds.get("email"):
        st.info("🔵 Credentials Saved (Unverified)")
    else:
        st.warning("🟡 Credentials Not Configured")

    st.divider()

    # Gemini API Key Setup
    st.subheader("🔑 Gemini AI API Configuration")
    gemini_key = st.text_input("Google Gemini API Key", value=os.environ.get("GEMINI_API_KEY", ""), type="password")
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

# --- MAIN APP TABS ---
tab_dash, tab_profile, tab_search, tab_studio, tab_terminal = st.tabs([
    "📊 Dashboard",
    "👤 Candidate Profile & Milestones",
    "🔍 Job Search Engine",
    "✨ AI Tailoring Studio",
    "🤖 Bot Terminal"
])

# ==============================================================================
# TAB 1: DASHBOARD
# ==============================================================================
with tab_dash:
    st.header("Candidate Command Center")
    st.caption("Automate tailored resumes & cover letters enriched with your significant life markers.")

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    with col_m1:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-val">14</div>
            <div class="metric-lbl">Applications Submitted</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m2:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-val" style="color: #00ffaa;">94%</div>
            <div class="metric-lbl">Avg ATS Match Score</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m3:
        milestone_count = len(current_profile.get("life_milestones", [])) if current_profile else 0
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-val" style="color: #7000ff;">{milestone_count}</div>
            <div class="metric-lbl">Active Life Markers</div>
        </div>
        """, unsafe_allow_html=True)
    with col_m4:
        st.markdown("""
        <div class="metric-card">
            <div class="metric-val" style="color: #ffb700; font-size: 1.4rem;">READY</div>
            <div class="metric-lbl">Auto Apply Engine</div>
        </div>
        """, unsafe_allow_html=True)

    st.subheader("Selected Life Milestones for Cover Letters")
    if current_profile and current_profile.get("life_milestones"):
        for m in current_profile["life_milestones"]:
            if m.get("selected", True):
                st.markdown(f"""
                <div class="milestone-box">
                    <strong>💎 {m.get('title')}</strong> ({m.get('category')})<br>
                    <small style="color: #94a3b8;">{m.get('key_takeaways')}</small>
                </div>
                """, unsafe_allow_html=True)
    else:
        st.info("No life milestones added yet. Go to the Candidate Profile tab to add markers.")

# ==============================================================================
# TAB 2: CANDIDATE PROFILE, RESUME & MILESTONES
# ==============================================================================
with tab_profile:
    st.header("Candidate Profile, Base Resume & Life Milestones")
    st.caption("Upload your base resume and configure life markers that give your cover letters a human voice.")

    col_prof1, col_prof2 = st.columns(2)

    with col_prof1:
        st.subheader("📄 Base Resume Upload & Parser")
        uploaded_file = st.file_uploader("Upload Base Resume (PDF, DOCX, TXT)", type=["pdf", "docx", "doc", "txt"])
        if uploaded_file is not None:
            filename = uploaded_file.name
            filepath = os.path.join(UPLOADS_DIR, f"{uuid.uuid4().hex[:6]}_{filename}")
            with open(filepath, "wb") as f:
                f.write(uploaded_file.getbuffer())

            with st.spinner("Parsing resume experience & skills..."):
                parsed_info, raw_text = parse_uploaded_resume(filepath)
                if current_profile:
                    if parsed_info.get("personal"):
                        for k, v in parsed_info["personal"].items():
                            if v and not current_profile["personal"].get(k):
                                current_profile["personal"][k] = v
                    if parsed_info.get("skills"):
                        existing = set(current_profile.get("skills", []))
                        existing.update(parsed_info["skills"])
                        current_profile["skills"] = list(existing)
                    current_profile["resume_text"] = raw_text
                    save_current_profile(current_profile)
                    st.success(f"Parsed and updated resume from {filename}!")

        st.markdown("**Extracted Primary Skills:**")
        if current_profile and current_profile.get("skills"):
            st.write(", ".join([f"`{s}`" for s in current_profile["skills"]]))

    with col_prof2:
        st.subheader("👤 Candidate Details")
        if current_profile:
            p_personal = current_profile.get("personal", {})
            p_pref = current_profile.get("preferences", {})

            col_fn, col_ln = st.columns(2)
            fname = col_fn.text_input("First Name", value=p_personal.get("first_name", ""))
            lname = col_ln.text_input("Last Name", value=p_personal.get("last_name", ""))

            email = st.text_input("Email Address", value=p_personal.get("email", ""))
            phone = st.text_input("Phone Number", value=p_personal.get("phone", ""))
            location = st.text_input("Location (City, State)", value=f"{p_personal.get('city', '')}, {p_personal.get('state', '')}".strip(", "))
            salary = st.text_input("Desired Salary", value=p_pref.get("salary", ""))

            if st.button("Save Profile Details"):
                p_personal["first_name"] = fname
                p_personal["last_name"] = lname
                p_personal["email"] = email
                p_personal["phone"] = phone
                loc_parts = location.split(",")
                p_personal["city"] = loc_parts[0].strip() if loc_parts else ""
                p_personal["state"] = loc_parts[1].strip() if len(loc_parts) > 1 else ""
                p_pref["salary"] = salary

                current_profile["personal"] = p_personal
                current_profile["preferences"] = p_pref
                save_current_profile(current_profile)
                st.success("Profile details updated successfully!")

    st.divider()

    # LIFE MILESTONES MANAGER
    st.subheader("💎 Significant Life Milestones & Markers")
    st.caption("Add key life moments, pivots, leadership feats, or personal challenges to weave into AI cover letters.")

    with st.expander("➕ Add New Life Milestone / Marker", expanded=False):
        m_title = st.text_input("Milestone Title", placeholder="e.g. US Navy Submarine Squad Leader / Georgetown Policy Pivot")
        m_cat = st.selectbox("Category", ["Leadership & Service", "Career Pivot", "Academic Achievement", "Overcoming Adversity", "Public Health Impact"])
        m_desc = st.text_area("Narrative Description", placeholder="Describe what happened, your responsibilities, and challenges faced...")
        m_takeaway = st.text_input("Key Takeaway for Employers", placeholder="e.g. Proven resilience, high-stakes leadership, and analytical rigor.")

        if st.button("Save Life Milestone"):
            if m_title and m_desc:
                new_m = {
                    "id": f"m_{uuid.uuid4().hex[:8]}",
                    "title": m_title,
                    "category": m_cat,
                    "description": m_desc,
                    "key_takeaways": m_takeaway,
                    "selected": True
                }
                if "life_milestones" not in current_profile:
                    current_profile["life_milestones"] = []
                current_profile["life_milestones"].insert(0, new_m)
                save_current_profile(current_profile)
                st.success("New life milestone added!")
                st.rerun()

    # List Existing Milestones
    if current_profile and current_profile.get("life_milestones"):
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
                    save_current_profile(current_profile)

                st.write(m.get("description"))
                st.caption(f"💡 Key Takeaway: {m.get('key_takeaways')}")

            with col_m2:
                if st.button("🗑️ Delete", key=f"del_{m.get('id')}"):
                    current_profile["life_milestones"] = [x for x in current_profile["life_milestones"] if x.get("id") != m.get("id")]
                    save_current_profile(current_profile)
                    st.rerun()
            st.divider()

# ==============================================================================
# TAB 3: JOB SEARCH ENGINE
# ==============================================================================
with tab_search:
    st.header("Job Search Engine")
    st.caption("Search live postings, analyze ATS match scores, and tailor applications in 1 click.")

    col_s1, col_s2, col_s3 = st.columns([3, 2, 1])
    keywords = col_s1.text_input("Job Title / Keywords", value="Python Developer")
    search_loc = col_s2.text_input("Location", value="Baltimore, MD")
    remote_only = col_s3.checkbox("Remote Only", value=True)

    if st.button("🔍 Search Jobs Now") or "search_results" not in st.session_state:
        with st.spinner("Searching job boards..."):
            results = search_jobs(keywords, search_loc, remote_only)
            st.session_state["search_results"] = results

    results = st.session_state.get("search_results", [])
    st.subheader(f"Search Results ({len(results)} jobs found)")

    for job in results:
        with st.container():
            col_j1, col_j2 = st.columns([4, 1])
            with col_j1:
                st.markdown(f"### {job.get('title')} — {job.get('company')}")
                st.caption(f"📍 {job.get('location')} | 💰 {job.get('salary')} | Posted: {job.get('posted')}")
                st.write(job.get("description")[:280] + "...")
            with col_j2:
                st.metric("ATS Match", f"{job.get('match_score', 92)}%")
                if st.button("✨ Tailor & Preview", key=f"btn_tailor_{job.get('id')}"):
                    st.session_state["studio_job"] = job
                    st.success("Job sent to AI Tailoring Studio!")
            st.divider()

# ==============================================================================
# TAB 4: AI TAILORING STUDIO
# ==============================================================================
with tab_studio:
    st.header("AI Tailoring Studio")
    st.caption("Review your humanized cover letter (with life milestones woven in) and ATS-tailored resume.")

    studio_job = st.session_state.get("studio_job")
    if not studio_job:
        st.info("No job selected. Go to the Job Search Engine tab and click 'Tailor & Preview' on any job.")
    else:
        st.subheader(f"Targeting: {studio_job.get('title')} at {studio_job.get('company')}")

        if st.button("⚡ Generate AI Tailored Cover Letter & Resume"):
            with st.spinner("Weaving life milestones into cover letter and optimizing ATS keywords..."):
                cl_text = generate_tailored_cover_letter(studio_job.get('title'), studio_job.get('company'), studio_job.get('description'), current_profile)
                res_text = generate_tailored_resume(studio_job.get('title'), studio_job.get('company'), studio_job.get('description'), current_profile)

                st.session_state["generated_cl"] = cl_text
                st.session_state["generated_res"] = res_text
                st.success("Documents generated successfully!")

        col_t1, col_t2 = st.columns(2)
        with col_t1:
            st.subheader("✉️ Humanized Cover Letter")
            cl_content = st.text_area("Cover Letter Text", value=st.session_state.get("generated_cl", ""), height=400)
            if cl_content:
                st.download_button("📥 Download Cover Letter (TXT)", data=cl_content, file_name=f"CoverLetter_{studio_job.get('company')}.txt")

        with col_t2:
            st.subheader("📄 ATS Tailored Resume")
            res_content = st.text_area("Tailored Resume Text", value=st.session_state.get("generated_res", ""), height=400)
            if res_content:
                st.download_button("📥 Download Resume (TXT)", data=res_content, file_name=f"Resume_{studio_job.get('company')}.txt")

# ==============================================================================
# TAB 5: BOT TERMINAL
# ==============================================================================
with tab_terminal:
    st.header("Handshake Auto Apply Terminal")
    st.caption("Live execution console for stealth browser automation and 1-click apply campaigns.")

    col_b1, col_b2, col_b3 = st.columns(3)
    wpm = col_b1.slider("Typing Speed (WPM)", 40, 100, 65)
    jitter = col_b2.checkbox("Enable Mouse Jitter", value=True)
    delay_range = col_b3.slider("Random Delay (seconds)", 1, 10, (2, 5))

    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        if st.button("🚀 Start Auto-Apply Campaign"):
            st.success("Campaign launched! Monitoring execution log...")
    with col_btn2:
        if st.button("🛑 Stop Campaign"):
            st.warning("Campaign stopped.")

    st.subheader("Execution Terminal Output")
    st.code("""
    [SYSTEM] Handshake Auto Apply Initialized.
    [HANDSHAKE] Connecting to portal https://app.joinhandshake.com/login...
    [PROFILE] Loaded Candidate: Shariq Naqvi (Milestones: 3 active)
    [BOT] Humanized mouse curve initiated. Typing WPM: 65.
    [READY] Waiting for job selection...
    """, language="bash")
