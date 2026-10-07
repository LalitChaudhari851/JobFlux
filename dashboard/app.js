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
  sort: 'posted_desc',
  contacts: [],
  contactQuery: '',
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

  // Rows per page
  limitSelect.addEventListener('change', (e) => {
    state.limit = parseInt(e.target.value, 10) || 10;
    state.page = 1;
    fetchJobs();
  });

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

    renderJobs(data.jobs || []);
    renderPagination(data);
  } catch (err) {
    console.error('Error fetching jobs:', err);
    jobsTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state">
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
      <td colspan="7" class="loading-state">
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
        <td colspan="7" class="empty-state">
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

  jobs.forEach(job => {
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
    roleCell.innerHTML = `<span class="role-title">${escapeHtml(job.role)}</span>`;

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
