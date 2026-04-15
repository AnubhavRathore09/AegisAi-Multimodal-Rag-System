'use strict';

const API = "https://aegisai-multimodal-rag-system.onrender.com";

function apiUrl(path) {
  return API + path;
}

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
  voiceStream:    null,
  lastQuery:      '',
  lastImages:     [],
  lastAttachments: [],
  recentImages:   [],
  recentAttachments: [],
  speechRecognition: null,
  liveTranscript: '',
  speakingMessageId: null,
  speechVoices:    [],
  shareText:      '',
  mediaRecorder:  null,
  audioChunks:    [],
  audioMimeType:  'audio/webm',
  analyticsTimer: null,
  collapsed:      false,
  selectedModel:  null,
  roleMode:       'assistant',
  promptTemplate: 'default',
  featureConfig:  null,
  historyExpanded: false,
  archivedChats:   {},
  pinnedChats:     {},
  voiceProfile:    'auto',
  recognitionLanguage: 'auto',
  voiceAssistantMode: 'browser',
  voiceRetryCount: 0,
  voiceSubmitting: false,
  dragDepth: 0,
  _historyLoading: false,
  _sourcesLoading: false,
  _featureLoading: false,
  _sendLock:       false,
};

const $ = id => document.getElementById(id);

function apiUrl(path = '') {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API}${normalized}`;
}

function apiDisplayBase() {
  return API || window.location.origin || REMOTE_API;
}

function getLaunchParams() {
  try {
    return new URLSearchParams(window.location.search);
  } catch {
    return new URLSearchParams();
  }
}

function clearLaunchParams() {
  try {
    const clean = `${window.location.origin}${window.location.pathname}`;
    window.history.replaceState({}, document.title, clean);
  } catch {}
}

function getStoredToken() {
  return localStorage.getItem('rag-token') || null;
}

function getStoredUser() {
  try {
    return JSON.parse(
      localStorage.getItem('rag-user') ||
      localStorage.getItem('rag-current-user') ||
      'null'
    );
  } catch {
    return null;
  }
}

function persistUser(user) {
  localStorage.setItem('rag-user', JSON.stringify(user));
  localStorage.setItem('rag-current-user', JSON.stringify(user));
}

function clearStoredUser() {
  localStorage.removeItem('rag-user');
  localStorage.removeItem('rag-current-user');
}

function persistGuestSession() {
  const guestUser = { name: 'Guest', email: 'guest@aegis.ai' };
  localStorage.setItem('isGuest', 'true');
  localStorage.removeItem('isAdmin');
  localStorage.removeItem('rag-token');
  persistUser(guestUser);
  state.isGuest = true;
  state.isAdmin = false;
  state.token = null;
  state.user = guestUser;
}

function clearStoredSession() {
  clearStoredUser();
  localStorage.removeItem('rag-token');
  localStorage.removeItem('isGuest');
  localStorage.removeItem('isAdmin');
}

function restoreSession() {
  const savedUser = getStoredUser();
  const token = getStoredToken();
  const isGuest = localStorage.getItem('isGuest') === 'true';
  const isAdmin = localStorage.getItem('isAdmin') === 'true';

  if (isGuest) {
    persistGuestSession();
    return true;
  }

  if (savedUser && token) {
    state.user = savedUser;
    state.token = token;
    state.isGuest = false;
    state.isAdmin = isAdmin;
    return true;
  }

  if (savedUser || token || isAdmin) clearStoredSession();
  state.user = null;
  state.token = null;
  state.isGuest = false;
  state.isAdmin = false;
  return false;
}

function preferenceStorageKey(name) {
  return `rag-${name}-${state.user?.email || 'guest'}`;
}

function getStoredPreference(name, fallback = '') {
  try {
    return localStorage.getItem(preferenceStorageKey(name)) || fallback;
  } catch {
    return fallback;
  }
}

function setStoredPreference(name, value) {
  try {
    if (value) localStorage.setItem(preferenceStorageKey(name), value);
    else localStorage.removeItem(preferenceStorageKey(name));
  } catch {}
}

function getObjectPreference(name) {
  try {
    return JSON.parse(localStorage.getItem(preferenceStorageKey(name)) || '{}');
  } catch {
    return {};
  }
}

function setObjectPreference(name, value) {
  try {
    localStorage.setItem(preferenceStorageKey(name), JSON.stringify(value || {}));
  } catch {}
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

function queryRefersToRecentUpload(query) {
  return /\b(this|that|it|uploaded|upload|image|photo|document|file|receipt|pdf)\b/i.test(query || '');
}

function sessionsStorageKey() {
  return `rag-sessions-${state.user?.email}`;
}

function activeChatStorageKey() {
  return `rag-active-chat-${state.user?.email}`;
}

function uniqueSources(sources) {
  const seen = new Set();
  return (sources || []).filter(src => {
    const key = typeof src === 'string'
      ? src
      : `${src.source || src.name || 'source'}::${src.kind || ''}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function loadSpeechVoices() {
  if (!window.speechSynthesis) return;
  state.speechVoices = window.speechSynthesis.getVoices() || [];
}

function pickPreferredVoice() {
  const voices = state.speechVoices || [];
  if (!voices.length) return null;

  const profile = state.voiceProfile || 'auto';

  const byMatchers = matchers => {
    for (const matcher of matchers) {
      const match = voices.find(voice => matcher.test(`${voice.name} ${voice.lang}`));
      if (match) return match;
    }
    return null;
  };

  if (profile === 'hindi') {
    return byMatchers([/hi-in/i, /hindi/i, /india/i]) || voices.find(voice => /hi/i.test(voice.lang)) || voices[0];
  }
  if (profile === 'bilingual') {
    return byMatchers([/en-in/i, /hi-in/i, /india/i, /hindi/i, /google.*english/i, /samantha/i]) || voices[0];
  }
  if (profile === 'english') {
    return byMatchers([/google.*english/i, /samantha/i, /daniel/i, /karen/i, /zira/i, /jenny/i, /aria/i]) || voices[0];
  }
  if (profile === 'default') {
    return voices[0];
  }

  const preferredMatchers = [
    /google.*english/i, /en-in/i, /hi-in/i, /samantha/i, /daniel/i,
    /karen/i, /moira/i, /aaron/i, /zira/i, /jenny/i, /aria/i, /nova/i,
  ];

  for (const matcher of preferredMatchers) {
    const match = voices.find(voice => matcher.test(`${voice.name} ${voice.lang}`));
    if (match) return match;
  }

  return voices.find(voice => /en-/i.test(voice.lang)) || voices[0];
}

function detectSpeechLanguage(text = '') {
  if (state.recognitionLanguage && state.recognitionLanguage !== 'auto') return state.recognitionLanguage;
  const value = String(text || '');
  if (/[ऀ-ॿ]/.test(value)) return 'hi-IN';
  if (/\b(mera|mujhe|kya|kaise|hai|nahi|haan|acha|accha|samjhao|batao|please)\b/i.test(value)) return 'hi-IN';
  return navigator.language || 'en-IN';
}

function updateSpeakButtons() {
  document.querySelectorAll('.speak-btn').forEach(btn => {
    const isActive = btn.dataset.msgId === state.speakingMessageId;
    btn.classList.toggle('active', isActive);
    const label = btn.querySelector('.speak-btn-label');
    if (label) label.textContent = isActive ? 'Stop' : 'Speak';
  });
}

function setComposerDragActive(active) {
  const inputWrap = $('inputWrap');
  if (!inputWrap) return;
  inputWrap.classList.toggle('drag-active', !!active);
}

