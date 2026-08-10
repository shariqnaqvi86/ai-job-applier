/* ==========================================================================
   HANDSHAKE AUTO APPLY & CAREER APPLICATION SUITE
   Frontend Application Controller JavaScript
   ========================================================================== */

let currentProfile = null;
let currentProfilesList = [];
let currentSearchResults = [];
let currentStudioJob = null;
let botPollingInterval = null;

document.addEventListener('DOMContentLoaded', () => {
    loadProfiles();
    loadApplicationHistory();
    startBotPolling();
    executeJobSearch();
});

// --- TAB NAVIGATION ---
function switchTab(tabId) {
    document.querySelectorAll('.nav-tab').forEach(tab => tab.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));

    const targetBtn = Array.from(document.querySelectorAll('.nav-tab')).find(b => b.getAttribute('onclick').includes(tabId));
    if (targetBtn) targetBtn.classList.add('active');

    const targetPane = document.getElementById(`tab-${tabId}`);
    if (targetPane) targetPane.classList.add('active');
}

// --- PROFILES & CANDIDATE DATA ---
async function loadProfiles() {
    try {
        const res = await fetch('/api/profiles');
        const data = await res.json();
        currentProfilesList = data.profiles || [];
        const activeId = data.active_profile_id;

        const dropdown = document.getElementById('profile-select-dropdown');
        dropdown.innerHTML = '';

        currentProfilesList.forEach(p => {
            const opt = document.createElement('option');
            opt.value = p.id;
            opt.textContent = `${p.personal.first_name} ${p.personal.last_name} (${p.experience.current_role || 'Candidate'})`;
            if (p.id === activeId) opt.selected = true;
            dropdown.appendChild(opt);
        });

        currentProfile = currentProfilesList.find(p => p.id === activeId) || currentProfilesList[0];
        renderProfileState();
    } catch (err) {
        console.error('Error loading profiles:', err);
    }
}

async function onProfileChange() {
    const dropdown = document.getElementById('profile-select-dropdown');
    const selectedId = dropdown.value;

    try {
        await fetch('/api/profiles/active', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile_id: selectedId })
        });
        await loadProfiles();
    } catch (err) {
        console.error('Error changing profile:', err);
    }
}

function renderProfileState() {
    if (!currentProfile) return;

    // Header badge
    document.getElementById('active-profile-name').textContent = `${currentProfile.personal.first_name} ${currentProfile.personal.last_name}`;

    // Profile form fields
    document.getElementById('prof-fname').value = currentProfile.personal.first_name || '';
    document.getElementById('prof-lname').value = currentProfile.personal.last_name || '';
    document.getElementById('prof-email').value = currentProfile.personal.email || '';
    document.getElementById('prof-phone').value = currentProfile.personal.phone || '';
    document.getElementById('prof-location').value = `${currentProfile.personal.city || ''}, ${currentProfile.personal.state || ''}`.replace(/^, /, '');
    document.getElementById('prof-salary').value = (currentProfile.preferences && currentProfile.preferences.salary) || '';

    // Handshake Credentials fields
    const hsCreds = currentProfile.handshake_credentials || {};
    document.getElementById('prof-hs-email').value = hsCreds.email || '';
    document.getElementById('prof-hs-password').value = hsCreds.password || '';
    document.getElementById('prof-hs-portal').value = hsCreds.portal_url || 'https://app.joinhandshake.com/login';

    const hsBadge = document.getElementById('hs-status-badge');
    if (hsBadge) {
        if (hsCreds.connected) {
            hsBadge.textContent = 'CONNECTED';
            hsBadge.style.background = 'rgba(0,255,170,0.1)';
            hsBadge.style.color = 'var(--success)';
            hsBadge.style.borderColor = 'rgba(0,255,170,0.3)';
        } else if (hsCreds.email) {
            hsBadge.textContent = 'SAVED';
            hsBadge.style.background = 'rgba(0,240,255,0.1)';
            hsBadge.style.color = 'var(--primary)';
            hsBadge.style.borderColor = 'rgba(0,240,255,0.3)';
        } else {
            hsBadge.textContent = 'NOT CONFIG';
            hsBadge.style.background = 'rgba(255,183,0,0.1)';
            hsBadge.style.color = 'var(--warning)';
            hsBadge.style.borderColor = 'rgba(255,183,0,0.3)';
        }
    }

    // Render skills pills
    const skillsContainer = document.getElementById('profile-skills-pills');
    skillsContainer.innerHTML = '';
    (currentProfile.skills || []).forEach(skill => {
        const pill = document.createElement('span');
        pill.className = 'kw-badge';
        pill.style.background = 'rgba(0,240,255,0.1)';
        pill.style.color = 'var(--primary)';
        pill.style.borderColor = 'rgba(0,240,255,0.3)';
        pill.textContent = skill;
        skillsContainer.appendChild(pill);
    });

    // Render Life Milestones
    renderLifeMilestones();
}

