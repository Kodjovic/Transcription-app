'use strict';

// ─── Config ────────────────────────────────────────────────
// API en production (vide = relatif à l'origine actuelle, utile en dev)
const API_BASE = 'https://apitranscription.mapharmadegarde.com';
// Phase de test : audio uniquement
const ALLOWED_EXTENSIONS = new Set([
  'mp3', 'wav', 'm4a', 'ogg', 'flac', 'aac',
]);
const VIDEO_EXTENSIONS = new Set([
  'mp4', 'mkv', 'avi', 'mov', 'webm',
]);

const TIMEOUT_SIMPLE    = 20 * 60 * 1000;   // 20 min (Cohere)
const TIMEOUT_DIARIZE   = 45 * 60 * 1000;   // 45 min (Whisper + PyAnnote local)

// ─── État global ───────────────────────────────────────────
const state = {
  file:        null,
  youtubeUrl:  '',
  inputMode:   'file',
  result:      null,
  uploading:   false,
  diarize:     false,
  user:        null,
  config:      { default_credits: 30, cost_simple: 5, cost_diarize: 10, admin_contact: '' },
};

// ─── Références DOM ────────────────────────────────────────
let dropZone, fileInput, browseBtn, languageSelect, transcribeBtn;
let diarizeToggle, modeLabelEl, diarizeHint;
let progressSection, progressBar, progressLabel, progressPct, progressDetail;
let uploadSection, resultsSection;
let transcriptOutput, copyBtn;
let metaLanguage, metaDuration, metaChunks, metaSpeakers;
let exportTxtBtn, exportSrtBtn, exportDocxBtn;
let newTranscriptionBtn;
let errorBanner, errorMessage, errorDismiss;
let viewTabs, tabTextPanel, tabSpeakersPanel, speakersView;
let inputTabs, panelFile, panelUrl, urlInput, urlPasteBtn, urlMeta;
let loginOverlay, loginForm, loginCode, loginSubmit, loginError, loginContact;
let userWidget, creditsBadge, creditsCount, adminLink, logoutBtn;

