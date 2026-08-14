import warnings
warnings.filterwarnings("ignore", category=FutureWarning)

import time
import os
import random
import re
import sys
import select
import threading
from datetime import datetime
from collections import Counter
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
import google.generativeai as genai
from fpdf import FPDF


# ==============================
# PAUSE / UNPAUSE SYSTEM
# ==============================
# Press 'p' + Enter in terminal to pause/unpause at any time

paused = False
pause_lock = threading.Lock()


def pause_listener():
    """Background thread that listens for 'p' to toggle pause."""
    global paused
    while True:
        try:
            user_input = input()
            if user_input.strip().lower() == 'p':
                with pause_lock:
                    paused = not paused
                if paused:
                    print("\n" + "=" * 50)
                    print("  *** PAUSED — Press 'p' + Enter to resume ***")
                    print("  (Do what you need to do manually)")
                    print("=" * 50)
                else:
                    print("\n" + "=" * 50)
                    print("  *** RESUMED — Bot continuing... ***")
                    print("=" * 50)
        except EOFError:
            break
        except Exception:
            pass


def check_pause():
    """Call this throughout the bot to respect pause state."""
    while paused:
        time.sleep(0.5)

# --- GEMINI API ---
GEMINI_API_KEY = "AIzaSyC9w2M84ZmVtBIq5luLpNv0tcRZzLf8KK8"
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-1.5-flash")

# --- LOAD USER PROFILE FROM JSON ---
import json as json_mod

PROFILES_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "profiles.json"),
    "/home/admin/indeed/profiles.json",
    "/home/admin/sn_bot_app/profiles.json"
]
PROFILE_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "profile.json"),
    "/home/admin/indeed/profile.json"
]

def load_profile():
    """Load user profile from JSON. Supports multi-profile selection."""
    for path in PROFILES_PATHS:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    profiles = json_mod.load(f)
                if isinstance(profiles, list) and len(profiles) > 0:
                    real_profiles = [p for p in profiles 
                                  if p.get("personal", {}).get("first_name", "").strip() 
                                  and "TEMPLATE" not in p.get("profile_name", "").upper()]
                    if len(real_profiles) == 1:
                        chosen = real_profiles[0]
                        name = chosen.get("profile_name", f"{chosen['personal'].get('first_name','')} {chosen['personal'].get('last_name','')}")
                        print(f"\n  Loaded profile: {name}")
                        return chosen
                    elif len(real_profiles) > 1:
                        # If imported as a module or non-interactive, default to first profile
                        if __name__ != "__main__" or not sys.stdin.isatty():
                            chosen = real_profiles[0]
                            name = chosen.get("profile_name", f"{chosen['personal'].get('first_name','')} {chosen['personal'].get('last_name','')}")
                            print(f"\n  Loaded profile (default): {name}")
                            return chosen
                        print("\n" + "=" * 50)
                        print("  SELECT A PROFILE")
                        print("=" * 50)
                        for i, prof in enumerate(real_profiles):
                            name = prof.get("profile_name", 
                                f"{prof['personal'].get('first_name','')} {prof['personal'].get('last_name','')}")
                            role = prof.get("experience", {}).get("current_role", "")
                            city = prof.get("personal", {}).get("city", "")
                            print(f"  [{i + 1}] {name} — {role}, {city}")
                        print("=" * 50)
                        while True:
                            try:
                                choice = input(f"\n  Enter number (1-{len(real_profiles)}): ").strip()
                                idx = int(choice) - 1
                                if 0 <= idx < len(real_profiles):
                                    chosen = real_profiles[idx]
                                    name = chosen.get("profile_name", 
                                        f"{chosen['personal'].get('first_name','')} {chosen['personal'].get('last_name','')}")
                                    print(f"\n  Selected: {name}")
                                    return chosen
                                else:
                                    print(f"  Please enter a number between 1 and {len(real_profiles)}")
                            except ValueError:
                                print(f"  Please enter a number between 1 and {len(real_profiles)}")
                            except (EOFError, KeyboardInterrupt):
                                print("\n  Defaulting to first profile.")
                                return real_profiles[0]
            except Exception:
                continue

    for path in PROFILE_PATHS:
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    profile = json_mod.load(f)
                if isinstance(profile, list):
                    profile = profile[0]
                name = profile.get("profile_name",
                    f"{profile['personal'].get('first_name','')} {profile['personal'].get('last_name','')}")
                print(f"\n  Loaded profile: {name}")
                return profile
            except Exception:
                continue

    print("\n  WARNING: No profile file found! Profile initialized to empty dict.")
    return {}

PROFILE = load_profile()

# Shortcut accessors
def p(section, key, default=""):
    """Quick profile lookup: p('personal', 'first_name')"""
    return PROFILE.get(section, {}).get(key, default)

def full_name():
    return f"{p('personal','first_name')} {p('personal','last_name')}"

def skill_years(skill_name):
    """Get years of experience for a skill."""
    mapping = PROFILE.get("experience", {}).get("skill_years", {})
    return mapping.get(skill_name.lower(), mapping.get("default", 3))

def candidate_info_block():
    """Build the candidate info string for AI prompts."""
    pr = PROFILE
    pe = pr["personal"]
    wa = pr["work_authorization"]
    sc = pr.get("security_clearance", {})
    mi = pr["military"]
    ex = pr["experience"]
    pf = pr["preferences"]
    sd = pr["screening_defaults"]

    edu_lines = []
    for ed in pr.get("education", []):
        status = " (current)" if ed.get("current") else ""
        edu_lines.append(f"{ed['degree']} {ed['field']}, {ed['school']} ({ed['year']}){status}")

    return f"""- Name: {full_name()} | Email: {pe['email']} | Phone: {pe['phone']}
- Location: {pe['address']} | Citizen: {'Yes' if wa['us_citizen'] else 'No'}
- Work Auth: {'Yes' if wa['authorized_to_work'] else 'No'} | Sponsorship: {'No' if not wa['sponsorship_needed'] else 'Yes'}
- Citizenship answer: {wa.get('citizenship_answer', 'US Citizen')}
- Veteran: {'Yes' if mi.get('veteran') else 'No'} ({mi.get('branch', '')} {mi.get('years_served', '')})
- Experience: {ex['total_years']}+ years | Current: {ex['current_role']} at {ex['current_company']}
- Education: {'; '.join(edu_lines)}
- Skills: {', '.join(pr.get('skills', [])[:15])}
- Available: {ex.get('available_start', '2 weeks')} | Salary: {pf.get('salary_answer', 'negotiable')} ({pf.get('salary', 'negotiable')})
- Willing: {'remote, ' if pf.get('willing_remote') else ''}{'hybrid, ' if pf.get('willing_hybrid') else ''}{'on-site' if pf.get('willing_onsite') else ''}
- Relocate: {'Yes' if pf.get('willing_to_relocate') else 'No'} {pf.get('relocation_area', '')}
- Employee of applied company: {'No' if sd.get('employee_of_company') == False else 'Yes'}
- How heard: {pf.get('how_heard', 'Indeed')}
- Background check/drug test: {'Yes' if sd.get('background_check_ok') else 'No'}
- Criminal history: {'No' if not sd.get('criminal_history') else 'Yes'}
- Security Clearance: {sc.get('level', 'None')}{' (Active)' if sc.get('active') else ''}{' with Polygraph' if sc.get('polygraph') else ''}{' - ' + sc.get('notes', '') if sc.get('notes') else ''}
- Disability: {sd.get('disability', 'Prefer not to answer')}
- Gender: {sd.get('gender', 'Prefer not to answer')}
- Race/Ethnicity: {sd.get('race_ethnicity', 'Other')}"""

# --- TOKEN TRACKING ---
total_tokens_used = 0
total_applied = 0

CURRENT_USER_DATA = {
    "full_resume": None,
    "resume_summary": None,
    "name": None,
    "contact": None
}

# --- TEST MODE ---
# Set to True to generate docs but NOT click Submit
# Set to False to go live
TEST_MODE = False
SKIP_COOLDOWN = True  # Set True to skip the 3-7 min wait between applications
MAX_UNANSWERED_SKIP = 3  # Skip job if this many questions can't be answered on a single page

def test_gemini_api_key(api_key, model_name="gemini-1.5-flash"):
    """Test if a given Gemini API Key is valid and working."""
    if not api_key or not api_key.strip():
        return False, "API Key is empty."

    cleaned_key = api_key.strip()

    # 1. Try modern google.genai SDK
    try:
        from google import genai as modern_genai
        client = modern_genai.Client(api_key=cleaned_key)
        res = client.models.generate_content(model=model_name, contents="Hello")
        if res and res.text:
            return True, f"API Key is valid! Connected to {model_name}."
    except Exception as e1:
        err_str = str(e1)
        if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
            return False, "Invalid API Key. Please enter a valid key from Google AI Studio (aistudio.google.com)."
        
        # 2. Try legacy google.generativeai fallback
        try:
            genai.configure(api_key=cleaned_key)
            test_model = genai.GenerativeModel(model_name)
            res = test_model.generate_content("Hello", generation_config={"max_output_tokens": 5})
            if res and res.text:
                return True, f"API Key is valid! Connected to {model_name}."
        except Exception as e2:
            return False, f"API Key test failed: {e1}"

    return False, "No response returned from Gemini API."

def extract_text_from_file(uploaded_file):
    """Extract plain text from uploaded file (.pdf, .docx, .doc, .txt)."""
    if uploaded_file is None:
        return ""

    filename = uploaded_file.name.lower()

    if filename.endswith(".txt"):
        try:
            return uploaded_file.read().decode("utf-8", errors="ignore")
        except Exception as e:
            return f"Error reading TXT file: {e}"

    elif filename.endswith(".pdf"):
        try:
            import pypdf
            reader = pypdf.PdfReader(uploaded_file)
            text_parts = [page.extract_text() for page in reader.pages if page.extract_text()]
            return "\n\n".join(text_parts)
        except Exception as e:
            return f"Error reading PDF file: {e}"

    elif filename.endswith(".docx") or filename.endswith(".doc"):
        try:
            import docx
            doc = docx.Document(uploaded_file)
            paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]
            return "\n".join(paragraphs)
        except Exception as e:
            try:
                uploaded_file.seek(0)
                raw_bytes = uploaded_file.read()
                ascii_text = "".join(chr(b) if 32 <= b <= 126 or b in (10, 13, 9) else " " for b in raw_bytes)
                cleaned = "\n".join(line.strip() for line in ascii_text.splitlines() if len(line.strip()) > 3)
                if len(cleaned) > 50:
                    return cleaned
                return f"Could not parse binary .doc file. Please save/convert to .docx or .pdf."
            except Exception:
                return f"Error reading DOCX/DOC file: {e}"

    return ""

def generate_summary_from_resume(full_resume_text, api_key, model_name="gemini-1.5-flash"):
    """Generate a concise resume summary using Gemini API."""
    if not full_resume_text or len(full_resume_text.strip()) < 20:
        return False, "Full Resume text is empty or too short."
    if not api_key:
        return False, "Gemini API Key is required."

    prompt = (
        "You are an expert executive resume writer. Based on the full resume below, "
        "create a high-impact, 1-paragraph summary highlighting key roles, education, core skills, "
        "and total years of experience.\n\n"
        f"FULL RESUME:\n{full_resume_text}\n\n"
        "RESUME SUMMARY:"
    )
    try:
        genai.configure(api_key=api_key.strip())
        summary_model = genai.GenerativeModel(model_name)
        resp = summary_model.generate_content(prompt)
        if resp and resp.text:
            return True, resp.text.strip()
        return False, "Gemini returned empty text."
    except Exception as e:
        return False, f"Failed to generate summary: {e}"


def get_user_name(profile=None):
    pr = profile if profile is not None else PROFILE
    pe = pr.get("personal", {}) if pr else {}
    return f"{pe.get('first_name', '')} {pe.get('last_name', '')}".strip()

def get_user_contact(profile=None):
    pr = profile if profile is not None else PROFILE
    pe = pr.get("personal", {}) if pr else {}
    city = pe.get("city", "")
    state = pe.get("state", "")
    email = pe.get("email", "")
    phone = pe.get("phone", "")
    loc = f"{city}, {state}".strip(", ")
    parts = [p for p in [loc, email, phone] if p]
    return " | ".join(parts)

# --- FULL RESUME DATA (auto-generated from profile.json, used by Gemini to tailor) ---
def _build_full_resume(profile=None):
    pr = profile if profile is not None else PROFILE
    if not pr:
        return "" 
    pe = pr["personal"]
    lines = [f"{pr.get('personal',{}).get('first_name','')} {pr.get('personal',{}).get('last_name','')}".strip()]
    lines.append(f"{pe.get('city','')}, {pe.get('state','')} | {pe.get('phone','')} | {pe.get('email','')}")
    lines.append("")
    lines.append("EDUCATION:")
    for ed in pr.get("education", []):
        status = " (current)" if ed.get("current") else ""
        lines.append(f"- {ed['degree']}, {ed['field']}, {ed['school']} ({ed['year']}){status}")
    lines.append("")
    lines.append("PROFESSIONAL EXPERIENCE:")
    for job in pr.get("jobs", []):
        lines.append(f"\n{job['title']}, {job['company']}, {job.get('location','')} ({job['dates']}):")
        for b in job.get("bullets", []):
            lines.append(f"- {b}")
    lines.append("")
    lines.append("SKILLS:")
    lines.append(", ".join(pr.get("skills", [])))

    # Only include clearance if person actually has one
    sc = pr.get("security_clearance", {})
    if sc.get("has_clearance") and sc.get("level", "None") != "None":
        lines.append("")
        active_str = " (Active)" if sc.get("active") else " (Inactive)"
        poly_str = " with Polygraph" if sc.get("polygraph") else ""
        lines.append(f"SECURITY CLEARANCE: {sc['level']}{active_str}{poly_str}")

    # Military if veteran
    mi = pr.get("military", {})
    if mi.get("veteran"):
        lines.append("")
        lines.append(f"MILITARY: {mi.get('branch', '')} - {mi.get('rank', '')} ({mi.get('years_served', '')})")

    return "\n".join(lines)

def _build_resume_summary(profile=None):
    pr = profile if profile is not None else PROFILE
    if not pr:
        return "" 
    pe = pr["personal"]
    fn = f"{pr.get('personal',{}).get('first_name','')} {pr.get('personal',{}).get('last_name','')}".strip()
    lines = [f"{fn} | {pe.get('city','')}, {pe.get('state','')} | {pe.get('phone','')} | {pe.get('email','')}"]
    lines.append("")
    lines.append("EDUCATION:")
    for ed in pr.get("education", []):
        lines.append(f"- {ed['degree']} {ed['field']}, {ed['school']} ({ed['year']})")
    lines.append("")
    lines.append("EXPERIENCE:")
    for job in pr.get("jobs", []):
        bullets_short = ". ".join(job.get("bullets", [])[:2])
        lines.append(f"- {job['title']}, {job['company']} ({job['dates']}): {bullets_short}")
    lines.append("")
    lines.append(f"SKILLS: {', '.join(pr.get('skills', []))}")
    # Add resume_text if provided (extra context)
    rt = pr.get("resume_text", "")
    if rt:
        lines.append(f"\nSUMMARY: {rt}")
    return "\n".join(lines)

# FULL_RESUME and RESUME_SUMMARY globals removed in favor of parameterized functions

# --- BROWSER CONFIG ---
options = Options()
options.add_argument('--no-sandbox')
options.add_argument('--disable-dev-shm-usage')
options.add_argument('--disable-blink-features=AutomationControlled')
# Persistent profile: saves login cookies so you don't re-login every run
CHROME_PROFILE_DIR = os.path.expanduser("~/indeed_chrome_profile")
options.add_argument(f'--user-data-dir={CHROME_PROFILE_DIR}')
options.add_argument('--profile-directory=Default')
options.add_experimental_option("excludeSwitches", ["enable-automation"])
options.add_experimental_option('useAutomationExtension', False)
service = Service('/usr/bin/chromedriver')
driver = webdriver.Chrome(service=service, options=options)
driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
    'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
})
wait = WebDriverWait(driver, 15)

# --- OUTPUT FOLDERS (per-profile) ---
_profile_slug = f"{p('personal','first_name')}_{p('personal','last_name')}".lower().replace(" ", "_")
COVER_LETTER_DIR = os.path.expanduser(f"~/{_profile_slug}_indeed_cover_letters")
RESUME_DIR = os.path.expanduser(f"~/{_profile_slug}_indeed_resumes")
LOG_FILE = f"{_profile_slug}_indeed_log.txt"
os.makedirs(COVER_LETTER_DIR, exist_ok=True)
os.makedirs(RESUME_DIR, exist_ok=True)


# ==============================
# STEALTH FUNCTIONS
# ==============================

def human_delay(min_sec=2, max_sec=5):
    check_pause()
    delay = random.uniform(min_sec, max_sec)
    print(f"  (human pause: {delay:.1f}s)")
    time.sleep(delay)
    check_pause()


def job_cooldown():
    check_pause()
    if SKIP_COOLDOWN:
        print(f"\n  *** Cooldown SKIPPED (SKIP_COOLDOWN=True) ***")
        human_delay(2, 5)  # Still wait a few seconds to not look insane
        return
    wait_minutes = random.uniform(3, 7)
    wait_seconds = wait_minutes * 60
    now = datetime.now().strftime('%H:%M:%S')
    print(f"\n  *** Cooling down for {wait_minutes:.1f} minutes... ***")
    print(f"  *** (Started at {now}) ***")
    print(f"  *** Press 'p' + Enter to pause if needed ***")
    elapsed = 0
    while elapsed < wait_seconds:
        check_pause()
        chunk = min(5, wait_seconds - elapsed)
        time.sleep(chunk)
        elapsed += chunk


