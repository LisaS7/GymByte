// Menu toggle

document.addEventListener('DOMContentLoaded', () => {
  const toggle = document.querySelector('#app-header .menu-toggle');
  const nav = document.querySelector('#main-nav');

  if (!toggle || !nav) {
    return; // nothing to toggle
  }

  toggle.addEventListener('click', () => {
    const isOpen = nav.classList.toggle('is-open');
    toggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
  });
});

// Cancel form

document.closeForm = function (selector) {
  const container = document.querySelector(selector);
  if (container) container.innerHTML = '';
};

document.addEventListener('click', function (e) {
  const btn = e.target.closest('[data-cancel-target]');
  if (btn) document.closeForm(btn.dataset.cancelTarget);
});

// Toast is yummy
document.body.addEventListener('DOMContentLoaded', () => {
  document.body.addEventListener('demoResetDone', () => {
    const toast = document.getElementById('toast');
    if (!toast) return;

    toast.textContent = 'Demo reset complete.';
    toast.hidden = false;

    // re-hide after 2.5s
    window.clearTimeout(toast._t);
    toast._t = window.setTimeout(() => {
      toast.hidden = true;
    }, 2500);
  });
});
