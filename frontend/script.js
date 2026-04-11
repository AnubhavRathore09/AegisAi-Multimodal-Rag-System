'use strict';

const API = 'http://127.0.0.1:8000';
const ADMIN_TOKEN = 'anubhav_admin_secure';

const MAX_FILE_SIZE_MB = 20;
const MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024;

const IMAGE_TYPES = ['image/png', 'image/jpeg', 'image/jpg', 'image/webp'];
const DOC_TYPES   = ['application/pdf', 'text/plain'];

const state = {
  user:           null,
  token:          null,
  isGuest:        false,
  isAdmin:        false,
  chatId:         null,
  loading:        false,
  streaming:      false,
  streamMode:     true,
  recording:      false,
  pendingFiles:   [],
  currentStream:  null,
  lastQuery:      '',
  lastImages:     [],
  shareText:      '',
  mediaRecorder:  null,
  audioChunks:    [],
  analyticsTimer: null,
  collapsed:      false,
};

const $ = id => document.getElementById(id);

function getStoredToken() {
  return localStorage.getItem('rag-token') || null;
}

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    if (!file) { reject(new Error('No file provided')); return; }
    const reader = new FileReader();
    reader.onload  = () => {
      const result = reader.result;
      const base64 = result.includes(',') ? result.split(',')[1] : result;
      resolve(base64);
    };
    reader.onerror = () => reject(new Error('File read failed'));
    reader.readAsDataURL(file);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initParticles();
  initMarked();
  loadTheme();

  const savedUser = localStorage.getItem('rag-user');
  const isGuest   = localStorage.getItem('isGuest') === 'true';
  const isAdmin   = localStorage.getItem('isAdmin') === 'true';

  if (savedUser) {
    try {
      state.user    = JSON.parse(savedUser);
      state.token   = getStoredToken();
      state.isAdmin = isAdmin;
      showApp();
    } catch {
      localStorage.removeItem('rag-user');
    }
  } else if (isGuest) {
    state.isGuest = true;
    state.user    = { name: 'Guest', email: 'guest@aegis.ai' };
    showApp();
  }
});

function initParticles() {
  const canvas = $('particleCanvas');
  if (!canvas) return;
  const ctx       = canvas.getContext('2d');
  const particles = [];

  function resize() {
    canvas.width  = window.innerWidth;
    canvas.height = window.innerHeight;
  }
  resize();
  window.addEventListener('resize', resize);

  for (let i = 0; i < 55; i++) {
    particles.push({
      x:  Math.random() * window.innerWidth,
      y:  Math.random() * window.innerHeight,
      r:  Math.random() * 1.4 + 0.3,
      dx: (Math.random() - 0.5) * 0.28,
      dy: (Math.random() - 0.5) * 0.28,
      a:  Math.random(),
      da: (Math.random() - 0.5) * 0.007,
    });
  }

  function draw() {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    for (const p of particles) {
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      ctx.fillStyle = `rgba(99,179,237,${Math.max(0, Math.min(1, p.a))})`;
      ctx.fill();
      p.x += p.dx; p.y += p.dy; p.a += p.da;
      if (p.x < 0)             p.x = canvas.width;
      if (p.x > canvas.width)  p.x = 0;
      if (p.y < 0)             p.y = canvas.height;
      if (p.y > canvas.height) p.y = 0;
      if (p.a <= 0 || p.a >= 1) p.da *= -1;
    }
    requestAnimationFrame(draw);
  }
  draw();
}

function initMarked() {
  if (typeof marked === 'undefined') return;
  marked.setOptions({ breaks: true, gfm: true });
  const renderer  = new marked.Renderer();
  renderer.code   = (code, lang) => {
    const id = 'c' + Math.random().toString(36).slice(2, 7);
    return `<pre><div class="pre-header"><span class="pre-lang">${lang || 'code'}</span><button class="pre-copy" onclick="copyCodeBlock(this,'${id}')">Copy</button></div><code id="${id}">${escHtml(code)}</code></pre>`;
  };
  marked.use({ renderer });
}

function renderMd(text) {
  if (!text) return '';
  if (typeof marked === 'undefined') return escHtml(text).replace(/\n/g, '<br>');
  try {
    const raw = marked.parse(text);
    return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
  } catch {
    return escHtml(text).replace(/\n/g, '<br>');
  }
}

function getAuthHeaders(isJson = true) {
  const h   = {};
  if (isJson) h['Content-Type'] = 'application/json';
  const tok = state.isAdmin ? ADMIN_TOKEN : getStoredToken();
  if (tok && !state.isGuest) h['Authorization'] = `Bearer ${tok}`;
  return h;
}

function getUploadHeaders() {
  const h   = {};
  const tok = state.isAdmin ? ADMIN_TOKEN : getStoredToken();
  if (tok && !state.isGuest) h['Authorization'] = `Bearer ${tok}`;
  return h;
}

async function apiFetch(path, options = {}) {
  try {
    const res = await fetch(`${API}${path}`, options);
    if (res.status === 401) {
      handleAuthError();
    }
    return res;
  } catch (err) {
    if (err.name === 'TypeError' || err.message.includes('fetch')) {
      throw new Error(`Cannot connect to server at ${API}. Is the backend running?`);
    }
    throw err;
  }
}

function handleAuthError() {
  showToast('Session expired. Switching to guest mode.');
  state.isGuest = true;
  state.token   = null;
  localStorage.setItem('isGuest', 'true');
  localStorage.removeItem('rag-token');
}

function switchTab(tab) {
  $('tabLogin').classList.toggle('active', tab === 'login');
  $('tabSignup').classList.toggle('active', tab === 'signup');
  $('formLogin').style.display  = tab === 'login'  ? 'block' : 'none';
  $('formSignup').style.display = tab === 'signup' ? 'block' : 'none';
  $('loginError').textContent   = '';
  $('signupError').textContent  = '';
}

function continueAsGuest() {
  localStorage.setItem('isGuest', 'true');
  localStorage.removeItem('isAdmin');
  localStorage.removeItem('rag-token');
  state.isGuest = true;
  state.isAdmin = false;
  state.token   = null;
  state.user    = { name: 'Guest', email: 'guest@aegis.ai' };
  showApp();
}