function toggleHsPasswordVisibility() {
    const input = document.getElementById('prof-hs-password');
    const icon = document.getElementById('hs-pwd-icon');
    if (input.type === 'password') {
        input.type = 'text';
        icon.className = 'fa-solid fa-eye-slash';
    } else {
        input.type = 'password';
        icon.className = 'fa-solid fa-eye';
    }
}

async function saveHandshakeCredentials() {
    const email = document.getElementById('prof-hs-email').value;
    const password = document.getElementById('prof-hs-password').value;
    const portal_url = document.getElementById('prof-hs-portal').value;

    try {
        const res = await fetch('/api/handshake/credentials/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, portal_url })
        });
        const data = await res.json();
        if (data.status === 'success') {
            if (currentProfile) {
                currentProfile.handshake_credentials = data.handshake_credentials;
            }
            alert('Handshake credentials saved successfully!');
            renderProfileState();
        }
    } catch (err) {
        console.error('Error saving Handshake credentials:', err);
    }
}

async function verifyHandshakeCredentials() {
    const email = document.getElementById('prof-hs-email').value;
    const password = document.getElementById('prof-hs-password').value;
    const portal_url = document.getElementById('prof-hs-portal').value;

    const hsBadge = document.getElementById('hs-status-badge');
    if (hsBadge) {
        hsBadge.textContent = 'VERIFYING...';
        hsBadge.style.background = 'rgba(0,240,255,0.1)';
        hsBadge.style.color = 'var(--primary)';
    }

    try {
        const res = await fetch('/api/handshake/verify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ email, password, portal_url })
        });
        const data = await res.json();
        if (data.connected) {
            alert('✅ Handshake login verified successfully!');
        } else {
            alert(`Handshake status: ${data.message}`);
        }
        await loadProfiles();
    } catch (err) {
        console.error('Error verifying Handshake login:', err);
        alert('Verification endpoint reached.');
        renderProfileState();
    }
}

async function saveProfileDetails() {
    if (!currentProfile) return;

    currentProfile.personal.first_name = document.getElementById('prof-fname').value;
    currentProfile.personal.last_name = document.getElementById('prof-lname').value;
    currentProfile.personal.email = document.getElementById('prof-email').value;
    currentProfile.personal.phone = document.getElementById('prof-phone').value;
    
    const locParts = document.getElementById('prof-location').value.split(',');
    currentProfile.personal.city = locParts[0] ? locParts[0].strip ? locParts[0].strip() : locParts[0].trim() : '';
    currentProfile.personal.state = locParts[1] ? locParts[1].trim() : '';
    currentProfile.preferences.salary = document.getElementById('prof-salary').value;

    try {
        const res = await fetch('/api/profiles/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ profile: currentProfile })
        });
        const data = await res.json();
        if (data.status === 'success') {
            alert('Profile details saved successfully!');
            renderProfileState();
        }
    } catch (err) {
        console.error('Error saving profile:', err);
    }
}

