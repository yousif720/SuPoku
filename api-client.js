/* Split-host requests use an explicit session token, avoiding third-party cookies.
 * The token lives in localStorage so a sign-in survives closing the tab; the
 * server still expires it after 30 days, and signing out removes it. */
(() => {
  const base = (window.SUPOKU_API_BASE || '').replace(/\/+$/, '');
  const crossHost = !!base && new URL(base, location.href).origin !== location.origin;
  const key = 'supoku:session:' + base;
  let token = '';
  try {
    token = localStorage.getItem(key) || '';
    // Earlier versions kept the token per tab; carry an existing one over.
    const legacy = sessionStorage.getItem(key);
    if (legacy) {
      if (!token) { token = legacy; localStorage.setItem(key, token); }
      sessionStorage.removeItem(key);
    }
  } catch { /* memory-only session */ }
  window.SupokuAPI = {
    crossHost,
    async request(path, options = {}) {
      const headers = { ...options.headers };
      if (crossHost) {
        headers['X-SuPoku-Auth'] = 'bearer';
        if (token) headers.Authorization = 'Bearer ' + token;
      }
      return fetch(base + path, { ...options, headers, credentials: crossHost ? 'omit' : 'same-origin' });
    },
    setToken(value) {
      token = value || '';
      try { if (token) localStorage.setItem(key, token); else localStorage.removeItem(key); } catch { /* memory-only */ }
    }
  };
})();