async function doLogin() {
  const email    = $('loginEmail').value.trim();
  const password = $('loginPassword').value;
  const errEl    = $('loginError');

  if (!email || !password) { errEl.textContent = 'Please fill all fields.'; return; }

  const btnText   = $('loginBtnText');
  const spinner   = $('loginSpinner');
  const loginBtn  = $('loginBtn');
  if (btnText)  btnText.style.display  = 'none';
  if (spinner)  spinner.style.display  = 'block';
  if (loginBtn) loginBtn.disabled      = true;
  errEl.textContent = '';

  const isAdminLogin = (email === 'admin@aegis.ai'  && password === 'admin123');
  const isDemoLogin  = (email === 'demo@aegis.ai'   && password === 'demo123');

  if (isAdminLogin) {
    localStorage.setItem('isAdmin', 'true');
    localStorage.setItem('rag-token', ADMIN_TOKEN);
    localStorage.removeItem('isGuest');
    state.isAdmin = true;
    state.token   = ADMIN_TOKEN;
    loginSuccess({ name: 'Admin', email });
    return;
  }

  if (isDemoLogin) {
    localStorage.removeItem('isGuest');
    localStorage.removeItem('isAdmin');
    state.isAdmin = false;
    state.token   = null;
    loginSuccess({ name: 'Demo User', email });
    return;
  }

  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email, password }),
    });
    if (res.ok) {
      const data = await res.json();
      const tok  = data.access_token || data.token || null;
      if (tok) {
        state.token = tok;
        localStorage.setItem('rag-token', tok);
      }
      localStorage.removeItem('isGuest');
      localStorage.removeItem('isAdmin');
      loginSuccess(data.user || { name: email.split('@')[0], email });
      return;
    }
  } catch {}

  const users = JSON.parse(localStorage.getItem('rag-users') || '[]');
  const user  = users.find(u => u.email === email && u.password === password);

  if (!user) {
    errEl.textContent = 'Invalid email or password.';
    if (btnText)  btnText.style.display = 'block';
    if (spinner)  spinner.style.display = 'none';
    if (loginBtn) loginBtn.disabled     = false;
    return;
  }

  localStorage.removeItem('isGuest');
  localStorage.removeItem('isAdmin');
  loginSuccess(user);
}

function doSignup() {
  const name     = $('signupName').value.trim();
  const email    = $('signupEmail').value.trim();
  const password = $('signupPassword').value;
  const errEl    = $('signupError');

  if (!name || !email || !password) { errEl.textContent = 'Fill all fields.'; return; }
  if (password.length < 6)          { errEl.textContent = 'Password min 6 chars.'; return; }
  if (!email.includes('@'))         { errEl.textContent = 'Invalid email.'; return; }

  const users = JSON.parse(localStorage.getItem('rag-users') || '[]');
  if (users.find(u => u.email === email)) { errEl.textContent = 'Email already registered.'; return; }

  const newUser = { name, email, password };
  users.push(newUser);
  localStorage.setItem('rag-users', JSON.stringify(users));
  localStorage.removeItem('isGuest');
  localStorage.removeItem('isAdmin');
  loginSuccess(newUser);
}

function loginSuccess(user) {
  state.user = user;
  localStorage.setItem('rag-user', JSON.stringify(user));
  showApp();
}

function showApp() {
  const authScreen = $('authScreen');
  const appWrapper = $('appWrapper');
  if (authScreen) authScreen.style.display = 'none';
  if (appWrapper) appWrapper.style.display = 'flex';

  const name     = state.user?.name || 'User';
  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  const ua = $('userAvatar');
  const pa = $('profileAvatarBig');
  const un = $('userName');
  const ue = $('userEmail');
  const wt = $('welcomeTitle');
  if (ua) ua.textContent = initials;
  if (pa) pa.textContent = initials;
  if (un) un.textContent = name;
  if (ue) ue.textContent = state.user?.email || '';
  if (wt) wt.textContent = `Welcome${state.isGuest ? '' : ' back'}, ${name.split(' ')[0]}!`;

  const guestBadge = $('guestBadge');
  const adminBadge = $('adminBadge');
  if (guestBadge) guestBadge.style.display = state.isGuest ? 'flex' : 'none';
  if (adminBadge) adminBadge.style.display = state.isAdmin ? 'flex' : 'none';

  if (localStorage.getItem('rag-collapsed') === 'true') setSidebarCollapsed(true);
  updateStreamBadge();
  loadHistory();
  loadIndexedSources();
  loadTheme();
}

function doLogout() {
  localStorage.removeItem('rag-user');
  localStorage.removeItem('rag-token');
  localStorage.removeItem('isGuest');
  localStorage.removeItem('isAdmin');
  state.user    = null;
  state.token   = null;
  state.isGuest = false;
  state.isAdmin = false;
  state.chatId  = null;
  if (state.analyticsTimer) clearInterval(state.analyticsTimer);
  const authScreen = $('authScreen');
  const appWrapper = $('appWrapper');
  if (authScreen) authScreen.style.display = 'flex';
  if (appWrapper) appWrapper.style.display = 'none';
  closeProfileMenu();
}

const sidebarToggleBtn = $('sidebarToggle');
if (sidebarToggleBtn) {
  sidebarToggleBtn.addEventListener('click', () => {
    setSidebarCollapsed(!state.collapsed);
    localStorage.setItem('rag-collapsed', state.collapsed);
  });
}

function setSidebarCollapsed(val) {
  state.collapsed = val;
  const sb = document.getElementById('sidebar');
  if (sb) sb.classList.toggle('collapsed', val);
}

function openMobileSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('mobOverlay');
  if (sb) sb.classList.add('mob-open');
  if (ov) ov.classList.add('show');
}

function closeMobileSidebar() {
  const sb = document.getElementById('sidebar');
  const ov = document.getElementById('mobOverlay');
  if (sb) sb.classList.remove('mob-open');
  if (ov) ov.classList.remove('show');
}

document.addEventListener('click', e => {
  const menu    = $('profileMenu');
  const profile = $('userProfile');
  if (menu && profile && !profile.contains(e.target) && !menu.contains(e.target)) {
    menu.style.display = 'none';
  }
});

function loadTheme() {
  applyTheme(localStorage.getItem('rag-theme') || 'dark');
}

function toggleTheme() {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem('rag-theme', theme);
  document.querySelectorAll('.icon-moon').forEach(e => e.style.display = theme === 'dark' ? '' : 'none');
  document.querySelectorAll('.icon-sun').forEach(e  => e.style.display = theme === 'dark' ? 'none' : '');
  const lbl = $('themeLabel');
  if (lbl) lbl.textContent = theme === 'dark' ? 'Dark mode' : 'Light mode';
}

function toggleProfileMenu() {
  const m = $('profileMenu');
  if (m) m.style.display = m.style.display === 'none' ? 'block' : 'none';
}

function closeProfileMenu() {
  const m = $('profileMenu');
  if (m) m.style.display = 'none';
}

function openProfileModal() {
  closeProfileMenu();
  const pn = $('profileName');
  const pe = $('profileEmail');
  const pp = $('profilePassword');
  if (pn) pn.value = state.user?.name  || '';
  if (pe) pe.value = state.user?.email || '';
  if (pp) pp.value = '';
  const mo = $('profileModalOverlay');
  if (mo) mo.style.display = 'flex';
}

function closeProfileModal() {
  const mo = $('profileModalOverlay');
  if (mo) mo.style.display = 'none';
}

function saveProfile() {
  const name = $('profileName')?.value.trim();
  const pwd  = $('profilePassword')?.value;
  if (!name)                 { showToast('Name cannot be empty'); return; }
  if (pwd && pwd.length < 6) { showToast('Password min 6 chars'); return; }

  const updated = { ...state.user, name };
  if (pwd) updated.password = pwd;

  const users = JSON.parse(localStorage.getItem('rag-users') || '[]');
  const idx   = users.findIndex(u => u.email === state.user?.email);
  if (idx >= 0) users[idx] = updated;
  localStorage.setItem('rag-users', JSON.stringify(users));

  state.user = updated;
  localStorage.setItem('rag-user', JSON.stringify(updated));

  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  const ua = $('userAvatar');
  const pa = $('profileAvatarBig');
  const un = $('userName');
  if (ua) ua.textContent = initials;
  if (pa) pa.textContent = initials;
  if (un) un.textContent = name;
  closeProfileModal();
  showToast('Profile updated ✓');
}

