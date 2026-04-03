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

// Inline delete confirmation
// Buttons with class "delete-btn" require a second click to confirm.
// On first click the button text changes to data-confirm-label and htmx is suspended.
// On second click htmx fires the request. Clicking elsewhere resets the button.

document.addEventListener('click', function (e) {
  const btn = e.target.closest('.delete-btn');

  if (!btn) {
    // Click was outside — reset any pending delete buttons
    document.querySelectorAll('.delete-btn[data-pending]').forEach(function (pending) {
      pending.textContent = pending.dataset.originalLabel;
      pending.removeAttribute('data-pending');
    });
    return;
  }

  if (btn.hasAttribute('data-pending')) {
    // Second click: allow htmx to proceed (nothing to do, htmx fires naturally)
    btn.removeAttribute('data-pending');
    return;
  }

  // First click: show confirmation label and block htmx
  e.preventDefault();
  e.stopPropagation();

  // Reset any other pending buttons first
  document.querySelectorAll('.delete-btn[data-pending]').forEach(function (other) {
    if (other !== btn) {
      other.textContent = other.dataset.originalLabel;
      other.removeAttribute('data-pending');
    }
  });

  btn.setAttribute('data-pending', '');
  btn.textContent = btn.dataset.confirmLabel || 'Sure?';
});