def stealth_click(element):
    """Click an element, forcing it into view first, with JS fallback."""
    # 1. Force scroll to element first
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.3)
    except Exception:
        pass

    # 2. Try human-like ActionChains click
    try:
        action = ActionChains(driver)
        x_off = random.randint(-3, 3)
        y_off = random.randint(-3, 3)
        action.move_to_element_with_offset(element, x_off, y_off)
        action.click()
        action.perform()
    except Exception:
        # 3. Fallback: basic Selenium click
        try:
            element.click()
        except Exception:
            # 4. Nuclear: JS click (bypasses visibility/overlay blockers)
            driver.execute_script("arguments[0].click();", element)


def smooth_scroll(pixels):
    steps = random.randint(3, 6)
    per_step = pixels // steps
    for _ in range(steps):
        driver.execute_script(f"window.scrollBy(0, {per_step})")
        time.sleep(random.uniform(0.1, 0.3))


def stealth_type(element, text):
    """Type text character by character, bypassing React state issues."""
    try:
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
        time.sleep(0.2)
        element.click()
        
        # Select all + delete (better than .clear() for React)
        element.send_keys(Keys.CONTROL + "a")
        element.send_keys(Keys.DELETE)
        time.sleep(0.2)
        
        for char in text:
            element.send_keys(char)
            time.sleep(random.uniform(0.03, 0.12))
            
        # Trigger React's onChange by dispatching native events
        driver.execute_script(
            "arguments[0].dispatchEvent(new Event('input', { bubbles: true }));"
            "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));", 
            element
        )
    except Exception as e:
        print(f"      [!] Error typing: {e}")


# ==============================
# LOGGING
# ==============================

def log_application(status, match_score=None, keywords_found=None, keywords_total=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    score_str = ""
    if match_score is not None:
        score_str = f" [ATS Match: {match_score}%"
        if keywords_found is not None and keywords_total is not None:
            score_str += f" ({keywords_found}/{keywords_total} keywords)"
        score_str += "]"
    with open(LOG_FILE, "a") as f:
        f.write(f"{timestamp} - {status}{score_str}\n")


# ==============================
# ATS KEYWORD ENGINE
# ==============================

STOP_WORDS = set("""
a an the and or but in on at to for of is it its are was were be been being
have has had do does did will would shall should may might can could this that
these those i me my we our you your he she they them their him her with from
by as not no nor so if then than also very just about above after again all
any both each few more most other some such only own same too up down out off
over under between through during before into back how what which who whom
where when why there here how much many well still even must need get got make
made let us like new work job will role team company position looking working
able including include ability experience required requirements qualifications
looking seeking join responsible responsibilities description summary apply
application please ensure ensure providing provide strong preferred minimum
years year within across including candidate candidates opportunity equal
employer employment status ideal similar tools managing plus
posted ago deadline expires days left applicants views share save report
weeks months hours minutes pm am est edt pst cdt time date january february
march april may june july august september october november december
monday tuesday wednesday thursday friday saturday sunday
involves requires requiring handling tasks
salary hourly rate compensation pay wage per hour hr wk week
""".split())

SKILL_BOOSTERS = set("""
python java javascript sql nosql aws azure gcp docker kubernetes terraform
ansible jenkins git github ci cd devops agile scrum kanban jira confluence
react angular vue node express django flask spring rest api graphql
microservices serverless cloud etl informatica oracle pl-sql mysql postgres
mongodb redis kafka spark hadoop airflow databricks snowflake tableau
power bi microstrategy excel sas spss matlab r cuda c++ grpc tensorflow
pytorch machine learning deep learning nlp data science data engineering
data analysis analytics project management product management leadership
cybersecurity compliance hipaa pci gdpr risk assessment penetration testing
public health epidemiology biostatistics health policy addiction substance
harm reduction clinical research grant writing nih cdc fda regulatory
""".split())


def extract_keywords(jd_text, top_n=15):
    """Extract top keywords from job description for ATS matching."""
    text = jd_text.lower()
    sentences = re.split(r'[.,;:\n]+', text)

    all_singles = []
    all_bigrams = []
    all_trigrams = []

    for sentence in sentences:
        clean = re.sub(r'[^a-z0-9\s\+\#\-]', ' ', sentence)
        clean = re.sub(r'\s+', ' ', clean).strip()
        words = clean.split()

        for w in words:
            if w not in STOP_WORDS and len(w) > 2:
                all_singles.append(w)

        for i in range(len(words) - 1):
            w1, w2 = words[i], words[i+1]
            if w1 not in STOP_WORDS and w2 not in STOP_WORDS and len(w1) > 1 and len(w2) > 1:
                all_bigrams.append(f"{w1} {w2}")

        for i in range(len(words) - 2):
            w1, w2, w3 = words[i], words[i+1], words[i+2]
            if w1 not in STOP_WORDS and w3 not in STOP_WORDS and len(w1) > 1 and len(w3) > 1:
                all_trigrams.append(f"{w1} {w2} {w3}")

    word_counts = Counter(all_singles)
    bigram_counts = Counter(all_bigrams)
    trigram_counts = Counter(all_trigrams)

    scored = {}
    for word, count in word_counts.items():
        score = count
        if word in SKILL_BOOSTERS:
            score *= 3
        if len(word) > 5:
            score *= 1.2
        scored[word] = score

    for phrase, count in bigram_counts.items():
        score = count * 2
        if any(w in SKILL_BOOSTERS for w in phrase.split()):
            score *= 2.5
        scored[phrase] = score

    for phrase, count in trigram_counts.items():
        score = count * 2.5
        if any(w in SKILL_BOOSTERS for w in phrase.split()):
            score *= 2
        scored[phrase] = score

    sorted_keywords = sorted(scored.items(), key=lambda x: x[1], reverse=True)

    final = []
    seen_words = set()
    for kw, score in sorted_keywords:
        kw_words = set(kw.split())
        if kw_words.issubset(seen_words) and len(kw.split()) == 1:
            continue
        final.append(kw)
        seen_words.update(kw_words)
        if len(final) >= top_n:
            break

    return final


def calculate_match_score(document_text, target_keywords):
    """Calculate what % of target keywords made it into the final document."""
    if not target_keywords:
        return 0, 0, 0, []

    found = []
    missed = []

    for kw in target_keywords:
        pattern = re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
        if pattern.search(document_text):
            found.append(kw)
        else:
            missed.append(kw)

    score = (len(found) / len(target_keywords)) * 100
    return round(score, 1), len(found), len(target_keywords), missed


def strip_formatting(text):
    """Remove any bold/markdown formatting that Gemini might add."""
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'`(.+?)`', r'\1', text)  # Remove backtick/code formatting
    text = re.sub(r'^#{1,3}\s*', '', text, flags=re.MULTILINE)
    return text


# ==============================
# GEMINI API
# ==============================

def call_gemini(prompt, model_name=None, api_key=None):
    """Shared Gemini API call supporting both google.genai and legacy google.generativeai."""
    global total_tokens_used, CURRENT_USER_DATA

    target_model = model_name or CURRENT_USER_DATA.get("model_name") or "gemini-1.5-flash"
    target_key = api_key or CURRENT_USER_DATA.get("api_key") or GEMINI_API_KEY

    max_retries = 3
    for attempt in range(max_retries):
        try:
            # 1. Try modern google.genai SDK
            try:
                from google import genai as modern_genai
                client = modern_genai.Client(api_key=target_key.strip())
                response = client.models.generate_content(
                    model=target_model,
                    contents=prompt
                )
                if response and response.text:
                    tokens = getattr(getattr(response, 'usage_metadata', None), 'total_token_count', 1000)
                    total_tokens_used += tokens
                    print(f"  Tokens: {tokens} | Running total: {total_tokens_used}")
                    time.sleep(2)
                    return response.text
            except Exception as e_new:
                err_str = str(e_new)
                if "API_KEY_INVALID" in err_str or "API key not valid" in err_str:
                    print(f"  Gemini API error: Invalid API Key provided.")
                    return None

            # 2. Fallback to legacy google.generativeai SDK
            genai.configure(api_key=target_key.strip())
            legacy_model = genai.GenerativeModel(target_model)
            response = legacy_model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            text = response.text
            tokens = getattr(getattr(response, 'usage_metadata', None), 'total_token_count', 1000)
            total_tokens_used += tokens
            print(f"  Tokens: {tokens} | Running total: {total_tokens_used}")
            time.sleep(2)
            return text

        except Exception as e:
            error_msg = str(e)
            if "429" in error_msg or "quota" in error_msg.lower():
                wait_time = 5 * (attempt + 1)
                print(f"  Rate limited. Waiting {wait_time}s... ({attempt+1}/{max_retries})")
                time.sleep(wait_time)
            else:
                print(f"  Gemini API error: {e}")
                return None
    print("  Max retries reached.")
    return None


# ==============================
# INDEED JOB SCRAPER
# ==============================

def get_indeed_job_description():
    """Scrape the job description from Indeed's RIGHT pane (split-pane layout)."""
    jd_text = ""

    # Target the right pane's job description area
    # From DOM inspection: jobsearch-embeddedBody, jobDescriptionText, etc.
    selectors = [
        "div[data-hook='job-description']",
        "div[class*='style__description']",
        "div[class*='description']",
        "div[class*='Description']",
        "div#jobDescriptionText",
        "div.jobsearch-jobDescriptionText",
        "div.jobsearch-embeddedBody",
        "div[class*='jobDescription']",
        "div.jobsearch-JobComponent-description",
        "div[id*='jobDescription']",
        "div.jobsearch-RightPane div[class*='description']",
        "div.jobsearch-ViewJobLayout div[class*='description']",
        "div#jobsearch-ViewJobPaneWrapper",
    ]

    for selector in selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, selector)
            jd_text = el.text
            if len(jd_text) > 50:
                print(f"  Scraped JD from: {selector} ({len(jd_text)} chars)")
                break
        except Exception:
            continue

    # Fallback: grab entire right pane
    if len(jd_text) < 50:
        for fallback in ["div.jobsearch-RightPane", "div.jobsearch-ViewJobLayout", "div.jobsearch-JobComponent"]:
            try:
                body = driver.find_element(By.CSS_SELECTOR, fallback)
                jd_text = body.text
                if len(jd_text) > 50:
                    print(f"  Scraped JD from: {fallback} (fallback, {len(jd_text)} chars)")
                    break
            except Exception:
                continue

    if len(jd_text) < 50:
        return ""

    # Clean metadata
    lines = jd_text.split('\n')
    clean_lines = []
    for line in lines:
        lower = line.lower().strip()
        if any(skip in lower for skip in [
            'posted', 'ago', 'days left', 'applicants', 'views',
            'save this job', 'report job', 'similar jobs', 'back to search',
            'apply now', 'urgently hiring', 'responsive employer',
            'how often', 'notifications', 'sign up', 'log in',
            'not interested', 'let employers find you',
            'indeed rating', 'company rating', 'reviews',
            'profile insights', 'here\'s how the job',
            'do you have experience', 'easily apply',
            'sponsor your job', 'employers, reach',
        ]):
            continue
        if len(lower) < 3:
            continue
        if re.match(r'^(january|february|march|april|may|june|july|august|september|october|november|december)\s+\d', lower):
            continue
        # Skip Yes/No/Skip buttons text
        if lower in ['yes', 'no', 'skip']:
            continue
        clean_lines.append(line)

    cleaned = '\n'.join(clean_lines)
    return cleaned[:3000]


def get_indeed_metadata():
    """Extract job metadata from Indeed's right pane."""
    metadata = {}

    # Job title - from the right pane header
    title_selectors = [
        "div.jobsearch-HeaderContainer h2",
        "h2.jobsearch-JobInfoHeader-title",
        "h1.jobsearch-JobInfoHeader-title",
        "div.jobsearch-InfoHeaderContainer h2",
        "h2[class*='JobTitle']",
        "h1[class*='JobTitle']",
        # Fallback from the embedded view
        "div.fastviewjob h2",
        "div.jobsearch-ViewJobLayout h2",
    ]
    for sel in title_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text and len(text) > 2:
                metadata['title'] = text
                break
        except Exception:
            continue

    # Company name
    company_selectors = [
        "div[data-testid='inlineHeader-companyName'] a",
        "div.jobsearch-InlineCompanyRating a",
        "span[data-testid='company-name']",
        "div.jobsearch-HeaderContainer a[data-tn-element='companyName']",
        # From screenshot: company link near the top
        "div.jobsearch-InfoHeaderContainer a",
    ]
    for sel in company_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text and len(text) > 1:
                metadata['company'] = text
                break
        except Exception:
            continue

    # Location
    location_selectors = [
        "div[data-testid='inlineHeader-companyLocation']",
        "div[data-testid='job-location']",
        "div.jobsearch-InlineCompanyRating + div",
        "div.jobsearch-InfoHeaderContainer div:nth-child(2)",
    ]
    for sel in location_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            text = el.text.strip()
            if text and len(text) > 3 and not text.startswith('$'):
                metadata['location'] = text
                break
        except Exception:
            continue

    # Salary - from screenshot: div#salaryInfoAndJobType
    try:
        salary_el = driver.find_element(By.CSS_SELECTOR, "div#salaryInfoAndJobType")
        metadata['salary'] = salary_el.text.strip()
    except Exception:
        pass

    return metadata


# ==============================
# INDEED APPLY BUTTON DETECTION
# ==============================

def _get_indeed_apply_selectors():
    """Apply button selectors — Handshake and Indeed."""
    return [
        ("CSS", "button[aria-label*='Apply']"),
        ("CSS", "button[aria-label*='apply']"),
        ("CSS", "button[data-hook*='apply']"),
        ("CSS", "button[class*='apply']"),
        ("CSS", ".ia-IndeedApplyButton"),
        ("CSS", "button.ia-IndeedApplyButton"),
        ("CSS", "div.jobsearch-IndeedApplyButton-contentWrapper"),
        ("CSS", "button#indeedApplyButton"),
        ("CSS", "button.indeed-apply-button"),
        ("XPATH", "//button[contains(text(),'Apply')]"),
        ("XPATH", "//button[contains(text(),'Quick Apply')]"),
        ("XPATH", "//button[contains(text(),'Apply now')]"),
        ("XPATH", "//a[contains(text(),'Apply')]"),
        ("XPATH", "//a[contains(text(),'Quick Apply')]"),
    ]


def has_easy_apply():
    """Check if this job has Handshake or Indeed Easy Apply (not external apply)."""
    current_url = driver.current_url.lower()

    # Handshake Apply check
    if 'joinhandshake.com' in current_url:
        for sel in ["button[aria-label*='Apply']", "button[data-hook*='apply']", "button[class*='apply']", "a[href*='apply']"]:
            try:
                for btn in driver.find_elements(By.CSS_SELECTOR, sel):
                    if btn.is_displayed():
                        text = (btn.text or "").lower().strip()
                        if "external" in text or "company site" in text:
                            continue
                        return True
            except Exception:
                continue
        for xpath in ["//button[contains(text(),'Apply')]", "//button[contains(text(),'Quick Apply')]", "//a[contains(text(),'Apply')]"]:
            try:
                for btn in driver.find_elements(By.XPATH, xpath):
                    if btn.is_displayed():
                        text = (btn.text or "").lower().strip()
                        if "external" in text or "company site" in text:
                            continue
                        return True
            except Exception:
                continue

    # On full-page /viewjob, button may be below fold
    if '/viewjob' in current_url:
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
            time.sleep(0.5)
        except Exception:
            pass

    for sel_type, sel in _get_indeed_apply_selectors():
        try:
            by = By.CSS_SELECTOR if sel_type == "CSS" else By.XPATH
            elements = driver.find_elements(by, sel)
            for btn in elements:
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.3)
                except Exception:
                    pass
                btn_id = btn.get_attribute("id") or ""
                if btn.is_displayed() or btn_id == "indeedApplyButton":
                    btn_text = (btn.text or "").lower().strip()
                    if "company site" in btn_text or "external" in btn_text:
                        print(f"  External apply: '{btn_text}' — skipping")
                        return False
                    return True
        except Exception:
            continue

    return False


