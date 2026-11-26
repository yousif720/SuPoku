/* Apply before styles load to avoid flashing light paper on a dark-theme visit. */
(() => {
  'use strict';
  const key = 'supoku:theme';
  const system = window.matchMedia('(prefers-color-scheme: dark)');
  let preference = null;
  try { preference = localStorage.getItem(key); } catch (_) { /* Storage is optional. */ }
  if (preference !== 'dark' && preference !== 'light') preference = null;

  function apply() {
    const dark = preference ? preference === 'dark' : system.matches;
    document.documentElement.dataset.theme = dark ? 'dark' : 'light';
    document.querySelectorAll('[data-theme-toggle]').forEach(control => {
      if (control instanceof HTMLInputElement) control.checked = dark;
      else control.setAttribute('aria-pressed', String(dark));
    });
  }
  function choose(dark) {
    preference = dark ? 'dark' : 'light';
    try { localStorage.setItem(key, preference); } catch (_) { /* Keep the session choice. */ }
    apply();
  }
  apply();
  system.addEventListener('change', () => { if (!preference) apply(); });
  window.addEventListener('storage', event => {
    if (event.key !== key && event.key !== null) return;
    preference = event.newValue === 'dark' || event.newValue === 'light' ? event.newValue : null;
    apply();
  });
  document.addEventListener('DOMContentLoaded', () => {
    apply();
    document.querySelectorAll('[data-theme-toggle]').forEach(control => {
      if (control instanceof HTMLInputElement) {
        control.addEventListener('change', () => choose(control.checked));
      } else {
        control.addEventListener('click', () => choose(document.documentElement.dataset.theme !== 'dark'));
      }
    });
  });
})();
