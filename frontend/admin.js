'use strict';

const API_BASE = window.location.origin;

let createForm, newName, newCredits, newCodeResult, newCodeValue, copyCodeBtn;
let usersTbody, refreshBtn, logoutBtn, errorBanner, errorMessage, errorDismiss;

document.addEventListener('DOMContentLoaded', async () => {
  createForm     = document.getElementById('create-form');
  newName        = document.getElementById('new-name');
  newCredits     = document.getElementById('new-credits');
  newCodeResult  = document.getElementById('new-code-result');
  newCodeValue   = document.getElementById('new-code-value');
  copyCodeBtn    = document.getElementById('copy-code-btn');
  usersTbody     = document.getElementById('users-tbody');
  refreshBtn     = document.getElementById('refresh-btn');
  logoutBtn      = document.getElementById('logout-btn');
  errorBanner    = document.getElementById('error-banner');
  errorMessage   = document.getElementById('error-message');
  errorDismiss   = document.getElementById('error-dismiss');

  // Vérifier que l'utilisateur est admin
  const me = await fetchMe();
  if (!me) { window.location.href = 'app.html'; return; }
  if (!me.is_admin) {
    showError('Accès réservé à l\'administrateur.');
    setTimeout(() => { window.location.href = 'app.html'; }, 2000);
    return;
  }

  // Listeners
  createForm.addEventListener('submit', handleCreateUser);
  copyCodeBtn.addEventListener('click', copyNewCode);
  refreshBtn.addEventListener('click', loadUsers);
  logoutBtn.addEventListener('click', handleLogout);
  errorDismiss.addEventListener('click', () => errorBanner.classList.add('hidden'));

  // Chargement initial
  loadUsers();
});


async function fetchMe() {
  try {
    const res = await fetch(`${API_BASE}/auth/me`, { credentials: 'include' });
    if (!res.ok) return null;
    return await res.json();
  } catch (_) { return null; }
}


async function loadUsers() {
  usersTbody.innerHTML = '<tr><td colspan="6" class="loading">Chargement...</td></tr>';

  try {
    const res = await fetch(`${API_BASE}/admin/users`, { credentials: 'include' });
    if (!res.ok) throw new Error(`Erreur ${res.status}`);
    const users = await res.json();
    renderUsers(users);
  } catch (err) {
    usersTbody.innerHTML = `<tr><td colspan="6" class="empty">Erreur : ${escapeHtml(err.message)}</td></tr>`;
  }
}


function renderUsers(users) {
  if (users.length === 0) {
    usersTbody.innerHTML = '<tr><td colspan="6" class="empty">Aucun utilisateur</td></tr>';
    return;
  }

  usersTbody.innerHTML = '';
  for (const u of users) {
    const tr = document.createElement('tr');

    const lowCredits = !u.is_admin && u.credits < 10;
    const adminBadge = u.is_admin ? '<span class="badge-admin">ADMIN</span>' : '';
    const credits    = u.is_admin ? '∞' : u.credits;

    tr.innerHTML = `
      <td>${escapeHtml(u.name || '—')}${adminBadge}</td>
      <td class="col-code">${escapeHtml(u.code)}</td>
      <td class="col-credits ${lowCredits ? 'low' : ''}">${credits}</td>
      <td>${formatDate(u.created_at)}</td>
      <td>${u.last_used_at ? formatDate(u.last_used_at) : '—'}</td>
      <td class="actions"></td>
    `;

    const actions = tr.querySelector('.actions');

    if (!u.is_admin) {
      const addBtn = document.createElement('button');
      addBtn.className = 'btn-action';
      addBtn.textContent = '+ Crédits';
      addBtn.onclick = () => promptAddCredits(u);
      actions.appendChild(addBtn);

      const delBtn = document.createElement('button');
      delBtn.className = 'btn-action danger';
      delBtn.textContent = 'Supprimer';
      delBtn.onclick = () => promptDeleteUser(u);
      actions.appendChild(delBtn);
    } else {
      actions.textContent = '—';
    }

    usersTbody.appendChild(tr);
  }
}


async function handleCreateUser(e) {
  e.preventDefault();
  const name    = newName.value.trim() || null;
  const credits = parseInt(newCredits.value, 10) || 0;

  const submitBtn = createForm.querySelector('button[type="submit"]');
  submitBtn.disabled    = true;
  submitBtn.textContent = 'Création...';

  try {
    const res = await fetch(`${API_BASE}/admin/users`, {
      method:      'POST',
      credentials: 'include',
      headers:     { 'Content-Type': 'application/json' },
      body:        JSON.stringify({ name, credits }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erreur ${res.status}`);
    }
    const user = await res.json();
    newCodeValue.textContent = user.code;
    newCodeResult.classList.remove('hidden');
    newName.value    = '';
    newCredits.value = '30';
    loadUsers();
  } catch (err) {
    showError(err.message);
  } finally {
    submitBtn.disabled    = false;
    submitBtn.textContent = 'Générer un code';
  }
}


async function promptAddCredits(user) {
  const input = window.prompt(
    `Combien de crédits ajouter à ${user.name || user.code} ?\n` +
    `Crédits actuels : ${user.credits}\n` +
    `(Entrez un nombre négatif pour retirer des crédits)`,
    '10'
  );
  if (input === null) return;
  const delta = parseInt(input, 10);
  if (isNaN(delta) || delta === 0) return;

  try {
    const res = await fetch(`${API_BASE}/admin/users/${user.id}/credits`, {
      method:      'POST',
      credentials: 'include',
      headers:     { 'Content-Type': 'application/json' },
      body:        JSON.stringify({ credits: delta }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erreur ${res.status}`);
    }
    loadUsers();
  } catch (err) {
    showError(err.message);
  }
}


async function promptDeleteUser(user) {
  const ok = window.confirm(
    `Supprimer définitivement l'utilisateur "${user.name || user.code}" ?\n` +
    `Cette action est irréversible.`
  );
  if (!ok) return;

  try {
    const res = await fetch(`${API_BASE}/admin/users/${user.id}`, { method: 'DELETE', credentials: 'include' });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || `Erreur ${res.status}`);
    }
    loadUsers();
  } catch (err) {
    showError(err.message);
  }
}


async function handleLogout() {
  try { await fetch(`${API_BASE}/auth/logout`, { method: 'POST', credentials: 'include' }); } catch (_) {}
  window.location.href = 'index.html';  // redirige vers la home publique
}


function copyNewCode() {
  const code = newCodeValue.textContent;
  navigator.clipboard.writeText(code).then(() => {
    copyCodeBtn.textContent = '✓ Copié';
    setTimeout(() => { copyCodeBtn.textContent = 'Copier'; }, 2000);
  });
}


function showError(msg) {
  errorMessage.textContent = msg;
  errorBanner.classList.remove('hidden');
  errorBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}


function formatDate(timestamp) {
  if (!timestamp) return '—';
  const d = new Date(timestamp * 1000);
  const today = new Date();
  const isToday = d.toDateString() === today.toDateString();
  if (isToday) return `Aujourd'hui ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' });
}


function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}
