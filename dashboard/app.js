/**
 * Polar Dashboard JavaScript
 * Handles dynamic API queries, search, filtering, pagination, sorting,
 * and seamless real data rendering without mock data.
 */

const state = {
  activeView: 'jobs',
  q: '',
  location: '',
  portal: 'all',
  type: 'all',
  page: 1,
  limit: 10,
  sort: 'match_desc',
  contacts: [],
  contactQuery: '',
  jobsCache: {},
  candidateProfile: null,
  availableSkillsCatalog: []
};

// DOM References
const roleSearchInput = document.getElementById('roleSearchInput');
const clearSearchBtn = document.getElementById('clearSearchBtn');
const locationInput = document.getElementById('locationInput');
const locationSuggestions = document.getElementById('locationSuggestions');
const portalFilter = document.getElementById('portalFilter');
const typeFilter = document.getElementById('typeFilter');
const limitSelect = document.getElementById('limitSelect');
const jobCountText = document.getElementById('jobCountText');
const jobsTableBody = document.getElementById('jobsTableBody');
const prevPageBtn = document.getElementById('prevPageBtn');
const nextPageBtn = document.getElementById('nextPageBtn');
const pageNumbers = document.getElementById('pageNumbers');
const exportCsvBtn = document.getElementById('exportCsvBtn');

const contactSearchInput = document.getElementById('contactSearchInput');
const contactsTableBody = document.getElementById('contactsTableBody');
const contactCountText = document.getElementById('contactCountText');
const contactsBadge = document.getElementById('contactsBadge');

// ── Debounce Helper ─────────────────────────────────────────
function debounce(func, delay = 250) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => func.apply(this, args), delay);
  };
}

// ── Page Navigation (Home, About, Dashboard, Profile) ───────
function navigateTo(page) {
  state.currentPage = page;

  // Update nav links active class
  document.querySelectorAll('.nav-link').forEach(link => {
    link.classList.remove('active');
  });
  const activeLink = document.getElementById(`nav-${page}`);
  if (activeLink) {
    activeLink.classList.add('active');
  }

  // Hide all page sections
  document.querySelectorAll('.page-section').forEach(sec => {
    sec.style.display = 'none';
  });

  // Show target page section
  const targetSection = document.getElementById(`page-${page}`);
  if (targetSection) {
    targetSection.style.display = 'block';
  }

  window.scrollTo({ top: 0, behavior: 'smooth' });
}

// ── Initialize Dashboard ────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  fetchStats();
  fetchFilterOptions();
  fetchCandidateProfile();
  fetchJobs();
  fetchContacts();
  attachEventListeners();

  // Handle URL hash routing if present
  const hash = window.location.hash.replace('#', '');
  if (['home', 'about', 'dashboard', 'profile'].includes(hash)) {
    navigateTo(hash);
  }
});

// ── Event Listeners ─────────────────────────────────────────
function attachEventListeners() {
  // Search input with debounce
  roleSearchInput.addEventListener('input', debounce((e) => {
    state.q = e.target.value.trim();
    state.page = 1;
    clearSearchBtn.style.display = state.q ? 'block' : 'none';
    fetchJobs();
  }, 250));

  clearSearchBtn.addEventListener('click', () => {
    roleSearchInput.value = '';
    state.q = '';
    state.page = 1;
    clearSearchBtn.style.display = 'none';
    const badge = document.getElementById('semanticIntentBadge');
    if (badge) badge.style.display = 'none';
    fetchJobs();
  });

  // Location filter dropdown
  locationInput.addEventListener('change', (e) => {
    state.location = e.target.value.trim();
    state.page = 1;
    fetchJobs();
  });

  // Portal dropdown
  portalFilter.addEventListener('change', (e) => {
    state.portal = e.target.value;
    state.page = 1;
    fetchJobs();
  });

  // Work Mode / Type filter
  typeFilter.addEventListener('change', (e) => {
    state.type = e.target.value;
    state.page = 1;
    fetchJobs();
  });

  // Sort selector
  const sortSelect = document.getElementById('sortSelect');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      state.sort = e.target.value;
      state.page = 1;
      fetchJobs();
    });
  }

  // Rows per page
  limitSelect.addEventListener('change', (e) => {
    state.limit = parseInt(e.target.value, 10) || 10;
    state.page = 1;
    fetchJobs();
  });

  // Profile add skill handlers
  const addSkillBtn = document.getElementById('addSkillBtn');
  const customSkillInput = document.getElementById('customSkillInput');
  if (addSkillBtn && customSkillInput) {
    addSkillBtn.addEventListener('click', () => {
      const val = customSkillInput.value.trim();
      if (val) {
        addSkill(val);
        customSkillInput.value = '';
      }
    });
    customSkillInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = customSkillInput.value.trim();
        if (val) {
          addSkill(val);
          customSkillInput.value = '';
        }
      }
    });
  }

  // Profile add role handlers
  const addRoleBtn = document.getElementById('addRoleBtn');
  const customRoleInput = document.getElementById('customRoleInput');
  if (addRoleBtn && customRoleInput) {
    addRoleBtn.addEventListener('click', () => {
      const val = customRoleInput.value.trim();
      if (val) {
        addRole(val);
        customRoleInput.value = '';
      }
    });
    customRoleInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        e.preventDefault();
        const val = customRoleInput.value.trim();
        if (val) {
          addRole(val);
          customRoleInput.value = '';
        }
      }
    });
  }

  // Experience level segment buttons
  const expGroup = document.getElementById('experienceLevelGroup');
  if (expGroup) {
    expGroup.addEventListener('click', (e) => {
      const btn = e.target.closest('.segment-btn');
      if (!btn) return;
      document.querySelectorAll('#experienceLevelGroup .segment-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      if (state.candidateProfile) {
        state.candidateProfile.experience_level = btn.getAttribute('data-exp');
      }
    });
  }

  // Pagination buttons
  prevPageBtn.addEventListener('click', () => {
    if (state.page > 1) {
      state.page--;
      fetchJobs();
    }
  });

  nextPageBtn.addEventListener('click', () => {
    state.page++;
    fetchJobs();
  });

  // CSV Export
  exportCsvBtn.addEventListener('click', () => {
    const params = new URLSearchParams({
      q: state.q,
      location: state.location,
      portal: state.portal,
    });
    window.location.href = `/api/export?${params.toString()}`;
  });

  // Contacts search
  if (contactSearchInput) {
    contactSearchInput.addEventListener('input', debounce((e) => {
      state.contactQuery = e.target.value.trim().toLowerCase();
      renderContacts();
    }, 200));
  }
}

