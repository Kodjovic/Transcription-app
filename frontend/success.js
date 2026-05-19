// success.js — Page de succès post-paiement Chariow.
//
// Récupère le purchase_ref depuis l'URL, polle /payment/purchase/{ref}
// jusqu'à recevoir status = "paid" (code délivré) ou "failed", avec un
// timeout après ~2 minutes (le webhook peut arriver après quelques minutes
// — on ne bloque pas l'utilisateur).

(function () {
  'use strict';

  const API_BASE = window.location.origin;
  const POLL_INTERVAL_MS = 3000;
  const TIMEOUT_MS       = 120000;   // 2 min

  let pollHandle = null;
  let started    = 0;

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    const ref = new URLSearchParams(window.location.search).get('ref');

    if (!ref) {
      showState('state-not-found');
      return;
    }

    const refDisplay = document.getElementById('ref-display');
    if (refDisplay) refDisplay.textContent = ref;

    setupCopyButton();

    started = Date.now();
    pollOnce(ref);
    pollHandle = setInterval(() => pollOnce(ref), POLL_INTERVAL_MS);
  }

  async function pollOnce(ref) {
    try {
      const res = await fetch(`${API_BASE}/payment/purchase/${encodeURIComponent(ref)}`);

      if (res.status === 404) {
        stopPolling();
        showState('state-not-found');
        return;
      }

      if (!res.ok) {
        // erreur transitoire — on continue le polling
        return;
      }

      const data = await res.json();
      handleStatus(ref, data);

    } catch (_) {
      // erreur réseau — on retentera au prochain tick
    }

    if (Date.now() - started > TIMEOUT_MS) {
      stopPolling();
      showState('state-timeout');
    }
  }

  function handleStatus(ref, data) {
    switch (data.status) {

      case 'paid':
        stopPolling();
        showPaidState(data);
        break;

      case 'failed':
        stopPolling();
        showState('state-failed');
        break;

      case 'abandoned':
        stopPolling();
        showState('state-failed');
        break;

      case 'pending':
      default:
        // garde l'état pending, on continue le polling
        break;
    }
  }

  function showPaidState(data) {
    document.getElementById('user-code').textContent           = data.user_code || '—';
    document.getElementById('credits-granted').textContent     = data.credits_granted ?? '—';
    document.getElementById('customer-email-display').textContent = data.customer_email || '';
    showState('state-paid');
  }

  function showState(id) {
    ['state-pending', 'state-paid', 'state-failed', 'state-timeout', 'state-not-found']
      .forEach((s) => {
        const el = document.getElementById(s);
        if (el) el.classList.toggle('hidden', s !== id);
      });
  }

  function stopPolling() {
    if (pollHandle) {
      clearInterval(pollHandle);
      pollHandle = null;
    }
  }

  function setupCopyButton() {
    const btn  = document.getElementById('copy-code-btn');
    const lbl  = document.getElementById('copy-code-label');
    const code = document.getElementById('user-code');
    if (!btn || !code) return;

    btn.addEventListener('click', async () => {
      const text = code.textContent.trim();
      if (!text || text === '—') return;
      try {
        await navigator.clipboard.writeText(text);
        lbl.textContent = 'Copié !';
        setTimeout(() => { lbl.textContent = 'Copier'; }, 1800);
      } catch (_) {
        // fallback : sélection visuelle
        const range = document.createRange();
        range.selectNode(code);
        const sel = window.getSelection();
        sel.removeAllRanges();
        sel.addRange(range);
      }
    });
  }
})();