def click_apply_button():
    """Click the Indeed Apply button. Handles new tab OR iframe modal.
    
    FIXES APPLIED:
    - Scrolls down to find button (on full-page /viewjob, Apply is at bottom)
    - Checks both <button> AND <a> tags (Indeed uses both)
    - Waits up to 5s for new tab to spawn (race condition fix)
    """
    old_handles = set(driver.window_handles)
    num_old_handles = len(old_handles)

    # Handshake Apply Click Handler
    if 'joinhandshake.com' in driver.current_url.lower():
        hs_apply_selectors = [
            "button[aria-label*='Apply']",
            "button[aria-label*='apply']",
            "button[data-hook*='apply']",
            "button[class*='apply']",
            "a[href*='apply']",
            "//button[contains(text(),'Apply')]",
            "//button[contains(text(),'Quick Apply')]",
            "//a[contains(text(),'Apply')]"
        ]
        for sel in hs_apply_selectors:
            try:
                by = By.XPATH if sel.startswith("//") else By.CSS_SELECTOR
                btns = driver.find_elements(by, sel)
                for btn in btns:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.3)
                        stealth_click(btn)
                        print("  Clicked Handshake Apply button.")
                        time.sleep(2)
                        return "same_page"
            except Exception:
                continue

    # EARLY CHECK: Are we already on SmartApply? (Indeed sometimes auto-opens it)
    current = driver.current_url.lower()
    if 'smartapply' in current or 'indeedapply' in current:
        print(f"  Already on SmartApply! URL: {current[:80]}")
        return "same_page"
    
    # Check if SmartApply opened in another tab during doc generation
    original_handle = driver.current_window_handle
    for handle in driver.window_handles:
        if handle == original_handle:
            continue
        try:
            driver.switch_to.window(handle)
            tab_url = driver.current_url.lower()
            if 'smartapply' in tab_url or 'indeedapply' in tab_url:
                print(f"  Found SmartApply in another tab: {tab_url[:80]}")
                return "new_tab"
        except Exception:
            continue
    # Switch back to original tab if no SmartApply found
    try:
        driver.switch_to.window(original_handle)
    except Exception:
        pass

    # On full-page /viewjob, Apply button is at the bottom — scroll to find it
    if '/viewjob' in driver.current_url:
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.7);")
            time.sleep(1)
        except Exception:
            pass

    # Extended selectors: include <a> tags (full-page view uses anchor, not button)
    all_selectors = list(_get_indeed_apply_selectors()) + [
        ("XPATH", "//a[contains(text(),'Apply now')]"),
        ("XPATH", "//a[contains(@class,'IndeedApply')]"),
        ("XPATH", "//a[contains(@href,'indeedapply')]"),
        ("CSS", "a.indeed-apply-button"),
        ("CSS", "a[data-style='indeed-apply-button']"),
        ("CSS", "a.jobsearch-IndeedApplyButton-newDesign"),
    ]

    for sel_type, sel in all_selectors:
        try:
            by = By.CSS_SELECTOR if sel_type == "CSS" else By.XPATH
            elements = driver.find_elements(by, sel)
            for btn in elements:
                # CRITICAL: Scroll to element BEFORE checking visibility
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.5)
                except Exception:
                    pass

                # Check visibility OR known Apply button ID (bypass visibility check)
                btn_id = btn.get_attribute("id") or ""
                if btn.is_displayed() or btn_id == "indeedApplyButton":
                    btn_text = (btn.text or btn.get_attribute("aria-label") or "").lower().strip()
                    if "company site" in btn_text:
                        continue

                    stealth_click(btn)
                    print(f"  Clicked Apply: '{btn.text.strip() or 'Apply now'}'")

                    # CRITICAL: Wait up to 5 seconds for new tab to actually open
                    try:
                        WebDriverWait(driver, 5).until(
                            lambda d: len(d.window_handles) > num_old_handles
                        )
                        new_handles = set(driver.window_handles)
                        new_tabs = new_handles - old_handles
                        if new_tabs:
                            new_tab = new_tabs.pop()
                            driver.switch_to.window(new_tab)
                            print(f"  Switched to new tab: {driver.current_url[:80]}")
                            human_delay(2, 4)
                            return "new_tab"
                    except Exception:
                        pass  # No new tab opened within 5s — check for iframe

                    # Check if iframe modal opened
                    try:
                        iframe = WebDriverWait(driver, 5).until(
                            EC.presence_of_element_located((By.XPATH,
                                "//iframe[contains(@id,'modal-iframe') or contains(@src,'smartapply')]"))
                        )
                        driver.switch_to.frame(iframe)
                        print("  Switched to apply modal iframe")
                        try:
                            child_iframe = WebDriverWait(driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, "//iframe[contains(@src,'resumeapply')]"))
                            )
                            driver.switch_to.frame(child_iframe)
                            print("  Switched to nested resume iframe")
                        except Exception:
                            pass
                        return "iframe"
                    except Exception:
                        pass

                    return "same_page"
        except Exception:
            continue

    # If still not found, scroll all the way down and try one more time
    try:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        # Quick retry on just the text-based selectors
        for xpath in ["//button[contains(text(),'Apply now')]", "//a[contains(text(),'Apply now')]",
                       "//button[contains(text(),'Apply Now')]", "//a[contains(text(),'Apply Now')]"]:
            try:
                btn = driver.find_element(By.XPATH, xpath)
                if btn.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", btn)
                    time.sleep(0.5)
                    stealth_click(btn)
                    print(f"  Clicked Apply (after scroll): '{btn.text.strip()}'")
                    # Wait for new tab
                    try:
                        WebDriverWait(driver, 5).until(
                            lambda d: len(d.window_handles) > num_old_handles
                        )
                        new_handles = set(driver.window_handles)
                        new_tabs = new_handles - old_handles
                        if new_tabs:
                            driver.switch_to.window(new_tabs.pop())
                            print(f"  Switched to new tab: {driver.current_url[:80]}")
                            human_delay(2, 4)
                            return "new_tab"
                    except Exception:
                        pass
                    return "same_page"
            except Exception:
                continue
    except Exception:
        pass

    # Debug: show what IS clickable near bottom of page
    try:
        all_btns = driver.find_elements(By.CSS_SELECTOR, "button, a.indeed-apply-button, a[class*='Apply']")
        visible = [(b.tag_name, b.text.strip()[:30], b.get_attribute("class") or "") for b in all_btns if b.is_displayed() and b.text.strip()]
        if visible:
            print(f"  DEBUG clickable elements: {visible[:6]}")
    except Exception:
        pass

    # LAST RESORT: Check if SmartApply already opened (inline modal or redirect)
    # Detection: If we see "Save and close" + "Continue" buttons, the form is open
    try:
        has_save_close = driver.find_elements(By.XPATH, "//button[contains(text(),'Save and close')]")
        has_continue = driver.find_elements(By.XPATH, "//button[contains(text(),'Continue')]")
        if has_save_close and has_continue:
            print(f"  SmartApply opened inline (detected Save/Continue buttons)")
            return "same_page"
    except Exception:
        pass

    # Check URL for SmartApply redirect
    current = driver.current_url.lower()
    if 'smartapply' in current or 'indeedapply' in current:
        print(f"  Already on SmartApply! URL: {current[:80]}")
        return "same_page"

    # Check all tabs — SmartApply may have opened in another tab
    original_handle = driver.current_window_handle
    for handle in driver.window_handles:
        if handle == original_handle:
            continue
        try:
            driver.switch_to.window(handle)
            tab_url = driver.current_url.lower()
            if 'smartapply' in tab_url or 'indeedapply' in tab_url:
                print(f"  Found SmartApply in another tab: {tab_url[:80]}")
                return "new_tab"
        except Exception:
            continue
    # Switch back if we didn't find SmartApply
    try:
        driver.switch_to.window(original_handle)
    except Exception:
        pass

    return None


def check_already_applied():
    """Check if we already applied to this job."""
    already_indicators = [
        "//span[contains(text(),'Applied')]",
        "//div[contains(text(),'You applied')]",
        "//span[contains(text(),'already applied')]",
        "//div[contains(@class,'applied')]",
    ]
    for xpath in already_indicators:
        try:
            el = driver.find_element(By.XPATH, xpath)
            if el.is_displayed():
                return True
        except Exception:
            continue
    return False


# ==============================
# COVER LETTER GENERATION
# ==============================

def generate_cover_letter(job_description, job_title, user_resume_summary, user_name, metadata=None):
    """Two-phase cover letter: Phase 1 draft → Phase 2 humanize."""

    keywords = extract_keywords(job_description)
    keyword_str = ", ".join(keywords)
    print(f"  KEYWORDS EXTRACTED: {keyword_str}")

    company = metadata.get('company', 'this company') if metadata else 'this company'

    # ---- PHASE 1: Generate tailored draft ----
    print("  PHASE 1: Generating tailored draft...")
    phase1_prompt = (
        "Write a tailored, professional cover letter for the following job. "
        "Keep it to one page, 3 paragraphs.\n\n"
        "STRICT FILTERING RULES (CRITICAL):\n"
        "- IGNORE all dates, deadlines, 'posted X ago', and application metadata.\n"
        "- Do NOT reference the application deadline, post date, or number of applicants.\n"
        "- ONLY use actual job requirements, responsibilities, and qualifications.\n"
        "- NEVER mention salary, hourly rate, compensation, or pay range.\n\n"
        "OVERQUALIFICATION AWARENESS:\n"
        "- If the candidate appears overqualified for this role, acknowledge the career context naturally.\n"
        "- Example: Explain that the candidate is pursuing a Master's at Georgetown and seeking a "
        "role that fits their current life situation, while bringing valuable experience.\n"
        "- Don't lead with senior-level accomplishments for entry-level roles. Lead with fit.\n\n"
        "CRITICAL KEYWORD REQUIREMENT:\n"
        f"These are the TOP KEYWORDS from this job description. You MUST naturally "
        f"include as many of these as truthfully possible in the letter:\n"
        f"[{keyword_str}]\n\n"
        "RULES:\n"
        "- Directly connect the candidate's accomplishments to the job requirements.\n"
        "- Use the X-Y-Z formula: Accomplished [X] as measured by [Y] by doing [Z].\n"
        "- Include at least one real date, one percentage/number, and one proper noun per paragraph.\n"
        "- Active voice only. 'I built' not 'was built.'\n"
        "- NEVER fabricate security clearances, certifications, or credentials not in the resume.\n"
        f"- Address to: Dear Hiring Team at {company},\n"
        "- End with 'Sincerely,' followed by '" + str(user_name) + "'.\n"
        "- No placeholder brackets.\n\n"
        f"JOB: {job_title}\n"
        f"COMPANY: {company}\n"
        f"DESCRIPTION: {job_description}\n"
        f"RESUME: {user_resume_summary}\n\n"
        "Cover letter:"
    )

    initial_draft = call_gemini(phase1_prompt)
    if not initial_draft:
        return None

    # ---- PHASE 2: Humanizer voice pass ----
    print("  PHASE 2: Humanizing the draft...")
    phase2_prompt = (
        "Rewrite this cover letter to sound like a busy, capable human wrote it in 10 minutes. "
        "Not a robot. Not ChatGPT. A real person who's qualified and slightly impatient.\n\n"
        "STRICT VOICE RULES:\n\n"
        "STRUCTURAL CHAOS:\n"
        "- Paragraphs MUST be unequal length. First paragraph 4 sentences, second 2 sentences, "
        "third 3-5 sentences.\n"
        "- Vary sentences between 5 and 25 words. One long, two short, one medium.\n"
        "- Include exactly ONE sentence under 6 words per paragraph.\n\n"
        "CONTROLLED IMPERFECTION:\n"
        "- Use a casual pivot to start the middle paragraph: 'Truth be told,' 'Look,' "
        "'Here's the thing,' 'Anyway,' or just start directly.\n"
        "- Include one mid-sentence self-correction with a dash "
        "(e.g., 'My work at CareFirst--well, specifically the billing overhaul--connects directly here.').\n"
        "- Use contractions for EVERYTHING. Never 'I am' always 'I'm'. Never 'do not' always 'don't'. "
        "Never 'it is' always 'it's'. Never 'I have' always 'I've'.\n"
        "- Add one 'imperfect' sentence that acknowledges a non-obvious career path. Something like: "
        "'I know a Navy vet with an MBA isn't the obvious hire for this, but the systems thinking transfers.' "
        "Make it specific to the job and honest about the candidate's non-linear background.\n\n"
        "NO BOLDING:\n"
        "- Do NOT use any bold formatting, asterisks, or markdown. Plain text only.\n\n"
        "WORD REPETITION BAN:\n"
        "- No word should appear more than TWICE in the entire letter (except common words like "
        "'the,' 'and,' 'I'). Scan the draft and replace any repeated thematic words.\n\n"
        "MESSY STRUCTURE:\n"
        "- Do NOT follow a perfect 'Intro -> Evidence -> Closing' arc. Mix it up.\n"
        "- Put a piece of evidence in the opening. Put a personal note in the middle.\n"
        "- Real cover letters are a little messy. Lean into that.\n\n"
        "BANNED WORDS (remove if present):\n"
        "leverage, facilitate, underscore, robust, dynamic, synergy, tapestry, delve, innovative, "
        "comprehensive, furthermore, moreover, in addition, consequently, utilize, passionate, "
        "excited, thrilled, eager, spearheaded, orchestrated, pioneered, championed, "
        "it is crucial, I am passionate, I am excited, adept, proficient, commitment (max 1 use).\n\n"
        "BANNED TRANSITIONS:\n"
        "'Moreover,' 'Furthermore,' 'In conclusion,' 'Additionally.' "
        "Replace with 'Plus,' 'Also,' or nothing.\n\n"
        "KEEP:\n"
        "- All factual claims, numbers, dates, and proper nouns from the draft.\n"
        "- Opening greeting and 'Sincerely, " + str(user_name) + "' closing.\n"
        "- X-Y-Z evidence.\n"
        "- Active voice throughout.\n\n"
        "PROTECTED KEYWORDS (do NOT remove or change these terms):\n"
        f"[{keyword_str}]\n\n"
        f"DRAFT TO REWRITE:\n{initial_draft}"
    )

    humanized = call_gemini(phase2_prompt)
    if humanized:
        print("  Two-phase cover letter complete!")
        return strip_formatting(humanized)
    else:
        print("  Phase 2 failed. Using Phase 1 draft.")
        return strip_formatting(initial_draft)