document.addEventListener('DOMContentLoaded', () => {

  dropZone            = document.getElementById('drop-zone');
  fileInput           = document.getElementById('file-input');
  browseBtn           = document.getElementById('browse-btn');
  languageSelect      = document.getElementById('language-select');
  transcribeBtn       = document.getElementById('transcribe-btn');
  diarizeToggle       = document.getElementById('diarize-toggle');
  modeLabelEl         = document.getElementById('mode-label');
  diarizeHint         = document.getElementById('diarize-hint');
  uploadSection       = document.getElementById('upload-section');
  progressSection     = document.getElementById('progress-section');
  resultsSection      = document.getElementById('results-section');
  progressBar         = document.getElementById('progress-bar');
  progressLabel       = document.getElementById('progress-label');
  progressPct         = document.getElementById('progress-pct');
  progressDetail      = document.getElementById('progress-detail');
  transcriptOutput    = document.getElementById('transcript-output');
  copyBtn             = document.getElementById('copy-btn');
  metaLanguage        = document.getElementById('meta-language');
  metaDuration        = document.getElementById('meta-duration');
  metaChunks          = document.getElementById('meta-chunks');
  metaSpeakers        = document.getElementById('meta-speakers');
  exportTxtBtn        = document.getElementById('export-txt');
  exportSrtBtn        = document.getElementById('export-srt');
  exportDocxBtn       = document.getElementById('export-docx');
  newTranscriptionBtn = document.getElementById('new-transcription-btn');
  errorBanner         = document.getElementById('error-banner');
  errorMessage        = document.getElementById('error-message');
  errorDismiss        = document.getElementById('error-dismiss');
  viewTabs            = document.getElementById('view-tabs');
  tabTextPanel        = document.getElementById('tab-text');
  tabSpeakersPanel    = document.getElementById('tab-speakers');
  speakersView        = document.getElementById('speakers-view');
  panelFile           = document.getElementById('panel-file');
  panelUrl            = document.getElementById('panel-url');
  urlInput            = document.getElementById('url-input');
  urlPasteBtn         = document.getElementById('url-paste-btn');
  urlMeta             = document.getElementById('url-meta');

  // Auth / crédits
  loginOverlay        = document.getElementById('login-overlay');
  loginForm           = document.getElementById('login-form');
  loginCode           = document.getElementById('login-code');
  loginSubmit         = document.getElementById('login-submit');
  loginError          = document.getElementById('login-error');
  loginContact        = document.getElementById('login-contact');
  userWidget          = document.getElementById('user-widget');
  creditsBadge        = document.getElementById('credits-badge');
  creditsCount        = document.getElementById('credits-count');
  adminLink           = document.getElementById('admin-link');
  logoutBtn           = document.getElementById('logout-btn');

  // Auth — chargement initial
  loadPublicConfig().then(checkAuth);

  loginForm.addEventListener('submit', handleLogin);
  logoutBtn.addEventListener('click', handleLogout);

  // ── Onglets Fichier / URL ────────────────────────────────
  document.querySelectorAll('.input-tab').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.input-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      state.inputMode = btn.dataset.input;
      panelFile.classList.toggle('hidden', state.inputMode !== 'file');
      panelUrl.classList.toggle('hidden',  state.inputMode !== 'url');
      updateTranscribeBtn();
    });
  });

  // ── URL input ────────────────────────────────────────────
  urlInput.addEventListener('input', () => {
    state.youtubeUrl = urlInput.value.trim();
    updateTranscribeBtn();
    urlMeta.classList.add('hidden');
  });

  urlPasteBtn.addEventListener('click', async () => {
    try {
      const text = await navigator.clipboard.readText();
      urlInput.value   = text.trim();
      state.youtubeUrl = urlInput.value;
      updateTranscribeBtn();
    } catch (_) {
      urlInput.focus();
    }
  });

  // ── Drag & drop ──────────────────────────────────────────
  dropZone.addEventListener('dragover',  onDragOver);
  dropZone.addEventListener('dragleave', onDragLeave);
  dropZone.addEventListener('drop',      onDrop);
  dropZone.addEventListener('click', (e) => {
    if (e.target === browseBtn) return;
    fileInput.click();
  });
  dropZone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInput.click(); }
  });
  browseBtn.addEventListener('click', (e) => { e.stopPropagation(); fileInput.click(); });
  fileInput.addEventListener('change', () => { if (fileInput.files[0]) handleFileSelect(fileInput.files[0]); });

  // ── Toggle diarisation ───────────────────────────────────
  diarizeToggle.addEventListener('change', () => {
    state.diarize = diarizeToggle.checked;
    if (state.diarize) {
      modeLabelEl.textContent = '🎙️ Diarisation activée';
      diarizeHint.textContent = 'Identification des interlocuteurs — traitement local (peut prendre plusieurs minutes)';
    } else {
      modeLabelEl.textContent = 'Transcription simple';
      diarizeHint.textContent = 'Activez pour identifier les interlocuteurs & horodater chaque prise de parole';
    }
  });

  // ── Onglets vue résultat ─────────────────────────────────
  viewTabs.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      viewTabs.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      const tab = btn.dataset.tab;
      tabTextPanel.classList.toggle('hidden',     tab !== 'text');
      tabSpeakersPanel.classList.toggle('hidden', tab !== 'speakers');
    });
  });

  // ── Autres boutons ───────────────────────────────────────
  transcribeBtn.addEventListener('click', handleTranscribe);
  copyBtn.addEventListener('click', handleCopy);
  exportTxtBtn.addEventListener('click',  () => handleExport('txt'));
  exportSrtBtn.addEventListener('click',  () => handleExport('srt'));
  exportDocxBtn.addEventListener('click', () => handleExport('docx'));
  newTranscriptionBtn.addEventListener('click', resetApp);
  errorDismiss.addEventListener('click', () => errorBanner.classList.add('hidden'));
});