const newChatBtn = $('newChatBtn');
if (newChatBtn) newChatBtn.addEventListener('click', startNewChat);

function startNewChat() {
  state.chatId       = null;
  state.pendingFiles = [];
  state.lastImages   = [];
  const mi = document.getElementById('messagesInner');
  const al = document.getElementById('attachmentsList');
  const ab = document.getElementById('attachmentsBar');
  const vt = document.getElementById('voiceTranscript');
  const dc = $('deleteChatBtn');
  if (mi) mi.innerHTML         = '';
  if (al) al.innerHTML         = '';
  if (ab) ab.style.display     = 'none';
  if (vt) vt.style.display     = 'none';
  if (dc) dc.style.display     = 'none';
  renderWelcome();
  document.querySelectorAll('.history-item').forEach(i => i.classList.remove('active'));
  closeMobileSidebar();
  const ui = document.getElementById('userInput');
  if (ui) ui.focus();
}

function renderWelcome() {
  const name = state.user?.name?.split(' ')[0] || 'there';
  const el   = document.createElement('div');
  el.className = 'welcome';
  el.id        = 'welcomeState';
  const ts     = Date.now();
  el.innerHTML = `
    <div class="welcome-icon">
      <div class="welcome-logo-wrap">
        <div class="logo-glow-ring welcome-glow"></div>
        <div class="welcome-spinner">
          <img class="welcome-logo-img" src="logo.png" alt="Aegis AI"
            onerror="this.style.display='none';this.nextElementSibling.style.display='block'"/>
          <svg class="welcome-svg-fallback" style="display:none" viewBox="0 0 100 100">
            <defs>
              <radialGradient id="wgd_${ts}" cx="40%" cy="35%" r="65%">
                <stop offset="0%"   stop-color="#a5f3fc"/>
                <stop offset="40%"  stop-color="#38bdf8"/>
                <stop offset="75%"  stop-color="#4f8ef7"/>
                <stop offset="100%" stop-color="#7c3aed"/>
              </radialGradient>
              <filter id="wgf_${ts}">
                <feGaussianBlur in="SourceGraphic" stdDeviation="3" result="b"/>
                <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
              </filter>
            </defs>
            <g filter="url(#wgf_${ts})" fill="url(#wgd_${ts})">
              <path d="M50 50 Q55 20 65 15 Q80 10 75 30 Q70 45 50 50Z" opacity="0.95"/>
              <path d="M50 50 Q78 48 85 58 Q90 72 70 72 Q55 70 50 50Z" opacity="0.90"/>
              <path d="M50 50 Q55 78 45 85 Q30 92 28 72 Q28 57 50 50Z" opacity="0.85"/>
              <path d="M50 50 Q22 52 15 42 Q10 28 30 28 Q45 30 50 50Z" opacity="0.80"/>
            </g>
            <circle cx="50" cy="50" r="14" fill="#060810" opacity="0.9"/>
          </svg>
        </div>
        <div class="logo-particles">
          <span class="lp lp1"></span><span class="lp lp2"></span>
          <span class="lp lp3"></span><span class="lp lp4"></span>
          <span class="lp lp5"></span><span class="lp lp6"></span>
        </div>
      </div>
    </div>
    <h1 class="welcome-title">Welcome${state.isGuest ? '' : ' back'}, ${escHtml(name)}!</h1>
    <p class="welcome-sub">Powered by Aegis AI — intelligent retrieval-augmented generation.<br>Upload documents, ask questions, get cited answers.</p>
    <div class="chips">
      <button class="chip" onclick="useChip(this)">📄 Summarize my uploaded document</button>
      <button class="chip" onclick="useChip(this)">❓ What are the key points in this file?</button>
      <button class="chip" onclick="useChip(this)">🔍 Find information about a specific topic</button>
      <button class="chip" onclick="useChip(this)">📝 Explain this in simple words</button>
      <button class="chip" onclick="useChip(this)">💡 What does this document say about pricing?</button>
      <button class="chip" onclick="useChip(this)">🗂️ Compare the main ideas in my files</button>
    </div>
  `;
  const mi = document.getElementById('messagesInner');
  if (mi) mi.appendChild(el);
}

function useChip(btn) {
  const text = btn.textContent.trim().replace(/^[\S]+\s/, '');
  const ui   = document.getElementById('userInput');
  if (ui) { ui.value = text; growInput(ui); }
  sendMessage();
}

async function loadHistory() {
  const hl    = $('historyLoading');
  const he    = $('historyEmpty');
  const hlist = $('historyList');
  if (hl)    hl.style.display    = 'flex';
  if (he)    he.style.display    = 'none';
  if (hlist) hlist.innerHTML     = '';

  if (state.isGuest) {
    if (hl) hl.style.display = 'none';
    if (he) he.style.display = 'flex';
    return;
  }

  try {
    const res = await apiFetch('/api/history', { headers: getAuthHeaders() });
    if (res && res.ok) {
      const data = await res.json();
      if (hl) hl.style.display = 'none';
      renderHistoryList(Array.isArray(data) ? data : (data.sessions || []));
      return;
    }
  } catch {}

  if (hl) hl.style.display = 'none';
  const key = `rag-sessions-${state.user?.email}`;
  renderHistoryList(JSON.parse(localStorage.getItem(key) || '[]'));
}

function renderHistoryList(sessions) {
  const hlist = $('historyList');
  const he    = $('historyEmpty');
  if (!hlist) return;
  hlist.innerHTML = '';
  if (!sessions?.length) {
    if (he) he.style.display = 'flex';
    return;
  }
  if (he) he.style.display = 'none';

  const groups = groupByDate(sessions);
  for (const [label, items] of Object.entries(groups)) {
    if (!items.length) continue;
    const lbl        = document.createElement('div');
    lbl.className    = 'history-group-label';
    lbl.textContent  = label;
    hlist.appendChild(lbl);
    items.forEach(s => {
      const div        = document.createElement('div');
      div.className    = 'history-item';
      div.dataset.id   = s.id;
      if (state.chatId === s.id) div.classList.add('active');
      div.innerHTML    = `
        <svg class="chat-icon" width="13" height="13" viewBox="0 0 24 24" fill="none">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="currentColor" stroke-width="2"/>
        </svg>
        <span class="history-item-text">${escHtml(s.title || 'Chat')}</span>
        <button class="history-item-del" onclick="deleteSession(event,'${s.id}')" title="Delete">
          <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
            <path d="M18 6L6 18M6 6l12 12" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/>
          </svg>
        </button>
      `;
      div.addEventListener('click', () => loadSession(s));
      hlist.appendChild(div);
    });
  }
}

function groupByDate(sessions) {
  const now   = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yday  = new Date(today); yday.setDate(yday.getDate() - 1);
  const week  = new Date(today); week.setDate(week.getDate() - 7);
  const g     = { Today: [], Yesterday: [], 'Last 7 days': [], Older: [] };
  sessions.forEach(s => {
    const d   = new Date(s.updated_at || s.created_at || Date.now());
    const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    if      (day >= today) g.Today.push(s);
    else if (day >= yday)  g.Yesterday.push(s);
    else if (day >= week)  g['Last 7 days'].push(s);
    else                   g.Older.push(s);
  });
  return g;
}