def save_cover_letter_pdf(text, job_title, user_name, user_contact, output_dir=None):
    safe_title = "".join(c for c in job_title if c.isalnum() or c in (' ', '-', '_'))
    safe_title = safe_title.strip()[:50]
    target_dir = output_dir if output_dir else COVER_LETTER_DIR
    filepath = os.path.join(target_dir, f"CoverLetter_{safe_title}.pdf")

    print("\n--- COVER LETTER ---")
    print(text)
    print("--------------------\n")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=25)

    pdf.set_font("Times", "B", size=14)
    pdf.cell(0, 10, str(user_name), ln=True, align="C")
    pdf.set_font("Times", size=10)
    pdf.cell(0, 6, str(user_contact), ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Times", size=12)
    for line in text.split("\n"):
        if line.strip():
            clean_line = line.replace('\u2014', '-')
            clean_line = clean_line.replace('\u2013', '-')
            clean_line = clean_line.replace('\u2018', "'")
            clean_line = clean_line.replace('\u2019', "'")
            clean_line = clean_line.replace('\u201c', '"')
            clean_line = clean_line.replace('\u201d', '"')
            clean_line = clean_line.replace('\u2022', '-')
            clean_line = clean_line.replace('\u00a0', ' ')
            clean_line = clean_line.encode('ascii', 'ignore').decode('ascii')
            pdf.multi_cell(0, 7, clean_line)
            pdf.ln(3)

    pdf.output(filepath)
    print(f"Saved cover letter: {filepath}")
    return filepath


# ==============================
# TAILORED RESUME GENERATION
# ==============================

def generate_tailored_resume(job_description, job_title, user_full_resume, metadata=None):
    """Two-phase resume: Phase 1 ATS draft → Phase 2 humanize."""

    keywords = extract_keywords(job_description)
    keyword_str = ", ".join(keywords)
    print(f"  KEYWORDS EXTRACTED: {keyword_str}")

    # ---- PHASE 1: ATS keyword-optimized draft ----
    print("  PHASE 1: Generating ATS-optimized draft...")
    phase1_prompt = (
        "You are an expert resume writer. Tailor this resume for the job below.\n\n"
        "STRICT FILTERING RULES (CRITICAL):\n"
        "- IGNORE all dates, deadlines, 'posted X ago', and application metadata.\n"
        "- Do NOT include the application deadline, post date, number of applicants, or any UI text.\n"
        "- ONLY extract actual job requirements: hard skills, soft skills, tools, responsibilities.\n"
        "- NEVER put phrases like 'posted 2 weeks ago' anywhere in the resume.\n"
        "- NEVER include salary, hourly rate, compensation, or pay range.\n"
        "- NEVER copy phrases directly from the JD into the Skills section.\n\n"
        "OVERQUALIFICATION AWARENESS:\n"
        "- If the candidate appears overqualified, pivot the Professional Summary to explain context.\n"
        "- Example: 'Georgetown graduate student with a technical management background seeking a "
        "stability-focused supporting role while completing a Master's degree.'\n"
        "- Lead with transferable skills that match the role level.\n\n"
        "MANDATORY KEYWORDS (include ALL of these in the resume):\n"
        f"[{keyword_str}]\n"
        "Place these in the SKILLS section AND weave them into experience bullets.\n\n"
        "SKILL GROUPING:\n"
        "- Group skills into categories based on the job type.\n"
        "- For admin/support roles: 'Administrative & Support' first, then 'Technical Tools'.\n"
        "- For technical roles: 'Technical' first, then 'Data & Analytics', then 'Leadership'.\n"
        "- Skills must be actual skill names, NOT job description sentences.\n\n"
        "ATS OPTIMIZATION:\n"
        "- Mirror EXACT phrasing from the job description.\n"
        "- Include spelled-out term AND acronym (e.g., 'Extract Transform Load (ETL)').\n"
        "- Place top keywords in BOTH Professional Summary AND Skills.\n\n"
        "X-Y-Z EVIDENCE FORMULA:\n"
        "- Every bullet: Accomplished [X] as measured by [Y] by doing [Z].\n"
        "- Include real numbers: percentages, team sizes, dollar amounts.\n\n"
        "STRUCTURE: PROFESSIONAL SUMMARY, SKILLS, EXPERIENCE, EDUCATION\n"
        "- ONE page. Active voice only. Strong action verbs.\n"
        "- Most relevant bullets first per role.\n"
        "- Keep ALL facts accurate. Do NOT invent anything.\n"
        "- NEVER fabricate security clearances, certifications, or credentials.\n"
        "  Only include a clearance if it appears in the candidate's actual resume.\n"
        "- No candidate name/contact (goes in PDF header).\n"
        "- No markdown. Plain text. Bullets start with '-'.\n"
        "- CRITICAL: Write the COMPLETE resume. Include ALL sections, ALL jobs, ALL education.\n"
        "  Do NOT stop early or truncate. Every job must have 2-4 bullets minimum.\n\n"
        f"JOB TITLE: {job_title}\n"
        f"JOB DESCRIPTION: {job_description}\n\n"
        f"FULL RESUME TO TAILOR:\n{user_full_resume}\n\n"
        "Tailored resume:"
    )

    initial_draft = call_gemini(phase1_prompt)
    if not initial_draft:
        return None

    # ---- PHASE 2: Humanizer voice pass ----
    print("  PHASE 2: Humanizing the resume...")
    phase2_prompt = (
        "Rewrite this resume so it passes AI detection tools. "
        "A real human wrote this on their laptop while drinking coffee.\n\n"
        "STRICT REWRITE RULES:\n\n"
        "BURSTINESS:\n"
        "- Mix bullet lengths dramatically. Some bullets 5-8 words. Some 15-20 words.\n"
        "- Never make consecutive bullets the same length.\n"
        "- Include at least one very short punchy bullet per job (e.g., 'Cut deploy time by 40%.').\n"
        "- Include at least one longer bullet with a dash side-thought per job.\n\n"
        "NO BOLDING OR FORMATTING:\n"
        "- Do NOT use asterisks, bold, or any markdown. Plain text ONLY.\n\n"
        "WORD REPETITION BAN:\n"
        "- No action verb should appear more than TWICE across all bullets.\n"
        "- If you use 'managed' once, use 'ran,' 'led,' 'owned' next time.\n\n"
        "VARIED BULLET STARTERS:\n"
        "- Never start 3+ consecutive bullets with the same pattern.\n"
        "- Mix: verb-first, context-first, result-first.\n\n"
        "BANNED WORDS:\n"
        "leverage, facilitate, underscore, robust, dynamic, synergy, tapestry, delve, innovative, "
        "comprehensive, utilize, spearheaded, orchestrated, pioneered, championed, adept, proficient, "
        "streamlined (replace with 'cleaned up' or 'simplified').\n\n"
        "HUMAN ACTION VERBS (use these instead):\n"
        "built, ran, cut, led, shipped, fixed, wrote, trained, managed, owned, created, "
        "designed, set up, rolled out, moved, handled, pulled, pushed, cleaned up, rewrote, "
        "took over, figured out, put together.\n\n"
        "VOICE:\n"
        "- Active voice ONLY. Write like a real person describing what they did.\n"
        "- Use a dash (--) once or twice for side thoughts.\n\n"
        "KEEP INTACT:\n"
        "- ALL numbers, metrics, dates, and proper nouns.\n"
        "- Section structure: PROFESSIONAL SUMMARY, SKILLS, EXPERIENCE, EDUCATION.\n"
        "- No markdown. Plain text. Bullets start with '-'.\n"
        "- No candidate name/contact.\n"
        "- CRITICAL: Output the COMPLETE resume. Do NOT stop mid-section.\n"
        "  Include ALL jobs with 2-4 bullets each, ALL skills, and ALL education entries.\n\n"
        "PROTECTED KEYWORDS:\n"
        f"[{keyword_str}]\n\n"
        f"DRAFT TO REWRITE:\n{initial_draft}"
    )

    humanized = call_gemini(phase2_prompt)
    if humanized:
        print("  Two-phase resume complete!")
        return strip_formatting(humanized)
    else:
        print("  Phase 2 failed. Using Phase 1 draft.")
        return strip_formatting(initial_draft)


def save_resume_pdf(text, job_title, user_name, user_contact, output_dir=None):
    safe_title = "".join(c for c in job_title if c.isalnum() or c in (' ', '-', '_'))
    safe_title = safe_title.strip()[:50]
    target_dir = output_dir if output_dir else RESUME_DIR
    filepath = os.path.join(target_dir, f"Resume_{safe_title}.pdf")

    print("\n--- TAILORED RESUME ---")
    print(text)
    print("-----------------------\n")

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Times", "B", size=16)
    pdf.cell(0, 8, str(user_name), ln=True, align="C")
    pdf.set_font("Times", size=10)
    pdf.cell(0, 5, str(user_contact), ln=True, align="C")
    pdf.line(10, pdf.get_y() + 2, 200, pdf.get_y() + 2)
    pdf.ln(5)

    # Body
    pdf.set_font("Times", size=11)
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            pdf.ln(2)
            continue

        clean_line = stripped.replace('\u2014', '-')
        clean_line = clean_line.replace('\u2013', '-')
        clean_line = clean_line.replace('\u2018', "'")
        clean_line = clean_line.replace('\u2019', "'")
        clean_line = clean_line.replace('\u201c', '"')
        clean_line = clean_line.replace('\u201d', '"')
        clean_line = clean_line.replace('\u2022', '-')
        clean_line = clean_line.replace('\u00a0', ' ')
        clean_line = clean_line.encode('ascii', 'ignore').decode('ascii')

        if clean_line.upper() == clean_line and len(clean_line) > 3 and not clean_line.startswith('-'):
            pdf.ln(2)
            pdf.set_font("Times", "B", size=11)
            pdf.cell(0, 6, clean_line, ln=True)
            pdf.line(10, pdf.get_y(), 200, pdf.get_y())
            pdf.ln(1)
            pdf.set_font("Times", size=11)
        elif clean_line.startswith('-'):
            pdf.cell(5)
            pdf.multi_cell(0, 5, clean_line)
        else:
            pdf.multi_cell(0, 5, clean_line)

    pdf.output(filepath)
    print(f"Saved tailored resume: {filepath}")
    return filepath


# ==============================
# INDEED APPLICATION FLOW
# ==============================

def handle_indeed_application(res_path=None, cl_path=None, jd=None, job_title=None, metadata=None, job_kws=None):
    """Navigate Indeed's Easy Apply wizard.
    
    Docs are generated ON-DEMAND when the app asks for them, not upfront.
    Returns (success, res_text, cl_text) so ATS scoring can happen after.
    
    Indeed uses TWO application modes:
    A) New tab to smartapply.indeed.com (buttons directly on page)
    B) Iframe modal on same page (must switch_to.frame first)
    """
    global paused
    human_delay(2, 4)

    # Track generated docs (on-demand)
    _generated_res_text = None
    _generated_cl_text = None
    _generated_res_path = res_path
    _generated_cl_path = cl_path

    def _ensure_resume():
        """Generate resume on-demand if not already generated."""
        nonlocal _generated_res_text, _generated_res_path
        if _generated_res_path and os.path.exists(_generated_res_path):
            return _generated_res_path
        if not jd:
            return None
        print("\n  Generating tailored resume (on-demand)...")
        u_full = CURRENT_USER_DATA.get("full_resume") or _build_full_resume(PROFILE)
        u_name = CURRENT_USER_DATA.get("name") or get_user_name(PROFILE)
        u_contact = CURRENT_USER_DATA.get("contact") or get_user_contact(PROFILE)
        _generated_res_text = generate_tailored_resume(jd, job_title or "", u_full, metadata or {})
        if _generated_res_text:
            _generated_res_path = save_resume_pdf(_generated_res_text, job_title or "Job", u_name, u_contact)
            return _generated_res_path
        return None

    def _ensure_cover_letter():
        """Generate cover letter on-demand if not already generated."""
        nonlocal _generated_cl_text, _generated_cl_path
        if _generated_cl_path and os.path.exists(_generated_cl_path):
            return _generated_cl_path
        if not jd:
            return None
        print("\n  Generating tailored cover letter (on-demand)...")
        u_sum = CURRENT_USER_DATA.get("resume_summary") or _build_resume_summary(PROFILE)
        u_name = CURRENT_USER_DATA.get("name") or get_user_name(PROFILE)
        u_contact = CURRENT_USER_DATA.get("contact") or get_user_contact(PROFILE)
        _generated_cl_text = generate_cover_letter(jd, job_title or "", u_sum, u_name, metadata or {})
        if _generated_cl_text:
            _generated_cl_path = save_cover_letter_pdf(_generated_cl_text, job_title or "Job", u_name, u_contact)
            return _generated_cl_path
        return None

    # Track which mode we're in
    apply_mode = None  # Will be set by click_apply_button return value

    max_steps = 15
    for step in range(max_steps):
        check_pause()

        # === IFRAME CHECK: Switch into iframe if present ===
        try:
            driver.switch_to.default_content()  # Always reset first
        except Exception:
            pass

        switched_to_frame = try_switch_to_apply_iframe()

        current_url = driver.current_url
        print(f"\n  --- Application Step {step + 1} ---")
        print(f"  URL: {current_url[:80]}")
        if switched_to_frame:
            print(f"  (Inside iframe)")

        # === CHECK FOR ASSESSMENT URL ===
        if any(kw in current_url.lower() for kw in ['assessment', 'test', '/quiz', 'skill-test']):
            print("  !!! ASSESSMENT URL DETECTED !!!")
            print(f"  URL: {current_url[:100]}")
            print("  >>> Complete this manually, then type 'p' + Enter to resume <<<")
            with pause_lock:
                paused = True
            check_pause()

        # Wait for content to render
        time.sleep(2)

        # === CHECK FOR SUCCESS ===
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        except Exception:
            body_text = ""

        success_phrases = [
            "application submitted",
            "application has been submitted",
            "successfully applied",
            "your application has been",
            "thank you for applying",
            "you've applied to this job",
            "you have applied",
        ]
        if any(phrase in body_text for phrase in success_phrases):
            print("  APPLICATION SUBMITTED SUCCESSFULLY!")
            try:
                driver.switch_to.default_content()
            except Exception:
                pass
            return (True, _generated_res_text, _generated_cl_text)

        # Also check Indeed's specific success class (from working bot)
        try:
            applied_el = driver.find_element(By.CLASS_NAME, "ia-HasApplied-bodyTop")
            if "applied" in applied_el.text.lower():
                print("  APPLICATION SUBMITTED (ia-HasApplied detected)!")
                try:
                    driver.switch_to.default_content()
                except Exception:
                    pass
                return (True, _generated_res_text, _generated_cl_text)
        except Exception:
            pass

        # === READ HEADINGS TO IDENTIFY STEP ===
        page_heading = ""
        # Try Indeed's specific heading class first (from working bot)
        try:
            heading_el = driver.find_element(By.CLASS_NAME, "ia-BasePage-heading")
            if heading_el.is_displayed():
                page_heading = heading_el.text.strip().lower()
                print(f"  Heading: '{heading_el.text.strip()}'")
        except Exception:
            pass

        if not page_heading:
            for tag in ["h1", "h2", "h3", "legend"]:
                try:
                    headings = driver.find_elements(By.TAG_NAME, tag)
                    for h in headings:
                        if h.is_displayed():
                            txt = h.text.strip().lower()
                            if txt and len(txt) > 3:
                                page_heading = txt
                                print(f"  Heading: '{h.text.strip()}'")
                                break
                    if page_heading:
                        break
                except Exception:
                    continue

        # === HANDLE EACH STEP TYPE ===
        # SmartApply URLs are descriptive — use them for reliable step detection
        url_lower = current_url.lower()
        is_qualification_page = 'qualification-questions' in url_lower
        is_resume_page = 'resume-selection' in url_lower or 'resume-upload' in url_lower
        is_review_page = ('review' in url_lower and 'smartapply' in url_lower 
                         and 'profile-edu' not in url_lower and 'work-experience' not in url_lower)
        is_contact_page = 'contact-info' in url_lower
        is_cover_letter_page = 'cover-letter' in url_lower
        is_employer_vis_page = 'employer' in page_heading and 'find you' in page_heading
        is_work_exp_page = 'work-experience' in url_lower
        is_education_page = 'profile-edu' in url_lower or 'review education' in page_heading

        # For inline SmartApply, also detect step from button/module classes
        if not any([is_qualification_page, is_resume_page, is_review_page,
                     is_contact_page, is_cover_letter_page, is_education_page]):
            try:
                all_btns_classes = " ".join([
                    (b.get_attribute("class") or "") for b in
                    driver.find_elements(By.TAG_NAME, "button") if b.is_displayed()
                ]).lower()
                if 'resume-selection' in all_btns_classes or 'resume-upload' in all_btns_classes:
                    is_resume_page = True
                elif 'qualification' in all_btns_classes:
                    is_qualification_page = True
            except Exception:
                pass

        if is_qualification_page or 'question' in page_heading or 'qualification' in page_heading:
            print("  Step: Screening Questions")
            unanswered = answer_screening_questions()
            if unanswered >= MAX_UNANSWERED_SKIP:
                print(f"  *** {unanswered} unanswered questions — too many to proceed. SKIPPING JOB. ***")
                try:
                    # Close SmartApply tab if we're in one
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    else:
                        driver.switch_to.default_content()
                except Exception:
                    pass
                return (False, _generated_res_text, _generated_cl_text)

        elif is_resume_page or 'resume' in page_heading or 'upload a resume' in body_text[:500] or 'add a resume' in body_text[:500]:
            print("  Step: Resume Upload")
            rpath = _ensure_resume()  # Generate on-demand if needed
            handle_resume_step(rpath)

        elif is_cover_letter_page or 'cover letter' in page_heading:
            print("  Step: Cover Letter")
            cpath = _ensure_cover_letter()  # Generate on-demand if needed
            handle_cover_letter_step(cpath)

        elif is_contact_page or 'contact' in page_heading or 'first name' in body_text[:500]:
            print("  Step: Contact Information")
            fill_any_empty_fields()

        elif 'location' in page_heading or 'zip code' in body_text[:500]:
            print("  Step: Location Details")
            fill_any_empty_fields()

        elif is_employer_vis_page:
            print("  Step: Employer Visibility (just clicking Continue)")

        elif is_education_page or 'education' in page_heading:
            print("  Step: Review Education")
            handle_education_review()

        elif is_review_page or 'review' in page_heading:
            print("  Step: Review")

        elif is_work_exp_page or 'experience' in page_heading or 'work history' in page_heading:
            print("  Step: Work Experience")
            # Fill any empty fields on work experience review
            fill_any_empty_fields()

        # === ASSESSMENT TEST DETECTION ===
        elif any(kw in page_heading for kw in ['assessment', 'test', 'quiz', 'evaluation', 'skill test']):
            print("  !!! ASSESSMENT TEST DETECTED !!!")
            print("  Bot cannot safely answer skill assessments.")
            print("  >>> Complete this manually, then type 'p' + Enter to resume <<<")
            with pause_lock:
                paused = True
            check_pause()

        elif any(kw in body_text[:800] for kw in ['assessment', 'skill test', 'take a test', 'timed assessment',
                                                     'complete this assessment', 'begin assessment']):
            print("  !!! ASSESSMENT TEST DETECTED (from page text) !!!")
            print("  >>> Complete this manually, then type 'p' + Enter to resume <<<")
            with pause_lock:
                paused = True
            check_pause()

        else:
            print(f"  Step: Unknown — filling fields and answering questions")
            fill_any_empty_fields()
            unanswered = answer_screening_questions()
            if unanswered >= MAX_UNANSWERED_SKIP:
                print(f"  *** {unanswered} unanswered on unknown page — SKIPPING JOB. ***")
                try:
                    if len(driver.window_handles) > 1:
                        driver.close()
                        driver.switch_to.window(driver.window_handles[0])
                    else:
                        driver.switch_to.default_content()
                except Exception:
                    pass
                return (False, _generated_res_text, _generated_cl_text)

        # === CLICK CONTINUE / SUBMIT ===
        human_delay(1, 2)
        pre_click_url = driver.current_url
        clicked = click_continue_or_submit()

        if not clicked:
            # Scroll down and retry
            try:
                driver.execute_script("window.scrollBy(0, 300);")
            except Exception:
                pass
            time.sleep(1)
            clicked = click_continue_or_submit()

        if clicked:
            # Check if we're stuck on the same page (validation errors = required fields empty)
            human_delay(1.5, 2.5)
            post_click_url = driver.current_url
            if post_click_url == pre_click_url:
                # Check for validation error messages
                try:
                    error_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                    has_errors = any(err in error_text for err in [
                        'this field is required', 'please select', 'required field',
                        'please answer', 'answer this question', 'this question is required',
                        'please complete', 'please fill', 'is required'
                    ])
                    if has_errors:
                        remaining = count_unanswered_fields()
                        print(f"  *** Stuck — validation errors with {remaining} unanswered field(s). SKIPPING JOB. ***")
                        try:
                            if len(driver.window_handles) > 1:
                                driver.close()
                                driver.switch_to.window(driver.window_handles[0])
                            else:
                                driver.switch_to.default_content()
                        except Exception:
                            pass
                        return (False, _generated_res_text, _generated_cl_text)
                except Exception:
                    pass

        if not clicked:
            print(f"  No button found — SKIPPING JOB.")
            try:
                if len(driver.window_handles) > 1:
                    driver.close()
                    driver.switch_to.window(driver.window_handles[0])
                else:
                    driver.switch_to.default_content()
            except Exception:
                pass
            return (False, _generated_res_text, _generated_cl_text)

        human_delay(2, 4)

    print("  Reached max steps without confirmation.")
    try:
        driver.switch_to.default_content()
    except Exception:
        pass
    return (False, _generated_res_text, _generated_cl_text)


def try_switch_to_apply_iframe():
    """Try to switch into Indeed's application iframe(s).
    
    Indeed nests forms inside iframes:
    - Parent: iframe with id containing 'modal-iframe' or src containing 'smartapply'
    - Child:  iframe with src containing 'resumeapply'
    
    Returns True if switched into an iframe.
    """
    try:
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        for frame in iframes:
            try:
                src = (frame.get_attribute("src") or "").lower()
                frame_id = (frame.get_attribute("id") or "").lower()

                if any(kw in src for kw in ["smartapply", "indeedapply", "resumeapply"]) or \
                   any(kw in frame_id for kw in ["modal-iframe", "indeedapply", "apply"]):
                    if frame.is_displayed():
                        driver.switch_to.frame(frame)
                        print(f"  Switched to iframe: id='{frame_id}' src='{src[:60]}'")

                        # Check for nested child iframe
                        try:
                            child_frames = driver.find_elements(By.TAG_NAME, "iframe")
                            for child in child_frames:
                                child_src = (child.get_attribute("src") or "").lower()
                                if "resumeapply" in child_src or "indeedapply" in child_src:
                                    driver.switch_to.frame(child)
                                    print(f"  Switched to nested iframe: src='{child_src[:60]}'")
                                    break
                        except Exception:
                            pass
                        return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def fill_any_empty_fields():
    """Fill empty form fields using placeholder, aria-label, name, and id attributes.
    Works inside iframes and on smartapply.indeed.com pages."""

    field_map = {
        'first name': p('personal', 'first_name'),
        'firstname': p('personal', 'first_name'),
        'first_name': p('personal', 'first_name'),
        'last name': p('personal', 'last_name'),
        'lastname': p('personal', 'last_name'),
        'last_name': p('personal', 'last_name'),
        'phone': p('personal', 'phone'),
        'email': p('personal', 'email'),
        'zip': p('personal', 'zip'),
        'postal': p('personal', 'zip'),
        'city': p('personal', 'city'),
        'state': p('personal', 'state'),
        'street': '',
    }

    try:
        inputs = driver.find_elements(By.CSS_SELECTOR, "input, textarea")
        for inp in inputs:
            try:
                if not inp.is_displayed() or not inp.is_enabled():
                    continue

                current = (inp.get_attribute("value") or "").strip()
                if current:
                    continue  # Already filled

                # Gather all identifying attributes
                attr_text = " ".join([
                    inp.get_attribute("placeholder") or "",
                    inp.get_attribute("aria-label") or "",
                    inp.get_attribute("name") or "",
                    inp.get_attribute("id") or "",
                    inp.get_attribute("autocomplete") or "",
                ]).lower()

                # Also check for associated label
                try:
                    inp_id = inp.get_attribute("id")
                    if inp_id:
                        label = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                        attr_text += " " + label.text.lower()
                except Exception:
                    pass

                # Try parent text as fallback
                try:
                    parent = inp.find_element(By.XPATH, "./..")
                    attr_text += " " + (parent.text or "").lower()[:100]
                except Exception:
                    pass

                for key, val in field_map.items():
                    if key in attr_text and val:
                        inp.clear()
                        stealth_type(inp, val)
                        print(f"    Filled '{key}' -> '{val}'")
                        human_delay(0.3, 0.6)
                        # Tab out to trigger validation
                        try:
                            inp.send_keys(Keys.TAB)
                        except Exception:
                            pass
                        human_delay(0.5, 1)
                        break
            except Exception:
                continue
    except Exception as e:
        print(f"  Field fill error: {e}")


def handle_education_review():
    """Handle SmartApply's 'Review Education' page.
    
    Indeed parses education from the uploaded resume and shows a review page.
    Each entry may have 'City, State' missing (required). The bot:
    1. Finds entries with error messages
    2. Clicks the edit (pencil) icon
    3. Fills in City, State from the profile
    4. Clicks Save
    """
    edu_data = PROFILE.get("education", [])
    if not edu_data:
        print("  No education data in profile — skipping education review")
        return

    # Build school -> city_state lookup
    school_locations = {}
    for ed in edu_data:
        school_name = ed.get("school", "").lower()
        city_state = ed.get("city_state", "")
        if school_name and city_state:
            school_locations[school_name] = city_state
    
    # Find all education cards with errors
    error_cards = []
    try:
        # Look for cards with red error text
        cards = driver.find_elements(By.CSS_SELECTOR, 
            "div[class*='card'], div[class*='education'], div[class*='item'], "
            "div[class*='module'], div[class*='entry']")
        
        # Also try finding by the error message
        error_elements = driver.find_elements(By.XPATH, 
            "//*[contains(text(),'required details missing')]")
        
        if not error_elements:
            print("  No education errors found — proceeding")
            return
        
        print(f"  Found {len(error_elements)} education entries needing fixes")
    except Exception:
        pass

    # Strategy: Click each edit button, fill City/State, click Save
    max_edits = len(edu_data)
    for edit_round in range(max_edits):
        try:
            # Re-find error messages each round (DOM changes after Save)
            error_elements = driver.find_elements(By.XPATH, 
                "//*[contains(text(),'required details missing')]")
            
            if not error_elements:
                print("  All education entries fixed!")
                break

            # Find the edit (pencil) button near the first error
            # Go up to the card container, then find the edit button
            error_el = error_elements[0]
            
            # Try to find the parent card and its edit button
            edit_clicked = False
            
            # Strategy 1: Find edit buttons (pencil icons) on the page
            edit_buttons = driver.find_elements(By.CSS_SELECTOR,
                "button[aria-label*='Edit'], button[aria-label*='edit'], "
                "button[class*='edit'], button svg, "
                "button[data-testid*='edit']")
            
            if not edit_buttons:
                # Try generic icon buttons near error text
                edit_buttons = driver.find_elements(By.XPATH,
                    "//button[contains(@class,'icon') or contains(@class,'edit') or "
                    "contains(@aria-label,'Edit')]")
            
            # Click the first available edit button
            for btn in edit_buttons:
                try:
                    if btn.is_displayed():
                        # Check if this edit button is for an entry that has errors
                        # by seeing if there's an error message nearby
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.3)
                        stealth_click(btn)
                        print(f"  Clicked edit button for education entry")
                        edit_clicked = True
                        human_delay(1, 2)
                        break
                except Exception:
                    continue

            if not edit_clicked:
                # Try clicking the error message link itself
                try:
                    error_link = driver.find_element(By.XPATH,
                        "//a[contains(text(),'Edit this item')] | "
                        "//*[contains(text(),'required details missing')]//a | "
                        "//*[contains(text(),'required details missing')]")
                    stealth_click(error_link)
                    edit_clicked = True
                    human_delay(1, 2)
                except Exception:
                    pass

            if not edit_clicked:
                print(f"  Could not find edit button — skipping remaining")
                break

            # Now we should be in the edit form
            # Find which school this is by reading the School name field
            human_delay(1, 2)
            school_name = ""
            try:
                # Look for school name input
                school_inputs = driver.find_elements(By.CSS_SELECTOR,
                    "input[name*='school'], input[name*='School'], "
                    "input[aria-label*='School'], input[aria-label*='school']")
                for si in school_inputs:
                    val = (si.get_attribute("value") or "").strip()
                    if val:
                        school_name = val.lower()
                        break
                
                if not school_name:
                    # Try reading any visible text that matches a school
                    body = driver.find_element(By.TAG_NAME, "body").text.lower()
                    for ed in edu_data:
                        if ed["school"].lower() in body:
                            school_name = ed["school"].lower()
                            break
            except Exception:
                pass

            # Find the City, State field and fill it
            city_state_value = ""
            if school_name:
                city_state_value = school_locations.get(school_name, "")
            
            if not city_state_value:
                # Try partial match
                for sname, cstate in school_locations.items():
                    if sname in school_name or school_name in sname:
                        city_state_value = cstate
                        break
            
            if not city_state_value:
                # Default to profile city/state
                city_state_value = f"{p('personal', 'city')}, {p('personal', 'state')}"

            # Fill City, State field
            filled = False
            city_selectors = [
                "input[name*='city'], input[name*='City']",
                "input[aria-label*='City'], input[aria-label*='city']",
                "input[placeholder*='City'], input[placeholder*='city']",
                "input[id*='city'], input[id*='City']",
            ]
            for sel in city_selectors:
                try:
                    for inp in driver.find_elements(By.CSS_SELECTOR, sel):
                        if inp.is_displayed():
                            current = (inp.get_attribute("value") or "").strip()
                            if not current:
                                inp.clear()
                                stealth_type(inp, city_state_value)
                                print(f"  Filled City, State: {city_state_value}")
                                filled = True
                                break
                    if filled:
                        break
                except Exception:
                    continue

            if not filled:
                # Try by label text
                try:
                    labels = driver.find_elements(By.TAG_NAME, "label")
                    for lbl in labels:
                        if 'city' in lbl.text.lower():
                            # Find the input associated with this label
                            lbl_for = lbl.get_attribute("for")
                            if lbl_for:
                                inp = driver.find_element(By.ID, lbl_for)
                            else:
                                inp = lbl.find_element(By.XPATH, "following::input[1]")
                            if inp.is_displayed():
                                inp.clear()
                                stealth_type(inp, city_state_value)
                                print(f"  Filled City, State (by label): {city_state_value}")
                                filled = True
                                break
                except Exception:
                    pass

            if not filled:
                # Last resort: fill ALL empty visible inputs on the edit form
                try:
                    empty_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='text']")
                    for inp in empty_inputs:
                        if inp.is_displayed() and not (inp.get_attribute("value") or "").strip():
                            inp.clear()
                            stealth_type(inp, city_state_value)
                            print(f"  Filled empty field with: {city_state_value}")
                            filled = True
                            break
                except Exception:
                    pass

            # Click Save
            human_delay(0.5, 1)
            saved = False
            for save_sel in [
                "//button[contains(text(),'Save')]",
                "//button[contains(text(),'save')]",
                "//button[@type='submit']",
            ]:
                try:
                    save_btn = driver.find_element(By.XPATH, save_sel)
                    if save_btn.is_displayed():
                        stealth_click(save_btn)
                        print(f"  Clicked Save")
                        saved = True
                        human_delay(1.5, 2.5)
                        break
                except Exception:
                    continue

            if not saved:
                print(f"  Could not find Save button")
                # Try clicking Cancel to get back
                try:
                    cancel = driver.find_element(By.XPATH, "//button[contains(text(),'Cancel')]")
                    stealth_click(cancel)
                    human_delay(1, 2)
                except Exception:
                    pass

        except Exception as e:
            print(f"  Education edit error: {e}")
            continue

    print(f"  Education review complete")


