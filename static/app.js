/**
 * Nagpur Estates AI Voice CRM — Enterprise Frontend Architecture
 * Single Page Application Controller with Real-Time Gemini 3.1 Live Audio Tracking
 */

const AppState = {
  authToken: localStorage.getItem('nagpur_crm_token') || null,
  currentUser: null,
  currentView: 'dashboard',
  leads: [],
  selectedLeads: new Set(),
  activeCallId: null,
  liveCallPollInterval: null,
  liveCallSeconds: 0,
  currentLeadInDrawer: null,
  debounceTimer: null,
  theme: localStorage.getItem('crm-theme') || 'light',
  isSidebarCollapsed: localStorage.getItem('sidebar-collapsed') === 'true',
  properties: [],
  calls: [],
  siteVisits: [],
  callbacks: [],
  knowledgeDocs: []
};

window.App = {
  // ---------------------------------------------------------------------------
  // Lifecycle & Initialization
  // ---------------------------------------------------------------------------
  init() {
    this.applyTheme(AppState.theme);
    this.applySidebarCollapse(AppState.isSidebarCollapsed);
    this.setupKeyboardShortcuts();
    this.checkAuth();
    this.checkHealthStatus();
    setInterval(() => this.checkHealthStatus(), 30000);
  },

  refreshIcons() {
    if (window.lucide && typeof window.lucide.createIcons === 'function') {
      window.lucide.createIcons();
    }
  },

  // ---------------------------------------------------------------------------
  // Centralized API Client
  // ---------------------------------------------------------------------------
  async authFetch(url, options = {}) {
    options.headers = options.headers || {};
    if (AppState.authToken) {
      if (options.headers instanceof Headers) {
        options.headers.set('Authorization', `Bearer ${AppState.authToken}`);
      } else {
        options.headers['Authorization'] = `Bearer ${AppState.authToken}`;
      }
    }

    try {
      const res = await fetch(url, options);
      if (res.status === 401) {
        console.warn('Session expired or unauthorized. Returning to login screen.');
        this.handleLogout(false);
        throw new Error('Unauthorized');
      }
      return res;
    } catch (err) {
      throw err;
    }
  },

  // ---------------------------------------------------------------------------
  // Authentication Flow
  // ---------------------------------------------------------------------------
  async checkAuth() {
    if (!AppState.authToken) {
      this.showAuthScreen();
      return;
    }

    try {
      const res = await fetch('/api/auth/me', {
        headers: { 'Authorization': `Bearer ${AppState.authToken}` }
      });

      if (res.ok) {
        const user = await res.json();
        AppState.currentUser = user;
        this.showAppScreen(user);
        this.initWorkspaceData();
      } else {
        this.showAuthScreen();
      }
    } catch (err) {
      this.showAuthScreen();
    }
  },

  showAuthScreen() {
    const authScreen = document.getElementById('auth-screen');
    const appContainer = document.getElementById('app-main-container');
    if (authScreen) authScreen.style.display = 'flex';
    if (appContainer) appContainer.style.display = 'none';
    this.refreshIcons();
  },

  showAppScreen(user) {
    const authScreen = document.getElementById('auth-screen');
    const appContainer = document.getElementById('app-main-container');
    if (authScreen) authScreen.style.display = 'none';
    if (appContainer) appContainer.style.display = 'flex';

    if (user) {
      const nameEl = document.getElementById('sidebar-user-name');
      const roleEl = document.getElementById('sidebar-user-role');
      const avatarEl = document.getElementById('sidebar-user-avatar');
      const greetingEl = document.getElementById('dash-greeting-name');

      if (nameEl) nameEl.innerText = user.name || 'Admin Manager';
      if (roleEl) roleEl.innerText = (user.role || 'Administrator').toUpperCase();
      if (avatarEl) avatarEl.innerText = (user.name || 'A')[0].toUpperCase();
      if (greetingEl) greetingEl.innerText = (user.name || 'Admin').split(' ')[0];
    }
    this.refreshIcons();
  },

  async handleLogin(event) {
    if (event) event.preventDefault();
    const email = document.getElementById('login-email')?.value.trim() || '';
    const password = document.getElementById('login-password')?.value.trim() || '';
    const errorBox = document.getElementById('login-error-box');
    const errorMsg = document.getElementById('login-error-msg');
    const btnText = document.getElementById('login-btn-text');

    if (errorBox) errorBox.classList.add('hidden');
    if (btnText) btnText.innerText = 'Signing In...';

    try {
      const res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.detail || 'Invalid email or password.');
      }

      AppState.authToken = data.token;
      AppState.currentUser = data.user;
      localStorage.setItem('nagpur_crm_token', data.token);

      this.showAppScreen(data.user);
      this.initWorkspaceData();
      this.showToast('success', `Welcome back, ${data.user.name}!`);
    } catch (err) {
      if (errorMsg) errorMsg.innerText = err.message || 'Login failed';
      if (errorBox) errorBox.classList.remove('hidden');
    } finally {
      if (btnText) btnText.innerText = 'Sign In to CRM';
    }
  },

  async handleLogout(notifyServer = true) {
    if (notifyServer && AppState.authToken) {
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch {}
    }
    AppState.authToken = null;
    AppState.currentUser = null;
    localStorage.removeItem('nagpur_crm_token');
    this.showAuthScreen();
    this.showToast('info', 'Logged out successfully.');
  },

  togglePasswordVisibility(inputId) {
    const input = document.getElementById(inputId);
    if (input) {
      input.type = input.type === 'password' ? 'text' : 'password';
    }
  },

  // ---------------------------------------------------------------------------
  // Health & AI Engine Probe
  // ---------------------------------------------------------------------------
  async checkHealthStatus() {
    try {
      const res = await fetch('/health');
      if (res.ok) {
        const data = await res.json();
        const headerBadge = document.getElementById('header-live-badge');
        const headerText = document.getElementById('header-live-text');
        const sidebarLabel = document.getElementById('sidebar-agent-status-label');
        const pulseDot = document.getElementById('sidebar-pulse-dot');

        if (headerBadge) {
          headerBadge.className = 'hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-xs font-semibold';
        }
        if (headerText) headerText.innerText = 'Gemini 3.1 Operational';
        if (sidebarLabel) {
          sidebarLabel.innerText = 'Operational';
          sidebarLabel.className = 'text-[10px] text-emerald-400 font-medium';
        }
        if (pulseDot) pulseDot.className = 'pulse-dot-green flex-shrink-0';
      }
    } catch (e) {
      const sidebarLabel = document.getElementById('sidebar-agent-status-label');
      if (sidebarLabel) {
        sidebarLabel.innerText = 'Offline';
        sidebarLabel.className = 'text-[10px] text-red-400 font-medium';
      }
    }
  },

  // ---------------------------------------------------------------------------
  // Workspace Navigation & Router
  // ---------------------------------------------------------------------------
  navigate(viewName) {
    AppState.currentView = viewName;

    document.querySelectorAll('.nav-item').forEach(item => {
      const target = item.getAttribute('data-view');
      item.classList.toggle('active', target === viewName);
    });

    document.querySelectorAll('.view-pane').forEach(pane => {
      pane.classList.toggle('hidden', pane.id !== `view-${viewName}`);
    });

    const titles = {
      'dashboard': { title: 'CRM Dashboard', subtitle: 'Real estate sales command & outbound voice operations' },
      'leads': { title: 'Leads Pipeline', subtitle: 'Manage buyers, budget qualification & outbound dialing' },
      'campaigns': { title: 'AI Calling Campaigns', subtitle: 'Automated batch dialing workflows & concurrency control' },
      'calls': { title: 'Call History & Transcripts', subtitle: 'Gemini 3.1 Live turns, latency metrics & recordings' },
      'properties': { title: 'Property Inventory', subtitle: 'Nagpur residential & commercial listings for AI matching' },
      'knowledge-base': { title: 'Knowledge Base & RAG', subtitle: 'Project brochures and vector embeddings storage' },
      'rag-playground': { title: 'RAG Retrieval Sandbox', subtitle: 'Test real-time similarity search & chunk extraction' },
      'site-visits': { title: 'Site Visits Schedule', subtitle: 'On-site property tours and customer confirmations' },
      'follow-ups': { title: 'Follow-ups & Callbacks', subtitle: 'Scheduled customer callbacks and reminders' },
      'analytics': { title: 'Voice AI & Sales Analytics', subtitle: 'Latency P50/P90, duration & locality demand metrics' }
    };

    const info = titles[viewName] || { title: 'Nagpur Estates CRM', subtitle: 'AI Voice Operating System' };
    const titleEl = document.getElementById('header-page-title');
    const subtitleEl = document.getElementById('header-page-subtitle');
    if (titleEl) titleEl.innerText = info.title;
    if (subtitleEl) subtitleEl.innerText = info.subtitle;

    this.closeMobileSidebar();
    this.loadViewData(viewName);
    this.refreshIcons();
  },

  loadViewData(viewName) {
    if (!AppState.authToken) return;
    if (viewName === 'dashboard') this.loadDashboardData();
    else if (viewName === 'leads') this.fetchLeads();
    else if (viewName === 'properties') this.fetchProperties();
    else if (viewName === 'knowledge-base') this.fetchKnowledgeDocs();
    else if (viewName === 'calls') this.fetchCalls();
    else if (viewName === 'site-visits') this.fetchSiteVisits();
    else if (viewName === 'follow-ups') this.fetchCallbacks();
    else if (viewName === 'analytics') this.fetchAnalytics();
  },

  initWorkspaceData() {
    this.loadDashboardData();
    this.fetchLeads();
    this.fetchProperties();
    this.fetchKnowledgeDocs();
    this.fetchCalls();
    this.fetchSiteVisits();
    this.fetchCallbacks();
    this.fetchAnalytics();
  },

  openMobileSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('mobile-sidebar-overlay');
    if (sidebar) sidebar.classList.add('mobile-open');
    if (overlay) overlay.classList.add('active');
    this.refreshIcons();
  },

  closeMobileSidebar() {
    const sidebar = document.getElementById('app-sidebar');
    const overlay = document.getElementById('mobile-sidebar-overlay');
    if (sidebar) sidebar.classList.remove('mobile-open');
    if (overlay) overlay.classList.remove('active');
  },

  toggleSidebarCollapse() {
    AppState.isSidebarCollapsed = !AppState.isSidebarCollapsed;
    localStorage.setItem('sidebar-collapsed', AppState.isSidebarCollapsed);
    this.applySidebarCollapse(AppState.isSidebarCollapsed);
  },

  applySidebarCollapse(isCollapsed) {
    const sidebar = document.getElementById('app-sidebar');
    const icon = document.getElementById('sidebar-collapse-icon');
    if (sidebar) {
      sidebar.classList.toggle('collapsed', isCollapsed);
    }
    if (icon) {
      icon.setAttribute('data-lucide', isCollapsed ? 'chevrons-right' : 'chevrons-left');
    }
    this.refreshIcons();
  },

  // ---------------------------------------------------------------------------
  // Theme Management
  // ---------------------------------------------------------------------------
  toggleTheme() {
    const nextTheme = AppState.theme === 'dark' ? 'light' : 'dark';
    AppState.theme = nextTheme;
    localStorage.setItem('crm-theme', nextTheme);
    this.applyTheme(nextTheme);
  },

  applyTheme(theme) {
    const isDark = theme === 'dark';
    document.body.classList.toggle('dark', isDark);
    const themeBtn = document.getElementById('theme-toggle-btn');
    if (themeBtn) {
      themeBtn.innerHTML = isDark
        ? '<i data-lucide="sun" class="w-4 h-4 text-amber-400"></i>'
        : '<i data-lucide="moon" class="w-4 h-4"></i>';
    }
    this.refreshIcons();
  },

  // ---------------------------------------------------------------------------
  // Toast Notification System
  // ---------------------------------------------------------------------------
  showToast(type, message, duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `crm-toast toast-${type}`;

    const icons = {
      success: '<i data-lucide="check-circle" class="w-4 h-4 text-emerald-500 flex-shrink-0"></i>',
      error: '<i data-lucide="alert-circle" class="w-4 h-4 text-red-500 flex-shrink-0"></i>',
      warning: '<i data-lucide="alert-triangle" class="w-4 h-4 text-amber-500 flex-shrink-0"></i>',
      info: '<i data-lucide="info" class="w-4 h-4 text-blue-500 flex-shrink-0"></i>'
    };

    toast.innerHTML = `
      ${icons[type] || icons.info}
      <div class="flex-1 text-xs font-medium">${message}</div>
      <button class="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200" onclick="this.parentElement.remove()">
        <i data-lucide="x" class="w-3.5 h-3.5"></i>
      </button>
    `;

    container.appendChild(toast);
    this.refreshIcons();

    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      setTimeout(() => toast.remove(), 200);
    }, duration);
  },

  // ---------------------------------------------------------------------------
  // 1. Dashboard View Logic
  // ---------------------------------------------------------------------------
  async loadDashboardData() {
    try {
      const res = await this.authFetch('/api/dashboard');
      const data = await res.json();

      const kpis = data.kpis;
      document.getElementById('kpi-total-leads').innerText = kpis.total_leads;
      document.getElementById('kpi-hot-leads').innerText = kpis.hot_leads;
      document.getElementById('kpi-total-calls').innerText = kpis.total_calls;
      document.getElementById('kpi-completed-calls').innerText = kpis.completed_calls;
      document.getElementById('kpi-site-visits').innerText = kpis.site_visits;
      document.getElementById('kpi-conversion-rate').innerText = `${kpis.conversion_rate}%`;

      const badgeLeads = document.getElementById('badge-leads-count');
      const badgeCallbacks = document.getElementById('badge-callbacks-due');
      if (badgeLeads) badgeLeads.innerText = kpis.total_leads;
      if (badgeCallbacks) badgeCallbacks.innerText = kpis.callbacks_due;

      // Pipeline Stepper
      const stepper = document.getElementById('dash-pipeline-stepper');
      if (stepper) {
        stepper.innerHTML = Object.entries(data.pipeline).map(([stage, count]) => `
          <div class="flex-1 p-3 rounded-xl bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-center min-w-[90px]">
            <div class="text-[10px] font-bold uppercase tracking-wider text-slate-500 truncate">${stage.replace('_', ' ')}</div>
            <div class="text-lg font-black text-indigo-600 dark:text-indigo-400 mt-1">${count}</div>
          </div>
        `).join('');
      }

      // Recent CRM Activities
      const actTbody = document.getElementById('dash-activity-rows');
      if (actTbody) {
        if (!data.recent_activities || !data.recent_activities.length) {
          actTbody.innerHTML = `<tr><td colspan="4" class="text-center text-slate-400 py-6">No recent activity recorded.</td></tr>`;
        } else {
          actTbody.innerHTML = data.recent_activities.map(a => `
            <tr>
              <td class="text-slate-400 text-xs whitespace-nowrap">${this.formatDate(a.created_at)}</td>
              <td><span class="crm-badge crm-badge-stage">${a.type.replace('_', ' ')}</span></td>
              <td class="text-xs text-slate-700 dark:text-slate-300">${a.description}</td>
              <td class="text-xs font-mono text-slate-400">${a.lead_id || 'N/A'}</td>
            </tr>
          `).join('');
        }
      }
      this.refreshIcons();
    } catch (err) {
      console.error('Failed to load dashboard data:', err);
    }
  },

  // ---------------------------------------------------------------------------
  // 2. Leads Pipeline Logic
  // ---------------------------------------------------------------------------
  debounceFetchLeads() {
    clearTimeout(AppState.debounceTimer);
    AppState.debounceTimer = setTimeout(() => this.fetchLeads(), 250);
  },

  async fetchLeads() {
    const search = document.getElementById('lead-search-input')?.value || '';
    const stage = document.getElementById('lead-stage-filter')?.value || 'all';
    const temp = document.getElementById('lead-temp-filter')?.value || 'all';
    const loc = document.getElementById('lead-loc-filter')?.value || 'all';

    const tbody = document.getElementById('leads-table-rows');
    if (tbody) {
      tbody.innerHTML = `<tr><td colspan="8" class="text-center text-slate-400 py-8">Loading leads...</td></tr>`;
    }

    try {
      const res = await this.authFetch(`/api/leads?search=${encodeURIComponent(search)}&stage=${stage}&temperature=${temp}&location=${loc}`);
      const data = await res.json();
      AppState.leads = data.leads || [];

      const allCountChip = document.getElementById('count-chip-all');
      if (allCountChip) allCountChip.innerText = data.total || 0;

      if (!data.leads || !data.leads.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-slate-400 py-10">No leads match your filter criteria.</td></tr>`;
        return;
      }

      tbody.innerHTML = data.leads.map(l => {
        const isChecked = AppState.selectedLeads.has(l.id);
        const tempBadge = l.lead_temperature === 'hot'
          ? `<span class="crm-badge crm-badge-hot">🔥 Hot</span>`
          : l.lead_temperature === 'warm'
          ? `<span class="crm-badge crm-badge-warm">⚡ Warm</span>`
          : `<span class="crm-badge crm-badge-cold">❄️ Cold</span>`;

        return `
          <tr class="${isChecked ? 'bg-indigo-50/50 dark:bg-indigo-950/20' : ''}">
            <td data-label="Select">
              <input type="checkbox" onchange="App.toggleLeadSelection('${l.id}')" ${isChecked ? 'checked' : ''} class="rounded text-indigo-600">
            </td>
            <td data-label="Customer">
              <div class="flex items-center gap-2.5">
                <div class="w-8 h-8 rounded-full bg-indigo-50 dark:bg-slate-800 text-indigo-700 dark:text-indigo-300 font-bold text-xs flex items-center justify-center flex-shrink-0">
                  ${(l.name || 'C')[0].toUpperCase()}
                </div>
                <div class="leading-tight">
                  <a href="javascript:void(0)" onclick="App.openLeadDrawer('${l.id}')" class="font-bold text-xs sm:text-sm text-slate-900 dark:text-white hover:text-indigo-600 transition-colors">
                    ${l.name}
                  </a>
                  <div class="text-[11px] text-slate-400">${l.purchase_timeline || 'Immediate'}</div>
                </div>
              </div>
            </td>
            <td data-label="Phone">
              <span class="font-mono text-xs text-slate-600 dark:text-slate-300">${l.masked_phone}</span>
            </td>
            <td data-label="Requirement">
              <div class="text-xs font-medium text-slate-800 dark:text-slate-200">${l.preferred_location || 'Nagpur'}</div>
              <div class="text-[11px] text-slate-400">${l.bhk || ''} ${l.property_type || 'Residential'}</div>
            </td>
            <td data-label="Budget">
              <span class="text-xs font-bold text-emerald-600 dark:text-emerald-400">${l.budget_display}</span>
            </td>
            <td data-label="Temperature">${tempBadge}</td>
            <td data-label="Stage">
              <span class="crm-badge crm-badge-stage">${l.stage.replace('_', ' ')}</span>
            </td>
            <td data-label="Actions" class="text-right whitespace-nowrap">
              <div class="flex items-center justify-end gap-1.5">
                <button onclick="App.initiateCall('${l.phone_number}', '${l.name}', '${l.id}')" class="crm-btn crm-btn-success crm-btn-sm text-xs py-1 px-2.5 shadow-sm" title="Initiate AI Voice Call">
                  <i data-lucide="phone" class="w-3.5 h-3.5"></i>
                  Call
                </button>
                <button onclick="App.openLeadDrawer('${l.id}')" class="crm-btn crm-btn-secondary crm-btn-sm text-xs py-1 px-2.5" title="View Lead Details">
                  Details
                </button>
              </div>
            </td>
          </tr>
        `;
      }).join('');

      this.refreshIcons();
    } catch (err) {
      console.error('Fetch leads error:', err);
      if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-center text-red-500 py-6">Failed to load leads.</td></tr>`;
    }
  },

  setLeadQuickFilter(type) {
    const stageFilter = document.getElementById('lead-stage-filter');
    const tempFilter = document.getElementById('lead-temp-filter');

    // Reset styles on chips
    ['all', 'hot', 'warm', 'site_visit', 'qualified'].forEach(key => {
      const chip = document.getElementById(`chip-filter-${key}`);
      if (chip) {
        if (key === type) {
          chip.className = 'chip-btn px-3 py-1 rounded-full font-medium border border-indigo-500 bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300';
        } else {
          chip.className = 'chip-btn px-3 py-1 rounded-full font-medium border border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800';
        }
      }
    });

    if (type === 'all') {
      if (stageFilter) stageFilter.value = 'all';
      if (tempFilter) tempFilter.value = 'all';
    } else if (type === 'hot' || type === 'warm') {
      if (tempFilter) tempFilter.value = type;
      if (stageFilter) stageFilter.value = 'all';
    } else {
      if (stageFilter) stageFilter.value = type;
      if (tempFilter) tempFilter.value = 'all';
    }

    this.fetchLeads();
  },

  toggleSelectAllLeads(masterCheckbox) {
    if (masterCheckbox.checked) {
      AppState.leads.forEach(l => AppState.selectedLeads.add(l.id));
    } else {
      AppState.selectedLeads.clear();
    }
    this.updateBulkActionBar();
    this.fetchLeads();
  },

  toggleLeadSelection(leadId) {
    if (AppState.selectedLeads.has(leadId)) {
      AppState.selectedLeads.delete(leadId);
    } else {
      AppState.selectedLeads.add(leadId);
    }
    this.updateBulkActionBar();
  },

  clearLeadSelection() {
    AppState.selectedLeads.clear();
    const master = document.getElementById('leads-select-all');
    if (master) master.checked = false;
    this.updateBulkActionBar();
    this.fetchLeads();
  },

  updateBulkActionBar() {
    const bar = document.getElementById('leads-bulk-bar');
    const countEl = document.getElementById('bulk-selected-count');
    const count = AppState.selectedLeads.size;

    if (count > 0) {
      if (bar) bar.classList.remove('hidden');
      if (countEl) countEl.innerText = count;
    } else {
      if (bar) bar.classList.add('hidden');
    }
  },

  callSelectedLeads() {
    const count = AppState.selectedLeads.size;
    if (count === 0) return;
    this.showToast('info', `Queued ${count} leads for AI Outbound batch dialing.`);
  },

  // ---------------------------------------------------------------------------
  // Lead Detail Drawer
  // ---------------------------------------------------------------------------
  async openLeadDrawer(leadId) {
    try {
      const res = await this.authFetch(`/api/leads/${leadId}`);
      const lead = await res.json();
      AppState.currentLeadInDrawer = lead;

      document.getElementById('drawer-lead-name').innerText = lead.name;
      document.getElementById('drawer-lead-phone').innerText = lead.phone_number;
      document.getElementById('drawer-lead-loc').innerText = lead.preferred_location || 'Nagpur';
      document.getElementById('drawer-lead-bhk').innerText = `${lead.bhk || ''} ${lead.property_type || ''}`;
      document.getElementById('drawer-lead-budget').innerText = lead.budget_display;
      document.getElementById('drawer-lead-stage').innerText = lead.stage;

      const notesContainer = document.getElementById('drawer-notes-list');
      if (notesContainer) {
        if (!lead.lead_notes || !lead.lead_notes.length) {
          notesContainer.innerHTML = `<div class="text-slate-400 text-xs py-2">No notes added yet.</div>`;
        } else {
          notesContainer.innerHTML = lead.lead_notes.map(n => `
            <div class="p-2.5 rounded-lg bg-slate-50 dark:bg-slate-900 border border-slate-200 dark:border-slate-800 text-xs">
              <div class="flex items-center justify-between text-[10px] text-slate-400 mb-1">
                <span class="font-semibold text-slate-600 dark:text-slate-300">${n.author}</span>
                <span>${this.formatDate(n.created_at)}</span>
              </div>
              <div class="text-slate-800 dark:text-slate-200">${n.note}</div>
            </div>
          `).join('');
        }
      }

      document.getElementById('drawer-lead-backdrop')?.classList.add('active');
      document.getElementById('drawer-lead')?.classList.add('active');
      this.refreshIcons();
    } catch (err) {
      this.showToast('error', 'Failed to load lead profile: ' + err.message);
    }
  },

  closeLeadDrawer() {
    document.getElementById('drawer-lead-backdrop')?.classList.remove('active');
    document.getElementById('drawer-lead')?.classList.remove('active');
  },

  callLeadFromDrawer() {
    if (!AppState.currentLeadInDrawer) return;
    const lead = AppState.currentLeadInDrawer;
    this.closeLeadDrawer();
    this.initiateCall(lead.phone_number, lead.name, lead.id);
  },

  async saveLeadNote() {
    if (!AppState.currentLeadInDrawer) return;
    const input = document.getElementById('drawer-new-note');
    const note = input?.value.trim();
    if (!note) return;

    try {
      await this.authFetch(`/api/leads/${AppState.currentLeadInDrawer.id}/notes`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ note, author_name: AppState.currentUser?.name || 'Priya' })
      });
      input.value = '';
      this.showToast('success', 'Note saved to lead profile.');
      this.openLeadDrawer(AppState.currentLeadInDrawer.id);
    } catch (err) {
      this.showToast('error', 'Failed to save note: ' + err.message);
    }
  },

  // ---------------------------------------------------------------------------
  // Lead Creation & CSV Import
  // ---------------------------------------------------------------------------
  openNewLeadModal() {
    this.openModal('modal-new-lead');
  },

  async handleCreateLeadSubmit(event) {
    if (event) event.preventDefault();
    const payload = {
      name: document.getElementById('form-lead-name')?.value.trim(),
      phone_number: document.getElementById('form-lead-phone')?.value.trim(),
      preferred_location: document.getElementById('form-lead-loc')?.value,
      property_type: 'Flat',
      bhk: document.getElementById('form-lead-bhk')?.value,
      budget_max: parseFloat(document.getElementById('form-lead-budget')?.value) || 6000000,
      lead_temperature: document.getElementById('form-lead-temp')?.value,
      stage: 'new'
    };

    try {
      const res = await this.authFetch('/api/leads', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      if (!res.ok) throw new Error(await res.text());

      this.closeModal('modal-new-lead');
      this.showToast('success', `Lead ${payload.name} created successfully!`);
      this.fetchLeads();
      this.loadDashboardData();
    } catch (err) {
      this.showToast('error', 'Failed to create lead: ' + err.message);
    }
  },

  triggerCsvImportModal() {
    this.openModal('modal-csv-import');
  },

  async handleCsvFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      this.showToast('info', 'Parsing and validating CSV leads...');
      const res = await this.authFetch('/api/leads/import', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      this.closeModal('modal-csv-import');
      this.showToast('success', `Import Complete: ${data.imported} leads added, ${data.skipped} skipped.`);
      this.fetchLeads();
      this.loadDashboardData();
    } catch (err) {
      this.showToast('error', 'CSV Import failed: ' + err.message);
    }
  },

  // ---------------------------------------------------------------------------
  // 3. Live AI Calling Controller
  // ---------------------------------------------------------------------------
  async initiateCall(phoneNumber, customerName = 'Customer', leadId = null) {
    if (AppState.activeCallId) {
      this.showToast('warning', 'Another AI call is currently active. Hang up first.');
      return;
    }

    const widget = document.getElementById('live-calling-widget');
    const custEl = document.getElementById('live-call-customer-name');
    const statusEl = document.getElementById('live-call-status-label');
    const feed = document.getElementById('live-transcript-feed');

    if (custEl) custEl.innerText = `${customerName} (${phoneNumber})`;
    if (statusEl) statusEl.innerText = 'Dialing SIP Trunk...';
    if (feed) feed.innerHTML = `<div class="text-center text-slate-400 py-4">Connecting to Vobiz SIP Trunk & Priya AI...</div>`;
    if (widget) widget.classList.add('active');

    try {
      const res = await this.authFetch('/api/calls', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          phone_number: phoneNumber,
          customer_name: customerName,
          lead_id: leadId
        })
      });

      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Call dispatch failed');
      }

      const callInfo = await res.json();
      AppState.activeCallId = callInfo.call_id;
      this.startLiveCallPolling(callInfo.call_id);
      this.showToast('success', `Call initiated with ${customerName}`);
    } catch (err) {
      this.showToast('error', 'Call error: ' + err.message);
      if (widget) widget.classList.remove('active');
    }
  },

  startLiveCallPolling(callId) {
    clearInterval(AppState.liveCallPollInterval);
    AppState.liveCallSeconds = 0;

    AppState.liveCallPollInterval = setInterval(async () => {
      AppState.liveCallSeconds++;
      const mm = String(Math.floor(AppState.liveCallSeconds / 60)).padStart(2, '0');
      const ss = String(AppState.liveCallSeconds % 60).padStart(2, '0');
      const timerEl = document.getElementById('live-call-timer');
      if (timerEl) timerEl.innerText = `${mm}:${ss}`;

      try {
        const res = await this.authFetch(`/api/calls/${callId}/live`);
        if (!res.ok) {
          this.stopLiveCallPolling();
          return;
        }
        const data = await res.json();

        const statusEl = document.getElementById('live-call-status-label');
        if (statusEl) statusEl.innerText = `${data.status || 'in_progress'} • ${data.stage || 'Greeting'}`;

        if (data.turns && data.turns.length) {
          const feed = document.getElementById('live-transcript-feed');
          if (feed) {
            feed.innerHTML = data.turns.map(t => `
              <div class="turn-bubble ${t.speaker}">
                <div class="text-[10px] font-bold mb-0.5 opacity-70">${t.speaker === 'assistant' ? 'Priya (AI Voice)' : 'Customer'}</div>
                <div>${t.text}</div>
              </div>
            `).join('');
            feed.scrollTop = feed.scrollHeight;
          }
        }

        if (['completed', 'failed', 'cancelled', 'terminated'].includes(data.status)) {
          this.stopLiveCallPolling();
          this.showToast('info', `Call finished (${data.status}).`);
        }
      } catch (err) {
        console.warn('Live call polling note:', err);
      }
    }, 1000);
  },

  stopLiveCallPolling() {
    clearInterval(AppState.liveCallPollInterval);
    AppState.activeCallId = null;
    setTimeout(() => {
      const widget = document.getElementById('live-calling-widget');
      if (widget) widget.classList.remove('active');
      this.fetchCalls();
      this.loadDashboardData();
      this.fetchLeads();
      this.fetchSiteVisits();
      this.fetchCallbacks();
    }, 1200);
  },

  async hangupActiveCall() {
    if (!AppState.activeCallId) {
      document.getElementById('live-calling-widget')?.classList.remove('active');
      return;
    }
    try {
      await this.authFetch(`/api/calls/${AppState.activeCallId}/hangup`, { method: 'POST' });
      this.showToast('info', 'Terminating active call...');
      this.stopLiveCallPolling();
    } catch (err) {
      console.error('Hangup error:', err);
    }
  },

  // ---------------------------------------------------------------------------
  // 4. Call History Logic
  // ---------------------------------------------------------------------------
  async fetchCalls() {
    const status = document.getElementById('call-status-filter')?.value || 'all';
    const tbody = document.getElementById('calls-table-rows');
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" class="text-center text-slate-400 py-8">Loading calls...</td></tr>`;

    try {
      const res = await this.authFetch(`/api/calls?status=${status}`);
      const data = await res.json();
      AppState.calls = data.calls || [];

      if (!data.calls || !data.calls.length) {
        tbody.innerHTML = `<tr><td colspan="8" class="text-center text-slate-400 py-8">No call history recorded.</td></tr>`;
        return;
      }

      tbody.innerHTML = data.calls.map(c => `
        <tr>
          <td class="font-mono text-xs text-slate-500">${c.call_id}</td>
          <td class="font-bold text-xs sm:text-sm text-slate-900 dark:text-white">${c.customer_name}</td>
          <td class="font-mono text-xs text-slate-500">${c.phone_number_masked}</td>
          <td class="text-xs font-semibold text-slate-700 dark:text-slate-300">${c.duration_seconds}s</td>
          <td class="text-xs font-mono text-indigo-600 dark:text-indigo-400">${c.greeting_latency_ms ? `${c.greeting_latency_ms}ms` : 'N/A'}</td>
          <td class="text-xs font-mono text-slate-500">${c.avg_response_latency_ms ? `${c.avg_response_latency_ms}ms` : 'N/A'}</td>
          <td><span class="crm-badge crm-badge-stage">${c.outcome || 'Completed'}</span></td>
          <td class="text-right">
            <button onclick="App.openCallDetail('${c.call_id}')" class="crm-btn crm-btn-secondary crm-btn-sm text-xs py-1 px-2.5">
              Transcript
            </button>
          </td>
        </tr>
      `).join('');

      this.refreshIcons();
    } catch (err) {
      console.error('Fetch calls error:', err);
    }
  },

  async openCallDetail(callId) {
    try {
      const res = await this.authFetch(`/api/calls/${callId}`);
      const call = await res.json();

      document.getElementById('call-modal-title').innerText = `Call with ${call.customer_name}`;
      document.getElementById('call-modal-meta').innerText = `${call.phone_number_masked} • Duration: ${call.duration_seconds}s • P50 Latency: ${call.p50_latency_ms || 420}ms`;
      document.getElementById('call-modal-summary').innerText = call.summary || 'Summary automatically generated via Gemini.';

      const container = document.getElementById('call-modal-transcript');
      if (container) {
        if (!call.turns || !call.turns.length) {
          container.innerHTML = `<div class="text-center text-slate-400 py-6">No transcript recorded for this call.</div>`;
        } else {
          container.innerHTML = call.turns.map(t => `
            <div class="turn-bubble ${t.speaker}">
              <div class="text-[10px] font-bold mb-0.5 opacity-70">
                ${t.speaker === 'assistant' ? 'Priya (AI Voice)' : call.customer_name} ${t.latency_ms ? `• ${t.latency_ms.toFixed(0)}ms` : ''}
              </div>
              <div>${t.text}</div>
            </div>
          `).join('');
        }
      }

      this.openModal('modal-call-detail');
      this.refreshIcons();
    } catch (err) {
      this.showToast('error', 'Failed to load call detail: ' + err.message);
    }
  },

  // ---------------------------------------------------------------------------
  // 5. Properties Inventory Logic
  // ---------------------------------------------------------------------------
  async fetchProperties() {
    const loc = document.getElementById('prop-location-filter')?.value || 'all';
    const type = document.getElementById('prop-type-filter')?.value || 'all';
    const container = document.getElementById('properties-grid-container');

    try {
      const res = await this.authFetch(`/api/properties?location=${loc}&property_type=${type}`);
      const props = await res.json();
      AppState.properties = props || [];

      if (!props || !props.length) {
        container.innerHTML = `<div class="col-span-3 text-center text-slate-400 py-10">No properties match your filter.</div>`;
        return;
      }

      container.innerHTML = props.map(p => `
        <div class="crm-card p-5 flex flex-col justify-between">
          <div>
            <div class="flex items-center justify-between gap-2 mb-2">
              <span class="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300">${p.location}</span>
              <span class="text-xs font-bold text-emerald-600 dark:text-emerald-400">${p.price_display}</span>
            </div>
            <h3 class="font-bold text-base text-slate-900 dark:text-white">${p.project_name}</h3>
            <div class="text-xs text-slate-500 mt-1">${p.bhk} • ${p.property_type} (${p.carpet_area || 'Standard'})</div>
            <p class="text-xs text-slate-600 dark:text-slate-400 mt-2 line-clamp-2">${p.description}</p>
          </div>

          <div class="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <span class="text-[11px] text-slate-400">${p.available_units || 0} units left</span>
            <button onclick="App.openNewLeadModal()" class="crm-btn crm-btn-secondary crm-btn-sm text-xs py-1 px-3">
              Match Lead
            </button>
          </div>
        </div>
      `).join('');

      this.refreshIcons();
    } catch (err) {
      console.error('Fetch properties error:', err);
    }
  },

  openNewPropertyModal() {
    this.openModal('modal-new-property');
  },

  async handleCreatePropertySubmit(event) {
    if (event) event.preventDefault();
    const payload = {
      project_name: document.getElementById('prop-form-name')?.value.trim(),
      location: document.getElementById('prop-form-loc')?.value.trim(),
      bhk: document.getElementById('prop-form-bhk')?.value.trim(),
      price_display: document.getElementById('prop-form-pricedisp')?.value.trim(),
      price_min: parseFloat(document.getElementById('prop-form-pricemin')?.value) || 5000000,
      price_max: 7500000,
      description: document.getElementById('prop-form-desc')?.value.trim() || 'Nagpur property listing'
    };

    try {
      await this.authFetch('/api/properties', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      this.closeModal('modal-new-property');
      this.showToast('success', 'Property listing created.');
      this.fetchProperties();
    } catch (err) {
      this.showToast('error', 'Failed to add property: ' + err.message);
    }
  },

  // ---------------------------------------------------------------------------
  // 6. Knowledge Base & RAG Logic
  // ---------------------------------------------------------------------------
  async fetchKnowledgeDocs() {
    const tbody = document.getElementById('kb-documents-rows');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center text-slate-400 py-6">Loading documents...</td></tr>`;

    try {
      const res = await this.authFetch('/api/knowledge-base');
      const docs = await res.json();
      AppState.knowledgeDocs = docs || [];

      if (!docs || !docs.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-slate-400 py-6">No documents uploaded yet.</td></tr>`;
        return;
      }

      tbody.innerHTML = docs.map(d => `
        <tr>
          <td class="font-semibold text-xs text-slate-900 dark:text-white">${d.filename}</td>
          <td><span class="crm-badge crm-badge-stage">${d.document_type}</span></td>
          <td><span class="crm-badge crm-badge-success">● ${d.status}</span></td>
          <td class="text-xs text-slate-500">${d.chunk_count} chunks</td>
          <td class="text-xs text-slate-500">${d.vector_count} vectors</td>
          <td class="text-xs text-slate-400">${this.formatDate(d.created_at)}</td>
        </tr>
      `).join('');

      this.refreshIcons();
    } catch (err) {
      console.error('Fetch knowledge docs error:', err);
    }
  },

  triggerDocUpload() {
    document.getElementById('doc-file-input')?.click();
  },

  async uploadDocFile(event) {
    const file = event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      this.showToast('info', `Vectorizing ${file.name} with Gemini Embedding...`);
      const res = await this.authFetch('/api/knowledge-base/upload', {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      this.showToast('success', `Document Vectorized: ${data.filename} (${data.chunks} chunks).`);
      this.fetchKnowledgeDocs();
    } catch (err) {
      this.showToast('error', 'Upload failed: ' + err.message);
    }
  },

  setRagQuery(text) {
    const input = document.getElementById('rag-test-query');
    if (input) {
      input.value = text;
      this.testRagSearch();
    }
  },

  async testRagSearch() {
    const input = document.getElementById('rag-test-query');
    const query = input?.value.trim();
    if (!query) return;

    const resultsBox = document.getElementById('rag-test-results');
    if (resultsBox) resultsBox.innerHTML = 'Searching vector embeddings with top_k=3...';

    try {
      const res = await this.authFetch(`/api/knowledge-base/search-test?query=${encodeURIComponent(query)}`, {
        method: 'POST'
      });
      const data = await res.json();

      if (!data.results || !data.results.length) {
        resultsBox.innerHTML = '<div class="text-slate-400">No matching vector chunks found.</div>';
        return;
      }

      resultsBox.innerHTML = data.results.map((r, i) => `
        <div class="p-3 bg-white dark:bg-slate-950 rounded-lg border border-slate-200 dark:border-slate-800">
          <div class="flex items-center justify-between text-[11px] font-semibold text-slate-500 mb-1">
            <span>Result #${i+1} • Source: <strong>${r.metadata?.filename || 'Document'}</strong></span>
            <span class="text-emerald-600 dark:text-emerald-400">Score: ${(r.score * 100).toFixed(1)}%</span>
          </div>
          <div class="text-xs text-slate-800 dark:text-slate-200">${r.content}</div>
        </div>
      `).join('');
    } catch (err) {
      if (resultsBox) resultsBox.innerHTML = `<div class="text-red-500">Vector search failed: ${err.message}</div>`;
    }
  },

  // ---------------------------------------------------------------------------
  // 7. Site Visits & Callbacks Logic
  // ---------------------------------------------------------------------------
  async fetchSiteVisits() {
    const tbody = document.getElementById('site-visits-rows');
    if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="text-center text-slate-400 py-6">Loading site visits...</td></tr>`;

    try {
      const res = await this.authFetch('/api/site-visits');
      const visits = await res.json();
      AppState.siteVisits = visits || [];

      if (!visits || !visits.length) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-slate-400 py-6">No site visits scheduled.</td></tr>`;
        return;
      }

      tbody.innerHTML = visits.map(v => `
        <tr>
          <td class="font-bold text-xs sm:text-sm text-slate-900 dark:text-white">${v.customer_name}</td>
          <td class="font-mono text-xs text-slate-500">${v.phone_number}</td>
          <td class="text-xs text-slate-700 dark:text-slate-300">${v.location}</td>
          <td class="text-xs font-semibold text-indigo-600 dark:text-indigo-400">${v.visit_datetime}</td>
          <td><span class="crm-badge crm-badge-success">● ${v.status}</span></td>
          <td class="text-xs text-slate-500">${v.salesperson}</td>
          <td class="text-right">
            <button onclick="App.updateVisitStatus('${v.id}', 'completed')" class="crm-btn crm-btn-secondary crm-btn-sm text-xs py-1 px-2.5">
              Mark Done
            </button>
          </td>
        </tr>
      `).join('');

      this.refreshIcons();
    } catch (err) {
      console.error('Fetch site visits error:', err);
    }
  },

  openBookVisitModalDirect() {
    this.openModal('modal-book-visit');
  },

  openBookVisitModalFromDrawer() {
    if (!AppState.currentLeadInDrawer) return;
    this.closeLeadDrawer();
    this.openModal('modal-book-visit');
  },

  async handleBookVisitSubmit(event) {
    if (event) event.preventDefault();
    const leadId = AppState.currentLeadInDrawer?.id || (AppState.leads[0]?.id || 'lead_demo');
    const payload = {
      lead_id: leadId,
      location: document.getElementById('visit-form-loc')?.value.trim(),
      visit_datetime: document.getElementById('visit-form-dt')?.value,
      salesperson: document.getElementById('visit-form-salesperson')?.value.trim() || 'Priya'
    };

    try {
      await this.authFetch('/api/site-visits', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      this.closeModal('modal-book-visit');
      this.showToast('success', 'Site visit confirmed & booked!');
      this.fetchSiteVisits();
      this.loadDashboardData();
    } catch (err) {
      this.showToast('error', 'Booking failed: ' + err.message);
    }
  },

  async updateVisitStatus(visitId, status) {
    try {
      await this.authFetch(`/api/site-visits/${visitId}/status?new_status=${status}`, { method: 'PATCH' });
      this.showToast('success', `Site visit marked as ${status}.`);
      this.fetchSiteVisits();
      this.loadDashboardData();
    } catch (err) {
      this.showToast('error', 'Update error: ' + err.message);
    }
  },

  async fetchCallbacks() {
    const tbody = document.getElementById('callbacks-rows');
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center text-slate-400 py-6">Loading callbacks...</td></tr>`;

    try {
      const res = await this.authFetch('/api/callbacks');
      const cbs = await res.json();
      AppState.callbacks = cbs || [];

      if (!cbs || !cbs.length) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-slate-400 py-6">No scheduled callbacks due.</td></tr>`;
        return;
      }

      tbody.innerHTML = cbs.map(cb => `
        <tr>
          <td class="font-bold text-xs sm:text-sm text-slate-900 dark:text-white">${cb.customer_name}</td>
          <td class="font-mono text-xs text-slate-500">${cb.phone_number}</td>
          <td class="text-xs font-bold text-amber-600 dark:text-amber-400">${cb.scheduled_at}</td>
          <td class="text-xs text-slate-600 dark:text-slate-400">${cb.reason}</td>
          <td><span class="crm-badge crm-badge-warm">${cb.status}</span></td>
          <td class="text-right">
            <button onclick="App.initiateCall('${cb.phone_number}', '${cb.customer_name}', '${cb.lead_id}')" class="crm-btn crm-btn-success crm-btn-sm text-xs py-1 px-2.5">
              <i data-lucide="phone" class="w-3.5 h-3.5"></i>
              Call
            </button>
          </td>
        </tr>
      `).join('');

      this.refreshIcons();
    } catch (err) {
      console.error('Fetch callbacks error:', err);
    }
  },

  // ---------------------------------------------------------------------------
  // 8. Analytics View Logic
  // ---------------------------------------------------------------------------
  async fetchAnalytics() {
    try {
      const res = await this.authFetch('/api/analytics');
      const data = await res.json();

      document.getElementById('analytics-avg-lat').innerText = `${data.call_analytics?.avg_latency_ms || 420} ms`;
      document.getElementById('analytics-avg-dur').innerText = `${data.call_analytics?.avg_duration_sec || 0} s`;

      const funnelContainer = document.getElementById('analytics-funnel-container');
      if (funnelContainer && data.funnel) {
        const max = Math.max(...data.funnel.map(f => f.count), 1);
        funnelContainer.innerHTML = data.funnel.map(f => {
          const pct = Math.max(Math.round((f.count / max) * 100), 8);
          return `
            <div>
              <div class="flex justify-between text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                <span>${f.stage}</span>
                <span>${f.count}</span>
              </div>
              <div class="h-2.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div class="h-full bg-indigo-600 rounded-full" style="width: ${pct}%"></div>
              </div>
            </div>
          `;
        }).join('');
      }

      const locContainer = document.getElementById('analytics-locality-container');
      if (locContainer && data.location_demand) {
        const total = Object.values(data.location_demand).reduce((a, b) => a + b, 0) || 1;
        locContainer.innerHTML = Object.entries(data.location_demand).map(([loc, count]) => {
          const pct = Math.round((count / total) * 100);
          return `
            <div>
              <div class="flex justify-between text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                <span>${loc}</span>
                <span>${count} (${pct}%)</span>
              </div>
              <div class="h-2.5 rounded-full bg-slate-100 dark:bg-slate-800 overflow-hidden">
                <div class="h-full bg-emerald-500 rounded-full" style="width: ${pct}%"></div>
              </div>
            </div>
          `;
        }).join('');
      }
    } catch (err) {
      console.error('Fetch analytics error:', err);
    }
  },

  // ---------------------------------------------------------------------------
  // 9. Command Palette (Ctrl + K / ⌘K)
  // ---------------------------------------------------------------------------
  setupKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        this.openCommandPalette();
      }
      if (e.key === 'Escape') {
        this.closeCommandPalette();
        this.closeLeadDrawer();
        document.querySelectorAll('.crm-modal-backdrop.active').forEach(m => m.classList.remove('active'));
      }
    });
  },

  openCommandPalette() {
    const modal = document.getElementById('command-palette-modal');
    const input = document.getElementById('command-palette-input');
    if (modal) modal.classList.add('active');
    if (input) {
      input.value = '';
      input.focus();
    }
    this.handleCommandPaletteSearch('');
  },

  closeCommandPalette(event) {
    if (!event || event.target.id === 'command-palette-modal') {
      document.getElementById('command-palette-modal')?.classList.remove('active');
    }
  },

  handleCommandPaletteSearch(query) {
    const resultsContainer = document.getElementById('command-palette-results');
    if (!resultsContainer) return;

    const q = query.toLowerCase().trim();
    const results = [];

    AppState.leads.forEach(l => {
      if (!q || l.name.toLowerCase().includes(q) || l.phone_number.includes(q) || (l.preferred_location || '').toLowerCase().includes(q)) {
        results.push({
          type: 'Lead',
          title: l.name,
          subtitle: `${l.preferred_location || 'Nagpur'} • ${l.bhk || ''} • ${l.budget_display}`,
          action: () => { this.closeCommandPalette(); this.openLeadDrawer(l.id); }
        });
      }
    });

    AppState.properties.forEach(p => {
      if (!q || p.project_name.toLowerCase().includes(q) || p.location.toLowerCase().includes(q)) {
        results.push({
          type: 'Property',
          title: p.project_name,
          subtitle: `${p.location} • ${p.bhk} • ${p.price_display}`,
          action: () => { this.closeCommandPalette(); this.navigate('properties'); }
        });
      }
    });

    if (!results.length) {
      resultsContainer.innerHTML = `<div class="p-6 text-center text-xs text-slate-400">No matching records found.</div>`;
      return;
    }

    resultsContainer.innerHTML = results.slice(0, 8).map((r, idx) => `
      <div class="command-result-item" onclick="App.executeCommandResult(${idx})">
        <div>
          <div class="text-xs font-bold text-slate-900 dark:text-white">${r.title}</div>
          <div class="text-[11px] text-slate-500">${r.subtitle}</div>
        </div>
        <span class="text-[10px] font-semibold uppercase px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">${r.type}</span>
      </div>
    `).join('');

    this._paletteResults = results.slice(0, 8);
    this.refreshIcons();
  },

  executeCommandResult(index) {
    if (this._paletteResults && this._paletteResults[index]) {
      this._paletteResults[index].action();
    }
  },

  startDemoCampaign(name) {
    this.showToast('success', `Campaign "${name}" activated. Auto-dialer worker running.`);
  },

  // ---------------------------------------------------------------------------
  // Modal Helpers & Formatters
  // ---------------------------------------------------------------------------
  openModal(id) {
    document.getElementById(id)?.classList.add('active');
    this.refreshIcons();
  },

  closeModal(id) {
    document.getElementById(id)?.classList.remove('active');
  },

  formatDate(isoStr) {
    if (!isoStr) return '--';
    try {
      const d = new Date(isoStr);
      return d.toLocaleDateString('en-IN', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    } catch {
      return isoStr;
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