// ─── Drag & Drop ───────────────────────────────────────────
function onDragOver(e) {
  e.preventDefault();
  dropZone.classList.add('drag-over');
}
function onDragLeave(e) {
  if (!dropZone.contains(e.relatedTarget)) dropZone.classList.remove('drag-over');
}
function onDrop(e) {
  e.preventDefault();
  dropZone.classList.remove('drag-over');
  const file = e.dataTransfer.files[0];
  if (file) handleFileSelect(file);
}


// ─── Activation du bouton Transcrire ──────────────────────
function updateTranscribeBtn() {
  if (state.inputMode === 'file') {
    transcribeBtn.disabled = !state.file;
  } else {
    transcribeBtn.disabled = !state.youtubeUrl.startsWith('http');
  }
}


// ─── Sélection de fichier ──────────────────────────────────
function handleFileSelect(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (VIDEO_EXTENSIONS.has(ext)) {
    showError("Audio requis pour la phase de test. Si vous avez une vidéo, extrayez d'abord la piste audio.");
    return;
  }
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    showError(`Format non supporté : .${ext}. Formats acceptés : ${[...ALLOWED_EXTENSIONS].join(', ')}`);
    return;
  }
  state.file = file;
  hideError();
  dropZone.classList.add('has-file');
  dropZone.querySelector('.drop-title').textContent = `${file.name}  (${formatBytes(file.size)})`;
  dropZone.querySelector('.drop-sub').textContent   = 'Fichier sélectionné ✓';
  updateTranscribeBtn();
}


// ─── Transcription principale ──────────────────────────────
async function handleTranscribe() {
  if (state.uploading) return;
  if (state.inputMode === 'file' && !state.file) return;
  if (state.inputMode === 'url'  && !state.youtubeUrl) return;

  // Vérification crédits côté client (UX)
  const cost = state.diarize ? state.config.cost_diarize : state.config.cost_simple;
  if (state.user && !state.user.is_admin && state.user.credits < cost) {
    showError(creditsExhaustedMessage(cost));
    return;
  }

  state.uploading = true;
  hideError();
  showSection('progress');

  const isUrl     = state.inputMode === 'url';
  const endpoint  = isUrl ? `${API_BASE}/transcribe-url` : `${API_BASE}/transcribe`;
  const formData  = new FormData();

  if (isUrl) {
    formData.append('url',      state.youtubeUrl);
  } else {
    formData.append('file',     state.file);
  }
  formData.append('language', languageSelect.value);
  formData.append('diarize',  state.diarize ? 'true' : 'false');

  const timeoutMs = state.diarize ? TIMEOUT_DIARIZE : TIMEOUT_SIMPLE;

  const steps = state.diarize
    ? [
        [15,  'Envoi du fichier...'],
        [30,  'Extraction audio...'],
        [45,  'Diarisation PyAnnote... (peut prendre 2-5 min)'],
        [70,  'Transcription Whisper... (peut prendre 2-5 min)'],
        [88,  'Assemblage des résultats...'],
      ]
    : [
        [15,  'Envoi du fichier...'],
        [35,  'Traitement audio...'],
        [55,  'Transcription Cohere...'],
        [80,  'Finalisation...'],
      ];

  try {
    setProgress(10, 'Envoi du fichier au serveur...');
    if (state.diarize) showProgressDetail('⚠️ Mode diarisation : le traitement local peut prendre plusieurs minutes selon la durée du fichier.');

    // Progression simulée pendant l'attente
    let stepIdx = 0;
    let currentPct = 10;
    const progressTimer = setInterval(() => {
      if (stepIdx < steps.length) {
        const [pct, label] = steps[stepIdx++];
        currentPct = pct;
        setProgress(pct, label);
      } else {
        // Une fois les étapes finies, on continue à grimper lentement vers 90%
        // pour montrer que ça travaille toujours (Cohere prend son temps)
        if (currentPct < 90) {
          currentPct += 0.5;
          setProgress(currentPct, 'Transcription en cours... (peut prendre jusqu\'à 1 min selon la durée)');
        }
      }
    }, state.diarize ? 12000 : 3000);

    const controller = new AbortController();
    const timeoutId  = setTimeout(() => controller.abort(), timeoutMs);

    const response = await fetch(endpoint, {
      method:      'POST',
      body:        formData,
      credentials: 'include',
      signal:      controller.signal,
    });

    clearTimeout(timeoutId);
    clearInterval(progressTimer);
    hideProgressDetail();
    setProgress(92, 'Finalisation...');

    if (!response.ok) {
      let errMsg = `Erreur serveur (${response.status})`;
      try {
        const parsed = await response.json();
        errMsg = parsed.detail || parsed.error || errMsg;
      } catch (_) {}

      // Session expirée
      if (response.status === 401) {
        state.user = null;
        showLogin();
        throw new Error('Session expirée. Veuillez vous reconnecter.');
      }

      // Crédits insuffisants
      if (response.status === 402) {
        await refreshUser();
        throw new Error(`${errMsg} ${contactLine()}`);
      }

      throw new Error(errMsg);
    }

    const data = await response.json();

    state.result = data;

    // Mettre à jour les crédits affichés après succès
    if (data.credits_charged) {
      await refreshUser();
    }

    setProgress(100, 'Terminé !');
    setTimeout(() => displayResults(data), 400);

  } catch (err) {
    if (err.name === 'AbortError') {
      showError('Délai dépassé — le fichier est trop long ou le serveur ne répond pas.');
    } else {
      showError(err.message || 'Une erreur est survenue. Veuillez réessayer.');
    }
    hideProgressDetail();
    showSection('upload');
    state.uploading = false;
  }
}