def handle_resume_step(res_path=None):
    """Handle the resume upload step on SmartApply.
    
    SmartApply has a TWO-STEP resume flow:
    1. Selection page: Choose "Upload a resume" vs "Build an Indeed Resume"
    2. Upload page: Actual file input appears after clicking Continue
    
    This function handles BOTH pages.
    """
    body_text = ""
    try:
        body_text = driver.find_element(By.TAG_NAME, "body").text.lower()
    except Exception:
        pass

    # Check if a resume is ALREADY selected (Indeed profile resume pre-loaded)
    already_has_resume = any(phrase in body_text for phrase in [
        'resume uploaded', 'your resume', 'resume selected', 
        'added a resume', 'resume added', '.pdf', 'shariq'
    ])
    if already_has_resume and 'upload a resume' not in body_text:
        print("  Resume already selected — just clicking Continue")
        return

    # === STEP 1: If this is the SELECTION page, click "Upload a resume" ===
    if 'upload a resume' in body_text and 'build an indeed' in body_text:
        print("  Resume selection page detected — clicking 'Upload a resume'")
        clicked_upload = False

        # Strategy 1: Click any element containing "Upload a resume" text
        for xpath in [
            "//*[contains(text(),'Upload a resume')]",
            "//h3[contains(text(),'Upload a resume')]",
            "//b[contains(text(),'Upload a resume')]",
            "//strong[contains(text(),'Upload a resume')]",
            "//div[contains(text(),'Upload a resume')]",
            "//span[contains(text(),'Upload a resume')]",
        ]:
            try:
                el = driver.find_element(By.XPATH, xpath)
                if el.is_displayed():
                    # Click the element AND its parent (card container)
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", el)
                    print("  Clicked 'Upload a resume' text")
                    clicked_upload = True
                    human_delay(1, 2)
                    break
            except Exception:
                continue

        # Strategy 2: Find card containers and click the one with "Upload"
        if not clicked_upload:
            try:
                all_clickable = driver.find_elements(By.CSS_SELECTOR,
                    "div[class*='card'], div[role='button'], div[class*='option'], "
                    "div[class*='selection'], div[class*='choice'], label, a")
                for el in all_clickable:
                    txt = el.text.lower()
                    if 'upload' in txt and 'resume' in txt and 'build' not in txt:
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.3)
                        driver.execute_script("arguments[0].click();", el)
                        print("  Clicked upload card container")
                        clicked_upload = True
                        human_delay(1, 2)
                        break
            except Exception:
                pass

        # Strategy 3: Use page-text AI solver as last resort
        if not clicked_upload:
            print("  Could not find upload card — trying AI click...")
            _click_element_by_visible_text("Upload a resume")
            human_delay(1, 2)

        # After clicking the card, check if a file input appeared immediately
        # If yes, upload now. If no, Continue will be clicked by main loop.
        time.sleep(1)

    # === STEP 2: Try to find and use file input (may be on this page or next) ===
    if res_path and os.path.exists(res_path):
        # Make hidden file inputs visible
        try:
            driver.execute_script(
                "document.querySelectorAll('input[type=file]').forEach("
                "el => { el.style.display='block'; el.style.visibility='visible'; "
                "el.style.height='1px'; el.style.width='1px'; el.style.opacity='1'; "
                "el.style.position='absolute'; el.style.left='0'; el.style.top='0'; })"
            )
            time.sleep(0.5)
        except Exception:
            pass

        # Try to upload
        uploaded = False
        for sel in ["input[type='file']", "input[name*='resume']", "input[name*='Resume']",
                     "input[name*='file']", "input[accept*='pdf']", "input[accept*='.pdf']"]:
            try:
                for fi in driver.find_elements(By.CSS_SELECTOR, sel):
                    fi.send_keys(res_path)
                    print(f"  Uploaded resume: {os.path.basename(res_path)}")
                    human_delay(3, 5)
                    uploaded = True
                    break
                if uploaded:
                    break
            except Exception:
                continue

        if not uploaded:
            # File input might appear after a click — look for drag-and-drop zone too
            try:
                dropzones = driver.find_elements(By.CSS_SELECTOR,
                    "[class*='dropzone'], [class*='upload-area'], [class*='file-upload'], "
                    "[class*='drag-drop'], [data-testid*='upload']")
                for dz in dropzones:
                    if dz.is_displayed():
                        stealth_click(dz)
                        print("  Clicked upload dropzone")
                        human_delay(1, 2)
                        # Check again for file input
                        for fi in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                            fi.send_keys(res_path)
                            print(f"  Uploaded resume via dropzone: {os.path.basename(res_path)}")
                            uploaded = True
                            human_delay(3, 5)
                            break
                        if uploaded:
                            break
            except Exception:
                pass

        if not uploaded:
            print("  No file input found yet — will try on next page after Continue")
    else:
        print("  No resume PDF to upload — will use Indeed profile resume")


def handle_cover_letter_step(cl_path=None):
    """Handle cover letter upload or skip."""
    if cl_path and os.path.exists(cl_path):
        try:
            driver.execute_script(
                "document.querySelectorAll('input[type=file]').forEach("
                "el => { el.style.display='block'; el.style.visibility='visible'; })"
            )
        except Exception:
            pass
        try:
            for fi in driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                fi.send_keys(cl_path)
                print(f"  Uploaded cover letter: {os.path.basename(cl_path)}")
                human_delay(3, 5)
                return
        except Exception:
            pass

    # Try to skip
    try:
        skip = driver.find_element(By.XPATH, "//button[contains(text(),'Skip')]")
        if skip.is_displayed():
            stealth_click(skip)
            print("  Skipped cover letter.")
    except Exception:
        pass