async function loadSession(session) {
  state.chatId = session.id;
  closeMobileSidebar();
  document.querySelectorAll('.history-item').forEach(i => i.classList.toggle('active', i.dataset.id === session.id));
  const dc = $('deleteChatBtn');
  if (dc) dc.style.display = 'flex';

  const mi = document.getElementById('messagesInner');
  if (mi) {
    mi.innerHTML = `<div style="padding:20px;display:flex;flex-direction:column;gap:16px">
      ${['52px','80px','52px'].map(h =>
        `<div style="height:${h};border-radius:12px;background:linear-gradient(90deg,var(--bg3) 25%,var(--bg4) 50%,var(--bg3) 75%);background-size:200% 100%;animation:shimmer 1.4s infinite"></div>`
      ).join('')}
    </div>`;
  }

  try {
    const res  = await apiFetch(`/api/history/${session.id}`, { headers: getAuthHeaders() });
    if (!res || !res.ok) throw new Error('Failed to load session');
    const data = await res.json();
    const msgs = Array.isArray(data) ? data : (data.messages || []);
    if (mi) mi.innerHTML = '';
    if (msgs.length === 0) renderWelcome();
    else msgs.forEach(m => {
      if (m.role === 'user')      appendUserMsg(m.content, m.timestamp, []);
      else if (m.role === 'assistant') appendAIMsg(m.content, {}, m.timestamp);
    });
  } catch {
    if (mi) mi.innerHTML = '';
    const raw  = localStorage.getItem(`rag-msgs-${session.id}`);
    const msgs = raw ? JSON.parse(raw) : [];
    if (msgs.length === 0) renderWelcome();
    else msgs.forEach(m => {
      if (m.role === 'user')      appendUserMsg(m.content, m.timestamp, []);
      else if (m.role === 'assistant') appendAIMsg(m.content, {}, m.timestamp);
    });
  }
  scrollDown();
}

function saveSessionLocal(id, title) {
  if (state.isGuest) return;
  const key      = `rag-sessions-${state.user?.email}`;
  const sessions = JSON.parse(localStorage.getItem(key) || '[]');
  const now      = new Date().toISOString();
  const idx      = sessions.findIndex(s => s.id === id);
  if (idx >= 0) { sessions[idx].title = title; sessions[idx].updated_at = now; }
  else sessions.unshift({ id, title, created_at: now, updated_at: now });
  localStorage.setItem(key, JSON.stringify(sessions));
  renderHistoryList(sessions);
}

function saveMsgLocal(chatId, role, content) {
  if (state.isGuest) return;
  const key  = `rag-msgs-${chatId}`;
  const msgs = JSON.parse(localStorage.getItem(key) || '[]');
  msgs.push({ role, content, timestamp: new Date().toISOString() });
  localStorage.setItem(key, JSON.stringify(msgs));
}

async function deleteCurrentChat() {
  if (!state.chatId || !confirm('Delete this conversation?')) return;
  await deleteSession(null, state.chatId);
}

