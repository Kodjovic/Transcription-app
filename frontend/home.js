// home.js — interactions partagées pour les pages publiques (index.html, pricing.html)
//
// - Gère la fermeture exclusive des items <details> (FAQ) : un seul ouvert à la fois.
// - Gère l'ouverture/fermeture du modal "Contactez l'admin" sur la page pricing.

(function () {
  'use strict';

  document.addEventListener('DOMContentLoaded', () => {
    initFaqAccordion();
    initContactModal();
  });

  // ─── FAQ : un seul item ouvert à la fois ─────────────────────────────────
  function initFaqAccordion() {
    const items = document.querySelectorAll('.faq-item');
    if (!items.length) return;

    items.forEach((item) => {
      item.addEventListener('toggle', () => {
        if (item.open) {
          items.forEach((other) => {
            if (other !== item) other.open = false;
          });
        }
      });
    });
  }

  // ─── Modal de contact pour le plan gratuit ───────────────────────────────
  function initContactModal() {
    const modal     = document.getElementById('contact-modal');
    const trigger   = document.getElementById('btn-free');
    const closeBtn  = document.getElementById('contact-close');

    if (!modal || !trigger) return;

    const open  = () => {
      modal.classList.remove('hidden');
      document.body.style.overflow = 'hidden';
    };
    const close = () => {
      modal.classList.add('hidden');
      document.body.style.overflow = '';
    };

    trigger.addEventListener('click', (e) => {
      e.preventDefault();
      open();
    });

    if (closeBtn) closeBtn.addEventListener('click', close);

    // Clic en dehors du card → fermeture
    modal.addEventListener('click', (e) => {
      if (e.target === modal) close();
    });

    // Touche Échap → fermeture
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && !modal.classList.contains('hidden')) close();
    });
  }
})();