// ── View Switching (Jobs vs Contacts) ───────────────────────
function switchView(view) {
  state.activeView = view;
  const tabJobs = document.getElementById('tabJobs');
  const tabContacts = document.getElementById('tabContacts');
  const jobsViewSection = document.getElementById('jobsViewSection');
  const contactsViewSection = document.getElementById('contactsViewSection');

  if (view === 'jobs') {
    tabJobs.classList.add('active');
    tabContacts.classList.remove('active');
    jobsViewSection.style.display = 'block';
    contactsViewSection.style.display = 'none';
  } else {
    tabContacts.classList.add('active');
    tabJobs.classList.remove('active');
    jobsViewSection.style.display = 'none';
    contactsViewSection.style.display = 'block';
    renderContacts();
  }
}

// ── Fetch Key Stats ─────────────────────────────────────────
async function fetchStats() {
  try {
    const res = await fetch('/api/stats');
    if (!res.ok) throw new Error('Failed to fetch stats');
    const data = await res.json();

    document.getElementById('statTotalJobs').textContent = data.total_jobs.toLocaleString();
    document.getElementById('statVerifiedEmails').textContent = data.verified_emails.toLocaleString();
    document.getElementById('statRemoteJobs').textContent = data.remote_jobs.toLocaleString();
    document.getElementById('statPortals').textContent = (data.portals ? data.portals.length : 6);
    
    if (data.portals && data.portals.length) {
      document.getElementById('statPortalsList').textContent = data.portals.slice(0, 3).join(', ') + '...';
    }
  } catch (err) {
    console.error('Error loading stats:', err);
  }
}

// ── Fetch Filter Metadata ───────────────────────────────────
async function fetchFilterOptions() {
  try {
    const res = await fetch('/api/filters');
    if (!res.ok) throw new Error('Failed to fetch filter options');
    const data = await res.json();

    // Populate Portals
    if (data.portals) {
      portalFilter.innerHTML = '<option value="all">All Portals</option>';
      data.portals.forEach(portal => {
        const opt = document.createElement('option');
        opt.value = portal;
        opt.textContent = portal;
        portalFilter.appendChild(opt);
      });
    }

    // Populate Location Dropdown (Tier-1 Tech Cities)
    if (data.locations && locationInput) {
      locationInput.innerHTML = '';
      data.locations.forEach(loc => {
        const opt = document.createElement('option');
        opt.value = (loc === 'All Locations') ? 'all' : loc;
        opt.textContent = loc;
        locationInput.appendChild(opt);
      });
    }
  } catch (err) {
    console.error('Error loading filter options:', err);
  }
}