// --- SIGNIFICANT LIFE MILESTONES / MARKERS ---
function renderLifeMilestones() {
    const milestones = currentProfile.life_milestones || [];
    const container = document.getElementById('milestones-container');
    const dashContainer = document.getElementById('dash-milestones-list');

    document.getElementById('dash-milestones-count').textContent = milestones.length;

    container.innerHTML = '';
    dashContainer.innerHTML = '';

    milestones.forEach(m => {
        // Hub Card
        const card = document.createElement('div');
        card.className = `milestone-card ${m.selected ? 'selected' : ''}`;
        card.innerHTML = `
            <div class="milestone-header">
                <div class="milestone-title">${m.title}</div>
                <span class="milestone-badge">${m.category || 'Milestone'}</span>
            </div>
            <div class="milestone-desc">${m.description}</div>
            <div class="milestone-takeaway">
                <i class="fa-solid fa-lightbulb"></i> <strong>Key Takeaway:</strong> ${m.key_takeaways || 'Personal growth & resilience.'}
            </div>
            <div class="milestone-actions">
                <label class="checkbox-toggle">
                    <input type="checkbox" ${m.selected ? 'checked' : ''} onchange="toggleMilestoneSelection('${m.id}', this.checked)">
                    <span>Include in AI Cover Letters</span>
                </label>
                <button style="background: none; border: none; color: var(--danger); cursor: pointer;" onclick="deleteMilestone('${m.id}')">
                    <i class="fa-solid fa-trash"></i>
                </button>
            </div>
        `;
        container.appendChild(card);

        // Dashboard Summary list item
        if (m.selected) {
            const dashItem = document.createElement('div');
            dashItem.style.background = 'rgba(255,255,255,0.03)';
            dashItem.style.border = '1px solid var(--border-glass)';
            dashItem.style.padding = '0.75rem';
            dashItem.style.borderRadius = 'var(--radius-sm)';
            dashItem.innerHTML = `
                <div style="font-weight: 700; font-size: 0.85rem; color: #fff;">${m.title}</div>
                <div style="font-size: 0.75rem; color: var(--text-muted); text-overflow: ellipsis; overflow: hidden; white-space: nowrap;">${m.key_takeaways}</div>
            `;
            dashContainer.appendChild(dashItem);
        }
    });
}

async function toggleMilestoneSelection(id, isSelected) {
    try {
        const res = await fetch('/api/milestones/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id, selected: isSelected })
        });
        const data = await res.json();
        if (data.status === 'success') {
            currentProfile.life_milestones = data.milestones;
            renderLifeMilestones();
        }
    } catch (err) {
        console.error('Error toggling milestone:', err);
    }
}

function openAddMilestoneModal() {
    document.getElementById('modal-add-milestone').classList.add('active');
}
function closeAddMilestoneModal() {
    document.getElementById('modal-add-milestone').classList.remove('active');
}

async function saveNewMilestone() {
    const title = document.getElementById('m-title').value;
    const category = document.getElementById('m-category').value;
    const description = document.getElementById('m-description').value;
    const takeaways = document.getElementById('m-takeaways').value;

    if (!title || !description) {
        alert('Please enter a title and description for your milestone.');
        return;
    }

    try {
        const res = await fetch('/api/milestones/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                title: title,
                category: category,
                description: description,
                key_takeaways: takeaways
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            currentProfile.life_milestones = data.milestones;
            renderLifeMilestones();
            closeAddMilestoneModal();
            document.getElementById('m-title').value = '';
            document.getElementById('m-description').value = '';
            document.getElementById('m-takeaways').value = '';
        }
    } catch (err) {
        console.error('Error adding milestone:', err);
    }
}

async function deleteMilestone(id) {
    if (!confirm('Are you sure you want to delete this life milestone?')) return;

    try {
        const res = await fetch('/api/milestones/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: id })
        });
        const data = await res.json();
        if (data.status === 'success') {
            currentProfile.life_milestones = data.milestones;
            renderLifeMilestones();
        }
    } catch (err) {
        console.error('Error deleting milestone:', err);
    }
}

// --- RESUME FILE UPLOAD ---
async function uploadResumeFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/resume/upload', {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (data.status === 'success') {
            alert(data.message);
            currentProfile = data.profile;
            renderProfileState();
        } else {
            alert(data.message || 'Upload failed');
        }
    } catch (err) {
        console.error('Error uploading resume file:', err);
    }
}

// --- JOB SEARCH ---
async function executeJobSearch() {
    const kw = document.getElementById('search-keywords').value;
    const loc = document.getElementById('search-location').value;
    const remote = document.getElementById('search-remote').checked;

    try {
        const res = await fetch('/api/jobs/search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ keywords: kw, location: loc, remote_only: remote })
        });
        const data = await res.json();
        currentSearchResults = data.jobs || [];
        renderJobSearchFeed();
    } catch (err) {
        console.error('Error searching jobs:', err);
    }
}

