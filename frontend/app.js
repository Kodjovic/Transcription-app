'use strict';

// ─── Config ────────────────────────────────────────────────
const API_BASE = 'http://localhost:8000';
const ALLOWED_EXTENSIONS = new Set([
  'mp3', 'wav', 'm4a', 'ogg', 'flac', 'aac',
  'mp4', 'mkv', 'avi', 'mov', 'webm',
]);

// Timeout : 3 min pour Cohere, 15 min pour la diarisation (modèles locaux = lents)
const TIMEOUT_SIMPLE    = 10 * 60 * 1000;   // 10 min (Cohere)
const TIMEOUT_DIARIZE   = 45 * 60 * 1000;   // 45 min (Whisper + PyAnnote local)

// ─── État global ───────────────────────────────────────────
const state = {
  file:        null,
  youtubeUrl:  '',
  inputMode:   'file',   // 'file' ou 'url'
  result:      null,
  uploading:   false,
  diarize:     false,
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

document.addEventListener('DOMContentLoaded', () => {

  // Récupération des éléments du DOM
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

  // Messages de progression adaptés au mode
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

    const xhr = new XMLHttpRequest();
    const uploadPromise = new Promise((resolve, reject) => {
      xhr.upload.addEventListener('progress', (e) => {
        if (e.lengthComputable) {
          setProgress(Math.round((e.loaded / e.total) * 15), 'Envoi du fichier...');
        }
      });
      xhr.addEventListener('load',    () => resolve(xhr));
      xhr.addEventListener('error',   () => reject(new Error('Erreur réseau — vérifiez que le serveur est démarré sur http://localhost:8000')));
      xhr.addEventListener('abort',   () => reject(new Error('Requête annulée')));
      xhr.addEventListener('timeout', () => reject(new Error('Délai dépassé — le fichier est trop long ou le serveur ne répond pas.')));
    });

    xhr.open('POST', endpoint);
    xhr.timeout = timeoutMs;
    xhr.send(formData);

    // Progression simulée pendant l'attente
    let stepIdx = 0;
    const progressTimer = setInterval(() => {
      if (stepIdx < steps.length) {
        const [pct, label] = steps[stepIdx++];
        setProgress(pct, label);
      }
    }, state.diarize ? 12000 : 4000);  // toutes les 12s en mode diarisation

    const xhrResult = await uploadPromise;
    clearInterval(progressTimer);
    hideProgressDetail();
    setProgress(92, 'Finalisation...');

    if (xhrResult.status < 200 || xhrResult.status >= 300) {
      let errMsg = `Erreur serveur (${xhrResult.status})`;
      try {
        const parsed = JSON.parse(xhrResult.responseText);
        errMsg = parsed.detail || parsed.error || errMsg;
      } catch (_) {}
      throw new Error(errMsg);
    }

    let data;
    try {
      data = JSON.parse(xhrResult.responseText);
    } catch (parseErr) {
      console.error('JSON parse error:', parseErr);
      throw new Error('Réponse invalide du serveur (erreur JSON)');
    }

    state.result = data;
    setProgress(100, 'Terminé !');
    setTimeout(() => displayResults(data), 400);

  } catch (err) {
    console.error('handleTranscribe error:', err);
    hideProgressDetail();
    showError(err.message || 'Une erreur est survenue. Veuillez réessayer.');
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

  // Texte principal (textarea)
  transcriptOutput.value = data.text || '';

  // Chips de métadonnées
  const lang = data.language_detected || 'unknown';
  metaLanguage.textContent = `🌐 ${langNames[lang] || lang.toUpperCase()}`;
  metaDuration.textContent = `⏱ ${formatDuration(data.duration_seconds || 0)}`;

  // Interlocuteurs détectés
  const speakers = data.speakers || [];
  if (speakers.length > 0) {
    metaSpeakers.textContent = `🎙️ ${speakers.length} interlocuteur${speakers.length > 1 ? 's' : ''}`;
    metaSpeakers.classList.remove('hidden');
  }

  // Onglets : afficher "Par interlocuteur" uniquement si diarisation
  if (data.diarized && data.segments && data.segments.some(s => s.speaker)) {
    viewTabs.classList.remove('hidden');
    renderSpeakersView(data.segments);
  } else {
    viewTabs.classList.add('hidden');
  }

  // Toujours commencer sur l'onglet "Texte brut"
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

  // Construire une map de couleur par locuteur
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