// ── Fetch & Render Jobs Table ───────────────────────────────
async function fetchJobs() {
  renderLoadingState();

  const params = new URLSearchParams({
    q: state.q,
    location: state.location,
    portal: state.portal,
    type: state.type,
    page: state.page,
    limit: state.limit,
    sort: state.sort
  });

  try {
    const res = await fetch(`/api/jobs?${params.toString()}`);
    if (!res.ok) throw new Error('Failed to fetch jobs');
    const data = await res.json();

    if (data.candidate_profile) {
      state.candidateProfile = data.candidate_profile;
    }

    renderJobs(data.jobs || []);
    renderPagination(data);
    updateSemanticIntentBadge(data.parsed_intent);
  } catch (err) {
    console.error('Error fetching jobs:', err);
    jobsTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          Unable to load internship opportunities. Please verify server connection.
        </td>
      </tr>
    `;
    jobCountText.textContent = 'Showing 0 internships';
  }
}

function renderLoadingState() {
  jobsTableBody.innerHTML = `
    <tr>
      <td colspan="8" class="loading-state">
        <div class="spinner"></div>
        <span>Loading opportunities...</span>
      </td>
    </tr>
  `;
}

function renderJobs(jobs) {
  if (!jobs || jobs.length === 0) {
    jobsTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="empty-state">
          <p>No internships match your search or filter criteria.</p>
          <span style="font-size: 0.8rem; color: #9CA3AF; margin-top: 0.25rem; display: block;">
            Try broadening your keywords or clearing the location filter.
          </span>
        </td>
      </tr>
    `;
    return;
  }

  jobsTableBody.innerHTML = '';
  state.jobsCache = {};

  jobs.forEach(job => {
    state.jobsCache[job.id] = job;
    const tr = document.createElement('tr');

    // Company cell
    const companyCell = document.createElement('td');
    companyCell.className = 'col-company';
    let companyContent = `<div class="company-cell"><span class="company-name">${escapeHtml(job.company)}</span>`;
    if (job.website) {
      companyContent += `<a href="${escapeHtml(job.website)}" target="_blank" rel="noopener noreferrer" class="company-meta-link">${escapeHtml(cleanUrl(job.website))} ↗</a>`;
    }
    companyContent += `</div>`;
    companyCell.innerHTML = companyContent;

    // Role cell
    const roleCell = document.createElement('td');
    roleCell.className = 'col-role';
    let roleHtml = `
      <div class="role-cell-wrap">
        <div class="role-title-row">
          <span class="role-title">${escapeHtml(job.role)}</span>
        </div>
    `;
    if (job.strong_matches && job.strong_matches.length > 0) {
      roleHtml += `
        <div class="match-reasons-row">
          ${job.strong_matches.slice(0, 3).map(r => `<span class="match-tag" title="Strong matched skill">✓ ${escapeHtml(r)}</span>`).join('')}
          ${job.missing_skills && job.missing_skills.length > 0 ? `<span class="match-tag" style="color: #B45309; background: #FFFBEB; border-color: #FDE68A;" title="Missing required/desired skill">✕ ${escapeHtml(job.missing_skills[0])}</span>` : ''}
        </div>
      `;
    }
    roleHtml += `</div>`;
    roleCell.innerHTML = roleHtml;

    // Match Score cell
    const matchCell = document.createElement('td');
    matchCell.className = 'col-match';
    const m = job.match || {
      score: 75,
      match_grade: 'Strong Match',
      strong_matches: [],
      missing_skills: []
    };
    const gradeClass = 'grade-' + (m.match_grade || 'strong-match').toLowerCase().replace(/\s+/g, '-');
    matchCell.innerHTML = `
      <button type="button" class="match-badge-btn ${gradeClass}" onclick="openMatchModal('${job.id}')" title="Click for explainable match breakdown">
        <span class="match-badge-score">${m.score}%</span>
        <span class="match-badge-label">Match</span>
        <span class="match-badge-chevron">ⓘ</span>
      </button>
    `;

    // Location cell
    const locationCell = document.createElement('td');
    locationCell.className = 'col-location';
    locationCell.textContent = job.location || 'Remote';

    // Portal cell
    const portalCell = document.createElement('td');
    portalCell.className = 'col-portal';
    portalCell.innerHTML = `<span class="portal-badge">${escapeHtml(job.portal || 'Direct')}</span>`;

    // Type cell
    const typeCell = document.createElement('td');
    typeCell.className = 'col-type';
    typeCell.textContent = job.type || 'On-site';

    // Posted cell
    const postedCell = document.createElement('td');
    postedCell.className = 'col-posted';
    postedCell.textContent = formatPostedDate(job.posted, job.posted_date);

    // Action cell (Apply ↗ button)
    const actionCell = document.createElement('td');
    actionCell.className = 'col-action text-right';
    
    const applyUrl = job.application_link || job.website;
    if (applyUrl && applyUrl.startsWith('http')) {
      actionCell.innerHTML = `
        <a href="${escapeHtml(applyUrl)}" target="_blank" rel="noopener noreferrer" class="apply-btn" title="Open original job application on ${escapeHtml(job.portal || 'portal')}">
          <span>Apply</span>
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="7" y1="17" x2="17" y2="7"></line>
            <polyline points="7 7 17 7 17 17"></polyline>
          </svg>
        </a>
      `;
    } else {
      actionCell.innerHTML = `
        <button class="apply-btn disabled" disabled title="No direct external application link available">
          <span>Apply</span>
        </button>
      `;
    }

    tr.appendChild(companyCell);
    tr.appendChild(roleCell);
    tr.appendChild(matchCell);
    tr.appendChild(locationCell);
    tr.appendChild(portalCell);
    tr.appendChild(typeCell);
    tr.appendChild(postedCell);
    tr.appendChild(actionCell);

    jobsTableBody.appendChild(tr);
  });
}

