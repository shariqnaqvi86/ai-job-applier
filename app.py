import os
import json
import uuid
from flask import Flask, render_template, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename

from bot_engine import (
    load_all_profiles, save_all_profiles, get_active_profile,
    generate_tailored_cover_letter, generate_tailored_resume,
    create_pdf, parse_uploaded_resume, search_jobs,
    global_bot, TAILORED_DOCS_DIR, UPLOADS_DIR
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.config['UPLOAD_FOLDER'] = UPLOADS_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max upload

ACTIVE_PROFILE_ID = None

def get_current_profile():
    global ACTIVE_PROFILE_ID
    profiles = load_all_profiles()
    if not profiles:
        return None
    if ACTIVE_PROFILE_ID:
        for p in profiles:
            if p.get("id") == ACTIVE_PROFILE_ID:
                return p
    ACTIVE_PROFILE_ID = profiles[0].get("id")
    return profiles[0]

# --- ROUTES ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/profiles', methods=['GET'])
def get_profiles():
    profiles = load_all_profiles()
    active_profile = get_current_profile()
    return jsonify({
        "profiles": profiles,
        "active_profile_id": active_profile.get("id") if active_profile else None
    })

# --- AUTHENTICATION & CANDIDATE LOGIN ---

@app.route('/api/auth/login', methods=['POST'])
def auth_login():
    global ACTIVE_PROFILE_ID
    data = request.json or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "").strip()
    portal_url = data.get("portal_url", "https://app.joinhandshake.com/login").strip()

    if not email:
        return jsonify({"status": "error", "message": "Email address is required"}), 400

    profiles = load_all_profiles()
    matching_profile = None
    for p in profiles:
        p_email = p.get("personal", {}).get("email", "").strip().lower()
        hs_email = p.get("handshake_credentials", {}).get("email", "").strip().lower()
        if email == p_email or email == hs_email:
            matching_profile = p
            break

    if not matching_profile:
        # Create fresh profile for new signing candidate
        new_id = f"profile_{uuid.uuid4().hex[:6]}"
        user_part = email.split("@")[0].title()
        matching_profile = {
            "id": new_id,
            "profile_name": user_part,
            "personal": {
                "first_name": user_part,
                "last_name": "",
                "email": email,
                "phone": "",
                "city": "Baltimore",
                "state": "MD"
            },
            "preferences": {
                "salary": "$85,000"
            },
            "handshake_credentials": {
                "email": email,
                "password": password,
                "portal_url": portal_url,
                "connected": True
            },
            "skills": ["Python", "Project Management", "Data Analysis"],
            "life_milestones": []
        }
        profiles.append(matching_profile)
        save_all_profiles(profiles)

    # Save credentials into existing profile if updated
    if password or portal_url:
        matching_profile["handshake_credentials"] = {
            "email": email,
            "password": password or matching_profile.get("handshake_credentials", {}).get("password", ""),
            "portal_url": portal_url or matching_profile.get("handshake_credentials", {}).get("portal_url", "https://app.joinhandshake.com/login"),
            "connected": True
        }
        for idx, p in enumerate(profiles):
            if p.get("id") == matching_profile["id"]:
                profiles[idx] = matching_profile
                break
        save_all_profiles(profiles)

    ACTIVE_PROFILE_ID = matching_profile["id"]
    return jsonify({
        "status": "success",
        "message": f"Welcome back, {matching_profile['personal'].get('first_name')}!",
        "profile": matching_profile
    })

@app.route('/api/auth/logout', methods=['POST'])
def auth_logout():
    global ACTIVE_PROFILE_ID
    ACTIVE_PROFILE_ID = None
    return jsonify({"status": "success", "message": "Logged out successfully"})

@app.route('/api/profiles/active', methods=['POST'])
def set_active_profile():
    global ACTIVE_PROFILE_ID
    data = request.json or {}
    profile_id = data.get("profile_id")
    if profile_id:
        ACTIVE_PROFILE_ID = profile_id
        return jsonify({"status": "success", "active_profile_id": ACTIVE_PROFILE_ID})
    return jsonify({"status": "error", "message": "No profile_id provided"}), 400

@app.route('/api/profiles/save', methods=['POST'])
def save_profile():
    data = request.json or {}
    profiles = load_all_profiles()
    updated_profile = data.get("profile")
    if not updated_profile:
        return jsonify({"status": "error", "message": "Invalid profile data"}), 400
        
    p_id = updated_profile.get("id")
    found = False
    for idx, p in enumerate(profiles):
        if p.get("id") == p_id:
            profiles[idx] = updated_profile
            found = True
            break
            
    if not found:
        profiles.append(updated_profile)
        
    save_all_profiles(profiles)
    return jsonify({"status": "success", "profile": updated_profile})