def click_continue_or_submit():
    """Click Continue/Submit in Indeed's wizard.
    
    Confirmed IDs: form-action-continue, form-action-submit
    SAFETY: "Apply" removed from text matches (prevents infinite loop).
    SAFETY: "primary" removed from CSS (prevents clicking Search bar).
    """

    # === PRIORITY 1: Indeed's confirmed button IDs ===
    for btn_id in ["form-action-continue", "form-action-submit", "form-action-next"]:
        try:
            btn = driver.find_element(By.ID, btn_id)
            if btn.is_displayed() and btn.is_enabled():
                btn_text = btn.text.strip() or btn_id
                if TEST_MODE and 'submit' in btn_id:
                    print(f"  [TEST MODE] Would click: '{btn_text}'")
                    return True
                stealth_click(btn)
                print(f"  Clicked (by ID): '{btn_text}'")
                return True
        except Exception:
            pass

    # === PRIORITY 2: Button text matches (NO "Apply" — prevents loop) ===
    button_texts = [
        "Continue",
        "Next",
        "Review your application",
        "Review",
        "Submit your application",
        "Submit application",
        "Submit",
    ]

    for btn_text in button_texts:
        try:
            buttons = driver.find_elements(By.XPATH,
                f"//button[contains(normalize-space(.),'{btn_text}')]"
            )
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    actual_text = btn.text.strip()
                    if TEST_MODE and 'submit' in actual_text.lower():
                        print(f"  [TEST MODE] Would click: '{actual_text}'")
                        return True
                    stealth_click(btn)
                    print(f"  Clicked: '{actual_text}'")
                    return True
        except Exception:
            pass

    # === PRIORITY 3: CSS class patterns from working bots ===
    class_selectors = [
        # From working bot — these are Indeed SmartApply's actual CSS classes
        ".css-1gljdq7",   # Continue button
        ".css-10w34ze",   # Qualifications continue
        ".css-njr1op",    # Submit button
        # Standard class patterns
        "button.ia-continueButton",
        "button.ia-submitButton",
        "button[data-testid='continueButton']",
        "button[data-testid='submitButton']",
        "button[class*='continue']",
        "button[class*='Continue']",
        "button[type='submit']",
    ]

    for sel in class_selectors:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, sel)
            for btn in buttons:
                if btn.is_displayed() and btn.is_enabled():
                    actual_text = (btn.text.strip() or btn.get_attribute("aria-label") or "").lower()
                    # Safety: never click Apply Now or Search
                    if "apply" in actual_text and "now" in actual_text:
                        continue
                    if "search" in actual_text:
                        continue
                    if TEST_MODE and 'submit' in actual_text:
                        print(f"  [TEST MODE] Would click: '{actual_text}'")
                        return True
                    stealth_click(btn)
                    print(f"  Clicked (CSS): '{actual_text}'")
                    return True
        except Exception:
            continue

    # === DEBUG: Show what buttons ARE visible ===
    try:
        all_btns = driver.find_elements(By.TAG_NAME, "button")
        visible = [(b.text.strip(), b.get_attribute("id") or "") for b in all_btns if b.is_displayed() and (b.text.strip() or b.get_attribute("id"))]
        if visible:
            print(f"  DEBUG visible buttons: {visible[:8]}")
    except Exception:
        pass

    return False


def answer_screening_questions():
    """Answer screening questions using Indeed's actual HTML structure.
    
    Three phases:
    1. Indeed-native: Use ia-Questions-item containers with [id^='input-q'] inputs
       (this is what the working bots use)
    2. Standard form: fieldset/radio/select elements
    3. AI fallback: Read page text and ask Gemini what to click
    """
    import json as json_mod

    handled = 0

    # === PHASE 1: Indeed-native question containers (from working bot) ===
    try:
        questions = driver.find_elements(By.CLASS_NAME, "ia-Questions-item")
        if not questions:
            # Also try SmartApply's question containers
            questions = driver.find_elements(By.CSS_SELECTOR, 
                "div[class*='Questions-item'], div[class*='question-item'], "
                "div[data-testid*='question'], fieldset")
        
        if questions:
            print(f"  Found {len(questions)} question containers")
            for q in questions:
                try:
                    # Get question text
                    q_text = ""
                    try:
                        q_text_el = q.find_element(By.CSS_SELECTOR, 
                            ".css-kyg8or, [class*='question-text'], legend, label, span[id*='label']")
                        q_text = q_text_el.text.lower().strip()
                    except Exception:
                        q_text = q.text.lower().strip()[:200]
                    
                    if not q_text:
                        continue

                    # Try to find and fill text input within this question
                    text_input = None
                    try:
                        text_input = q.find_element(By.CSS_SELECTOR, "[id^='input-q']")
                    except Exception:
                        try:
                            text_input = q.find_element(By.CSS_SELECTOR, 
                                "input[type='text'], input[type='number'], input[type='tel'], textarea")
                        except Exception:
                            pass

                    # Try to find radio/option elements within this question  
                    has_radios = False
                    try:
                        radios = q.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                        if radios:
                            has_radios = True
                    except Exception:
                        pass

                    # === HARDCODED ANSWERS (instant, free) ===
                    answered = False

                    # Work authorization
                    if any(kw in q_text for kw in ['authorized to work', 'authorization', 'authorised', 'right to work']):
                        if has_radios:
                            answered = _click_option_in_container(q, "Yes")
                        elif text_input:
                            stealth_type(text_input, "Yes")
                            answered = True

                    # Sponsorship
                    elif 'sponsorship' in q_text:
                        if has_radios:
                            answered = _click_option_in_container(q, "No")
                        elif text_input:
                            stealth_type(text_input, "No")
                            answered = True

                    # Experience questions
                    elif 'experience' in q_text and text_input:
                        years = str(PROFILE.get("experience", {}).get("total_years", 7))
                        # Check for specific skill mentions
                        for skill, yrs in PROFILE.get("experience", {}).get("skill_years", {}).items():
                            if skill != "default" and skill in q_text:
                                years = str(yrs)
                                break
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(years)
                        print(f"  Answered experience: {years} years")
                        answered = True

                    # Salary
                    elif 'salary' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(str(PROFILE.get("preferences", {}).get("salary", 85000)))
                        answered = True

                    # Phone
                    elif 'phone' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(p('personal', 'phone'))
                        answered = True

                    # Address
                    elif 'address' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(p('personal', 'address'))
                        answered = True

                    # City
                    elif 'city' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(p('personal', 'city'))
                        answered = True

                    # State
                    elif 'state' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(p('personal', 'state'))
                        answered = True

                    # Zip / postal
                    elif ('postal' in q_text or 'zip' in q_text) and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(p('personal', 'zip'))
                        answered = True

                    # LinkedIn
                    elif 'linkedin' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(p('personal', 'linkedin'))
                        answered = True

                    # Commute / travel / relocation
                    elif any(kw in q_text for kw in ['commute', 'travel', 'relocate']):
                        answered = _click_option_in_container(q, "Yes")

                    # Shift / schedule
                    elif 'shift' in q_text or 'schedule' in q_text:
                        answered = _click_option_in_container(q, "Yes")

                    # Criminal
                    elif 'criminal' in q_text:
                        answered = _click_option_in_container(q, "No")

                    # Veteran
                    elif 'veteran' in q_text:
                        answered = _click_option_in_container(q, "Yes")

                    # Disability
                    elif 'disability' in q_text or 'disabilities' in q_text:
                        dis_answer = PROFILE.get("screening_defaults", {}).get("disability", "Prefer not to answer")
                        answered = _click_option_in_container(q, dis_answer) or \
                                   _click_option_in_container(q, "Prefer not to answer") or \
                                   _click_option_in_container(q, "No")

                    # Education level
                    elif 'level of education' in q_text or 'highest degree' in q_text:
                        edu_answer = PROFILE.get("screening_defaults", {}).get("education_level", "Master's Degree")
                        answered = _click_option_in_container(q, edu_answer) or \
                                   _click_option_in_container(q, "Master") or \
                                   _click_option_in_container(q, "Master's")

                    # Gender
                    elif 'gender' in q_text:
                        gender_answer = PROFILE.get("screening_defaults", {}).get("gender", "Prefer not to answer")
                        answered = _click_option_in_container(q, gender_answer) or \
                                   _click_option_in_container(q, "Prefer not to answer")

                    # Race / Ethnicity (radio, dropdown, or checkbox)
                    elif any(kw in q_text for kw in ['race', 'ethnicity', 'ethnic background', 'racial']):
                        sd = PROFILE.get("screening_defaults", {})
                        race_answer = sd.get("race_ethnicity", "Other")
                        fallbacks = sd.get("race_ethnicity_fallbacks", 
                            ["Other", "Two or More Races", "White", "Prefer not to answer", "Decline to answer"])
                        
                        # Try primary answer first
                        answered = _click_option_in_container(q, race_answer)
                        
                        # Try fallbacks
                        if not answered:
                            for fb in fallbacks:
                                answered = _click_option_in_container(q, fb)
                                if answered:
                                    break

                        # Handle dropdown select elements within this question
                        if not answered:
                            try:
                                select_el = q.find_element(By.TAG_NAME, "select")
                                if select_el:
                                    options = select_el.find_elements(By.TAG_NAME, "option")
                                    # Try each fallback against dropdown options
                                    for target in [race_answer] + fallbacks:
                                        for opt in options:
                                            if target.lower() in opt.text.strip().lower():
                                                opt.click()
                                                print(f"  Selected dropdown race/ethnicity: '{opt.text.strip()}'")
                                                answered = True
                                                break
                                        if answered:
                                            break
                            except Exception:
                                pass

                        # Text input fallback
                        if not answered and text_input:
                            text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                            text_input.send_keys(race_answer)
                            answered = True

                    # How did you hear / how did you learn
                    elif 'hear about' in q_text or 'learn about' in q_text or 'how did you find' in q_text:
                        how_heard = PROFILE.get("preferences", {}).get("how_heard", "Indeed")
                        answered = _click_option_in_container(q, how_heard) or \
                                   _click_option_in_container(q, "Indeed") or \
                                   _click_option_in_container(q, "Job Board") or \
                                   _click_option_in_container(q, "Online")

                    # Are you an employee of [company]
                    elif ('employee' in q_text and ('are you' in q_text or 'current' in q_text)):
                        answered = _click_option_in_container(q, "No")

                    # Drug test / background check
                    elif any(kw in q_text for kw in ['drug test', 'background check', 'background screening']):
                        answered = _click_option_in_container(q, "Yes")

                    # Security Clearance questions
                    elif any(kw in q_text for kw in ['clearance', 'security clearance', 'ts/sci', 'top secret', 'secret clearance', 'public trust']):
                        sc = PROFILE.get("security_clearance", {})
                        cl_level = sc.get("level", "None")
                        has_cl = sc.get("has_clearance", False)
                        active = sc.get("active", False)
                        can_obtain = sc.get("able_to_obtain", False)

                        # "Do you have a security clearance?" — Yes/No
                        if 'do you have' in q_text or 'do you hold' in q_text or 'do you possess' in q_text:
                            if has_cl and active:
                                answered = _click_option_in_container(q, "Yes")
                            elif can_obtain:
                                # Try "Able to obtain" first, then "No"
                                answered = _click_option_in_container(q, "Able to obtain") or \
                                           _click_option_in_container(q, "Willing to obtain") or \
                                           _click_option_in_container(q, "Can obtain") or \
                                           _click_option_in_container(q, "No, but able to obtain") or \
                                           _click_option_in_container(q, "No")
                            else:
                                answered = _click_option_in_container(q, "No")

                        # "What level clearance?" — dropdown or radio
                        elif 'level' in q_text or 'what' in q_text:
                            if has_cl:
                                answered = _click_option_in_container(q, cl_level) or \
                                           _click_option_in_container(q, cl_level.replace("/", " / "))
                            else:
                                answered = _click_option_in_container(q, "None") or \
                                           _click_option_in_container(q, "No clearance") or \
                                           _click_option_in_container(q, "N/A")

                        # "Is it active?" 
                        elif 'active' in q_text:
                            answered = _click_option_in_container(q, "Yes" if active else "No")

                        # "Do you have a valid TS/SCI with Polygraph?"
                        elif 'polygraph' in q_text or 'poly' in q_text:
                            poly = sc.get("polygraph", False)
                            answered = _click_option_in_container(q, "Yes" if poly else "No")

                        # Text input for clearance
                        elif text_input:
                            if has_cl and active:
                                text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                                text_input.send_keys(cl_level)
                            else:
                                text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                                text_input.send_keys(sc.get("notes", "Able to obtain"))
                            answered = True

                        if answered:
                            print(f"  Clearance Q: '{q_text[:50]}' -> answered")

                    # Citizenship (multi-option like US Citizen, Canadian Citizen, etc.)
                    elif 'citizen' in q_text or 'citizenship' in q_text:
                        answered = _click_option_in_container(q, "US Citizen") or \
                                   _click_option_in_container(q, "United States") or \
                                   _click_option_in_container(q, "Yes")

                    # Available to start / start date
                    elif 'available' in q_text and ('start' in q_text or 'when' in q_text):
                        if text_input:
                            text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                            text_input.send_keys(PROFILE.get("experience", {}).get("available_start", "2 weeks notice"))
                            answered = True

                    # Interview availability
                    elif 'interview' in q_text and text_input:
                        text_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                        text_input.send_keys(PROFILE.get("preferences", {}).get("interview_availability", "Available anytime"))
                        answered = True

                    # Default: if text input, put default; if radio, skip for AI
                    if not answered and text_input:
                        current_val = (text_input.get_attribute("value") or "").strip()
                        if not current_val:
                            # Leave for AI solver
                            pass

                    if answered:
                        handled += 1
                        human_delay(0.3, 0.8)

                except Exception as e:
                    print(f"  Error on question: {e}")
                    continue

            print(f"  Phase 1 (Indeed-native): answered {handled} questions")
    except Exception as e:
        print(f"  Phase 1 error: {e}")

    # === PHASE 2: AI Form Solver for anything remaining ===
    print(f"  Calling AI Form Solver (hardcoded handled {handled})...")
    ai_form_solver()

    # === Count what's still unanswered ===
    remaining = count_unanswered_fields()
    if remaining > 0:
        print(f"  *** {remaining} question(s) still unanswered after AI solver ***")
    return remaining


def _click_option_in_container(container, option_text):
    """Click a radio/option/label within a question container by text match.
    This mirrors the working bot's approach: find element by text within the question div."""
    
    # Strategy 1: XPath text match within container (what the working bot does)
    try:
        el = container.find_element(By.XPATH, f'.//*[contains(text(), "{option_text}")]')
        driver.execute_script("arguments[0].click();", el)
        print(f"  Clicked option: '{option_text}'")
        return True
    except Exception:
        pass

    # Strategy 2: Case-insensitive match
    try:
        all_elements = container.find_elements(By.XPATH, ".//*")
        for el in all_elements:
            if el.text.strip().lower() == option_text.lower():
                driver.execute_script("arguments[0].click();", el)
                print(f"  Clicked option (ci): '{option_text}'")
                return True
    except Exception:
        pass

    # Strategy 3: Partial text match (e.g., "Master" matches "Master's Degree")
    try:
        all_elements = container.find_elements(By.XPATH, ".//*")
        for el in all_elements:
            el_text = el.text.strip().lower()
            if option_text.lower() in el_text and len(el_text) < len(option_text) * 3:
                driver.execute_script("arguments[0].click();", el)
                print(f"  Clicked option (partial): '{el.text.strip()}'")
                return True
    except Exception:
        pass

    # Strategy 4: Click radio input by label for= matching
    try:
        radios = container.find_elements(By.CSS_SELECTOR, "input[type='radio']")
        for r in radios:
            try:
                r_id = r.get_attribute("id")
                if r_id:
                    lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{r_id}']")
                    if option_text.lower() in lbl.text.lower():
                        driver.execute_script("arguments[0].click();", r)
                        print(f"  Clicked radio: '{lbl.text.strip()}'")
                        return True
            except Exception:
                continue
    except Exception:
        pass

    return False


def count_unanswered_fields():
    """Count how many visible form fields are still empty/unanswered."""
    count = 0
    try:
        # Empty text/number inputs
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='text'], input[type='number'], textarea"):
            try:
                if inp.is_displayed() and inp.is_enabled():
                    val = (inp.get_attribute("value") or "").strip()
                    if not val:
                        count += 1
            except Exception:
                continue

        # Unchecked radio groups (check if any radio in a fieldset is selected)
        for fs in driver.find_elements(By.CSS_SELECTOR, "fieldset, div[role='group']"):
            try:
                radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                if radios and not any(r.is_selected() for r in radios):
                    count += 1
            except Exception:
                continue

        # Selects still on placeholder
        for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
            try:
                if sel.is_displayed():
                    selected = sel.find_elements(By.CSS_SELECTOR, "option:checked")
                    if selected:
                        val = selected[0].text.strip().lower()
                        if val in ["", "select", "select one", "choose", "--", "please select"]:
                            count += 1
            except Exception:
                continue
    except Exception:
        pass
    return count