async function deleteSession(e, id) {
  if (e) e.stopPropagation();
  try {
    await apiFetch(`/api/history/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
  } catch {}
  localStorage.removeItem(`rag-msgs-${id}`);
  const key      = `rag-sessions-${state.user?.email}`;
  const sessions = JSON.parse(localStorage.getItem(key) || '[]').filter(s => s.id !== id);
  localStorage.setItem(key, JSON.stringify(sessions));
  renderHistoryList(sessions);
  if (state.chatId === id) startNewChat();
  showToast('Conversation deleted');
}

async function handleFiles(input) {
  const files = Array.from(input.files || []);
  for (const file of files) {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      showToast(`File too large: ${file.name} (max ${MAX_FILE_SIZE_MB}MB)`);
      continue;
    }
    const isImage = IMAGE_TYPES.includes(file.type);
    const isDoc   = DOC_TYPES.includes(file.type) || file.name.toLowerCase().endsWith('.txt');
    if (!isImage && !isDoc) {
      showToast(`Unsupported file type: ${file.name}`);
      continue;
    }
    const entry = {
      file,
      type:       isImage ? 'image' : 'doc',
      base64:     null,
      uploaded:   false,
      previewUrl: null,
      id:         Date.now() + Math.random(),
    };
    state.pendingFiles.push(entry);
    addAttachPreview(entry);
    if (isImage) {
      try {
        entry.base64      = await fileToBase64(file);
        entry.previewUrl  = `data:${file.type};base64,${entry.base64}`;
        updateAttachPreview(entry, 'done');
      } catch (err) {
        updateAttachPreview(entry, 'err');
        showToast(`Failed to process image: ${file.name}`);
      }
    } else {
      await uploadDocToBackend(entry);
    }
  }
  input.value = '';
  const ab = document.getElementById('attachmentsBar');
  if (ab) ab.style.display = state.pendingFiles.length ? 'block' : 'none';
}

function addAttachPreview(entry) {
  const al = document.getElementById('attachmentsList');
  if (!al) return;
  const div     = document.createElement('div');
  div.className = 'attach-preview attach-uploading';
  div.id        = `ap-${entry.id}`;
  const isImg   = entry.type === 'image';
  div.innerHTML = `
    ${isImg
      ? `<img src="" alt="img"/>`
      : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" stroke-width="2"/><polyline points="14 2 14 8 20 8" stroke="currentColor" stroke-width="2"/></svg>`
    }
    <span class="attach-preview-name">${escHtml(entry.file.name.length > 20 ? entry.file.name.slice(0, 18) + '…' : entry.file.name)}</span>
    <span class="attach-preview-del" onclick="removeAttachment(${entry.id})">✕</span>
  `;
  al.appendChild(div);
}

function updateAttachPreview(entry, status) {
  const div = $(`ap-${entry.id}`);
  if (!div) return;
  div.classList.remove('attach-uploading');
  div.classList.add(status);
  if (entry.previewUrl) {
    const img = div.querySelector('img');
    if (img) img.src = entry.previewUrl;
  }
}

async function uploadDocToBackend(entry) {
  const form = new FormData();
  form.append('file', entry.file, entry.file.name);

  try {
    const res = await fetch(`${API}/api/upload`, {
      method:  'POST',
      headers: getUploadHeaders(),
      body:    form,
    });

    if (res.status === 401) { handleAuthError(); throw new Error('Unauthorized'); }
    if (!res.ok) {
      let errMsg = `Status ${res.status}`;
      try { const errData = await res.json(); errMsg = errData.detail || errData.message || errMsg; } catch {}
      throw new Error(errMsg);
    }

    const data   = await res.json();
    entry.uploaded = true;
    updateAttachPreview(entry, 'done');
    const chunks = data.chunks || data.chunk_count || 0;
    showToast(`✓ ${entry.file.name} indexed (${chunks} chunks)`);
    loadIndexedSources();
  } catch (err) {
    updateAttachPreview(entry, 'err');
    showToast(`Upload failed: ${entry.file.name} — ${err.message}`);
    console.error('Upload error:', err);
  }
}

function removeAttachment(id) {
  state.pendingFiles = state.pendingFiles.filter(f => f.id !== id);
  const el = $(`ap-${id}`);
  if (el) el.remove();
  const ab = document.getElementById('attachmentsBar');
  if (ab) ab.style.display = state.pendingFiles.length ? 'block' : 'none';
}

async function loadIndexedSources() {
  try {
    const res = await apiFetch('/api/chat/sources', { headers: getAuthHeaders() });
    if (!res || !res.ok) return;
    const data = await res.json();
    const srcs = data.sources || [];
    const ind  = $('docsIndicator');
    const dc   = $('docsCount');
    if (ind && dc) {
      ind.style.display = srcs.length > 0 ? 'flex' : 'none';
      if (srcs.length > 0) dc.textContent = `${srcs.length} doc${srcs.length > 1 ? 's' : ''} indexed`;
    }
  } catch {
    const ind = $('docsIndicator');
    if (ind) ind.style.display = 'none';
  }
}

async function toggleVoice() {
  if (state.recording) stopVoiceRecording();
  else await startVoiceRecording();
}

async function startVoiceRecording() {
  if (state.recording) return;

  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showToast('Microphone not supported. Using Web Speech API…');
    fallbackSpeechRecognition();
    return;
  }

  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
    state.audioChunks = [];

    const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : 'audio/ogg';

    state.mediaRecorder = new MediaRecorder(stream, { mimeType });

    state.mediaRecorder.ondataavailable = e => {
      if (e.data && e.data.size > 0) state.audioChunks.push(e.data);
    };

    state.mediaRecorder.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      if (state.audioChunks.length > 0) {
        const audioBlob = new Blob(state.audioChunks, { type: mimeType });
        if (audioBlob.size > 100) {
          await sendVoiceToBackend(audioBlob, mimeType);
        } else {
          showToast('Recording too short. Please speak longer.');
          resetVoiceUI();
        }
      } else {
        showToast('No audio recorded. Please try again.');
        resetVoiceUI();
      }
    };

    state.mediaRecorder.onerror = err => {
      console.error('MediaRecorder error:', err);
      showToast('Recording error. Please try again.');
      resetVoiceUI();
    };

    state.mediaRecorder.start(250);
    state.recording = true;
    const vb = $('voiceBtn');
    const vt = $('voiceTranscript');
    const tt = $('transcriptText');
    if (vb) vb.classList.add('recording');
    if (vt) vt.style.display = 'flex';
    if (tt) tt.textContent   = 'Recording… Click mic to stop.';

  } catch (err) {
    console.error('Mic access error:', err);
    const msg = err.name === 'NotAllowedError'
      ? 'Microphone permission denied. Please allow access in browser settings.'
      : err.name === 'NotFoundError'
      ? 'No microphone found. Please connect one and try again.'
      : `Microphone error: ${err.message}`;
    showToast(msg);
    fallbackSpeechRecognition();
  }
}

function stopVoiceRecording() {
  if (!state.recording) return;
  state.recording = false;
  const vb = $('voiceBtn');
  const tt = $('transcriptText');
  if (vb) vb.classList.remove('recording');
  if (tt) tt.textContent = 'Processing…';
  if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
    try { state.mediaRecorder.stop(); } catch {}
  }
}

function resetVoiceUI() {
  state.recording = false;
  const vb = $('voiceBtn');
  const vt = $('voiceTranscript');
  if (vb) vb.classList.remove('recording');
  if (vt) vt.style.display = 'none';
}

async function sendVoiceToBackend(audioBlob, mimeType) {
  const ext  = mimeType.includes('ogg') ? 'ogg' : 'webm';
  const form = new FormData();
  form.append('audio', audioBlob, `voice_${Date.now()}.${ext}`);

  try {
    const res = await fetch(`${API}/voice/voice-chat`, {
      method:  'POST',
      headers: getUploadHeaders(),
      body:    form,
    });

    if (res.status === 401) { handleAuthError(); throw new Error('Unauthorized'); }
    if (!res.ok) {
      let errMsg = `Status ${res.status}`;
      try { const d = await res.json(); errMsg = d.detail || d.message || errMsg; } catch {}
      throw new Error(errMsg);
    }

    const data = await res.json();
    resetVoiceUI();

    if (!state.chatId) {
      state.chatId = 'chat_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
    }

    const ws = $('welcomeState');
    if (ws) ws.remove();

    const userText = data.user_text || data.transcript || data.text || '';
    const aiText   = data.ai_text   || data.response   || data.answer || '';
    const audioUrl = data.audio_url || data.audio || '';

    if (userText) {
      appendUserMsg(userText, null, []);
      saveMsgLocal(state.chatId, 'user', userText);
    }

    if (aiText) {
      appendAIMsg(aiText, { sources: [], route: 'voice' });
      saveMsgLocal(state.chatId, 'assistant', aiText);
      saveSessionAfterSend(userText || 'Voice message');
    } else {
      showToast('No response from voice endpoint.');
    }

    if (audioUrl) {
      try {
        const audio = new Audio(audioUrl);
        audio.onerror = () => console.warn('Audio playback failed for URL:', audioUrl);
        await audio.play().catch(e => console.warn('Audio autoplay blocked:', e));
      } catch (err) {
        console.warn('Audio error:', err);
      }
    }

    scrollDown();

  } catch (err) {
    console.error('Voice backend error:', err);
    resetVoiceUI();
    showToast(`Voice processing failed: ${err.message}. Switching to Web Speech API…`);
    fallbackSpeechRecognition();
  }
}

function fallbackSpeechRecognition() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) {
    showToast('Voice input is not supported in this browser. Try Chrome.');
    return;
  }

  const recognition           = new SR();
  recognition.continuous      = false;
  recognition.interimResults  = true;
  recognition.lang            = 'en-US';

  state.recording = true;
  const vb = $('voiceBtn');
  const vt = $('voiceTranscript');
  const tt = $('transcriptText');
  if (vb) vb.classList.add('recording');
  if (vt) vt.style.display = 'flex';
  if (tt) tt.textContent   = 'Speak now…';

  recognition.onresult = evt => {
    const transcript = Array.from(evt.results).map(r => r[0].transcript).join('');
    if (tt) tt.textContent = transcript || 'Listening…';
    if (evt.results[evt.results.length - 1].isFinal) {
      const ui = document.getElementById('userInput');
      if (ui) { ui.value = transcript; growInput(ui); }
      stopFallbackVoice(recognition);
      sendMessage();
    }
  };

  recognition.onerror = e => {
    console.error('Speech recognition error:', e.error);
    const msgs = {
      'not-allowed':   'Microphone permission denied.',
      'no-speech':     'No speech detected. Please try again.',
      'network':       'Network error during speech recognition.',
      'aborted':       'Speech recognition aborted.',
    };
    showToast(msgs[e.error] || `Speech error: ${e.error}`);
    stopFallbackVoice(recognition);
  };
  recognition.onend = () => stopFallbackVoice(recognition);
  recognition.start();
}

function stopFallbackVoice(recognition) {
  state.recording = false;
  const vb = $('voiceBtn');
  const vt = $('voiceTranscript');
  if (vb) vb.classList.remove('recording');
  if (vt) vt.style.display = 'none';
  try { recognition.stop(); } catch {}
}

function cancelVoice() {
  state.recording = false;
  const vb = $('voiceBtn');
  const vt = $('voiceTranscript');
  if (vb) vb.classList.remove('recording');
  if (vt) vt.style.display = 'none';
  if (state.mediaRecorder && state.mediaRecorder.state !== 'inactive') {
    try { state.mediaRecorder.stream?.getTracks().forEach(t => t.stop()); } catch {}
    state.mediaRecorder = null;
  }
  state.audioChunks = [];
}

function speakText(text) {
  if (!window.speechSynthesis || !text) return;
  window.speechSynthesis.cancel();
  const utt   = new SpeechSynthesisUtterance(text.slice(0, 600));
  utt.rate    = 1;
  utt.pitch   = 1;
  utt.onerror = err => console.warn('TTS error:', err);
  window.speechSynthesis.speak(utt);
}

function speak(text) {
  speakText(text);
}

function toggleStreamMode() {
  state.streamMode = !state.streamMode;
  const st = $('streamToggle');
  if (st) st.classList.toggle('active', state.streamMode);
  updateStreamBadge();
  showToast(state.streamMode ? '⚡ Streaming ON' : '📦 Batch mode ON');
}

function updateStreamBadge() {
  const badge = $('streamBadge');
  const st    = $('streamToggle');
  if (badge) badge.classList.toggle('show', state.streamMode);
  if (st)    st.classList.toggle('active', state.streamMode);
}

function growInput(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 175) + 'px';
}

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
}

async function sendMessage() {
  const inp = document.getElementById('userInput');
  if (!inp) return;
  const text     = inp.value.trim();
  const hasFiles = state.pendingFiles.length > 0;

  if (!text && !hasFiles) return;

  if (state.streaming && state.currentStream) {
    state.currentStream.abort();
    return;
  }
  if (state.loading) return;

  if (!state.chatId) {
    state.chatId = 'chat_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  }

  const ws = $('welcomeState');
  if (ws) ws.remove();

  const query  = text || 'Please analyze the attached file(s).';
  const images = state.pendingFiles.filter(f => f.type === 'image' && f.base64);
  state.lastQuery  = query;
  state.lastImages = images;

  inp.value = '';
  growInput(inp);

  appendUserMsg(query, null, images);
  saveMsgLocal(state.chatId, 'user', query);

  state.pendingFiles = [];
  const al = document.getElementById('attachmentsList');
  const ab = document.getElementById('attachmentsBar');
  if (al) al.innerHTML     = '';
  if (ab) ab.style.display = 'none';
  scrollDown();

  if (state.streamMode) await sendStreaming(query, images);
  else                  await sendBatch(query, images);
}

function buildImagePayload(images) {
  return images.map(i => ({
    data:      i.base64,
    mime_type: i.file.type,
    filename:  i.file.name,
  }));
}

async function sendStreaming(query, images) {
  setLoading(true, true);
  const controller    = new AbortController();
  state.currentStream = controller;
  const aiDiv         = appendAIMsgStreaming();

  try {
    const body = {
      query,
      chat_id: state.chatId,
      user:    state.user?.name || 'User',
    };
    if (images.length > 0) body.images = buildImagePayload(images);

    const res = await fetch(`${API}/api/stream`, {
      method:  'POST',
      headers: getAuthHeaders(),
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });

    if (res.status === 401) { handleAuthError(); throw new Error('Unauthorized'); }
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let fullText  = '';
    let sources   = [];
    let buffer    = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.startsWith('data:')) continue;
        const raw = trimmed.slice(5).trim();
        if (!raw || raw === '[DONE]') continue;

        try {
          const data = JSON.parse(raw);
          const token = data.token || data.text || data.content || '';
          if (token) {
            fullText += token;
            updateStreamBubble(aiDiv, fullText);
          }
          if (data.response || data.answer) {
            fullText = data.response || data.answer;
            sources  = data.sources || [];
            updateStreamBubble(aiDiv, fullText);
          }
          if (data.sources) sources = data.sources;
          if (data.done)    sources = data.sources || sources;
          if (data.error)   throw new Error(data.error);
        } catch (jsonErr) {
if (raw) {
    try {
        const parsed = JSON.parse(raw);

         if (parsed && typeof parsed === "object"){
            if (parsed.response) {
                fullText += parsed.response;
            } else if (parsed.token) {
                fullText += parsed.token;
            } else {
                fullText += "";
            }
        } else {
            fullText += parsed;
        }

    } catch {
        fullText += raw;
    }

    updateStreamBubble(aiDiv, fullText);
}
        }
      }
    }

    if (!fullText.trim()) {
      aiDiv.remove();
      await sendBatch(query, images);
      return;
    }

    finalizeStreamBubble(aiDiv, fullText, { sources, route: 'stream' });
    saveMsgLocal(state.chatId, 'assistant', fullText);
    saveSessionAfterSend(query);

  } catch (err) {
    if (err.name === 'AbortError') {
      const cursor = aiDiv.querySelector('.streaming-cursor');
      if (cursor) cursor.remove();
      const bubble = aiDiv.querySelector('.bubble-ai');
      if (bubble && bubble.innerText.trim()) {
        const body = aiDiv.querySelector('.ai-body');
        if (body) {
          body.appendChild(buildMetaRow(aiDiv.id, bubble.innerText, { sources: [], route: 'stream' }));
        }
        saveMsgLocal(state.chatId, 'assistant', bubble.innerText);
        saveSessionAfterSend(query);
      }
    } else {
      console.error('Stream error:', err);
      const bubble = aiDiv.querySelector('.bubble-ai');
      if (bubble && !bubble.innerText.trim()) {
        aiDiv.remove();
        await sendBatch(query, images);
        return;
      }
      const cursor = aiDiv.querySelector('.streaming-cursor');
      if (cursor) cursor.remove();
      showToast(`Stream error: ${err.message}`);
    }
  } finally {
    setLoading(false, false);
    state.currentStream = null;
    scrollDown();
  }
}

async function sendBatch(query, images) {
  setLoading(true, false);
  const typer = appendTyping();

  try {
    const body = {
      query:   query,
      chat_id: state.chatId,
      user:    state.user?.name || 'User',
    };
    if (images.length > 0) body.images = buildImagePayload(images);

    const res = await apiFetch('/api/chat', {
      method:  'POST',
      headers: getAuthHeaders(),
      body:    JSON.stringify(body),
    });

    if (!res || !res.ok) {
      let errMsg = `Server error ${res?.status || ''}`;
      try { const d = await res?.json(); errMsg = d.detail || d.message || errMsg; } catch {}
      throw new Error(errMsg);
    }

    const data   = await res.json();
    typer.remove();

    const answer  = data.response || data.answer || data.message || data.content || '';
    const sources = data.sources  || data.citations || [];
    const route   = data.route    || null;

    if (!answer) throw new Error('Empty response from server');

    appendAIMsg(answer, { sources, route });
    saveMsgLocal(state.chatId, 'assistant', answer);
    saveSessionAfterSend(query);

  } catch (err) {
    if (typer && typer.remove) typer.remove();
    console.error('Batch error:', err);
    appendAIMsg(`⚠️ **Error:** ${escHtml(err.message)}\n\nPlease check if the backend is running at \`${API}\``, { sources: [], route: 'error' });
  } finally {
    setLoading(false, false);
    scrollDown();
  }
}