# --- MILESTONE MANAGEMENT ---

@app.route('/api/milestones/add', methods=['POST'])
def add_milestone():
    data = request.json or {}
    profile = get_current_profile()
    if not profile:
        return jsonify({"status": "error", "message": "No active profile"}), 400

    new_milestone = {
        "id": f"m_{uuid.uuid4().hex[:8]}",
        "title": data.get("title", "New Significant Milestone"),
        "category": data.get("category", "Leadership & Service"),
        "description": data.get("description", ""),
        "key_takeaways": data.get("key_takeaways", ""),
        "selected": True
    }

    if "life_milestones" not in profile:
        profile["life_milestones"] = []
    profile["life_milestones"].insert(0, new_milestone)

    profiles = load_all_profiles()
    for idx, p in enumerate(profiles):
        if p.get("id") == profile.get("id"):
            profiles[idx] = profile
            break
    save_all_profiles(profiles)

    return jsonify({"status": "success", "milestone": new_milestone, "milestones": profile["life_milestones"]})

@app.route('/api/milestones/update', methods=['POST'])
def update_milestone():
    data = request.json or {}
    milestone_id = data.get("id")
    profile = get_current_profile()
    if not profile or not milestone_id:
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    milestones = profile.get("life_milestones", [])
    found = False
    for m in milestones:
        if m.get("id") == milestone_id:
            if "selected" in data:
                m["selected"] = bool(data["selected"])
            if "title" in data:
                m["title"] = data["title"]
            if "category" in data:
                m["category"] = data["category"]
            if "description" in data:
                m["description"] = data["description"]
            if "key_takeaways" in data:
                m["key_takeaways"] = data["key_takeaways"]
            found = True
            break

    if found:
        profiles = load_all_profiles()
        for idx, p in enumerate(profiles):
            if p.get("id") == profile.get("id"):
                profiles[idx] = profile
                break
        save_all_profiles(profiles)
        return jsonify({"status": "success", "milestones": profile["life_milestones"]})
    return jsonify({"status": "error", "message": "Milestone not found"}), 404

@app.route('/api/milestones/delete', methods=['POST'])
def delete_milestone():
    data = request.json or {}
    milestone_id = data.get("id")
    profile = get_current_profile()
    if not profile or not milestone_id:
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    profile["life_milestones"] = [m for m in profile.get("life_milestones", []) if m.get("id") != milestone_id]
    profiles = load_all_profiles()
    for idx, p in enumerate(profiles):
        if p.get("id") == profile.get("id"):
            profiles[idx] = profile
            break
    save_all_profiles(profiles)

    return jsonify({"status": "success", "milestones": profile["life_milestones"]})

# --- RESUME UPLOAD ---

@app.route('/api/resume/upload', methods=['POST'])
def upload_resume():
    if 'file' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], f"{uuid.uuid4().hex[:6]}_{filename}")
    file.save(filepath)

    parsed_profile, raw_text = parse_uploaded_resume(filepath)
    profile = get_current_profile()

    # Merge parsed info into current profile
    if parsed_profile.get("personal"):
        for k, v in parsed_profile["personal"].items():
            if v and not profile["personal"].get(k):
                profile["personal"][k] = v
    if parsed_profile.get("skills"):
        existing_skills = set(profile.get("skills", []))
        for s in parsed_profile["skills"]:
            existing_skills.add(s)
        profile["skills"] = list(existing_skills)
    if parsed_profile.get("jobs"):
        profile["jobs"] = parsed_profile["jobs"]

    profile["resume_text"] = raw_text

    profiles = load_all_profiles()
    for idx, p in enumerate(profiles):
        if p.get("id") == profile.get("id"):
            profiles[idx] = profile
            break
    save_all_profiles(profiles)

    return jsonify({
        "status": "success",
        "message": f"Successfully parsed and updated profile from {filename}",
        "profile": profile
    })

# --- JOB SEARCH ---

@app.route('/api/jobs/search', methods=['POST'])
def api_search_jobs():
    data = request.json or {}
    keywords = data.get("keywords", "")
    location = data.get("location", "")
    remote_only = data.get("remote_only", False)
    
    results = search_jobs(keywords, location, remote_only)
    profile = get_current_profile()
    
    # Attach ATS match score calculation for each job relative to active profile
    from bot_engine import calculate_match_score, extract_keywords, format_resume_string
    resume_str = format_resume_string(profile) if profile else ""
    
    for job in results:
        kws = job.get("keywords", extract_keywords(job["description"]))
        job["keywords"] = kws
        job["match_score"] = calculate_match_score(resume_str, kws)

    return jsonify({"status": "success", "jobs": results, "count": len(results)})

# --- AI TAILORING WORKSTATION ---