def scrape_form_fields():
    """Extract all visible form elements with their labels, types, and options.
    Returns a structured list that can be sent to Gemini."""
    fields = []
    field_id = 0

    try:
        # Text inputs and textareas (including Indeed's input-q pattern)
        for inp in driver.find_elements(By.CSS_SELECTOR, 
            "input[type='text'], input[type='number'], input[type='tel'], "
            "input[type='email'], textarea, [id^='input-q']"):
            try:
                if not inp.is_displayed() or not inp.is_enabled():
                    continue
                current_val = (inp.get_attribute("value") or "").strip()

                # Get label
                label_text = ""
                try:
                    inp_id = inp.get_attribute("id")
                    if inp_id:
                        lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                        label_text = lbl.text.strip()
                except Exception:
                    pass
                if not label_text:
                    label_text = (inp.get_attribute("aria-label") or 
                                  inp.get_attribute("placeholder") or
                                  inp.get_attribute("name") or "")
                if not label_text:
                    try:
                        parent = inp.find_element(By.XPATH, "./..")
                        label_text = parent.text.strip()[:100]
                    except Exception:
                        pass

                fields.append({
                    "id": f"field_{field_id}",
                    "type": "text",
                    "input_type": inp.get_attribute("type") or "text",
                    "label": label_text,
                    "current_value": current_val,
                    "element_id": inp.get_attribute("id") or "",
                    "element_name": inp.get_attribute("name") or "",
                })
                field_id += 1
            except Exception:
                continue

        # Radio button groups
        seen_groups = set()
        for fs in driver.find_elements(By.CSS_SELECTOR, 
            "fieldset, div[role='group'], div[class*='question'], "
            ".ia-Questions-item, div[class*='Questions-item']"):
            try:
                radios = fs.find_elements(By.CSS_SELECTOR, "input[type='radio']")
                if not radios:
                    continue

                group_name = radios[0].get_attribute("name") or ""
                if group_name in seen_groups:
                    continue
                seen_groups.add(group_name)

                question = fs.text.strip()[:200]
                options = []
                selected = None
                for r in radios:
                    opt_label = ""
                    try:
                        r_id = r.get_attribute("id")
                        lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{r_id}']")
                        opt_label = lbl.text.strip()
                    except Exception:
                        opt_label = r.get_attribute("value") or ""
                    options.append(opt_label)
                    if r.is_selected():
                        selected = opt_label

                fields.append({
                    "id": f"field_{field_id}",
                    "type": "radio",
                    "label": question,
                    "options": options,
                    "current_value": selected,
                    "group_name": group_name,
                })
                field_id += 1
            except Exception:
                continue

        # Select dropdowns
        for sel in driver.find_elements(By.CSS_SELECTOR, "select"):
            try:
                if not sel.is_displayed():
                    continue

                label_text = ""
                try:
                    sel_id = sel.get_attribute("id")
                    if sel_id:
                        lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{sel_id}']")
                        label_text = lbl.text.strip()
                except Exception:
                    label_text = sel.get_attribute("aria-label") or sel.get_attribute("name") or ""

                options = []
                current = None
                for opt in sel.find_elements(By.TAG_NAME, "option"):
                    opt_text = opt.text.strip()
                    if opt_text:
                        options.append(opt_text)
                    if opt.is_selected():
                        current = opt_text

                fields.append({
                    "id": f"field_{field_id}",
                    "type": "select",
                    "label": label_text,
                    "options": options,
                    "current_value": current,
                    "element_id": sel.get_attribute("id") or "",
                })
                field_id += 1
            except Exception:
                continue

        # Checkboxes
        for cb in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
            try:
                if not cb.is_displayed():
                    continue
                label_text = ""
                try:
                    cb_id = cb.get_attribute("id")
                    if cb_id:
                        lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{cb_id}']")
                        label_text = lbl.text.strip()
                except Exception:
                    try:
                        parent = cb.find_element(By.XPATH, "./..")
                        label_text = parent.text.strip()[:100]
                    except Exception:
                        pass

                fields.append({
                    "id": f"field_{field_id}",
                    "type": "checkbox",
                    "label": label_text,
                    "current_value": cb.is_selected(),
                    "element_id": cb.get_attribute("id") or "",
                })
                field_id += 1
            except Exception:
                continue

    except Exception as e:
        print(f"  Form scrape error: {e}")

    return fields


def ai_form_solver():
    """Use Gemini to answer any form questions on the current page.
    
    Two modes:
    1. STRUCTURED: Scrapes form fields -> sends JSON -> executes by element ID
    2. PAGE TEXT (fallback): Reads full page text -> Gemini says which labels to click
    
    Mode 2 handles SmartApply's custom React components.
    """
    import json as json_mod

    fields = scrape_form_fields()
    
    unanswered = []
    for f in fields:
        if f["type"] == "text" and f.get("current_value"):
            continue
        if f["type"] == "radio" and f.get("current_value"):
            continue
        if f["type"] == "select" and f.get("current_value") and \
           f["current_value"].lower() not in ["", "select", "select one", "--", "please select"]:
            continue
        unanswered.append(f)

    if unanswered:
        print(f"  AI Solver: {len(unanswered)} unanswered fields (structured mode)")
        _ai_solve_structured(unanswered, json_mod)
    else:
        print(f"  AI Solver: No standard fields found. Using page-text mode...")
        _ai_solve_by_page_text(json_mod)


def _ai_solve_structured(unanswered, json_mod):
    """Structured mode: send scraped form fields as JSON to Gemini."""
    fields_json = json_mod.dumps(unanswered, indent=2)
    prompt = f"""You are filling out a job application form for {full_name()}.

CANDIDATE INFO:
{candidate_info_block()}

FORM FIELDS:
{fields_json}

RULES:
- For radio buttons: reply with EXACT text of the option to select
- For dropdowns: reply with EXACT text of the option to pick  
- For text fields: reply with text to type
- For salary questions: use industry average or {PROFILE.get('preferences', {}).get('salary', 85000)}
- If multiple work auth options (US Citizen, Canadian Citizen, etc.): pick "{PROFILE.get('work_authorization', {}).get('citizenship_answer', 'US Citizen')}"
- If unsure: pick the most positive/reasonable answer

Reply ONLY with a JSON array: [{{"id": "field_X", "answer": "exact answer"}}]
No explanation. No markdown fences."""

    response_text = call_gemini(prompt)
    if not response_text:
        print("  AI Solver: Gemini returned nothing.")
        return

    try:
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        answers = json_mod.loads(clean)
    except Exception as e:
        print(f"  AI Solver: Parse error: {e}")
        return

    if not isinstance(answers, list):
        return

    answer_map = {a["id"]: a["answer"] for a in answers if isinstance(a, dict) and "id" in a and "answer" in a}
    print(f"  AI Solver: Got {len(answer_map)} answers. Applying...")

    for field in unanswered:
        fid = field["id"]
        answer = answer_map.get(fid)
        if answer is None:
            continue
        try:
            if field["type"] == "text":
                inp = None
                if field.get("element_id"):
                    try: inp = driver.find_element(By.ID, field["element_id"])
                    except: pass
                if not inp and field.get("element_name"):
                    try: inp = driver.find_element(By.NAME, field["element_name"])
                    except: pass
                if inp and inp.is_displayed() and inp.is_enabled():
                    if not (inp.get_attribute("value") or "").strip():
                        stealth_type(inp, str(answer))
                        print(f"    AI filled '{field['label'][:40]}' -> '{answer}'")
                        human_delay(0.3, 0.6)
            elif field["type"] == "radio":
                _click_radio_by_label(field.get("group_name", ""), str(answer))
            elif field["type"] == "select":
                if field.get("element_id"):
                    try:
                        sel = driver.find_element(By.ID, field["element_id"])
                        for opt in sel.find_elements(By.TAG_NAME, "option"):
                            if opt.text.strip().lower() == str(answer).lower():
                                opt.click()
                                print(f"    AI selected '{answer}'")
                                break
                    except: pass
            elif field["type"] == "checkbox":
                if field.get("element_id"):
                    try:
                        cb = driver.find_element(By.ID, field["element_id"])
                        if str(answer).lower() in ["true", "yes", "1"] and not cb.is_selected():
                            driver.execute_script("arguments[0].click();", cb)
                            print(f"    AI checked '{field['label'][:40]}'")
                    except: pass
        except Exception as e:
            print(f"    AI error on {fid}: {e}")

    print(f"  AI Solver (structured) complete.")


def _ai_solve_by_page_text(json_mod):
    """Page-text mode: read visible page text and ask Gemini what to click.
    Handles SmartApply's custom React components that don't use standard HTML inputs."""
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text
    except Exception:
        print("  AI Solver: Could not read page text.")
        return

    if len(page_text) < 20:
        print("  AI Solver: Page text too short.")
        return

    page_text = page_text[:3000]

    prompt = f"""You are filling out a job application on Indeed for {full_name()}.
Below is the text visible on the current page. Determine what needs to be answered.

CANDIDATE INFO:
{candidate_info_block()}

PAGE TEXT:
{page_text}

For each question, tell me EXACTLY which option to click or what to type.

Reply ONLY with a JSON array:
- To click a radio/option: {{"action": "click_label", "label": "exact visible text"}}
- To type into a field: {{"action": "type", "label": "field label", "value": "text to type"}}
- If no questions (just info page): {{"action": "none"}}

CRITICAL: "label" must match EXACTLY what appears on the page.

Example: [
  {{"action": "click_label", "label": "No"}},
  {{"action": "click_label", "label": "Indeed"}},
  {{"action": "click_label", "label": "US Citizen"}}
]

JSON ONLY."""

    response_text = call_gemini(prompt)
    if not response_text:
        return

    try:
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = re.sub(r'^```\w*\n?', '', clean)
            clean = re.sub(r'\n?```$', '', clean)
        actions = json_mod.loads(clean)
    except Exception as e:
        print(f"  AI Solver: Parse error: {e}")
        return

    if not isinstance(actions, list):
        return

    print(f"  AI Solver: {len(actions)} actions from page text. Executing...")

    for action in actions:
        if not isinstance(action, dict):
            continue
        act_type = action.get("action", "")
        if act_type == "none":
            print("  AI Solver: No questions on this page.")
            break
        elif act_type == "click_label":
            label = action.get("label", "")
            if label:
                clicked = _click_element_by_visible_text(label)
                if clicked:
                    print(f"    AI clicked: '{label}'")
                    human_delay(0.3, 0.8)
                else:
                    print(f"    AI could not find: '{label}'")
        elif act_type == "type":
            label = action.get("label", "")
            value = action.get("value", "")
            if value:
                typed = _type_into_field_by_label(label, value)
                if typed:
                    print(f"    AI typed '{value}' into '{label[:30]}'")
                    human_delay(0.3, 0.6)
                else:
                    print(f"    AI could not find field: '{label[:30]}'")

    print(f"  AI Solver (page-text) complete.")


def _click_element_by_visible_text(label_text):
    """Find and click any element containing the exact label text."""
    # Strategy 1: Click label elements (activates associated radio/checkbox)
    try:
        for lbl in driver.find_elements(By.TAG_NAME, "label"):
            if lbl.text.strip().lower() == label_text.lower():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", lbl)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", lbl)
                return True
    except Exception:
        pass

    # Strategy 2: Exact text match on any element
    for tag in ["label", "span", "div", "li", "p", "button"]:
        try:
            elements = driver.find_elements(By.XPATH, f"//{tag}[normalize-space(.)='{label_text}']")
            for el in elements:
                if el.is_displayed():
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", el)
                    return True
        except Exception:
            continue

    # Strategy 3: Contains match (for slight differences)
    try:
        elements = driver.find_elements(By.XPATH, f"//*[contains(normalize-space(.),'{label_text}')]")
        for el in elements:
            if el.is_displayed() and len(el.text.strip()) < len(label_text) * 2:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", el)
                return True
    except Exception:
        pass

    # Strategy 4: Radio inputs by label or value
    try:
        for inp in driver.find_elements(By.CSS_SELECTOR, "input[type='radio'], input[type='checkbox']"):
            try:
                inp_id = inp.get_attribute("id")
                if inp_id:
                    lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{inp_id}']")
                    if lbl.text.strip().lower() == label_text.lower():
                        driver.execute_script("arguments[0].click();", inp)
                        return True
                if (inp.get_attribute("value") or "").lower() == label_text.lower():
                    driver.execute_script("arguments[0].click();", inp)
                    return True
            except Exception:
                continue
    except Exception:
        pass
    return False


def _type_into_field_by_label(label_text, value):
    """Find a text input near a label and type into it."""
    try:
        for lbl in driver.find_elements(By.TAG_NAME, "label"):
            if label_text.lower() in lbl.text.lower():
                for_id = lbl.get_attribute("for")
                if for_id:
                    try:
                        inp = driver.find_element(By.ID, for_id)
                        if inp.is_displayed():
                            stealth_type(inp, value)
                            return True
                    except Exception:
                        pass
                try:
                    inp = lbl.find_element(By.CSS_SELECTOR, "input, textarea")
                    if inp.is_displayed():
                        stealth_type(inp, value)
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    try:
        for inp in driver.find_elements(By.CSS_SELECTOR, "input, textarea"):
            if not inp.is_displayed():
                continue
            attrs = " ".join([
                inp.get_attribute("placeholder") or "",
                inp.get_attribute("aria-label") or "",
                inp.get_attribute("name") or "",
            ]).lower()
            if any(word in attrs for word in label_text.lower().split()[:3]):
                stealth_type(inp, value)
                return True
    except Exception:
        pass
    return False


def _click_radio_by_label(group_name, answer_text):
    """Click a radio button matching the answer text."""
    try:
        radios = driver.find_elements(By.CSS_SELECTOR,
            f"input[name='{group_name}']" if group_name else "input[type='radio']")
        for r in radios:
            try:
                r_id = r.get_attribute("id")
                if r_id:
                    lbl = driver.find_element(By.CSS_SELECTOR, f"label[for='{r_id}']")
                    if lbl.text.strip().lower() == answer_text.lower():
                        driver.execute_script("arguments[0].click();", r)
                        print(f"    AI clicked radio: '{answer_text}'")
                        return True
            except Exception:
                if (r.get_attribute("value") or "").lower() == answer_text.lower():
                    driver.execute_script("arguments[0].click();", r)
                    print(f"    AI clicked radio: '{answer_text}'")
                    return True
    except Exception:
        pass
    return _click_element_by_visible_text(answer_text)



# ==============================
# JOB COLLECTION
# ==============================

def collect_job_cards():
    """Collect job cards from Indeed search results.
    
    Indeed uses two approaches:
    1. Embedded JSON in window.mosaic.providerData (most reliable)
    2. DOM selectors: a.tapItem for cards, h2.jobTitle>span for titles
    """
    human_delay(2, 4)

    current_url = driver.current_url
    if 'employers.indeed.com' in current_url or 'resumes.indeed.com' in current_url:
        print("  ERROR: Not on job search page!")
        return []

    job_cards = []

    # === STRATEGY 1: Parse embedded JSON (most reliable) ===
    try:
        page_source = driver.page_source
        import json as json_mod
        match = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.+?\});',
            page_source
        )
        if match:
            data = json_mod.loads(match.group(1))
            results = data.get("metaData", {}).get("mosaicProviderJobCardsModel", {}).get("results", [])
            print(f"  Parsed {len(results)} jobs from embedded JSON")
            for r in results:
                jk = r.get("jobkey", "")
                title = r.get("title", "")
                company = r.get("company", "")
                location = r.get("jobLocationCity", "") or r.get("formattedLocation", "")
                # Build the job view URL
                url = f"https://www.indeed.com/viewjob?jk={jk}" if jk else ""
                easy = r.get("indeedApplyEnabled", False) or r.get("indeedApply", False)

                if title and jk:
                    job_cards.append({
                        'jk': jk,
                        'url': url,
                        'title': title,
                        'company': company,
                        'location': location,
                        'easy_apply': easy,
                        'from_json': True,
                    })
            if job_cards:
                return job_cards
    except Exception as e:
        print(f"  JSON parse failed: {e}")

    # === STRATEGY 2: DOM selectors (fallback) ===
    # Indeed's main card selector is a.tapItem or div.job_seen_beacon
    card_selectors = [
        ("a.tapItem", "h2.jobTitle > span", "span.companyName"),
        ("div.job_seen_beacon", "h2.jobTitle a", "span.companyName"),
        ("div.cardOutline", "h2 a", "span.companyName"),
        ("td.resultContent", "h2.jobTitle a", "span.companyName"),
    ]

    for card_sel, title_sel, comp_sel in card_selectors:
        try:
            cards = driver.find_elements(By.CSS_SELECTOR, card_sel)
            if not cards:
                continue
            print(f"  Found {len(cards)} cards using: {card_sel}")

            for card in cards:
                try:
                    # Get title
                    title = ""
                    try:
                        title_el = card.find_element(By.CSS_SELECTOR, title_sel)
                        title = title_el.text.strip()
                    except Exception:
                        try:
                            title_el = card.find_element(By.CSS_SELECTOR, "h2")
                            title = title_el.text.strip()
                        except Exception:
                            pass

                    if not title:
                        continue

                    # Get company
                    company = ""
                    try:
                        comp_el = card.find_element(By.CSS_SELECTOR, comp_sel)
                        company = comp_el.text.strip()
                    except Exception:
                        pass

                    # Get job key from data attribute or href
                    jk = ""
                    try:
                        jk = card.get_attribute("data-jk") or ""
                    except Exception:
                        pass
                    if not jk:
                        try:
                            link = card.find_element(By.CSS_SELECTOR, "a[data-jk]")
                            jk = link.get_attribute("data-jk") or ""
                        except Exception:
                            pass

                    job_cards.append({
                        'element': card,
                        'title': title,
                        'company': company,
                        'jk': jk,
                        'url': f"https://www.indeed.com/viewjob?jk={jk}" if jk else "",
                        'from_json': False,
                    })
                except Exception:
                    continue

            if job_cards:
                break
        except Exception:
            continue

    # === STRATEGY 3: Handshake job cards ===
    if 'joinhandshake.com' in current_url:
        try:
            selectors = [
                "a[href*='/stu/jobs/']",
                "a[href*='/jobs/']",
                "div[data-hook='job-card']",
                "div[class*='JobCard']",
                "div[class*='style__job-card']",
                "div[class*='style__card']",
                "a[class*='card']"
            ]
            seen_urls = set()
            for sel in selectors:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elements:
                    try:
                        href = el.get_attribute("href") or ""
                        if not href:
                            try:
                                link_child = el.find_element(By.CSS_SELECTOR, "a[href*='/jobs/']")
                                href = link_child.get_attribute("href") or ""
                            except Exception:
                                pass

                        # Must match a real Handshake job posting URL pattern
                        if href:
                            if not re.search(r'/jobs/\d+', href) and not re.search(r'/stu/jobs/\d+', href) and not re.search(r'/jobs/[a-zA-Z0-9_-]+', href):
                                continue
                            if any(ignore in href for ignore in ["/employers/", "/events/", "/messages/", "/career-center/", "/login", "/saved", "/explore"]):
                                continue

                        card_id = href or el.get_attribute("id") or str(hash(el.text[:50]))
                        if not card_id or card_id in seen_urls:
                            continue

                        seen_urls.add(card_id)
                        raw_text = el.text.strip()
                        if not raw_text or len(raw_text) < 3 or raw_text.lower() in ["jobs", "saved", "explore", "inbox", "search"]:
                            continue

                        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]
                        job_title = lines[0] if lines else "Job Position"
                        company_name = lines[1] if len(lines) > 1 else ""

                        job_cards.append({
                            'url': href,
                            'title': job_title,
                            'company': company_name,
                            'element': el,
                            'jk': href.split("/")[-1] if href else "hs_card",
                            'from_handshake': True
                        })
                    except Exception:
                        continue
                if job_cards:
                    print(f"  Collected {len(job_cards)} Handshake jobs using selector: {sel}")
                    return job_cards
        except Exception as e:
            print(f"  Handshake collection error: {e}")

    if not job_cards:
        print("  NO JOBS FOUND. Debug info:")
        print(f"  URL: {driver.current_url}")
        try:
            page_text = driver.find_element(By.TAG_NAME, "body").text[:300]
            print(f"  Body preview: {page_text}...")
        except Exception:
            pass

    return job_cards