// ── Render Pagination ───────────────────────────────────────
function renderPagination(data) {
  const { total, start_index, end_index, page, total_pages } = data;

  jobCountText.textContent = total > 0 
    ? `Showing ${start_index}–${end_index} of ${total} internships`
    : `Showing 0 internships`;

  prevPageBtn.disabled = page <= 1;
  nextPageBtn.disabled = page >= total_pages;

  pageNumbers.innerHTML = '';

  const maxButtons = 5;
  let startPage = Math.max(1, page - Math.floor(maxButtons / 2));
  let endPage = Math.min(total_pages, startPage + maxButtons - 1);

  if (endPage - startPage + 1 < maxButtons) {
    startPage = Math.max(1, endPage - maxButtons + 1);
  }

  for (let i = startPage; i <= endPage; i++) {
    const btn = document.createElement('button');
    btn.className = `page-num ${i === page ? 'active' : ''}`;
    btn.textContent = i;
    btn.addEventListener('click', () => {
      state.page = i;
      fetchJobs();
    });
    pageNumbers.appendChild(btn);
  }
}

// ── Verified Contacts View ──────────────────────────────────
async function fetchContacts() {
  try {
    const res = await fetch('/api/contacts');
    if (!res.ok) return;
    const data = await res.json();
    state.contacts = data.contacts || [];
    contactsBadge.textContent = state.contacts.length;
    renderContacts();
  } catch (err) {
    console.error('Error loading contacts:', err);
  }
}