@app.route('/api/tailor', methods=['POST'])
def tailor_documents():
    data = request.json or {}
    job_title = data.get("job_title", "Position")
    company_name = data.get("company_name", "Target Company")
    job_description = data.get("job_description", "")
    
    profile = get_current_profile()
    if not profile:
        return jsonify({"status": "error", "message": "No active profile"}), 400

    # Generate Tailored Cover Letter incorporating Life Milestones
    cover_letter_text = generate_tailored_cover_letter(job_title, company_name, job_description, profile)
    cl_filename = f"CoverLetter_{uuid.uuid4().hex[:6]}.pdf"
    cl_pdf_path = create_pdf(cover_letter_text, f"Cover Letter - {job_title}", cl_filename)

    # Generate Tailored Resume
    tailored_resume_text = generate_tailored_resume(job_title, company_name, job_description, profile)
    res_filename = f"Resume_{uuid.uuid4().hex[:6]}.pdf"
    res_pdf_path = create_pdf(tailored_resume_text, f"Resume - {job_title}", res_filename)

    from bot_engine import extract_keywords, calculate_match_score
    kws = extract_keywords(job_description)
    match_score = calculate_match_score(tailored_resume_text, kws)

    return jsonify({
        "status": "success",
        "job_title": job_title,
        "company_name": company_name,
        "match_score": match_score,
        "keywords": kws,
        "cover_letter_text": cover_letter_text,
        "cover_letter_pdf": cl_filename,
        "resume_text": tailored_resume_text,
        "resume_pdf": res_filename
    })

@app.route('/api/tailored_docs/<filename>')
def serve_tailored_doc(filename):
    return send_from_directory(TAILORED_DOCS_DIR, filename)

# --- BOT CONTROL & TERMINAL ---

@app.route('/api/bot/start', methods=['POST'])
def start_bot():
    data = request.json or {}
    job_ids = data.get("job_ids", [])
    humanizer_settings = data.get("humanizer_settings", {})
    profile = get_current_profile()

    success, msg = global_bot.start_apply_campaign(job_ids, profile, humanizer_settings)
    if success:
        return jsonify({"status": "success", "message": msg})
    else:
        return jsonify({"status": "error", "message": msg}), 400

@app.route('/api/bot/pause', methods=['POST'])
def pause_bot():
    is_paused = global_bot.pause()
    return jsonify({"status": "success", "is_paused": is_paused})

@app.route('/api/bot/stop', methods=['POST'])
def stop_bot():
    global_bot.stop()
    return jsonify({"status": "success", "is_running": False})

@app.route('/api/bot/status', methods=['GET'])
def get_bot_status():
    return jsonify({
        "is_running": global_bot.is_running,
        "is_paused": global_bot.is_paused,
        "current_step": global_bot.current_step,
        "logs": global_bot.logs
    })

@app.route('/api/applications/history', methods=['GET'])
def get_application_history():
    return jsonify({
        "status": "success",
        "applications": global_bot.applications
    })

# --- HANDSHAKE CREDENTIALS & VERIFICATION ---

@app.route('/api/handshake/credentials/save', methods=['POST'])
def save_handshake_credentials():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    portal_url = data.get("portal_url", "https://app.joinhandshake.com/login").strip()

    profile = get_current_profile()
    if not profile:
        return jsonify({"status": "error", "message": "No active profile"}), 400

    profile["handshake_credentials"] = {
        "email": email,
        "password": password,
        "portal_url": portal_url or "https://app.joinhandshake.com/login",
        "connected": bool(email)
    }

    profiles = load_all_profiles()
    for idx, p in enumerate(profiles):
        if p.get("id") == profile.get("id"):
            profiles[idx] = profile
            break
    save_all_profiles(profiles)

    return jsonify({
        "status": "success",
        "message": "Handshake credentials saved successfully",
        "handshake_credentials": profile["handshake_credentials"]
    })

@app.route('/api/handshake/verify', methods=['POST'])
def verify_handshake():
    data = request.json or {}
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    portal_url = data.get("portal_url", "https://app.joinhandshake.com/login").strip()

    from bot_engine import verify_handshake_login
    success, msg = verify_handshake_login(email, password, portal_url)

    profile = get_current_profile()
    if profile:
        profile["handshake_credentials"] = {
            "email": email,
            "password": password,
            "portal_url": portal_url,
            "connected": success
        }
        profiles = load_all_profiles()
        for idx, p in enumerate(profiles):
            if p.get("id") == profile.get("id"):
                profiles[idx] = profile
                break
        save_all_profiles(profiles)

    return jsonify({
        "status": "success" if success else "error",
        "connected": success,
        "message": msg
    })

if __name__ == '__main__':
    print("Starting Handshake Auto Apply Server on http://0.0.0.0:5000 ...")
    app.run(host='0.0.0.0', port=5000, debug=True)