// ─── Affichage des résultats ───────────────────────────────
function displayResults(data) {
  const langNames = {
    fr: 'Français', en: 'English',   es: 'Español',  it: 'Italiano',
    de: 'Deutsch',  pt: 'Português', ja: '日本語',    zh: '中文',
    ar: 'العربية',  ru: 'Русский',   ko: '한국어',    nl: 'Nederlands', pl: 'Polski',
  };

  transcriptOutput.value = data.text || '';

  const lang = data.language_detected || 'unknown';
  metaLanguage.textContent = `🌐 ${langNames[lang] || lang.toUpperCase()}`;
  metaDuration.textContent = `⏱ ${formatDuration(data.duration_seconds || 0)}`;

  const speakers = data.speakers || [];
  if (speakers.length > 0) {
    metaSpeakers.textContent = `🎙️ ${speakers.length} interlocuteur${speakers.length > 1 ? 's' : ''}`;
    metaSpeakers.classList.remove('hidden');
  }

  if (data.diarized && data.segments && data.segments.some(s => s.speaker)) {
    viewTabs.classList.remove('hidden');
    renderSpeakersView(data.segments);
  } else {
    viewTabs.classList.add('hidden');
  }

  viewTabs.querySelectorAll('.tab-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === 'text');
  });
  tabTextPanel.classList.remove('hidden');
  tabSpeakersPanel.classList.add('hidden');

  showSection('results');
  state.uploading = false;
}