function renderJobSearchFeed() {
    const feed = document.getElementById('search-results-feed');
    const dashFeed = document.getElementById('dash-job-list');

    feed.innerHTML = '';
    dashFeed.innerHTML = '';

    currentSearchResults.forEach(job => {
        // Job Search Feed Card
        const card = document.createElement('div');
        card.className = 'job-card';
        card.innerHTML = `
            <div class="job-info">
                <div class="job-title">${job.title}</div>
                <div class="job-company">${job.company}</div>
                <div class="job-meta">
                    <span><i class="fa-solid fa-location-dot"></i> ${job.location}</span>
                    <span><i class="fa-solid fa-money-bill-wave"></i> ${job.salary}</span>
                    <span><i class="fa-solid fa-clock"></i> ${job.posted}</span>
                </div>
                <div class="job-keywords">
                    ${(job.keywords || []).map(k => `<span class="kw-badge">${k}</span>`).join('')}
                </div>
            </div>

            <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 0.75rem;">
                <div class="match-score-pill">
                    <i class="fa-solid fa-bullseye"></i> ${job.match_score || 90}% Match
                </div>
                <div style="display: flex; gap: 0.5rem;">
                    <button class="btn btn-secondary" onclick="openStudioForJob('${job.id}')">
                        <i class="fa-solid fa-wand-magic-sparkles"></i> Tailor & Preview
                    </button>
                    <button class="btn" onclick="startSingleJobApply('${job.id}')">
                        <i class="fa-solid fa-paper-plane"></i> Apply Now
                    </button>
                </div>
            </div>
        `;
        feed.appendChild(card);

        // Dashboard Card
        const dashCard = card.cloneNode(true);
        dashFeed.appendChild(dashCard);
    });
}

// --- AI STUDIO ---
async function openStudioForJob(jobId) {
    const job = currentSearchResults.find(j => j.id === jobId);
    if (!job) return;

    currentStudioJob = job;
    switchTab('ai-studio');

    document.getElementById('studio-empty-state').style.display = 'none';
    document.getElementById('studio-content').style.display = 'block';

    document.getElementById('studio-job-title').textContent = job.title;
    document.getElementById('studio-company').textContent = `${job.company} • ${job.location}`;
    document.getElementById('studio-match-score').textContent = `${job.match_score || 95}%`;

    // Render Milestone Tags
    const tagsContainer = document.getElementById('studio-milestones-tags');
    tagsContainer.innerHTML = '';
    const selectedMilestones = (currentProfile.life_milestones || []).filter(m => m.selected);
    selectedMilestones.forEach(m => {
        const tag = document.createElement('span');
        tag.className = 'milestone-badge';
        tag.style.background = 'rgba(255,0,122,0.15)';
        tag.style.color = 'var(--accent)';
        tag.style.borderColor = 'rgba(255,0,122,0.3)';
        tag.textContent = m.title;
        tagsContainer.appendChild(tag);
    });

    document.getElementById('studio-cl-text').value = "Generating tailored cover letter weaving resume + selected life milestones...";
    document.getElementById('studio-res-text').value = "Generating ATS tailored resume...";

    try {
        const res = await fetch('/api/tailor', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                job_title: job.title,
                company_name: job.company,
                job_description: job.description
            })
        });
        const data = await res.json();
        if (data.status === 'success') {
            document.getElementById('studio-cl-text').value = data.cover_letter_text;
            document.getElementById('studio-res-text').value = data.resume_text;

            document.getElementById('studio-cl-pdf-link').href = `/api/tailored_docs/${data.cover_letter_pdf}`;
            document.getElementById('studio-res-pdf-link').href = `/api/tailored_docs/${data.resume_pdf}`;

            document.getElementById('studio-match-score').textContent = `${data.match_score}%`;
        }
    } catch (err) {
        console.error('Error tailoring documents:', err);
    }
}

// --- BOT TERMINAL & CONTROL ---
async function startSingleJobApply(jobId) {
    switchTab('bot-console');
    const settings = getBotSettings();
    try {
        await fetch('/api/bot/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_ids: [jobId], humanizer_settings: settings })
        });
    } catch (err) {
        console.error('Error starting bot:', err);
    }
}

async function launchBotWithStudioJob() {
    if (!currentStudioJob) return;
    startSingleJobApply(currentStudioJob.id);
}

function getBotSettings() {
    return {
        typing_wpm: parseInt(document.getElementById('bot-wpm').value) || 65,
        mouse_jitter: document.getElementById('bot-jitter').value === 'true',
        min_delay: parseInt(document.getElementById('bot-min-delay').value) || 2,
        max_delay: parseInt(document.getElementById('bot-max-delay').value) || 5
    };
}

async function triggerBotStart() {
    const settings = getBotSettings();
    const jobIds = currentSearchResults.map(j => j.id);
    try {
        await fetch('/api/bot/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_ids: jobIds, humanizer_settings: settings })
        });
    } catch (err) {
        console.error('Error starting campaign:', err);
    }
}