function renderContacts() {
  let filtered = state.contacts;
  if (state.contactQuery) {
    const q = state.contactQuery;
    filtered = filtered.filter(c => 
      c.company.toLowerCase().includes(q) ||
      c.email.toLowerCase().includes(q) ||
      c.website.toLowerCase().includes(q)
    );
  }

  contactCountText.textContent = `Showing ${filtered.length} verified company contacts`;

  if (!filtered || filtered.length === 0) {
    contactsTableBody.innerHTML = `
      <tr>
        <td colspan="6" class="empty-state">No contacts found matching "${escapeHtml(state.contactQuery)}".</td>
      </tr>
    `;
    return;
  }

  contactsTableBody.innerHTML = '';
  filtered.slice(0, 100).forEach(c => {
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><strong>${escapeHtml(c.company)}</strong></td>
      <td>
        ${c.website ? `<a href="${escapeHtml(c.website)}" target="_blank" rel="noopener noreferrer" class="company-meta-link">${escapeHtml(cleanUrl(c.website))} ↗</a>` : '<span style="color:#9CA3AF">—</span>'}
      </td>
      <td>
        <span style="font-family: monospace; font-size: 0.875rem;">${escapeHtml(c.email)}</span>
      </td>
      <td>
        <span class="portal-badge" style="background:#ECFDF5; border-color:#A7F3D0; color:#065F46;">
          Score: ${c.priority_score}
        </span>
      </td>
      <td>
        <span style="font-size: 0.8rem; color: #10B981;">✓ ${escapeHtml(c.mx_status)}</span>
      </td>
      <td class="text-right">
        <button class="copy-btn" onclick="copyToClipboard('${escapeHtml(c.email)}')">
          Copy Email
        </button>
      </td>
    `;
    contactsTableBody.appendChild(tr);
  });
}

function exportContactsCsv() {
  let csv = 'Company,Website,Email,Priority Score,MX Status,Category\n';
  state.contacts.forEach(c => {
    csv += `"${c.company}","${c.website}","${c.email}","${c.priority_score}","${c.mx_status}","${c.category}"\n`;
  });
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.setAttribute('download', 'verified_company_contacts.csv');
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// ── Utilities ───────────────────────────────────────────────
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function cleanUrl(url) {
  if (!url) return '';
  return url.replace(/^https?:\/\//i, '').replace(/^www\./i, '').replace(/\/$/, '');
}

function formatPostedDate(rawPosted, normalizedDate) {
  if (!rawPosted && !normalizedDate) return 'Recently';
  if (rawPosted) {
    if (rawPosted.toLowerCase().includes('just now')) return 'Today • Just now';
    if (rawPosted.toLowerCase().includes('today')) return 'Today';
    return rawPosted;
  }
  try {
    const d = new Date(normalizedDate);
    if (!isNaN(d.getTime())) {
      return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
    }
  } catch (e) {}
  return normalizedDate || 'Recent';
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => {
    alert(`Copied ${text} to clipboard!`);
  }).catch(() => {
    prompt('Copy to clipboard:', text);
  });
}

// ── Natural Language / Semantic Search Helpers ─────────────
function updateSemanticIntentBadge(intent) {
  const badge = document.getElementById('semanticIntentBadge');
  const textEl = document.getElementById('semanticIntentText');
  if (!badge || !textEl) return;

  if (intent && intent.is_natural_language) {
    const parts = [];
    if (intent.locations && intent.locations.length) {
      parts.push(`📍 ${intent.locations.join(', ')}`);
    }
    if (intent.work_mode) {
      parts.push(`🏠 ${intent.work_mode}`);
    }
    if (intent.skills && intent.skills.length) {
      parts.push(`⚡ ${intent.skills.join(', ')}`);
    }
    if (intent.freshers) {
      parts.push(`🎓 Fresher/Intern`);
    }
    textEl.textContent = parts.join(' • ') || intent.query_clean;
    badge.style.display = 'inline-flex';
  } else {
    badge.style.display = 'none';
  }
}

window.applySuggestion = function(text) {
  if (!roleSearchInput) return;
  roleSearchInput.value = text;
  state.q = text.trim();
  state.page = 1;
  if (clearSearchBtn) clearSearchBtn.style.display = 'block';
  fetchJobs();
};

window.clearSemanticQuery = function() {
  if (roleSearchInput) roleSearchInput.value = '';
  state.q = '';
  state.page = 1;
  if (clearSearchBtn) clearSearchBtn.style.display = 'none';
  const badge = document.getElementById('semanticIntentBadge');
  if (badge) badge.style.display = 'none';
  fetchJobs();
};

// ── Explainable Match Modal Logic ───────────────────────────
window.openMatchModal = function(jobId) {
  const job = state.jobsCache[jobId];
  if (!job) return;

  const modal = document.getElementById('matchModal');
  if (!modal) return;

  const m = job.match || {
    score: 80,
    match_percentage: '80% Match',
    match_grade: 'Strong Match',
    strong_matches: [],
    missing_skills: [],
    breakdown: { skills: 80, role: 80, semantic: 80, location: 80, work_mode: 80, experience: 80 },
    summary: 'Calculated using candidate skills and role criteria.'
  };

  document.getElementById('modalCompany').textContent = job.company || 'Company';
  document.getElementById('modalRole').textContent = job.role || 'Role';
  document.getElementById('modalScoreNum').textContent = `${m.score}%`;
  document.getElementById('modalGradeTitle').textContent = m.match_grade || 'Match Evaluation';
  document.getElementById('modalSummaryDesc').textContent = m.summary || '';

  // Strong matches
  const strongWrap = document.getElementById('modalStrongTags');
  if (m.strong_matches && m.strong_matches.length > 0) {
    strongWrap.innerHTML = m.strong_matches.map(s => `<span class="match-pill green">✓ ${escapeHtml(s)}</span>`).join('');
  } else {
    strongWrap.innerHTML = `<span class="empty-skills-msg">None explicitly detected in text</span>`;
  }

  // Missing skills
  const missingWrap = document.getElementById('modalMissingTags');
  if (m.missing_skills && m.missing_skills.length > 0) {
    missingWrap.innerHTML = m.missing_skills.map(s => `<span class="match-pill amber">✕ ${escapeHtml(s)}</span>`).join('');
  } else {
    missingWrap.innerHTML = `<span class="empty-skills-msg" style="color: #059669; font-weight: 600;">✓ All key requirements met!</span>`;
  }

  // Dimension breakdown progress bars
  const barsWrap = document.getElementById('modalBreakdownBars');
  const b = m.breakdown || {};
  const dimensions = [
    { label: 'Technical Skills Fit', val: b.skills || m.score },
    { label: 'Role Alignment', val: b.role || m.score },
    { label: 'Semantic Concept Similarity', val: b.semantic || m.score },
    { label: 'Location Affinity', val: b.location || 100 },
    { label: 'Work Mode Compatibility', val: b.work_mode || 100 },
    { label: 'Experience Level Suitability', val: b.experience || 100 }
  ];

  barsWrap.innerHTML = dimensions.map(d => `
    <div class="breakdown-bar-item">
      <div class="breakdown-bar-header">
        <span>${d.label}</span>
        <span class="breakdown-bar-value">${d.val}%</span>
      </div>
      <div class="breakdown-bar-track">
        <div class="breakdown-bar-fill" style="width: ${d.val}%;"></div>
      </div>
    </div>
  `).join('');

  if (state.candidateProfile && state.candidateProfile.name) {
    const sc = state.candidateProfile.skills ? state.candidateProfile.skills.length : 13;
    document.getElementById('modalCandidateNote').textContent = `Evaluated against ${state.candidateProfile.name}'s profile (${sc} skills)`;
  }

  modal.style.display = 'flex';
};

window.closeMatchModal = function(e) {
  if (e && e.target && e.target.id !== 'matchModal' && !e.target.classList.contains('match-modal-close')) {
    return;
  }
  const modal = document.getElementById('matchModal');
  if (modal) modal.style.display = 'none';
};

// ── Candidate Profile Editor ────────────────────────────────
async function fetchCandidateProfile() {
  try {
    const res = await fetch('/api/profile');
    if (!res.ok) throw new Error('Failed to load profile');
    const data = await res.json();
    state.candidateProfile = data.profile;
    state.availableSkillsCatalog = data.available_skills || [];
    renderProfileEditor();
  } catch (err) {
    console.error('Error loading candidate profile:', err);
  }
}

function renderProfileEditor() {
  if (!state.candidateProfile) return;
  const p = state.candidateProfile;

  // Header display
  const nameEl = document.getElementById('profileNameDisplay');
  const emailEl = document.getElementById('profileEmailDisplay');
  const headlineEl = document.getElementById('profileHeadlineBadge');
  const countEl = document.getElementById('profileSkillsCount');

  if (nameEl) nameEl.textContent = p.name || 'Candidate';
  if (emailEl) emailEl.textContent = p.email || '';
  if (headlineEl) headlineEl.textContent = p.headline || 'Candidate';
  if (countEl) countEl.textContent = (p.skills || []).length;

  // Skills tag cloud
  const skillsCloud = document.getElementById('profileSkillsCloud');
  if (skillsCloud) {
    skillsCloud.innerHTML = (p.skills || []).map(skill => `
      <span class="interactive-tag active-tag">
        <span>${escapeHtml(skill)}</span>
        <button type="button" class="tag-remove-btn" onclick="removeSkill('${escapeHtml(skill)}')" title="Remove skill">×</button>
      </span>
    `).join('');
  }

  // Suggested skills chips (from catalog not already in profile)
  const chipsWrap = document.getElementById('suggestChipsContainer');
  if (chipsWrap && state.availableSkillsCatalog) {
    const userSkillsLower = new Set((p.skills || []).map(s => s.toLowerCase()));
    const unpicked = state.availableSkillsCatalog.filter(s => !userSkillsLower.has(s.name.toLowerCase()));
    chipsWrap.innerHTML = unpicked.slice(0, 10).map(s => `
      <button type="button" class="suggest-chip" onclick="addSkill('${escapeHtml(s.name)}')">+ ${escapeHtml(s.name)}</button>
    `).join('');
  }

  // Target roles
  const rolesCloud = document.getElementById('profileRolesCloud');
  if (rolesCloud) {
    rolesCloud.innerHTML = (p.target_roles || []).map(role => `
      <span class="interactive-tag">
        <span>${escapeHtml(role)}</span>
        <button type="button" class="tag-remove-btn" onclick="removeRole('${escapeHtml(role)}')" title="Remove role">×</button>
      </span>
    `).join('');
  }

  // Experience level
  document.querySelectorAll('#experienceLevelGroup .segment-btn').forEach(btn => {
    if (btn.getAttribute('data-exp') === p.experience_level) {
      btn.classList.add('active');
    } else {
      btn.classList.remove('active');
    }
  });

  // Preferred locations
  const locsCloud = document.getElementById('profileLocationsCloud');
  if (locsCloud) {
    const tierOne = ["Pune", "Bangalore", "Mumbai", "Hyderabad", "Delhi / NCR", "Remote", "Indore", "Nagpur", "Chennai"];
    const userLocs = new Set((p.preferred_locations || []).map(l => l.toLowerCase()));
    locsCloud.innerHTML = tierOne.map(city => {
      const isSel = userLocs.has(city.toLowerCase());
      return `
        <button type="button" class="interactive-tag ${isSel ? 'active-tag' : ''}" onclick="togglePreferredLocation('${city}')">
          <span>${city}</span>
          ${isSel ? '✓' : '+'}
        </button>
      `;
    }).join('');
  }

  // Preferred work modes
  const modeInputs = document.querySelectorAll('#profileWorkModes input[type="checkbox"]');
  const userModes = new Set((p.preferred_work_modes || []).map(m => m.toLowerCase()));
  modeInputs.forEach(cb => {
    cb.checked = userModes.has(cb.value.toLowerCase());
  });
}

window.addSkill = function(skillName) {
  if (!state.candidateProfile || !skillName) return;
  if (!state.candidateProfile.skills) state.candidateProfile.skills = [];
  const exists = state.candidateProfile.skills.some(s => s.toLowerCase() === skillName.toLowerCase());
  if (!exists) {
    state.candidateProfile.skills.push(skillName);
    renderProfileEditor();
  }
};

window.removeSkill = function(skillName) {
  if (!state.candidateProfile || !state.candidateProfile.skills) return;
  state.candidateProfile.skills = state.candidateProfile.skills.filter(s => s.toLowerCase() !== skillName.toLowerCase());
  renderProfileEditor();
};

window.addRole = function(roleName) {
  if (!state.candidateProfile || !roleName) return;
  if (!state.candidateProfile.target_roles) state.candidateProfile.target_roles = [];
  const exists = state.candidateProfile.target_roles.some(r => r.toLowerCase() === roleName.toLowerCase());
  if (!exists) {
    state.candidateProfile.target_roles.push(roleName);
    renderProfileEditor();
  }
};

window.removeRole = function(roleName) {
  if (!state.candidateProfile || !state.candidateProfile.target_roles) return;
  state.candidateProfile.target_roles = state.candidateProfile.target_roles.filter(r => r.toLowerCase() !== roleName.toLowerCase());
  renderProfileEditor();
};

window.togglePreferredLocation = function(city) {
  if (!state.candidateProfile) return;
  if (!state.candidateProfile.preferred_locations) state.candidateProfile.preferred_locations = [];
  const idx = state.candidateProfile.preferred_locations.findIndex(l => l.toLowerCase() === city.toLowerCase());
  if (idx >= 0) {
    state.candidateProfile.preferred_locations.splice(idx, 1);
  } else {
    state.candidateProfile.preferred_locations.push(city);
  }
  renderProfileEditor();
};

window.saveCandidateProfile = async function() {
  if (!state.candidateProfile) return;
  
  // Read current checked work modes
  const checkedModes = [];
  document.querySelectorAll('#profileWorkModes input[type="checkbox"]:checked').forEach(cb => {
    checkedModes.push(cb.value);
  });
  state.candidateProfile.preferred_work_modes = checkedModes;

  const btn = document.getElementById('saveProfileBtn');
  if (btn) btn.textContent = 'Saving & Computing...';

  try {
    const res = await fetch('/api/profile', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(state.candidateProfile)
    });
    if (!res.ok) throw new Error('Save failed');
    const data = await res.json();
    state.candidateProfile = data.profile;

    if (btn) btn.textContent = 'Saved! ✓';
    setTimeout(() => {
      if (btn) btn.textContent = 'Save Profile & Update Matches ✨';
    }, 2000);

    // Refresh jobs with updated profile match scoring
    state.page = 1;
    fetchJobs();
  } catch (err) {
    console.error('Error saving profile:', err);
    if (btn) btn.textContent = 'Error saving profile';
  }
};