async function processSelectedFiles(files) {
  for (const file of files) {
    if (file.size > MAX_FILE_SIZE_BYTES) {
      showToast(`File too large: ${file.name} (max ${MAX_FILE_SIZE_MB}MB)`);
      continue;
    }
    const isImage = IMAGE_TYPES.includes(file.type);
    const isDoc = DOC_TYPES.includes(file.type) || file.name.toLowerCase().endsWith('.txt');
    if (!isImage && !isDoc) {
      showToast(`Unsupported file type: ${file.name}`);
      continue;
    }
    const entry = {
      file,
      type: isImage ? 'image' : 'doc',
      base64: null,
      uploaded: false,
      previewUrl: null,
      id: Date.now() + Math.random(),
    };
    state.pendingFiles.push(entry);
    addAttachPreview(entry);
    if (isImage) {
      try {
        entry.base64 = await fileToBase64(file);
        entry.previewUrl = `data:${file.type};base64,${entry.base64}`;
        updateAttachPreview(entry, 'done');
      } catch (err) {
        updateAttachPreview(entry, 'err');
        showToast(`Failed to process image: ${file.name}`);
      }
    } else {
      await uploadDocToBackend(entry);
    }
  }
  const ab = $('attachmentsBar');
  if (ab) ab.style.display = state.pendingFiles.length ? 'block' : 'none';
}

function initComposerDragDrop() {
  const inputWrap = $('inputWrap');
  if (!inputWrap) return;

  document.addEventListener('dragover', event => { event.preventDefault(); });
  document.addEventListener('drop', event => {
    if (!inputWrap.contains(event.target)) event.preventDefault();
  });

  ['dragenter', 'dragover'].forEach(type => {
    inputWrap.addEventListener(type, event => {
      event.preventDefault();
      event.stopPropagation();
      state.dragDepth += 1;
      setComposerDragActive(true);
    });
  });

  ['dragleave', 'dragend'].forEach(type => {
    inputWrap.addEventListener(type, event => {
      event.preventDefault();
      event.stopPropagation();
      state.dragDepth = Math.max(0, state.dragDepth - 1);
      if (state.dragDepth === 0) setComposerDragActive(false);
    });
  });

  inputWrap.addEventListener('drop', async event => {
    event.preventDefault();
    event.stopPropagation();
    state.dragDepth = 0;
    setComposerDragActive(false);
    const dropped = Array.from(event.dataTransfer?.files || []);
    if (!dropped.length) return;
    await processSelectedFiles(dropped);
  });
}

document.addEventListener('DOMContentLoaded', () => {
  if (typeof window.doLogin !== 'function') window.doLogin = doLogin;
  if (typeof window.doSignup !== 'function') window.doSignup = doSignup;
  if (typeof window.switchTab !== 'function') window.switchTab = switchTab;
  if (typeof window.continueAsGuest !== 'function') window.continueAsGuest = continueAsGuest;
  if (typeof window.openForgotPasswordModal !== 'function') window.openForgotPasswordModal = openForgotPasswordModal;
  loadSpeechVoices();
  if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = () => loadSpeechVoices();
  }
  initParticles();
  initMarked();
  loadTheme();
  initComposerDragDrop();

  const launchParams = getLaunchParams();
  const autoGuest = launchParams.get('auto_guest') === '1';
  const autoMic   = launchParams.get('auto_mic')   === '1';

  if (restoreSession() && !window.location.search.includes("force_login")) {
  showApp();
} else if (autoGuest) {
  persistGuestSession();
  showApp();
} else {
  switchTab('login');
}

  if (autoMic) {
    setTimeout(async () => {
      clearLaunchParams();
      if (!state.user && !state.isGuest) continueAsGuest();
      if (window.location.protocol !== 'file:') {
        try { await startVoiceRecording(); } catch (err) { console.error('Auto mic start failed:', err); }
      }
    }, 500);
  } else if (launchParams.toString()) {
    clearLaunchParams();
  }
});

function getStoredActiveChatId() {
  try { return localStorage.getItem(activeChatStorageKey()) || null; } catch { return null; }
}

function setStoredActiveChatId(chatId) {
  try {
    if (chatId) localStorage.setItem(activeChatStorageKey(), chatId);
    else localStorage.removeItem(activeChatStorageKey());
  } catch {}
}

async function loadFeatureConfig() {
  if (state._featureLoading) return;
  state._featureLoading = true;
  try {
    const res = await apiFetch('/features', { headers: getAuthHeaders() });
    if (!res || !res.ok) return;
    const data = await res.json();
    state.featureConfig = data;
    const models          = data.models          || [];
    const roleModes       = data.role_modes       || [];
    const promptTemplates = data.prompt_templates || [];

    state.selectedModel    = getStoredPreference('model',                models[0]          || null);
    state.roleMode         = getStoredPreference('role-mode',            roleModes[0]       || 'assistant');
    state.promptTemplate   = getStoredPreference('prompt-template',      promptTemplates[0] || 'default');
    state.voiceProfile     = getStoredPreference('voice-profile',        'auto');
    state.recognitionLanguage = getStoredPreference('recognition-language', 'auto');
    state.voiceAssistantMode  = getStoredPreference('voice-assistant',   'browser');
    state.archivedChats    = getObjectPreference('archived-chats');
    state.pinnedChats      = getObjectPreference('pinned-chats');
    updateTopbarStatus();
    syncSettingsUI();
  } catch (err) {
    console.error('Feature config load failed:', err);
  } finally {
    state._featureLoading = false;
  }
}

function updateTopbarStatus() {
  const status = $('topbarStatus');
  if (!status) return;
  status.textContent = 'Aegis AI · v2.1';
}

function fillSelectWithOptions(id, values, selectedValue) {
  const el = $(id);
  if (!el) return;
  el.innerHTML = '';
  (values || []).forEach(value => {
    const option = document.createElement('option');
    option.value = value;
    option.textContent = prettyOptionLabel(value);
    option.selected = value === selectedValue;
    el.appendChild(option);
  });
}

function syncSettingsUI() {
  fillSelectWithOptions('settingsRoleMode',      state.featureConfig?.role_modes       || ['assistant'], state.roleMode);
  fillSelectWithOptions('settingsPromptTemplate', state.featureConfig?.prompt_templates || ['default'],   state.promptTemplate);
  const themeEl     = $('settingsTheme');
  const voiceEl     = $('settingsVoiceProfile');
  const recEl       = $('settingsRecognitionLanguage');
  const assistantEl = $('settingsVoiceAssistant');
  if (themeEl)     themeEl.value     = document.documentElement.dataset.theme || 'dark';
  if (voiceEl)     voiceEl.value     = state.voiceProfile;
  if (recEl)       recEl.value       = state.recognitionLanguage;
  if (assistantEl) assistantEl.value = state.voiceAssistantMode;
  renderArchivedChatsList();
}

function renderArchivedChatsList() {
  const wrap = $('archivedChatsList');
  if (!wrap) return;
  const sessions        = JSON.parse(localStorage.getItem(sessionsStorageKey()) || '[]');
  const archivedEntries = Object.entries(state.archivedChats || {});
  const archived = archivedEntries.map(([id, meta]) => {
    const session = sessions.find(item => item.id === id);
    if (session) return session;
    if (meta && typeof meta === 'object') {
      return { id, title: meta.title || 'Archived chat', updated_at: meta.updated_at || new Date().toISOString() };
    }
    return { id, title: 'Archived chat', updated_at: new Date().toISOString() };
  });
  if (!archived.length) {
    wrap.innerHTML = '<div class="archived-empty">No archived chats</div>';
    return;
  }
  wrap.innerHTML = archived.map(session => `
    <div class="archived-chat-row">
      <div class="archived-chat-title">${escHtml(session.title || 'Chat')}</div>
      <button class="archived-chat-btn" onclick="unarchiveChat('${session.id}')">Restore</button>
    </div>
  `).join('');
}