function saveSessionAfterSend(query) {
  const title = query.length > 45 ? query.slice(0, 42) + '…' : query;
  saveSessionLocal(state.chatId, title);
  const dc = $('deleteChatBtn');
  if (dc) dc.style.display = 'flex';
  document.querySelectorAll('.history-item').forEach(i => {
    i.classList.toggle('active', i.dataset.id === state.chatId);
  });
}

function appendUserMsg(text, timestamp, images) {
  const mi = document.getElementById('messagesInner');
  if (!mi) return;
  const div     = document.createElement('div');
  div.className = 'msg-group msg-user';
  const imgs    = (images || [])
    .filter(img => img.previewUrl)
    .map(img => `<img class="msg-img" src="${img.previewUrl}" alt="attachment"/>`)
    .join('');
  div.innerHTML = `
    <div class="bubble-user">
      ${imgs}
      ${text ? `<div>${escHtml(text)}</div>` : ''}
    </div>
    <div class="msg-meta">
      <span class="msg-time">${fmtTime(timestamp)}</span>
    </div>
  `;
  mi.appendChild(div);
  scrollDown();
}

function appendAIMsgStreaming() {
  const id      = 'msg-' + Date.now();
  const div     = document.createElement('div');
  div.className = 'msg-group msg-ai';
  div.id        = id;
  div.innerHTML = `
    <div class="ai-ava">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div class="ai-body">
      <div class="bubble-ai" id="bubble-${id}"><span class="streaming-cursor"></span></div>
    </div>
  `;
  const mi = document.getElementById('messagesInner');
  if (mi) mi.appendChild(div);
  scrollDown();
  return div;
}