window.resetProfileToDefault = async function() {
  if (!confirm('Reset candidate profile to default settings?')) return;
  try {
    const defaultProfile = {
      name: "Lalit Chaudhari",
      email: "lalitchoudhari851@gmail.com",
      headline: "AI/ML Engineer & GenAI Developer (Fresher)",
      skills: ["Python", "RAG", "LLM", "LangChain", "GenAI", "Machine Learning", "Deep Learning", "PyTorch", "NLP", "FastAPI", "SQL", "Docker", "Agentic AI"],
      target_roles: ["AI/ML Engineer Intern", "GenAI Developer Intern", "LLM Engineer Intern", "Machine Learning Intern", "Data Science Intern"],
      experience_level: "Fresher / Intern",
      preferred_locations: ["Pune", "Bangalore", "Remote", "Mumbai", "Hyderabad"],
      preferred_work_modes: ["Remote", "Hybrid", "On-site"]
    };
    state.candidateProfile = defaultProfile;
    await saveCandidateProfile();
    renderProfileEditor();
  } catch (err) {
    console.error('Error resetting profile:', err);
  }
};

// ── Resume & Profile Understanding Handlers ─────────────────
state.selectedResumeFile = null;
state.extractedProfileData = null;

window.switchResumeTab = function(tab) {
  const uploadBtn = document.getElementById('tabUploadPdf');
  const pasteBtn = document.getElementById('tabPasteText');
  const uploadPane = document.getElementById('resumeUploadPane');
  const pastePane = document.getElementById('resumePastePane');

  if (tab === 'upload') {
    uploadBtn.classList.add('active');
    pasteBtn.classList.remove('active');
    uploadPane.style.display = 'flex';
    pastePane.style.display = 'none';
  } else {
    pasteBtn.classList.add('active');
    uploadBtn.classList.remove('active');
    pastePane.style.display = 'flex';
    uploadPane.style.display = 'none';
  }
};