async function triggerBotPause() {
    try {
        const res = await fetch('/api/bot/pause', { method: 'POST' });
        const data = await res.json();
        const pauseBtn = document.getElementById('btn-bot-pause');
        if (data.is_paused) {
            pauseBtn.innerHTML = '<i class="fa-solid fa-play"></i> Resume';
        } else {
            pauseBtn.innerHTML = '<i class="fa-solid fa-pause"></i> Pause';
        }
    } catch (err) {
        console.error('Error toggling pause:', err);
    }
}

async function triggerBotStop() {
    try {
        await fetch('/api/bot/stop', { method: 'POST' });
    } catch (err) {
        console.error('Error stopping bot:', err);
    }
}

function startBotPolling() {
    if (botPollingInterval) clearInterval(botPollingInterval);
    botPollingInterval = setInterval(pollBotStatus, 1500);
}

async function pollBotStatus() {
    try {
        const res = await fetch('/api/bot/status');
        const data = await res.json();

        // Update Pill
        const statusPill = document.getElementById('bot-live-status-pill');
        const dashStatus = document.getElementById('dash-bot-status');

        if (data.is_running) {
            if (data.is_paused) {
                statusPill.textContent = 'PAUSED';
                statusPill.style.color = 'var(--warning)';
                dashStatus.textContent = 'PAUSED';
                dashStatus.style.color = 'var(--warning)';
            } else {
                statusPill.textContent = 'RUNNING';
                statusPill.style.color = 'var(--primary)';
                dashStatus.textContent = 'APPLYING...';
                dashStatus.style.color = 'var(--primary)';
            }
        } else {
            statusPill.textContent = 'IDLE / READY';
            statusPill.style.color = 'var(--success)';
            dashStatus.textContent = 'READY';
            dashStatus.style.color = 'var(--success)';
        }

        // Render Logs
        const logContainer = document.getElementById('terminal-log-output');
        const logs = data.logs || [];
        logContainer.innerHTML = '';
        logs.forEach(logText => {
            const line = document.createElement('div');
            line.className = 'log-line';

            // Extract level
            const match = logText.match(/\[(.*?)\]/g);
            if (match && match[1]) {
                const level = match[1].replace('[', '').replace(']', '');
                line.setAttribute('data-level', level);
            }

            line.textContent = logText;
            logContainer.appendChild(line);
        });

        logContainer.scrollTop = logContainer.scrollHeight;

        // Refresh application history if logs changed
        loadApplicationHistory();
    } catch (err) {
        console.error('Error polling status:', err);
    }
}

// --- APPLICATION HISTORY ---
async function loadApplicationHistory() {
    try {
        const res = await fetch('/api/applications/history');
        const data = await res.json();
        const apps = data.applications || [];

        document.getElementById('dash-applied-count').textContent = apps.length;

        const tbody = document.getElementById('app-history-tbody');
        tbody.innerHTML = '';

        if (apps.length === 0) {
            tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted);">No applications submitted yet.</td></tr>`;
            return;
        }

        apps.forEach(app => {
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td style="font-weight: 700; color: #fff;">${app.job_title}</td>
                <td style="color: var(--primary);">${app.company}</td>
                <td style="color: var(--text-muted);">${app.location}</td>
                <td style="color: var(--text-muted); font-size: 0.85rem;">${app.applied_at}</td>
                <td><span style="color: var(--success); font-weight: 800;">${app.match_score}%</span></td>
                <td>
                    <div style="display: flex; gap: 0.4rem;">
                        <a href="/api/tailored_docs/${app.cover_letter_file}" target="_blank" class="kw-badge" style="color: var(--accent); border-color: rgba(255,0,122,0.3); text-decoration: none;">
                            <i class="fa-solid fa-envelope"></i> Cover Letter
                        </a>
                        <a href="/api/tailored_docs/${app.resume_file}" target="_blank" class="kw-badge" style="color: var(--primary); border-color: rgba(0,240,255,0.3); text-decoration: none;">
                            <i class="fa-solid fa-file"></i> Resume
                        </a>
                    </div>
                </td>
                <td><span style="background: rgba(0,255,170,0.1); color: var(--success); padding: 0.2rem 0.6rem; border-radius: var(--radius-full); font-size: 0.75rem; font-weight: 700;">Applied</span></td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        console.error('Error loading app history:', err);
    }
}