function unarchiveChat(sessionId) {
  if (!state.archivedChats?.[sessionId]) return;
  delete state.archivedChats[sessionId];
  setObjectPreference('archived-chats', state.archivedChats);
  renderArchivedChatsList();
  loadHistory();
  showToast('Chat restored');
}

function shortModelLabel(model) {
  const value = String(model || '').trim();
  if (!value) return 'Default';
  if (value.length <= 20) return value;
  return value.replace('meta-llama/', '').replace('llama-', 'Llama ').replace('-versatile', '').replace('-instruct', '').replace(/-/g, ' ').trim().slice(0, 20);
}

function prettyOptionLabel(value, type = '') {
  const raw = String(value || '');
  if (!raw) return '';
  if (type === 'model') return shortModelLabel(raw);
  return raw.replace(/[_-]/g, ' ').replace(/\b\w/g, char => char.toUpperCase());
}

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
      x: Math.random() * window.innerWidth,  y: Math.random() * window.innerHeight,
      r: Math.random() * 1.4 + 0.3,
      dx: (Math.random() - 0.5) * 0.28,     dy: (Math.random() - 0.5) * 0.28,
      a: Math.random(),                       da: (Math.random() - 0.5) * 0.007,
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
  const renderer = new marked.Renderer();
  renderer.code  = (code, lang) => {
    const id = 'c' + Math.random().toString(36).slice(2, 7);
    return `<pre><div class="pre-header"><span class="pre-lang">${lang || 'code'}</span><button class="pre-copy" onclick="copyCodeBlock(this,'${id}')">Copy</button></div><code id="${id}">${escHtml(code)}</code></pre>`;
  };
  marked.use({ renderer });
}

function renderMd(text) {
  if (!text) return '';
  const prepared = prepareAnswerText(text);
  if (typeof marked === 'undefined') return escHtml(prepared).replace(/\n/g, '<br>');
  try {
    const raw = marked.parse(prepared);
    return typeof DOMPurify !== 'undefined' ? DOMPurify.sanitize(raw) : raw;
  } catch {
    return escHtml(prepared).replace(/\n/g, '<br>');
  }
}

function prepareAnswerText(text) {
  const value = String(text || '').trim();
  if (!value) return '';
  const looksLikeMarkdown = /(^|\n)\s*([-*]|#{1,6}|\d+\.)\s|```|\|/.test(value);
  if (looksLikeMarkdown || value.includes('\n\n')) return value;
  const sentences = value.match(/[^.!?]+[.!?]+|[^.!?]+$/g)?.map(s => s.trim()).filter(Boolean) || [value];
  if (sentences.length < 3) return value;
  const chunks = [];
  for (let i = 0; i < sentences.length; i += 2) {
    chunks.push(sentences.slice(i, i + 2).join(' '));
  }
  return chunks.join('\n\n');
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
    const res = await fetch(apiUrl(path), options);
    if (res.status === 401) handleAuthError();
    return res;
  } catch (err) {
    if (err.name === 'TypeError' || err.message.includes('fetch')) {
      throw new Error(`Cannot connect to server at ${apiDisplayBase()}`);
    }
    throw err;
  }
}

function handleAuthError() {
  clearStoredSession();
  state.user = null;
  state.token = null;
  state.isGuest = false;
  state.isAdmin = false;
  showToast('Session expired. Please sign in again.');
  const authScreen = $('authScreen');
  const appWrapper = $('appWrapper');
  if (authScreen) authScreen.style.display = 'flex';
  if (appWrapper) appWrapper.style.display = 'none';
}

function switchTab(tab) {
  $('tabLogin').classList.toggle('active', tab === 'login');
  $('tabSignup').classList.toggle('active', tab === 'signup');
  $('formLogin').style.display  = tab === 'login'  ? 'block' : 'none';
  $('formSignup').style.display = tab === 'signup' ? 'block' : 'none';
  $('loginError').textContent   = '';
  $('signupError').textContent  = '';
}

function openForgotPasswordModal() {
  const overlay = $('forgotPasswordOverlay');
  const err = $('forgotError');
  if (err) err.textContent = '';
  ['forgotEmail', 'forgotPassword', 'forgotPasswordConfirm'].forEach(id => {
    const el = $(id); if (el) el.value = '';
  });
  if (overlay) overlay.style.display = 'flex';
}

function closeForgotPasswordModal() {
  const overlay = $('forgotPasswordOverlay');
  if (overlay) overlay.style.display = 'none';
}

function recoverPassword() {
  const email    = $('forgotEmail')?.value.trim().toLowerCase();
  const password = $('forgotPassword')?.value || '';
  const confirm  = $('forgotPasswordConfirm')?.value || '';
  const err      = $('forgotError');
  if (err) err.textContent = '';

  if (!email || !password || !confirm) { if (err) err.textContent = 'Please fill all fields.'; return; }
  if (password.length < 6)             { if (err) err.textContent = 'Password must be at least 6 characters.'; return; }
  if (password !== confirm)            { if (err) err.textContent = 'Passwords do not match.'; return; }
  if (email === 'admin@aegis.ai' || email === 'demo@aegis.ai') {
    if (err) err.textContent = 'Demo/Admin accounts use fixed demo credentials.'; return;
  }

  const users = JSON.parse(localStorage.getItem('rag-users') || '[]');
  const index = users.findIndex(user => String(user.email || '').toLowerCase() === email);
  if (index < 0) { if (err) err.textContent = 'No local account found for that email.'; return; }

  users[index] = { ...users[index], password };
  localStorage.setItem('rag-users', JSON.stringify(users));
  closeForgotPasswordModal();
  const loginEmail = $('loginEmail');
  if (loginEmail) loginEmail.value = email;
  showToast('Password updated. You can sign in now.');
}

function continueAsGuest() {
  persistGuestSession();
  showApp();
}

window.onload = () => {
  if (!restoreSession()) {
    const authScreen = document.getElementById('authScreen');
    const appWrapper = document.getElementById('appWrapper');
    if (authScreen) authScreen.style.display = 'flex';
    if (appWrapper) appWrapper.style.display = 'none';
  }
};

async function doLogin() {
  const email = $('loginEmail').value.trim();
  const password = $('loginPassword').value;
  const errEl = $('loginError');

  if (!email || !password) {
    errEl.textContent = 'Please fill all fields.';
    return;
  }

  const btnText = $('loginBtnText');
  const spinner = $('loginSpinner');
  const loginBtn = $('loginBtn');

  if (btnText) btnText.style.display = 'none';
  if (spinner) spinner.style.display = 'block';
  if (loginBtn) loginBtn.disabled = true;

  errEl.textContent = '';

  try {
    const isAdminLogin = (email === 'admin@aegis.ai' && password === 'admin123');
    const isDemoLogin = (email === 'demo@aegis.ai' && password === 'demo123');

    if (isAdminLogin) {
      localStorage.setItem('isAdmin', 'true');
      localStorage.removeItem('isGuest');

      state.isAdmin = true;
      state.isGuest = false;
      state.token = ADMIN_TOKEN;

      localStorage.setItem('rag-token', ADMIN_TOKEN);

      loginSuccess({ name: 'Admin', email });
      return;
    }

    if (isDemoLogin) {
      state.token = "local-auth";
      localStorage.setItem('rag-token', "local-auth");

      localStorage.removeItem('isGuest');
      localStorage.removeItem('isAdmin');

      state.isAdmin = false;
      state.isGuest = false;

      loginSuccess({ name: 'Demo User', email });
      return;
    }

    const users = JSON.parse(localStorage.getItem('rag-users') || '[]');
    const user = users.find(u => u.email === email && u.password === password);

    if (!user) {
      errEl.textContent = 'Invalid email or password.';
    } else {
      state.token = "local-auth";
      localStorage.setItem('rag-token', "local-auth");

      localStorage.removeItem('isGuest');
      localStorage.removeItem('isAdmin');
      state.isAdmin = false;
      state.isGuest = false;

      loginSuccess(user);
      return;
    }

  } catch (err) {
    errEl.textContent = 'Login failed. Server error.';
  }

  if (btnText) btnText.style.display = 'block';
  if (spinner) spinner.style.display = 'none';
  if (loginBtn) loginBtn.disabled = false;
}

