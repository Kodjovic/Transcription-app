// pricing.js — Logique du modal de checkout Chariow (page pricing.html).
//
// Flux :
//   1. L'utilisateur clique sur "Choisir cette offre" (Standard ou Premium)
//   2. Le modal s'ouvre, pré-rempli avec le plan choisi
//   3. À la soumission → POST /payment/checkout
//   4. Si step == "payment" → redirection vers Chariow checkout_url
//   5. Si step == "completed" → redirection vers success.html
//   6. Si erreur → message inline dans le modal

(function () {
  'use strict';

  const API_BASE = window.location.origin;

  const PLAN_META = {
    standard: { label: 'Plan Standard', amount: 3000 },
    premium:  { label: 'Plan Premium',  amount: 5000 },
  };

  let dom = {};
  let planConfig = null;     // chargé depuis /payment/config
  let submitting = false;

  document.addEventListener('DOMContentLoaded', init);

  function init() {
    dom = {
      modal:       document.getElementById('checkout-modal'),
      closeBtn:    document.getElementById('checkout-close'),
      form:        document.getElementById('checkout-form'),
      planInput:   document.getElementById('checkout-plan'),
      planLabel:   document.getElementById('checkout-plan-label'),
      creditsLabel:document.getElementById('checkout-credits-label'),
      amount:      document.getElementById('checkout-amount'),
      firstName:   document.getElementById('ck-first-name'),
      lastName:    document.getElementById('ck-last-name'),
      email:       document.getElementById('ck-email'),
      country:     document.getElementById('ck-country'),
      phone:       document.getElementById('ck-phone'),
      error:       document.getElementById('checkout-error'),
      submitBtn:   document.getElementById('checkout-submit'),
      submitLabel: document.getElementById('checkout-submit-label'),
    };

    if (!dom.modal) return;

    // Boutons "Choisir cette offre"
    document.querySelectorAll('[data-plan]').forEach((btn) => {
      btn.addEventListener('click', () => openCheckout(btn.dataset.plan));
    });

    dom.closeBtn.addEventListener('click', closeCheckout);
    dom.modal.addEventListener('click', (e) => {
      if (e.target === dom.modal) closeCheckout();
    });
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !dom.modal.classList.contains('hidden')) closeCheckout();
    });

    dom.form.addEventListener('submit', handleSubmit);

    // Charger la config (montants, crédits) en arrière-plan
    fetchPaymentConfig();
  }

  async function fetchPaymentConfig() {
    try {
      const res = await fetch(`${API_BASE}/payment/config`);
      if (res.ok) {
        planConfig = await res.json();
      }
    } catch (_) { /* on continue avec les valeurs par défaut */ }
  }

  function openCheckout(planKey) {
    if (!PLAN_META[planKey]) return;

    const meta = PLAN_META[planKey];
    const cfg  = planConfig?.plans?.[planKey];
    const credits = cfg?.credits ?? '—';
    const amount  = cfg?.amount  ?? meta.amount;

    dom.planInput.value           = planKey;
    dom.planLabel.textContent     = meta.label;
    dom.creditsLabel.textContent  = `${credits} crédits`;
    dom.amount.textContent        = formatAmount(amount);

    hideError();
    dom.modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    setTimeout(() => dom.firstName.focus(), 50);
  }

  function closeCheckout() {
    if (submitting) return;
    dom.modal.classList.add('hidden');
    document.body.style.overflow = '';
  }

  async function handleSubmit(e) {
    e.preventDefault();
    if (submitting) return;

    hideError();

    const payload = {
      plan:               dom.planInput.value,
      email:              dom.email.value.trim(),
      first_name:         dom.firstName.value.trim(),
      last_name:          dom.lastName.value.trim(),
      phone_country_code: dom.country.value,
      phone_number:       dom.phone.value.trim(),
    };

    // Validation locale
    const localError = validate(payload);
    if (localError) {
      showError(localError);
      return;
    }

    setSubmitting(true);

    try {
      const res = await fetch(`${API_BASE}/payment/checkout`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      const body = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detail = body.detail || {};
        showError(detail.message || 'Le paiement a échoué. Veuillez réessayer.');
        setSubmitting(false);
        return;
      }

      // Redirection selon le step renvoyé par le backend
      switch (body.step) {
        case 'payment':
          // Redirection vers Chariow — la page de succès récupérera
          // ensuite le code via le purchase_ref.
          window.location.href = body.checkout_url;
          return;

        case 'completed':
          window.location.href = `success.html?ref=${encodeURIComponent(body.purchase_ref)}`;
          return;

        case 'already_purchased':
          showError(body.message || 'Vous avez déjà acheté cette offre.');
          setSubmitting(false);
          return;

        default:
          showError('Réponse inattendue du serveur. Réessayez.');
          setSubmitting(false);
      }

    } catch (err) {
      console.error(err);
      showError('Impossible de joindre le serveur. Vérifiez votre connexion.');
      setSubmitting(false);
    }
  }

  function validate(p) {
    if (!p.plan)                           return 'Plan invalide.';
    if (!p.first_name)                     return 'Veuillez saisir votre prénom.';
    if (!p.last_name)                      return 'Veuillez saisir votre nom.';
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(p.email)) return 'Email invalide.';
    const digits = p.phone_number.replace(/\D/g, '');
    if (digits.length < 6)                 return 'Numéro de téléphone trop court.';
    return null;
  }

  function setSubmitting(state) {
    submitting = state;
    dom.submitBtn.disabled = state;
    dom.submitLabel.textContent = state ? 'Redirection…' : 'Payer maintenant';
  }

  function showError(message) {
    dom.error.textContent = message;
    dom.error.classList.remove('hidden');
  }

  function hideError() {
    dom.error.textContent = '';
    dom.error.classList.add('hidden');
  }

  function formatAmount(value) {
    if (typeof value !== 'number') return value;
    return value.toLocaleString('fr-FR');
  }
})();