# ==============================
# PROCESS PAGE
# ==============================

def process_page():
    """Process all jobs on the current Indeed or Handshake search results page."""
    global total_applied
    list_url = driver.current_url
    print(f"\nSaved search URL: {list_url[:80]}")

    if 'joinhandshake.com' in list_url and '/stu/jobs' not in list_url and '/jobs' not in list_url and 'job-search' not in list_url:
        print("  Navigating from Handshake home page to Handshake Jobs search page...")
        target_jobs_url = "https://app.joinhandshake.com/stu/jobs"
        if '.joinhandshake.com' in list_url:
            subdomain = list_url.split('.joinhandshake.com')[0]
            target_jobs_url = f"{subdomain}.joinhandshake.com/stu/jobs"
        driver.get(target_jobs_url)
        human_delay(3, 5)
        list_url = driver.current_url

    if 'employers.indeed.com' in list_url or 'resumes.indeed.com' in list_url:
        print("  ERROR: Not on job search page. Stopping.")
        return

    job_cards = collect_job_cards()
    total = len(job_cards)
    print(f"Collected {total} jobs from this page.")

    if total == 0:
        return

    for i, job in enumerate(job_cards):
        title = job['title']
        company = job.get('company', '')

        try:
            check_pause()
            print(f"\n{'='*50}")
            print(f"[{i+1}/{total}] {title}" + (f" @ {company}" if company else ""))
            print(f"Total applied so far: {total_applied}")
            print(f"Time: {datetime.now().strftime('%I:%M %p')}")
            print(f"{'='*50}")

            # Click the job card to load details
            try:
                if job.get('from_handshake'):
                    card_element = job.get('element')
                    clicked = False
                    if card_element:
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_element)
                            human_delay(0.5, 1)
                            stealth_click(card_element)
                            print(f"  Clicked Handshake job card element.")
                            human_delay(2, 3)
                            clicked = True
                        except Exception:
                            pass
                    if not clicked and job.get('url'):
                        driver.get(job['url'])
                        print(f"  Navigated to Handshake job URL: {job['url'][:60]}")
                        human_delay(3, 5)
                elif job.get('from_json') and job.get('url'):
                    # JSON-sourced: navigate directly to job URL
                    driver.get(job['url'])
                    print(f"  Navigated to job page.")
                    human_delay(3, 5)
                elif job.get('jk'):
                    jk = job.get('jk')
                    # Re-find by data-jk to avoid stale element references
                    card_elements = driver.find_elements(By.CSS_SELECTOR, f"[data-jk='{jk}']")
                    if card_elements:
                        card_element = card_elements[0]
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_element)
                        human_delay(0.5, 1)
                        stealth_click(card_element)
                        print(f"  Clicked job card (fresh lookup by jk={jk}).")
                        human_delay(2, 4)
                    elif job.get('url'):
                        driver.get(job['url'])
                        print(f"  Card stale, navigated by URL instead.")
                        human_delay(3, 5)
                    else:
                        print(f"  Could not find card jk={jk} — SKIPPING")
                        continue
                elif job.get('element'):
                    card_element = job.get('element')
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", card_element)
                    human_delay(0.5, 1)
                    stealth_click(card_element)
                    print(f"  Clicked job card (stored element).")
                    human_delay(2, 4)
                else:
                    print(f"  No valid link or element — SKIPPING")
                    continue
            except Exception as e:
                print(f"  Could not click job card: {e}")
                log_application(f"SKIPPED (click failed): {title}")
                continue

            # Wait for right pane / detail section to update
            try:
                WebDriverWait(driver, 6).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR,
                        "div[data-hook='job-description'], div[class*='description'], div[class*='Description'], main, button[aria-label*='Apply'], div.jobsearch-RightPane, div.jobsearch-ViewJobLayout, div#jobDescriptionText"
                    ))
                )
            except Exception:
                print("  Right pane load wait finished.")

            # Check if already applied
            if check_already_applied():
                print(f"  Already applied — SKIPPING: {title}")
                log_application(f"SKIPPED (already applied): {title}")
                continue

            # ===== CHECK FOR APPLY BUTTON FIRST (save time & tokens) =====
            human_delay(1, 2)

            if not has_easy_apply():
                print(f"  No Easy Apply button — SKIPPING: {title}")
                log_application(f"SKIPPED (no easy apply): {title}")
                continue

            print("  Easy Apply confirmed! Scraping job details...")

            # Scrape job description from the RIGHT pane
            jd = get_indeed_job_description()
            metadata = get_indeed_metadata()

            if len(jd) < 50:
                print(f"  Could not scrape job description — SKIPPING: {title}")
                log_application(f"SKIPPED (no JD): {title}")
                continue

            job_title = metadata.get('title', title)
            company = metadata.get('company', company)
            print(f"  Title: {job_title}")
            print(f"  Company: {company}")
            if 'location' in metadata:
                print(f"  Location: {metadata['location']}")

            job_kws = extract_keywords(jd)

            # NO UPFRONT DOC GENERATION — docs built on-demand when the app asks for them
            # This saves ~$0.003 per job that doesn't need a resume/cover letter upload
            print(f"  Keywords: {', '.join(job_kws[:8])}...")

            # Now click Apply
            human_delay(1, 2)

            apply_result = click_apply_button()
            if not apply_result:
                print(f"  Apply button gone — SKIPPING: {title}")
                log_application(f"SKIPPED (apply button gone): {title}")
                continue

            # Navigate the application flow — docs generated on-demand inside
            success, res_text, cl_text = handle_indeed_application(
                jd=jd, job_title=job_title, metadata=metadata, job_kws=job_kws)

            # ATS scoring (after docs are generated, if they were)
            best_score, best_found, best_total = 0, 0, len(job_kws)
            if res_text:
                rs, rf, rt, rm = calculate_match_score(res_text, job_kws)
                print(f"\n  >>> RESUME ATS: {rs}% ({rf}/{rt})")
                if rm:
                    print(f"  >>> Missed: {', '.join(rm[:5])}")
                best_score, best_found = rs, rf
            if cl_text:
                cs, cf, ct2, _ = calculate_match_score(cl_text, job_kws)
                print(f"  >>> COVER LETTER ATS: {cs}% ({cf}/{ct2})")
            if res_text and cl_text:
                xs, xf, _, xm = calculate_match_score(res_text + " " + cl_text, job_kws)
                print(f"  >>> COMBINED ATS: {xs}% ({xf}/{best_total})")
                best_score, best_found = xs, xf

            if success:
                if TEST_MODE:
                    print(f"\n  [TEST MODE] Would have submitted: {title}")
                    log_application(f"TEST MODE: {title}", best_score, best_found, best_total)
                else:
                    total_applied += 1
                    print(f"\n  SUCCESS: Applied to {title} at {company} (#{total_applied})")
                    log_application(f"SUCCESS: {title} @ {company}", best_score, best_found, best_total)
            else:
                print(f"\n  Could not complete application for: {title}")
                print(f"  (Documents saved locally - you can apply manually)")
                log_application(f"INCOMPLETE: {title}", best_score, best_found, best_total)

            # After applying, clean up: exit iframes, close tabs, return to search
            human_delay(1, 2)

            # Exit any iframes
            try:
                driver.switch_to.default_content()
            except Exception:
                pass

            # Close extra tabs if Apply opened one
            if len(driver.window_handles) > 1:
                main_handle = driver.window_handles[0]
                for handle in driver.window_handles[1:]:
                    driver.switch_to.window(handle)
                    driver.close()
                driver.switch_to.window(main_handle)
                print("  Closed extra tabs.")

            # If we navigated away from search results, go back
            if 'indeed.com/jobs' not in driver.current_url:
                print("  Navigating back to search results...")
                driver.get(list_url)
                human_delay(3, 5)

            # Close any Indeed apply modals that might be lingering
            try:
                close_btns = driver.find_elements(By.CSS_SELECTOR,
                    "button[aria-label='Close'], button[class*='close'], button[aria-label='Dismiss']"
                )
                for btn in close_btns:
                    if btn.is_displayed():
                        btn.click()
                        print("  Closed modal.")
                        human_delay(1, 2)
                        break
            except Exception:
                pass

            job_cooldown()

        except Exception as e:
            print(f"  Error on job {i+1}: {e}")
            log_application(f"ERROR: {title} - {str(e)[:50]}")
            # Try to get back to search results
            try:
                if 'indeed.com/jobs' not in driver.current_url:
                    driver.get(list_url)
                    human_delay(3, 5)
            except Exception:
                pass
            continue


# ==============================
# PAGINATION
# ==============================

def go_to_next_page():
    """Click the next page button on Indeed search results."""
    # Don't paginate if we're not on a search page
    current = driver.current_url
    if 'employers.indeed.com' in current or 'resumes.indeed.com' in current:
        print("Not on a job search page — cannot paginate.")
        return False
    if 'indeed.com/jobs' not in current and 'indeed.com/q-' not in current:
        print("Not on a search results page — cannot paginate.")
        return False

    try:
        smooth_scroll(2000)
        human_delay(1, 3)

        # Indeed pagination selectors
        next_selectors = [
            "a[data-testid='pagination-page-next']",
            "a[aria-label='Next Page']",
            "a[aria-label='Next']",
            # Indeed's nav with numbered pages — find the "next" arrow
            "nav[role='navigation'] a[aria-label='Next']",
        ]

        for sel in next_selectors:
            try:
                next_btn = driver.find_element(By.CSS_SELECTOR, sel)
                if next_btn.is_displayed():
                    stealth_click(next_btn)
                    print("Clicked Next Page.")
                    human_delay(3, 6)
                    return True
            except Exception:
                continue

        # Fallback: look for numbered page links in pagination nav
        try:
            nav = driver.find_element(By.CSS_SELECTOR, "nav[role='navigation'], ul.pagination-list")
            page_links = nav.find_elements(By.TAG_NAME, "a")
            # Find current page, then click the next one
            for i, link in enumerate(page_links):
                if 'aria-current' in (link.get_attribute('aria-current') or ''):
                    if i + 1 < len(page_links):
                        stealth_click(page_links[i + 1])
                        print(f"Clicked next page link.")
                        human_delay(3, 6)
                        return True
        except Exception:
            pass

        print("No more pages.")
        return False
    except Exception:
        print("No next page button found.")
        return False


# ==============================
# MAIN ENTRY POINT
# ==============================

def run_bot():
    global total_tokens_used

    # Start the pause listener thread
    listener = threading.Thread(target=pause_listener, daemon=True)
    listener.start()

    driver.get("https://www.indeed.com")

    print("\n" + "=" * 55)
    print("  INDEED STEALTH BOT v1.6")
    print("  AI Cover Letters + Tailored Resumes")
    print("  Anti-AI Detection + ATS Keyword Optimization")
    print("  Apply-First: Skips jobs with no Easy Apply")
    print(f"  Profile: {full_name()}")
    if SKIP_COOLDOWN:
        print("  Cooldown: DISABLED (fast mode)")
    else:
        print("  Cooldown: 3-7 min between applications")
    if TEST_MODE:
        print("  *** TEST MODE: Will NOT submit applications ***")
    print("=" * 55)
    print("\n  PAUSE/RESUME: Type 'p' + Enter at any time")
    print("  to pause the bot for manual intervention.\n")
    print("INSTRUCTIONS:")
    print("1. Log in to Indeed (if needed)")
    print("2. In the search bar, type your keywords (e.g., 'Data Analyst')")
    print("3. Set your location (e.g., 'Baltimore, MD' or 'Remote')")
    print("4. Click 'Find Jobs' or press Enter")
    print("5. Apply any filters (Date Posted, Remote, Salary, etc.)")
    print("6. Make sure the URL starts with: www.indeed.com/jobs?")
    print("   NOT employers.indeed.com or resumes.indeed.com")
    print("7. When you see job listing cards, press ENTER here")
    print("=" * 55)

    while True:
        input("\nPress ENTER when on search results page...")
        current_url = driver.current_url
        if 'employers.indeed.com' in current_url:
            print(f"  ERROR: You're on the EMPLOYER dashboard, not job search!")
            print(f"  Current URL: {current_url[:80]}")
            print(f"  Go to indeed.com (not employers.indeed.com), search for jobs, then press ENTER.")
            continue
        if 'resumes.indeed.com' in current_url:
            print(f"  ERROR: You're on the RESUME page, not job search!")
            print(f"  Current URL: {current_url[:80]}")
            print(f"  Go to indeed.com, search for jobs, then press ENTER again.")
            continue
        if 'indeed.com/jobs' in current_url or 'indeed.com/q-' in current_url or 'indeed.com/l-' in current_url:
            # Make sure it's not employers subdomain
            if 'employers.' not in current_url:
                print(f"  Confirmed on job search page: {current_url[:80]}")
                break
        # Check if it looks like a search page by content
        try:
            driver.find_element(By.CSS_SELECTOR, "div.jobsearch-LeftPane, div.job_seen_beacon, a.jcs-JobTitle")
            print(f"  Found job cards on page. Proceeding.")
            break
        except Exception:
            pass
        print(f"  Current URL: {current_url[:80]}")
        print(f"  This might not be a search results page.")
        print(f"  Make sure you're on: indeed.com/jobs?q=your+search")
        confirm = input("  Continue anyway? (y/n): ").strip().lower()
        if confirm == 'y':
            break

    page_count = 0
    while True:
        page_count += 1
        print(f"\n{'='*55}")
        print(f"PROCESSING PAGE {page_count}")
        print(f"Total tokens used: {total_tokens_used}")
        print(f"Total applied: {total_applied}")
        print(f"Time: {datetime.now().strftime('%I:%M %p')}")
        est_cost = total_tokens_used * 0.0000004
        print(f"Estimated cost so far: ${est_cost:.4f}")
        print(f"{'='*55}")

        process_page()

        human_delay(3, 8)

        if not go_to_next_page():
            print("\nAll pages processed!")
            break

    print("\n" + "=" * 55)
    print("BOT FINISHED!")
    print(f"Processed {page_count} pages total.")
    print(f"Total jobs applied: {total_applied}")
    print(f"Total tokens used: {total_tokens_used}")
    est_cost = total_tokens_used * 0.0000004
    print(f"Estimated cost: ${est_cost:.4f}")
    print(f"Cover letters saved in: {COVER_LETTER_DIR}")
    print(f"Tailored resumes saved in: {RESUME_DIR}")
    print("Check the log file for results.")
    print("=" * 55)
    driver.quit()


def run_bot_logic(driver_arg, api_key_arg, user_full_resume, user_resume_summary, user_name, user_contact, max_applications=10, model_name="gemini-1.5-flash"):
    """Main execution loop triggered by Streamlit app.py UI."""
    global driver, genai, model, CURRENT_USER_DATA, total_applied

    if driver_arg is not None:
        driver = driver_arg

    if api_key_arg:
        genai.configure(api_key=api_key_arg)
        model = genai.GenerativeModel(model_name or "gemini-1.5-flash")

    CURRENT_USER_DATA["full_resume"] = user_full_resume
    CURRENT_USER_DATA["resume_summary"] = user_resume_summary
    CURRENT_USER_DATA["name"] = user_name
    CURRENT_USER_DATA["contact"] = user_contact

    print(f"\n==================================================")
    print(f"  STARTING RUN_BOT_LOGIC FOR {user_name.upper()}")
    print(f"  Target Max Applications: {max_applications}")
    print(f"==================================================\n")

    page_count = 0
    start_applied = total_applied

    while (total_applied - start_applied) < max_applications:
        page_count += 1
        print(f"\n--- PROCESSING SEARCH RESULTS PAGE {page_count} ---")
        process_page()

        if (total_applied - start_applied) >= max_applications:
            print(f"Reached maximum requested applications limit ({max_applications}). Stopping.")
            break

        if not go_to_next_page():
            print("No more search result pages available.")
            break

    total_submitted = total_applied - start_applied
    print(f"\nCompleted run_bot_logic. Applications submitted in this run: {total_submitted}")
    return total_submitted


if __name__ == "__main__":
    run_bot()