function doSignup() {
  const name = $('signupName').value.trim();
  const email = $('signupEmail').value.trim();
  const password = $('signupPassword').value;
  const errEl = $('signupError');

  if (!name || !email || !password) {
    errEl.textContent = 'Fill all fields.';
    return;
  }

  if (password.length < 6) {
    errEl.textContent = 'Password min 6 chars.';
    return;
  }

  if (!email.includes('@')) {
    errEl.textContent = 'Invalid email.';
    return;
  }

  const users = JSON.parse(localStorage.getItem('rag-users') || '[]');

  if (users.find(u => u.email === email)) {
    errEl.textContent = 'Email already registered.';
    return;
  }

  const newUser = { name, email, password };
  users.push(newUser);

  localStorage.setItem('rag-users', JSON.stringify(users));
  localStorage.removeItem('isGuest');
  localStorage.removeItem('isAdmin');

  state.token = "local-auth";
  localStorage.setItem('rag-token', "local-auth");
  state.isAdmin = false;
  state.isGuest = false;

  loginSuccess(newUser);
}

function loginSuccess(user) {
  state.user = user;
  state.isGuest = false;
  state.isAdmin = state.isAdmin || user?.role === 'admin' || user?.email === 'admin@aegis.ai';
  persistUser(user);

  const btnText = $('loginBtnText');
  const spinner = $('loginSpinner');
  const loginBtn = $('loginBtn');

  if (btnText) btnText.style.display = 'block';
  if (spinner) spinner.style.display = 'none';
  if (loginBtn) loginBtn.disabled = false;

  showApp();
}

function showApp() {
  const authScreen = $('authScreen');
  const appWrapper = $('appWrapper');

  if (authScreen) authScreen.style.display = 'none';
  if (appWrapper) appWrapper.style.display = 'flex';

  const name = state.user?.name || 'User';
  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();

  const ua = $('userAvatar');
  const pa = $('profileAvatarBig');
  const un = $('userName');
  const ue = $('userEmail');
  const wt = $('welcomeTitle');
  const pm = $('profileMenuName');
  const pma = $('profileMenuAvatar');

  if (ua) ua.textContent = initials;
  if (pa) pa.textContent = initials;
  if (pma) pma.textContent = initials;

  if (un) un.textContent = name;
  if (pm) pm.textContent = name;

  if (ue) ue.textContent = state.user?.email || '';

  if (wt) wt.textContent = `Welcome ${state.isGuest ? '' : 'back, '}${name.split(' ')[0]}!`;
  
  const guestBadge = $('guestBadge');
  const adminBadge = $('adminBadge');

  if (guestBadge) guestBadge.style.display = state.isGuest ? 'flex' : 'none';
  if (adminBadge) adminBadge.style.display = state.isAdmin ? 'flex' : 'none';

  if (localStorage.getItem('rag-collapsed') === 'true') {
    setSidebarCollapsed(true);
  }

  loadFeatureConfig();
  updateStreamBadge();
  loadTheme();
  loadHistory();
  loadIndexedSources();
}