function updateStreamBubble(div, text) {
  const bubble = div.querySelector('.bubble-ai');
  if (!bubble) return;
  bubble.innerHTML = renderMd(text) + '<span class="streaming-cursor"></span>';
  scrollDown();
}

function finalizeStreamBubble(div, text, meta) {
  const bubble = div.querySelector('.bubble-ai');
  if (bubble) bubble.innerHTML = renderMd(text);
  const body = div.querySelector('.ai-body');
  if (body) {
    body.appendChild(buildMetaRow(div.id, text, meta));
    if (meta.sources?.length) body.appendChild(buildSources(meta.sources));
    if (meta.route)           body.appendChild(buildRouteBadge(meta.route));
  }
}

function appendAIMsg(text, meta = {}, timestamp) {
  const id      = 'msg-' + Date.now();
  const div     = document.createElement('div');
  div.className = 'msg-group msg-ai';
  div.id        = id;

  const body    = document.createElement('div');
  body.className = 'ai-body';

  const bubble    = document.createElement('div');
  bubble.className = 'bubble-ai';
  bubble.innerHTML = renderMd(text);
  body.appendChild(bubble);
  body.appendChild(buildMetaRow(id, text, meta, timestamp));
  if (meta.sources?.length) body.appendChild(buildSources(meta.sources));
  if (meta.route)           body.appendChild(buildRouteBadge(meta.route));

  div.innerHTML = `
    <div class="ai-ava">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
  `;
  div.appendChild(body);
  const mi = document.getElementById('messagesInner');
  if (mi) mi.appendChild(div);
  scrollDown();
}

function buildMetaRow(msgId, text, meta, timestamp) {
  const row     = document.createElement('div');
  row.className = 'msg-meta';
  row.innerHTML = `
    <span class="msg-time">${fmtTime(timestamp)}</span>
    <button class="action-btn" onclick="copyMsgText(this,'${msgId}')">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
        <rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/>
        <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="2"/>
      </svg>
      Copy
    </button>
    <button class="action-btn" onclick="openShare('${msgId}')">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
        <circle cx="18" cy="5"  r="3" stroke="currentColor" stroke-width="2"/>
        <circle cx="6"  cy="12" r="3" stroke="currentColor" stroke-width="2"/>
        <circle cx="18" cy="19" r="3" stroke="currentColor" stroke-width="2"/>
        <path d="M8.59 13.51l6.83 3.98M15.41 6.51l-6.82 3.98" stroke="currentColor" stroke-width="2"/>
      </svg>
      Share
    </button>
    <button class="action-btn" onclick="regenerate('${msgId}')">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
        <path d="M1 4v6h6M23 20v-6h-6" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        <path d="M20.49 9A9 9 0 005.64 5.64L1 10M23 14l-4.64 4.36A9 9 0 013.51 15" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      Regenerate
    </button>
    <button class="action-btn" onclick="speakText(document.getElementById('${msgId}')?.querySelector('.bubble-ai')?.innerText||'')">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        <path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      Speak
    </button>
    <div style="flex:1"></div>
    <button class="feedback-btn" onclick="giveFeedback(this,1)"  title="Good">👍</button>
    <button class="feedback-btn" onclick="giveFeedback(this,-1)" title="Bad">👎</button>
  `;
  return row;
}

function buildSources(sources) {
  const bar     = document.createElement('div');
  bar.className = 'sources-bar';
  sources.forEach(src => {
    const chip     = document.createElement('span');
    chip.className = 'source-chip';
    chip.innerHTML = `
      <svg width="10" height="10" viewBox="0 0 24 24" fill="none">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" stroke="currentColor" stroke-width="2"/>
        <polyline points="14 2 14 8 20 8" stroke="currentColor" stroke-width="2"/>
      </svg>
      ${escHtml(typeof src === 'string' ? src : src.source || src.name || 'source')}
    `;
    bar.appendChild(chip);
  });
  return bar;
}

function buildRouteBadge(route) {
  const span     = document.createElement('span');
  span.className = 'route-badge';
  const icons    = { rag: '📚', general: '💬', search: '🌐', image: '🖼️', 'image+rag': '🖼️📚', voice: '🎤', stream: '⚡', error: '⚠️' };
  span.innerHTML = `${icons[route] || '💡'} ${route}`;
  return span;
}

function appendTyping() {
  const mi = document.getElementById('messagesInner');
  if (!mi) return { remove: () => {} };
  const div     = document.createElement('div');
  div.className = 'typing-wrap';
  div.innerHTML = `
    <div class="ai-ava">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none">
        <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
      </svg>
    </div>
    <div class="typing-bubble">
      <div class="t-dot"></div><div class="t-dot"></div><div class="t-dot"></div>
    </div>
  `;
  mi.appendChild(div);
  scrollDown();
  return div;
}

