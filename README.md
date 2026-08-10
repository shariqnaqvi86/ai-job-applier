# 🤖 AI Job Application Bot

An automated job application assistant built with Python, Selenium, Streamlit, and Google Gemini AI.

## 🔒 Privacy & Data Security Disclaimer

> **IMPORTANT**: This application does **NOT** hardcode, log, or store personal information, contact details, resume text, or API keys on any external server or database.
> - All profile inputs, resume contents, and API keys are held strictly in your active local browser session (`st.session_state`) during execution.
> - All AI resume/cover letter tailoring calls interact directly with Google Gemini API using your provided API key.
> - No personal data is tracked or pushed to this repository.

---

## ✨ Features

- **Streamlit Web UI**: Easy-to-use wide layout interface for pasting profile info and managing runs.
- **API Key Tester**: Live connection testing for Google Gemini API keys in the sidebar.
- **Document Uploader**: Upload `.pdf`, `.docx`, `.doc`, or `.txt` resume files for instant text extraction.
- **✨ Auto-Generate Summary with AI**: Generates a 1-paragraph summary from your full resume using Gemini AI.
- **Selenium Automation**: Stealth browser automation for Easy Apply wizards (Handshake & Indeed).
- **Two-Phase AI Document Tailoring**: Phase 1 ATS keyword optimization + Phase 2 anti-AI humanizer pass for resumes and cover letters.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install streamlit selenium google-genai fpdf pypdf python-docx
```

### 2. Launch the Application
```bash
streamlit run app.py
```

### 3. Usage Steps
1. Enter your **Gemini API Key** in the sidebar (get a free key at [Google AI Studio](https://aistudio.google.com)).
2. Fill in your name, email, phone, and location.
3. Paste or upload your **Full Resume** and **Resume Summary**.
4. Click **"Launch Browser & Log In"** to open Chrome.
5. In the opened Chrome browser, log in to Handshake or Indeed and navigate to your **Job Search Results** page.
6. Click **"🚀 Start Applying"**.

---

## 📄 License
MIT License