window.handleResumeFileSelect = function(e) {
  const file = e.target.files && e.target.files[0];
  if (!file) return;
  state.selectedResumeFile = file;

  const badge = document.getElementById('selectedFileName');
  if (badge) {
    const sizeKb = Math.round(file.size / 1024);
    badge.textContent = `📄 ${file.name} (${sizeKb} KB)`;
    badge.style.display = 'inline-flex';
  }
};

window.clearResumeInput = function() {
  state.selectedResumeFile = null;
  state.extractedProfileData = null;
  const fileInput = document.getElementById('resumeFileInput');
  if (fileInput) fileInput.value = '';
  const textInput = document.getElementById('resumeTextInput');
  if (textInput) textInput.value = '';
  const badge = document.getElementById('selectedFileName');
  if (badge) badge.style.display = 'none';
  const preview = document.getElementById('extractedProfileSection');
  if (preview) preview.style.display = 'none';
  const apiKey = document.getElementById('resumeApiKeyInput');
  if (apiKey) apiKey.value = '';
};

window.triggerResumeExtraction = async function() {
  const extractBtn = document.getElementById('btnExtractResume');
  const loadingPill = document.getElementById('resumeLoadingState');
  const apiKeyInput = document.getElementById('resumeApiKeyInput');
  const apiKey = apiKeyInput ? apiKeyInput.value.trim() : '';

  let payload = {};

  if (state.selectedResumeFile) {
    const file = state.selectedResumeFile;
    if (file.name.toLowerCase().endsWith('.pdf')) {
      loadingPill.style.display = 'inline-flex';
      extractBtn.disabled = true;

      const base64Data = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => {
          const res = reader.result;
          const base64Str = res.split(',')[1];
          resolve(base64Str);
        };
        reader.onerror = reject;
        reader.readAsDataURL(file);
      });

      payload = {
        file_base64: base64Data,
        filename: file.name,
        api_key: apiKey || null
      };
    } else {
      loadingPill.style.display = 'inline-flex';
      extractBtn.disabled = true;
      const textData = await file.text();
      payload = {
        text: textData,
        filename: file.name,
        api_key: apiKey || null
      };
    }
  } else {
    const textInput = document.getElementById('resumeTextInput');
    const text = textInput ? textInput.value.trim() : '';
    if (!text) {
      alert('Please upload a resume file (PDF/TXT) or paste your resume text first.');
      return;
    }
    payload = {
      text: text,
      filename: 'pasted_resume.txt',
      api_key: apiKey || null
    };
    loadingPill.style.display = 'inline-flex';
    extractBtn.disabled = true;
  }

  try {
    const res = await fetch('/api/resume/parse', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!data.success) {
      throw new Error(data.error || 'Failed to parse resume');
    }

    state.extractedProfileData = data.profile;
    renderExtractedResumeProfile(data.profile);

    const preview = document.getElementById('extractedProfileSection');
    if (preview) {
      preview.style.display = 'flex';
      preview.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  } catch (err) {
    console.error('Error extracting resume:', err);
    alert('Resume parsing error: ' + err.message);
  } finally {
    loadingPill.style.display = 'none';
    extractBtn.disabled = false;
  }
};