function doLogout() {
  clearStoredSession();
  state.user    = null;
  state.token   = null;
  state.isGuest = false;
  state.isAdmin = false;
  state.chatId  = null;
  setStoredActiveChatId(null);
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
  const menu     = $('profileMenu');
  const profile  = $('userProfile');
  const chatMenu = $('chatMenu');
  if (menu && profile && !profile.contains(e.target) && !menu.contains(e.target)) {
    menu.style.display = 'none';
  }
  if (chatMenu && !chatMenu.contains(e.target) && !e.target.closest('[onclick="toggleChatMenu()"]')) {
    chatMenu.style.display = 'none';
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
  const chatMenu = $('chatMenu');
  if (chatMenu) chatMenu.style.display = 'none';
  const m = $('profileMenu');
  if (m) m.style.display = m.style.display === 'none' ? 'block' : 'none';
}

function closeProfileMenu() {
  const m = $('profileMenu');
  if (m) m.style.display = 'none';
}

function toggleChatMenu() {
  closeProfileMenu();
  const menu = $('chatMenu');
  if (menu) menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
}

function closeChatMenu() {
  const menu = $('chatMenu');
  if (menu) menu.style.display = 'none';
}

function openSettingsModal(section = '') {
  closeProfileMenu();
  syncSettingsUI();
  const modal = $('settingsModalOverlay');
  if (modal) modal.style.display = 'flex';
  if (section === 'personalization') {
    const role = $('settingsRoleMode');
    if (role) role.focus();
  }
}

function closeSettingsModal() {
  const modal = $('settingsModalOverlay');
  if (modal) modal.style.display = 'none';
}

function saveSettings() {
  const role          = $('settingsRoleMode')?.value          || 'assistant';
  const template      = $('settingsPromptTemplate')?.value    || 'default';
  const theme         = $('settingsTheme')?.value             || 'dark';
  const voice         = $('settingsVoiceProfile')?.value      || 'auto';
  const recognition   = $('settingsRecognitionLanguage')?.value || 'auto';
  const voiceAssistant = $('settingsVoiceAssistant')?.value   || 'browser';
  state.roleMode           = role;
  state.promptTemplate     = template;
  state.voiceProfile       = voice;
  state.recognitionLanguage = recognition;
  state.voiceAssistantMode = voiceAssistant;
  setStoredPreference('role-mode',             role);
  setStoredPreference('prompt-template',       template);
  setStoredPreference('voice-profile',         voice);
  setStoredPreference('recognition-language',  recognition);
  setStoredPreference('voice-assistant',       voiceAssistant);
  applyTheme(theme);
  closeSettingsModal();
  showToast('Settings saved ✓');
}

function openHelpModal() {
  closeProfileMenu();
  closeChatMenu();
  const modal = $('helpModalOverlay');
  if (modal) modal.style.display = 'flex';
}

function closeHelpModal() {
  const modal = $('helpModalOverlay');
  if (modal) modal.style.display = 'none';
}

function switchAccount() {
  doLogout();
  showToast('Signed out. You can log into another account now.');
}

function toggleHistoryExpanded() {
  state.historyExpanded = !state.historyExpanded;
  loadHistory();
}

function togglePinCurrentChat() {
  if (!state.chatId) { showToast('Open a chat first.'); return; }
  state.pinnedChats[state.chatId] = !state.pinnedChats[state.chatId];
  if (!state.pinnedChats[state.chatId]) delete state.pinnedChats[state.chatId];
  setObjectPreference('pinned-chats', state.pinnedChats);
  closeChatMenu();
  loadHistory();
}

function archiveCurrentChat() {
  if (!state.chatId) { showToast('Open a chat first.'); return; }
  const sessions = JSON.parse(localStorage.getItem(sessionsStorageKey()) || '[]');
  const active   = sessions.find(session => session.id === state.chatId);
  state.archivedChats[state.chatId] = {
    title:      active?.title      || state.lastQuery || 'Archived chat',
    updated_at: active?.updated_at || new Date().toISOString(),
  };
  setObjectPreference('archived-chats', state.archivedChats);
  closeChatMenu();
  startNewChat();
  loadHistory();
  showToast('Chat archived');
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
  persistUser(updated);

  const initials = name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase();
  const ua  = $('userAvatar');
  const pa  = $('profileAvatarBig');
  const un  = $('userName');
  const pmn = $('profileMenuName');
  const pma = $('profileMenuAvatar');
  if (ua)  ua.textContent  = initials;
  if (pa)  pa.textContent  = initials;
  if (pma) pma.textContent = initials;
  if (un)  un.textContent  = name;
  if (pmn) pmn.textContent = name;
  closeProfileModal();
  showToast('Profile updated ✓');
}

const newChatBtn = $('newChatBtn');
if (newChatBtn) newChatBtn.addEventListener('click', startNewChat);

function startNewChat() {
  state.chatId       = null;
  setStoredActiveChatId(null);
  state.pendingFiles = [];
  state.lastImages   = [];
  const mi = document.getElementById('messagesInner');
  const al = document.getElementById('attachmentsList');
  const ab = document.getElementById('attachmentsBar');
  const vt = document.getElementById('voiceTranscript');
  const sc = $('shareChatBtn');
  if (mi) mi.innerHTML     = '';
  if (al) al.innerHTML     = '';
  if (ab) ab.style.display = 'none';
  if (vt) vt.style.display = 'none';
  if (sc) sc.style.display = 'none';
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
  if (state._historyLoading) return;
  state._historyLoading = true;

  const hl    = $('historyLoading');
  const he    = $('historyEmpty');
  const hlist = $('historyList');
  if (hl)    hl.style.display = 'flex';
  if (he)    he.style.display = 'none';
  if (hlist) hlist.innerHTML  = '';

  if (state.isGuest) {
    if (hl) hl.style.display = 'none';
    if (he) he.style.display = 'flex';
    state._historyLoading = false;
    return;
  }

  try {
    const res = await apiFetch('/api/history', { headers: getAuthHeaders() });
    if (res && res.ok) {
      const data = await res.json();
      if (hl) hl.style.display = 'none';
      const sessions = Array.isArray(data) ? data : (data.sessions || []);
      renderHistoryList(sessions);
      restoreActiveSession(sessions);
      state._historyLoading = false;
      return;
    }
  } catch {}

  if (hl) hl.style.display = 'none';
  const sessions = JSON.parse(localStorage.getItem(sessionsStorageKey()) || '[]');
  renderHistoryList(sessions);
  restoreActiveSession(sessions);
  state._historyLoading = false;
}

function restoreActiveSession(sessions) {
  const visibleSessions = (sessions || []).filter(session => !state.archivedChats?.[session.id]);
  if (!visibleSessions.length) return;
  const preferredId = state.chatId || getStoredActiveChatId();
  const match = preferredId
    ? visibleSessions.find(session => session.id === preferredId)
    : visibleSessions[0];
  if (!match) return;

  const mi = document.getElementById('messagesInner');
  const alreadyShowingActiveChat =
    state.chatId === match.id && !!mi && !!mi.children.length;
  if (alreadyShowingActiveChat) return;
  loadSession(match);
}

function renderHistoryList(sessions) {
  const hlist    = $('historyList');
  const he       = $('historyEmpty');
  const moreWrap = $('historyMoreWrap');
  const moreBtn  = $('historyMoreBtn');
  if (!hlist) return;
  hlist.innerHTML = '';
  if (!sessions?.length) {
    if (he)       he.style.display       = 'flex';
    if (moreWrap) moreWrap.style.display = 'none';
    return;
  }
  if (he) he.style.display = 'none';
  const visibleSessions = sessions.filter(session => !state.archivedChats?.[session.id]);
  if (!visibleSessions.length) {
    if (he)       he.style.display       = 'flex';
    if (moreWrap) moreWrap.style.display = 'none';
    return;
  }
  visibleSessions.sort((a, b) => {
    const pinnedA = !!state.pinnedChats?.[a.id];
    const pinnedB = !!state.pinnedChats?.[b.id];
    if (pinnedA !== pinnedB) return pinnedA ? -1 : 1;
    return new Date(b.updated_at || b.created_at || 0) - new Date(a.updated_at || a.created_at || 0);
  });
  const limitedSessions = state.historyExpanded ? visibleSessions : visibleSessions.slice(0, 10);
  if (moreWrap && moreBtn) {
    moreWrap.style.display = visibleSessions.length > 10 ? 'block' : 'none';
    moreBtn.textContent    = state.historyExpanded ? 'Show less' : `Show more (${visibleSessions.length - 10})`;
  }

  const groups = groupByDate(limitedSessions);
  for (const [label, items] of Object.entries(groups)) {
    if (!items.length) continue;
    const lbl       = document.createElement('div');
    lbl.className   = 'history-group-label';
    lbl.textContent = label;
    hlist.appendChild(lbl);
    items.forEach(s => {
      const div      = document.createElement('div');
      div.className  = 'history-item';
      div.dataset.id = s.id;
      if (state.chatId === s.id) div.classList.add('active');
      div.innerHTML  = `
        <svg class="chat-icon" width="13" height="13" viewBox="0 0 24 24" fill="none">
          <path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z" stroke="currentColor" stroke-width="2"/>
        </svg>
        <span class="history-item-text">${escHtml(s.title || 'Chat')}</span>
        ${state.pinnedChats?.[s.id] ? '<span class="history-pin">📌</span>' : ''}
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
  setStoredActiveChatId(session.id);
  closeMobileSidebar();
  document.querySelectorAll('.history-item').forEach(i => i.classList.toggle('active', i.dataset.id === session.id));
  const sc = $('shareChatBtn');
  if (sc) sc.style.display = 'flex';

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
      if (m.role === 'user')           appendUserMsg(m.content, m.timestamp, []);
      else if (m.role === 'assistant') appendAIMsg(m.content, {}, m.timestamp);
    });
  } catch {
    if (mi) mi.innerHTML = '';
    const raw  = localStorage.getItem(`rag-msgs-${session.id}`);
    const msgs = raw ? JSON.parse(raw) : [];
    if (msgs.length === 0) renderWelcome();
    else msgs.forEach(m => {
      if (m.role === 'user')           appendUserMsg(m.content, m.timestamp, []);
      else if (m.role === 'assistant') appendAIMsg(m.content, {}, m.timestamp);
    });
  }
  scrollDown();
}

function saveSessionLocal(id, title) {
  if (state.isGuest) return;
  const key      = sessionsStorageKey();
  const sessions = JSON.parse(localStorage.getItem(key) || '[]');
  const now      = new Date().toISOString();
  const idx      = sessions.findIndex(s => s.id === id);
  if (idx >= 0) { sessions[idx].title = title; sessions[idx].updated_at = now; }
  else sessions.unshift({ id, title, created_at: now, updated_at: now });
  localStorage.setItem(key, JSON.stringify(sessions));
  setStoredActiveChatId(id);
  if (state.archivedChats?.[id]) {
    delete state.archivedChats[id];
    setObjectPreference('archived-chats', state.archivedChats);
  }
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
  if (!state.chatId) return;
  closeChatMenu();
  const overlay = $('deleteChatOverlay');
  const text    = $('deleteChatText');
  if (text) {
    const active = JSON.parse(localStorage.getItem(sessionsStorageKey()) || '[]').find(session => session.id === state.chatId);
    text.textContent = `This will delete ${active?.title || 'this conversation'}.`;
  }
  if (overlay) overlay.style.display = 'flex';
}

function closeDeleteChatModal() {
  const overlay = $('deleteChatOverlay');
  if (overlay) overlay.style.display = 'none';
}

async function confirmDeleteCurrentChat() {
  if (!state.chatId) return;
  const id = state.chatId;
  closeDeleteChatModal();
  await deleteSession(null, id);
}

async function deleteSession(e, id) {
  if (e) e.stopPropagation();
  try {
    await apiFetch(`/api/history/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
  } catch {}
  localStorage.removeItem(`rag-msgs-${id}`);
  const key      = sessionsStorageKey();
  const sessions = JSON.parse(localStorage.getItem(key) || '[]').filter(s => s.id !== id);
  localStorage.setItem(key, JSON.stringify(sessions));
  if (state.archivedChats?.[id]) { delete state.archivedChats[id]; setObjectPreference('archived-chats', state.archivedChats); }
  if (state.pinnedChats?.[id])   { delete state.pinnedChats[id];   setObjectPreference('pinned-chats',   state.pinnedChats); }
  if (getStoredActiveChatId() === id) setStoredActiveChatId(null);
  renderHistoryList(sessions);
  if (state.chatId === id) startNewChat();
  showToast('Conversation deleted');
}

async function handleFiles(input) {
  const files = Array.from(input.files || []);
  await processSelectedFiles(files);
  input.value = '';
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
    const res = await fetch(apiUrl('/api/upload'), {
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

    const data     = await res.json();
    entry.uploadMeta = data;
    entry.uploaded   = true;
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

function buildAttachmentPayload(files) {
  return files
    .filter(f => f.type === 'doc' && f.uploadMeta)
    .map(f => ({
      upload_id:      f.uploadMeta.upload_id   || null,
      filename:       f.uploadMeta.filename    || f.file.name,
      content_type:   f.file.type              || 'application/octet-stream',
      kind:           'document',
      extracted_text: f.uploadMeta.extracted_text || '',
    }));
}

async function loadIndexedSources() {
  if (state._sourcesLoading) return;
  state._sourcesLoading = true;
  try {
    const res = await apiFetch('/chat/sources', { headers: getAuthHeaders() });
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
  } finally {
    state._sourcesLoading = false;
  }
}

async function toggleVoice() {
  if (window.location.protocol === 'file:') {
    showToast('Opening the app server for microphone access...');
    setTimeout(() => { window.location.href = `${apiDisplayBase()}?auto_guest=1&auto_mic=1`; }, 250);
    return;
  }
  if (state.recording) finishVoiceInput();
  else await startVoiceRecording();
}

async function startVoiceRecording() {
  if (state.recording) return;
  try {
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      showVoiceError('Audio recording is not supported in this browser. Open the app in Chrome.');
      return;
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    state.voiceStream   = stream;
    state.liveTranscript = '';
    state.audioChunks   = [];
    state.audioMimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
      ? 'audio/webm;codecs=opus'
      : 'audio/webm';

    const recorder = new MediaRecorder(stream, { mimeType: state.audioMimeType });
    state.mediaRecorder = recorder;

    state.recording = true;
    const vb = $('voiceBtn');
    const vt = $('voiceTranscript');
    const tt = $('transcriptText');
    const vs = $('voiceStatus');
    if (vb) vb.classList.add('recording');
    if (vt) vt.style.display = 'flex';
    if (tt) tt.textContent   = 'Listening... Speak now.';
    if (vs) vs.textContent   = 'Listening';

    recorder.ondataavailable = evt => {
      if (evt.data && evt.data.size > 0) state.audioChunks.push(evt.data);
    };

    recorder.onerror = evt => {
      console.error('Recorder error:', evt);
      showVoiceError('Audio recording failed. Please try again.');
    };

    recorder.start(250);
  } catch (err) {
    console.error('Mic access error:', err);
    showVoiceError(`Microphone error: ${err.message}`);
  }
}

async function transcribeRecordedAudio() {
  const blob = new Blob(state.audioChunks || [], { type: state.audioMimeType || 'audio/webm' });
  if (!blob.size) throw new Error('No speech detected. Please try again.');

  const form = new FormData();
  const lang = detectSpeechLanguage(state.liveTranscript);
  form.append('audio', blob, `voice.${(state.audioMimeType || 'audio/webm').includes('mp4') ? 'm4a' : 'webm'}`);
  form.append('language', String(lang || '').slice(0, 2));

  const res = await fetch(apiUrl('/api/voice/voice-chat'), {
    method:  'POST',
    headers: getUploadHeaders(),
    body:    form,
  });

  if (!res.ok) {
    let errMsg = `Voice transcription failed (${res.status})`;
    try { const data = await res.json(); errMsg = data.detail || data.message || errMsg; } catch {}
    throw new Error(errMsg);
  }

  const data = await res.json();
  return String(data.text || '').trim();
}

async function finishVoiceInput() {
  if (!state.recording || state.voiceSubmitting) return;
  const tt = $('transcriptText');
  const vs = $('voiceStatus');
  if (tt) tt.textContent = 'Transcribing audio...';
  if (vs) vs.textContent = 'Processing';

  state.recording      = false;
  state.voiceSubmitting = true;
  const recorder = state.mediaRecorder;
  if (!recorder) { state.voiceSubmitting = false; resetVoiceUI(); return; }

  await new Promise(resolve => {
    recorder.onstop = () => resolve(null);
    try {
      if (recorder.state !== 'inactive') recorder.stop();
      else resolve(null);
    } catch { resolve(null); }
  });

  try {
    const transcript = await transcribeRecordedAudio();
    if (!transcript) throw new Error('No speech detected. Please try again.');
    const ui = document.getElementById('userInput');
    if (ui) { ui.value = transcript; growInput(ui); }
    resetVoiceUI();
    await sendMessage();
  } catch (err) {
    showVoiceError(err.message || 'Voice transcription failed.');
  } finally {
    state.voiceSubmitting = false;
  }
}

function resetVoiceUI() {
  state.recording = false;
  const vb = $('voiceBtn');
  const vt = $('voiceTranscript');
  const tt = $('transcriptText');
  const vs = $('voiceStatus');
  if (vb) vb.classList.remove('recording');
  if (vt) vt.style.display = 'none';
  if (tt) tt.textContent   = 'Speak now…';
  if (vs) vs.textContent   = 'Listening';
  state.liveTranscript  = '';
  state.voiceRetryCount = 0;
  state.audioChunks     = [];
  if (state.mediaRecorder) {
    try { if (state.mediaRecorder.state !== 'inactive') state.mediaRecorder.stop(); } catch {}
    state.mediaRecorder = null;
  }
  if (state.voiceStream) {
    try { state.voiceStream.getTracks().forEach(track => track.stop()); } catch {}
    state.voiceStream = null;
  }
  if (state.speechRecognition) {
    try { state.speechRecognition.onresult = null; state.speechRecognition.onerror = null; state.speechRecognition.onend = null; } catch {}
    state.speechRecognition = null;
  }
}

function showVoiceError(message) {
  const vt = $('voiceTranscript');
  const tt = $('transcriptText');
  const vs = $('voiceStatus');
  const vb = $('voiceBtn');
  state.recording = false;
  if (vb) vb.classList.remove('recording');
  if (vt) vt.style.display = 'flex';
  if (vs) vs.textContent   = 'Voice unavailable';
  if (tt) tt.textContent   = message;
  if (state.speechRecognition) {
    try { state.speechRecognition.abort(); } catch {}
    state.speechRecognition = null;
  }
}

function cancelVoice() {
  if (state.mediaRecorder) {
    try { if (state.mediaRecorder.state !== 'inactive') state.mediaRecorder.stop(); } catch {}
  }
  if (state.speechRecognition) {
    try { state.speechRecognition.abort(); } catch {}
  }
  resetVoiceUI();
}

function stopSpeaking() {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.cancel();
  state.speakingMessageId = null;
  updateSpeakButtons();
}

function speakText(text, msgId = '') {
  if (!window.speechSynthesis || !text) return;

  if (msgId && state.speakingMessageId === msgId && window.speechSynthesis.speaking) {
    stopSpeaking();
    return;
  }

  window.speechSynthesis.cancel();
  const utt   = new SpeechSynthesisUtterance(text);
  const voice = pickPreferredVoice();
  if (voice) utt.voice = voice;
  utt.lang   = detectSpeechLanguage(text);
  utt.rate   = 1.02;
  utt.pitch  = 1.0;
  utt.volume = 1;

  state.speakingMessageId = msgId || null;
  updateSpeakButtons();

  utt.onend = () => { state.speakingMessageId = null; updateSpeakButtons(); };
  utt.onerror = err => { console.warn('TTS error:', err); state.speakingMessageId = null; updateSpeakButtons(); };

  window.speechSynthesis.speak(utt);
}

function speak(text) { speakText(text); }

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
  const inp      = document.getElementById('userInput');
  if (!inp) return;
  const text     = inp.value.trim();
  const hasFiles = state.pendingFiles.length > 0;

  if (!text && !hasFiles) return;

  if (state.streaming && state.currentStream) {
    state.currentStream.abort();
    return;
  }

  if (state.loading || state._sendLock) return;
  state._sendLock = true;

  if (!state.chatId) {
    state.chatId = 'chat_' + Date.now() + '_' + Math.random().toString(36).slice(2, 7);
  }

  const ws = $('welcomeState');
  if (ws) ws.remove();

  const query               = text || 'Please analyze the attached file(s).';
  const files               = [...state.pendingFiles];
  const currentImages       = files.filter(f => f.type === 'image' && f.base64);
  const currentAttachments  = buildAttachmentPayload(files);
  const hasCurrentUploadContext = currentImages.length > 0 || currentAttachments.length > 0;
  const useRecentContext    = !hasCurrentUploadContext && queryRefersToRecentUpload(query);
  const images              = hasCurrentUploadContext ? currentImages : (useRecentContext ? (state.recentImages || []) : []);
  const attachments         = hasCurrentUploadContext ? currentAttachments : (useRecentContext ? (state.recentAttachments || []) : []);

  state.lastQuery       = query;
  state.lastImages      = images;
  state.lastAttachments = attachments;
  if (hasCurrentUploadContext) {
    state.recentImages      = currentImages;
    state.recentAttachments = currentAttachments;
  }

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

  try {
    if (state.streamMode) await sendStreaming(query, images, attachments);
    else                  await sendBatch(query, images, attachments);
  } finally {
    state._sendLock = false;
  }
}

function buildImagePayload(images) {
  return images.map(i => ({
    data:      i.base64,
    mime_type: i.file.type,
    filename:  i.file.name,
  }));
}

async function sendStreaming(query, images, attachments = []) {
  setLoading(true, true);
  const controller    = new AbortController();
  state.currentStream = controller;
  const aiDiv         = appendAIMsgStreaming();
  let fullText        = '';
  let sources         = [];
  let meta            = {};
  let fallbackAttempted = false;

  try {
    const body = {
      query,
      chat_id:          state.chatId,
      user:             state.user?.name || 'User',
      model:            state.selectedModel,
      role_mode:        state.roleMode,
      prompt_template:  state.promptTemplate,
      use_hybrid_search: true,
    };
    if (images.length      > 0) body.images      = buildImagePayload(images);
    if (attachments.length > 0) body.attachments = attachments;

    const res = await fetch(apiUrl('/api/stream'), {
      method:  'POST',
      headers: getAuthHeaders(),
      body:    JSON.stringify(body),
      signal:  controller.signal,
    });

    if (res.status === 401) { handleAuthError(); throw new Error('Unauthorized'); }
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
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
          const data  = JSON.parse(raw);
          const token = data.token || data.text || data.content || '';
          if (token) { fullText += token; updateStreamBubble(aiDiv, fullText); }
          if (data.response || data.answer) {
            fullText = data.response || data.answer;
            sources  = data.sources || [];
            meta     = { ...meta, ...data };
            updateStreamBubble(aiDiv, fullText);
          }
          if (data.sources) sources = data.sources;
          if (data.done)    { sources = data.sources || sources; meta = { ...meta, ...data }; }
          if (data.error)   throw new Error(data.error);
        } catch (jsonErr) {
          if (raw && typeof raw === 'string' && raw.length < 2000) {
            try {
              const parsed = JSON.parse(raw);
              if (parsed && typeof parsed === 'object') {
                if (parsed.response) fullText += parsed.response;
                else if (parsed.token) fullText += parsed.token;
              } else if (typeof parsed === 'string') {
                fullText += parsed;
              }
            } catch {
              if (!raw.startsWith('{') && !raw.startsWith('[')) fullText += raw;
            }
            updateStreamBubble(aiDiv, fullText);
          }
        }
      }
    }

    if (!fullText.trim()) {
      aiDiv.remove();
      fallbackAttempted = true;
      await sendBatch(query, images, attachments);
      return;
    }

    finalizeStreamBubble(aiDiv, fullText, {
      sources,
      route:          meta.route          || 'stream',
      model:          meta.model          || state.selectedModel,
      usage:          meta.usage          || {},
      roleMode:       meta.role_mode      || state.roleMode,
      promptTemplate: meta.prompt_template || state.promptTemplate,
      retrieval:      meta.retrieval       || {},
    });
    saveMsgLocal(state.chatId, 'assistant', fullText);
    saveSessionAfterSend(query);

  } catch (err) {
    if (err.name === 'AbortError') {
      const cursor = aiDiv.querySelector('.streaming-cursor');
      if (cursor) cursor.remove();
      const bubble = aiDiv.querySelector('.bubble-ai');
      if (bubble && bubble.innerText.trim()) {
        const body = aiDiv.querySelector('.ai-body');
        if (body) body.appendChild(buildMetaRow(aiDiv.id, bubble.innerText, { sources: [], route: 'stream' }));
        saveMsgLocal(state.chatId, 'assistant', bubble.innerText);
        saveSessionAfterSend(query);
      }
   } else {
  console.error('Stream error:', err);

  if (!fallbackAttempted) {
    aiDiv.remove();
    fallbackAttempted = true;
    await sendBatch(query, images, attachments);
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

async function sendBatch(query, images, attachments = []) {
  setLoading(true, false);
  const typer = appendTyping();

  try {
    const body = {
      query,
      chat_id:          state.chatId,
      user:             state.user?.name || 'User',
      model:            state.selectedModel,
      role_mode:        state.roleMode,
      prompt_template:  state.promptTemplate,
      use_hybrid_search: true,
    };
    if (images.length      > 0) body.images      = buildImagePayload(images);
    if (attachments.length > 0) body.attachments = attachments;

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

    const data    = await res.json();
    typer.remove();

    const answer  = data.response || data.answer || data.message || data.content || '';
    const sources = data.sources  || data.citations || [];
    const route   = data.route    || null;

    if (!answer) throw new Error('Empty response from server');

    appendAIMsg(answer, {
      sources,
      route,
      model:          data.model          || state.selectedModel,
      usage:          data.usage          || {},
      roleMode:       data.role_mode      || state.roleMode,
      promptTemplate: data.prompt_template || state.promptTemplate,
      retrieval:      data.retrieval       || {},
    });
    saveMsgLocal(state.chatId, 'assistant', answer);
    saveSessionAfterSend(query);

  } catch (err) {
    if (typer && typer.remove) typer.remove();
    console.error('Batch error:', err);
    appendAIMsg(`⚠️ **Error:** ${escHtml(err.message)}\n\nPlease check if the backend is reachable at \`${apiDisplayBase()}\``, { sources: [], route: 'error' });
  } finally {
    setLoading(false, false);
    scrollDown();
  }
}

function saveSessionAfterSend(query) {
  const title = query.length > 45 ? query.slice(0, 42) + '…' : query;
  saveSessionLocal(state.chatId, title);
  const sc = $('shareChatBtn');
  if (sc) sc.style.display = 'flex';
}

function appendUserMsg(text, timestamp, images) {
  const mi = document.getElementById('messagesInner');
  if (!mi) return;
  const div     = document.createElement('div');
  div.className = 'msg-group msg-user';
  div.id        = 'user-' + Date.now();
  const imgs    = (images || [])
    .filter(img => img.previewUrl)
    .map(img => `<img class="msg-img" src="${img.previewUrl}" alt="attachment" onclick="openImagePreview('${img.previewUrl}')"/>`)
    .join('');
  div.innerHTML = `
    <div class="bubble-user">
      ${imgs}
      ${text ? `<div class="user-msg-text">${escHtml(text)}</div>` : ''}
    </div>
    <div class="msg-meta">
      <span class="msg-time">${fmtTime(timestamp)}</span>
      <button class="action-btn" onclick="copyUserMsgText(this,'${div.id}')">Copy</button>
      <button class="action-btn" onclick="editUserMsg('${div.id}')">Edit</button>
    </div>
  `;
  mi.appendChild(div);
  scrollDown();
}

function copyUserMsgText(btn, msgId) {
  const el = document.getElementById(msgId)?.querySelector('.user-msg-text');
  if (!el) return;
  navigator.clipboard.writeText(el.innerText).then(() => {
    btn.classList.add('ok');
    btn.textContent = '✓ Copied';
    setTimeout(() => { btn.classList.remove('ok'); btn.textContent = 'Copy'; }, 1800);
  }).catch(() => showToast('Copy failed'));
}

function editUserMsg(msgId) {
  const el    = document.getElementById(msgId)?.querySelector('.user-msg-text');
  const input = $('userInput');
  if (!el || !input) return;
  input.value = el.innerText;
  growInput(input);
  input.focus();
  input.selectionStart = input.selectionEnd = input.value.length;
}

function openImagePreview(src) {
  const overlay = $('imagePreviewOverlay');
  const image   = $('imagePreviewLarge');
  if (!overlay || !image || !src) return;
  image.src              = src;
  overlay.style.display  = 'flex';
}

function closeImagePreview() {
  const overlay = $('imagePreviewOverlay');
  const image   = $('imagePreviewLarge');
  if (overlay) overlay.style.display = 'none';
  if (image)   image.src             = '';
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
      <div class="bubble-ai thinking-bubble" id="bubble-${id}">
        <span class="thinking-label">Thinking</span>
        <span class="thinking-dots"><span class="t-dot"></span><span class="t-dot"></span><span class="t-dot"></span></span>
      </div>
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
  bubble.classList.remove('thinking-bubble');
  bubble.innerHTML = renderMd(text) + '<span class="streaming-cursor"></span>';
  scrollDown();
}

function finalizeStreamBubble(div, text, meta) {
  const bubble = div.querySelector('.bubble-ai');
  if (bubble) { bubble.classList.remove('thinking-bubble'); bubble.innerHTML = renderMd(text); }
  const body = div.querySelector('.ai-body');
  if (body) {
    body.appendChild(buildMetaRow(div.id, text, meta));
    if (meta.sources?.length) body.appendChild(buildSources(meta.sources));
  }
}

function appendAIMsg(text, meta = {}, timestamp) {
  const id      = 'msg-' + Date.now();
  const div     = document.createElement('div');
  div.className = 'msg-group msg-ai';
  div.id        = id;

  const body     = document.createElement('div');
  body.className = 'ai-body';

  const bubble     = document.createElement('div');
  bubble.className = 'bubble-ai';
  bubble.innerHTML = renderMd(text);
  body.appendChild(bubble);
  body.appendChild(buildMetaRow(id, text, meta, timestamp));
  if (meta.sources?.length) body.appendChild(buildSources(meta.sources));

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
    <button class="action-btn speak-btn" data-msg-id="${msgId}" onclick="speakText(document.getElementById('${msgId}')?.querySelector('.bubble-ai')?.innerText||'','${msgId}')">
      <svg width="11" height="11" viewBox="0 0 24 24" fill="none">
        <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        <path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
      </svg>
      <span class="speak-btn-label">Speak</span>
    </button>
    <div style="flex:1"></div>
    <button class="feedback-btn" onclick="giveFeedback(this,1)"  title="Good">👍</button>
    <button class="feedback-btn" onclick="giveFeedback(this,-1)" title="Bad">👎</button>
  `;
  updateSpeakButtons();
  return row;
}

function buildSources(sources) {
  const bar     = document.createElement('div');
  bar.className = 'sources-bar';
  uniqueSources(sources).forEach(src => {
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

function openCurrentChatShare() {
  if (!state.chatId) { showToast('Open a chat first.'); return; }
  const messages = Array.from(document.querySelectorAll('.msg-group')).map(node => node.innerText.trim()).filter(Boolean);
  if (!messages.length) { showToast('No messages to share yet.'); return; }
  const sessions = JSON.parse(localStorage.getItem(sessionsStorageKey()) || '[]');
  const active   = sessions.find(session => session.id === state.chatId);
  state.shareText = messages.join('\n\n');
  const sp = $('sharePreview');
  const so = $('shareModalOverlay');
  if (sp) {
    const title   = active?.title || 'Current conversation';
    const preview = state.shareText.slice(0, 420) + (state.shareText.length > 420 ? '…' : '');
    sp.innerHTML  = `<strong>${escHtml(title)}</strong><br><br>${escHtml(preview).replace(/\n/g, '<br>')}`;
  }
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
  } else if (platform === 'linkedin') {
    window.open(`https://www.linkedin.com/sharing/share-offsite/?url=${encodeURIComponent(window.location.href)}`, '_blank');
  } else if (platform === 'reddit') {
    window.open(`https://www.reddit.com/submit?url=${encodeURIComponent(window.location.href)}&title=${enc}`, '_blank');
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
  if (!state.lastQuery || state.loading || state._sendLock) return;
  const el = document.getElementById(msgId);
  if (el) el.remove();
  if (state.streamMode) await sendStreaming(state.lastQuery, state.lastImages || [], state.lastAttachments || []);
  else                  await sendBatch(state.lastQuery, state.lastImages || [], state.lastAttachments || []);
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
    const res = await fetch(apiUrl('/api/analytics'), {
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

function downloadCurrentChat() {
  closeChatMenu();
  exportChat();
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
  const el       = document.createElement('div');
  el.className   = 'toast';
  el.textContent = msg;
  el.dataset.msg = msg;
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
    closeSettingsModal();
    closeHelpModal();
    closeChatMenu();
    closeDeleteChatModal();
    closeMobileSidebar();
  }
});
window.doLogin = doLogin;
window.doSignup = doSignup;
window.switchTab = switchTab;
window.continueAsGuest = continueAsGuest;
window.openForgotPasswordModal = openForgotPasswordModal;