// ─── Vue interlocuteurs ────────────────────────────────────
function renderSpeakersView(segments) {
  speakersView.innerHTML = '';

  const speakerColorMap = {};
  let colorIdx = 0;

  segments.forEach((seg) => {
    if (!seg.speaker) return;

    const speaker = seg.speaker;
    if (!(speaker in speakerColorMap)) {
      speakerColorMap[speaker] = colorIdx++ % 6;
    }

    const entry  = document.createElement('div');
    entry.className = 'speaker-entry';

    const ts = document.createElement('span');
    ts.className   = 'speaker-ts';
    ts.textContent = formatTimestamp(seg.start);

    const badge = document.createElement('span');
    badge.className = `speaker-badge spk-color-${speakerColorMap[speaker]}`;
    badge.textContent = `🎙️ ${speaker}`;

    const text = document.createElement('span');
    text.className   = 'speaker-text';
    text.textContent = seg.text;

    entry.appendChild(ts);
    entry.appendChild(badge);
    entry.appendChild(text);
    speakersView.appendChild(entry);
  });
}


// ─── Export ────────────────────────────────────────────────
function handleExport(format) {
  if (!state.result) return;

  if (format === 'txt') {
    downloadText(state.result.exports.txt, 'transcription.txt', 'text/plain;charset=utf-8');

  } else if (format === 'srt') {
    downloadText(state.result.exports.srt, 'transcription.srt', 'text/plain;charset=utf-8');

  } else if (format === 'docx') {
    exportDocxBtn.disabled     = true;
    exportDocxBtn.textContent  = 'Génération...';

    fetch(`${API_BASE}/export/docx`, {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text:             state.result.text,
        language:         state.result.language_detected,
        duration_seconds: state.result.duration_seconds,
        segments:         state.result.segments || [],
      }),
    })
    .then((res) => { if (!res.ok) throw new Error(`Erreur ${res.status}`); return res.blob(); })
    .then((blob) => {
      const url = URL.createObjectURL(blob);
      const a   = document.createElement('a');
      a.href     = url;
      a.download = 'transcription.docx';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    })
    .catch((err) => showError(`Export Word échoué : ${err.message}`))
    .finally(() => {
      exportDocxBtn.disabled    = false;
      exportDocxBtn.innerHTML   = '<span class="export-icon">DOC</span> Word (.docx)';
    });
  }
}

function downloadText(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click();
  document.body.removeChild(a); URL.revokeObjectURL(url);
}


// ─── Copier ────────────────────────────────────────────────
function handleCopy() {
  const text = transcriptOutput.value;
  if (!text) return;
  navigator.clipboard.writeText(text).then(() => {
    copyBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;
    setTimeout(() => {
      copyBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`;
    }, 2000);
  });
}


// ─── Auth ──────────────────────────────────────────────────
async function loadPublicConfig() {
  try {
    const res = await fetch(`${API_BASE}/config`);
    if (res.ok) state.config = await res.json();
  } catch (_) { /* on garde les valeurs par défaut */ }

  // Mise à jour du lien "Contactez l'administrateur" sur la page login
  if (loginContact && state.config.admin_contact) {
    loginContact.innerHTML = `Contactez l'administrateur : <a href="${asContactHref(state.config.admin_contact)}">${escapeHtml(state.config.admin_contact)}</a>`;
  }
}

async function checkAuth() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    if (res.status === 401) { showLogin(); return; }
    if (!res.ok) { showLogin(); return; }
    state.user = await res.json();
    showApp();
  } catch (_) {
    showLogin();
  }
}

async function refreshUser() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    if (res.ok) {
      state.user = await res.json();
      updateCreditsDisplay();
    }
  } catch (_) { /* silencieux */ }
}

function showLogin() {
  loginOverlay.classList.remove('hidden');
  userWidget.classList.add('hidden');
  loginCode.focus();
}

function showApp() {
  loginOverlay.classList.add('hidden');
  userWidget.classList.remove('hidden');
  updateCreditsDisplay();
  adminLink.classList.toggle('hidden', !state.user || !state.user.is_admin);
}

function updateCreditsDisplay() {
  if (!state.user) return;
  if (state.user.is_admin) {
    creditsCount.textContent = '∞';
    creditsBadge.classList.remove('low');
  } else {
    creditsCount.textContent = state.user.credits;
    const lowThreshold = state.config.cost_diarize || 10;
    creditsBadge.classList.toggle('low', state.user.credits < lowThreshold);
  }
}