function copyMsgText(btn, msgId) {
  const el = document.getElementById(msgId)?.querySelector('.bubble-ai');
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {
    btn.classList.add('ok');
    btn.textContent = '✓ Copied';
    setTimeout(() => {
      btn.classList.remove('ok');
      btn.innerHTML = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none"><rect x="9" y="9" width="13" height="13" rx="2" stroke="currentColor" stroke-width="2"/><path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" stroke="currentColor" stroke-width="2"/></svg> Copy`;
    }, 2000);
  }).catch(() => showToast('Copy failed'));
}

function copyCodeBlock(btn, id) {
  const el = document.getElementById(id);
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {
    btn.classList.add('ok');
    btn.textContent = '✓ Copied';
    setTimeout(() => { btn.classList.remove('ok'); btn.textContent = 'Copy'; }, 2000);
  }).catch(() => showToast('Copy failed'));
}

function openShare(msgId) {
  const el = document.getElementById(msgId)?.querySelector('.bubble-ai');
  if (!el) return;
  state.shareText = el.innerText;
  const sp = $('sharePreview');
  const so = $('shareModalOverlay');
  if (sp) sp.textContent = state.shareText.slice(0, 300) + (state.shareText.length > 300 ? '…' : '');
  if (so) so.style.display = 'flex';
}

function closeShareModal() {
  const so = $('shareModalOverlay');
  if (so) so.style.display = 'none';
}

function shareAction(platform) {
  const text = state.shareText;
  const enc  = encodeURIComponent(text.slice(0, 500));
  if (platform === 'copy') {
    navigator.clipboard.writeText(text).then(() => showToast('Copied to clipboard ✓')).catch(() => showToast('Copy failed'));
  } else if (platform === 'whatsapp') {
    window.open(`https://wa.me/?text=${enc}`, '_blank');
  } else if (platform === 'twitter') {
    window.open(`https://twitter.com/intent/tweet?text=${enc}`, '_blank');
  } else if (platform === 'telegram') {
    window.open(`https://t.me/share/url?url=${encodeURIComponent(window.location.href)}&text=${enc}`, '_blank');
  }
  closeShareModal();
}

function giveFeedback(btn, rating) {
  const parent = btn.closest('.msg-meta');
  if (!parent) return;
  parent.querySelectorAll('.feedback-btn').forEach(b => b.classList.remove('active-up', 'active-down'));
  btn.classList.add(rating === 1 ? 'active-up' : 'active-down');
  showToast(rating === 1 ? '👍 Thanks for the feedback!' : '👎 We\'ll improve!');
}

async function regenerate(msgId) {
  if (!state.lastQuery || state.loading) return;
  const el = document.getElementById(msgId);
  if (el) el.remove();
  if (state.streamMode) await sendStreaming(state.lastQuery, state.lastImages || []);
  else                  await sendBatch(state.lastQuery, state.lastImages || []);
}

function openAnalytics() {
  if (!state.isAdmin) { showToast('Admin access required'); return; }
  const ao = $('analyticsModalOverlay');
  if (ao) ao.style.display = 'flex';
  loadAnalytics();
  if (state.analyticsTimer) clearInterval(state.analyticsTimer);
  state.analyticsTimer = setInterval(loadAnalytics, 30000);
}

function closeAnalytics() {
  const ao = $('analyticsModalOverlay');
  if (ao) ao.style.display = 'none';
  if (state.analyticsTimer) { clearInterval(state.analyticsTimer); state.analyticsTimer = null; }
}

async function loadAnalytics() {
  if (!state.isAdmin) return;
  const body = $('analyticsBody');
  if (!body) return;

  const refreshBtn = document.querySelector('.analytics-refresh-btn');
  if (refreshBtn) refreshBtn.classList.add('spinning');

  try {
    const res = await fetch(`${API}/analytics`, {
      headers: { 'Authorization': `Bearer ${ADMIN_TOKEN}` },
    });

    if (!res.ok) throw new Error(`Status ${res.status}`);
    const data = await res.json();

    const metrics = [
      { icon: '👥', label: 'Total Users',   value: data.total_users   ?? data.users   ?? '—' },
      { icon: '💬', label: 'Total Chats',   value: data.total_chats   ?? data.chats   ?? '—' },
      { icon: '⚡', label: 'Streams',       value: data.total_streams ?? data.streams ?? '—' },
      { icon: '📄', label: 'Uploads',       value: data.total_uploads ?? data.uploads ?? '—' },
      { icon: '🎤', label: 'Voice',         value: data.total_voice   ?? data.voice   ?? '—' },
    ];

    body.innerHTML = metrics.map(m => `
      <div class="analytics-card">
        <div class="analytics-card-icon">${m.icon}</div>
        <div class="analytics-card-value">${typeof m.value === 'number' ? m.value.toLocaleString() : m.value}</div>
        <div class="analytics-card-label">${m.label}</div>
      </div>
    `).join('') + `<div class="analytics-updated">Updated: ${new Date().toLocaleTimeString()}</div>`;

  } catch (err) {
    body.innerHTML = `<div class="analytics-error">⚠️ Failed to load analytics.<br><small>${escHtml(err.message)}</small></div>`;
    console.error('Analytics error:', err);
  } finally {
    if (refreshBtn) refreshBtn.classList.remove('spinning');
  }
}

function exportChat() {
  const msgs = document.querySelectorAll('.msg-group');
  if (!msgs.length) { showToast('No messages to export'); return; }
  let md = `# Aegis AI — Chat Export\nDate: ${new Date().toLocaleString()}\n\n---\n\n`;
  msgs.forEach(m => {
    if (m.classList.contains('msg-user')) {
      const txt = m.querySelector('.bubble-user')?.innerText || '';
      md += `**You:** ${txt}\n\n`;
    } else if (m.classList.contains('msg-ai')) {
      const txt = m.querySelector('.bubble-ai')?.innerText || '';
      md += `**Aegis AI:** ${txt}\n\n`;
    }
  });
  const blob = new Blob([md], { type: 'text/markdown' });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href     = url;
  a.download = `aegis-chat-${Date.now()}.md`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
  showToast('Chat exported ✓');
}

function setLoading(val, streaming) {
  state.loading   = val;
  state.streaming = streaming && val;

  const inp     = document.getElementById('userInput');
  const sendBtn = $('sendBtn');
  const si      = $('sendIcon');
  const sti     = $('stopIcon');

  if (inp) inp.disabled = val;

  if (streaming && val) {
    if (si)      si.style.display  = 'none';
    if (sti)     sti.style.display = '';
    if (sendBtn) { sendBtn.classList.add('stop-mode'); sendBtn.disabled = false; }
  } else {
    if (si)      si.style.display  = '';
    if (sti)     sti.style.display = 'none';
    if (sendBtn) { sendBtn.classList.remove('stop-mode'); sendBtn.disabled = false; }
  }
}

function escHtml(str) {
  return String(str)
    .replace(/&/g,  '&amp;')
    .replace(/</g,  '&lt;')
    .replace(/>/g,  '&gt;')
    .replace(/"/g,  '&quot;')
    .replace(/'/g,  '&#039;');
}

function fmtTime(ts) {
  return (ts ? new Date(ts) : new Date()).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function scrollDown() {
  requestAnimationFrame(() => {
    const ms = document.getElementById('messagesScroll');
    if (ms) ms.scrollTo({ top: ms.scrollHeight, behavior: 'smooth' });
  });
}

function showToast(msg, duration) {
  const existing = document.querySelector(`.toast[data-msg="${CSS.escape(msg)}"]`);
  if (existing) return;
  const el        = document.createElement('div');
  el.className    = 'toast';
  el.textContent  = msg;
  el.dataset.msg  = msg;
  document.body.appendChild(el);
  setTimeout(() => { if (el.parentNode) el.parentNode.removeChild(el); }, duration || 3200);
}

document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key === 'k') { e.preventDefault(); startNewChat(); }
  if ((e.ctrlKey || e.metaKey) && e.key === 'e') { e.preventDefault(); exportChat(); }
  if (e.key === 'Escape') {
    closeProfileModal();
    closeShareModal();
    closeAnalytics();
    closeMobileSidebar();
  }
});