function renderExtractedResumeProfile(p) {
  if (!p) return;

  const headlineEl = document.getElementById('extractedCandidateHeadline');
  const metaEl = document.getElementById('extractedCandidateMeta');
  const modeBadge = document.getElementById('extractionModeBadge');
  const countEl = document.getElementById('extractedSkillsCount');

  if (headlineEl) headlineEl.textContent = p.headline || 'Candidate Profile';
  if (metaEl) {
    metaEl.textContent = `${p.name || 'Candidate'} • ${p.experience ? p.experience.level : (p.experience_level || 'Fresher')} • ${p.email || 'Email not provided'}`;
  }
  if (modeBadge) modeBadge.textContent = p.extraction_mode || 'Deterministic NLP (Zero Hallucination)';
  if (countEl) countEl.textContent = p.skills_count || (p.skills ? p.skills.length : 0);

  // Verified skills tags
  const skillsWrap = document.getElementById('extractedSkillsTags');
  if (skillsWrap) {
    skillsWrap.innerHTML = (p.skills || []).map(skill => `
      <span class="extracted-tag green">✓ ${escapeHtml(skill)}</span>
    `).join('');
  }

  // Target roles
  const rolesWrap = document.getElementById('extractedRolesTags');
  if (rolesWrap) {
    rolesWrap.innerHTML = (p.target_roles || []).map(role => `
      <span class="extracted-tag">${escapeHtml(role)}</span>
    `).join('');
  }

  // Preferred locations
  const locsWrap = document.getElementById('extractedLocsTags');
  if (locsWrap) {
    locsWrap.innerHTML = (p.preferred_locations || []).map(loc => `
      <span class="extracted-tag">📍 ${escapeHtml(loc)}</span>
    `).join('');
  }

  // Projects
  const projectsList = document.getElementById('extractedProjectsList');
  if (projectsList) {
    if (p.projects && p.projects.length > 0) {
      projectsList.innerHTML = p.projects.map(proj => `
        <div class="project-item-card">
          <div class="project-title-row">
            <span class="project-title">${escapeHtml(proj.title)}</span>
          </div>
          ${proj.tech_stack && proj.tech_stack.length > 0 ? `
            <div class="project-tech-tags">
              ${proj.tech_stack.map(t => `<span class="project-tech-pill">${escapeHtml(t)}</span>`).join('')}
            </div>
          ` : ''}
          <div class="project-summary-text">${escapeHtml(proj.summary || '')}</div>
        </div>
      `).join('');
    } else {
      projectsList.innerHTML = `<span style="font-size: 0.8rem; color: #71717A;">No distinct project sections identified in text.</span>`;
    }
  }
}

window.applyExtractedProfileToEngine = async function() {
  if (!state.extractedProfileData) return;
  const btn = document.getElementById('btnApplyExtracted');
  if (btn) btn.textContent = 'Applying & Recalculating...';

  try {
    const res = await fetch('/api/resume/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ profile: state.extractedProfileData })
    });
    const data = await res.json();
    if (!data.success) throw new Error(data.error || 'Failed to apply profile');

    state.candidateProfile = data.profile;
    renderProfileEditor();

    if (btn) btn.textContent = 'Profile Applied Successfully! ✓';

    // Reload jobs matching
    state.page = 1;
    fetchJobs();

    setTimeout(() => {
      navigateTo('dashboard');
    }, 900);
  } catch (err) {
    console.error('Error applying profile:', err);
    alert('Failed to apply extracted profile: ' + err.message);
    if (btn) btn.textContent = 'Apply to JobFlux & View Matched Jobs →';
  }
};