async function handleLogin(e) {
  e.preventDefault();
  const code = loginCode.value.trim().toUpperCase();
  if (!code) return;

  loginError.classList.add('hidden');
  loginSubmit.disabled = true;
  loginSubmit.textContent = 'Connexion...';

  try {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method:      'POST',
      credentials: 'include',
      headers:     { 'Content-Type': 'application/json' },
      body:        JSON.stringify({ code }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      loginError.textContent = data.detail || 'Code invalide';
      loginError.classList.remove('hidden');
      return;
    }
    state.user = await res.json();
    loginCode.value = '';
    showApp();
  } catch (err) {
    loginError.textContent = err.message || 'Erreur de connexion';
    loginError.classList.remove('hidden');
  } finally {
    loginSubmit.disabled = false;
    loginSubmit.textContent = 'Se connecter';
  }
}

async function handleLogout() {
  try {
    await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' });
  } catch (_) { /* on continue quand même */ }
  state.user = null;
  resetApp();
  showLogin();
}

function creditsExhaustedMessage(cost) {
  return `Vous n'avez plus assez de crédits (${cost} requis). ${contactLine()}`;
}

function contactLine() {
  const c = state.config.admin_contact;
  if (!c) return "Contactez l'administrateur pour recharger votre compte.";
  return `Contactez l'administrateur : ${c}`;
}

function asContactHref(c) {
  if (c.includes('@')) return `mailto:${c}`;
  if (c.startsWith('http')) return c;
  return '#';
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}


// ─── Helpers UI ────────────────────────────────────────────
function showSection(name) {
  uploadSection.classList.toggle('hidden',   name !== 'upload');
  progressSection.classList.toggle('hidden', name !== 'progress');
  resultsSection.classList.toggle('hidden',  name !== 'results');
}

function setProgress(pct, label) {
  pct = Math.min(100, Math.max(0, Math.round(pct)));
  progressBar.style.width    = `${pct}%`;
  progressLabel.textContent  = label;
  progressPct.textContent    = `${pct}%`;
}

function showProgressDetail(msg) {
  progressDetail.textContent = msg;
  progressDetail.classList.remove('hidden');
}

function hideProgressDetail() {
  progressDetail.classList.add('hidden');
}

function showError(message) {
  errorMessage.textContent = message;
  errorBanner.classList.remove('hidden');
  errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function hideError() {
  errorBanner.classList.add('hidden');
}

function resetApp() {
  state.file       = null;
  state.youtubeUrl = '';
  state.result     = null;
  state.uploading  = false;
  fileInput.value  = '';
  urlInput.value   = '';
  urlMeta.classList.add('hidden');
  transcriptOutput.value = '';
  transcribeBtn.disabled = true;
  dropZone.classList.remove('has-file', 'drag-over');
  dropZone.querySelector('.drop-title').textContent = 'Glissez-déposez votre fichier ici';
  dropZone.querySelector('.drop-sub').textContent   = 'ou';
  metaChunks.classList.add('hidden');
  metaSpeakers.classList.add('hidden');
  viewTabs.classList.add('hidden');
  speakersView.innerHTML = '';
  hideError();
  showSection('upload');
}


// ─── Formatters ────────────────────────────────────────────
function formatBytes(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} Ko`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} Mo`;
}

function formatDuration(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${h}h ${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`;
  if (m > 0) return `${m}m ${s.toString().padStart(2, '0')}s`;
  return `${s}s`;
}

function formatTimestamp(seconds) {
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = Math.floor(seconds % 60);
  if (h > 0) return `${pad(h)}:${pad(m)}:${pad(s)}`;
  return `${pad(m)}:${pad(s)}`;
}

function pad(n) { return String(n).padStart(2, '0'); }
