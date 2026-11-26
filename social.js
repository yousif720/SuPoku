/* Account UI and ranked daily adapter. Guest play stays entirely available. */
'use strict';
window.Social = {
  user: null, ranked: false, busy: false, state: null,
  async api(path, method = 'GET', body) {
    const response = await SupokuAPI.request('/api/social/' + path, {
      method, credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-SuPoku-Request': '1' },
      ...(body ? { body: JSON.stringify(body) } : {})
    });
    const data = await response.json().catch(() => ({ error: 'Account service unavailable. Run the updated SuPoku server.' }));
    if (!response.ok) throw new Error(data.error || 'Could not complete that request.');
    if (data.token) SupokuAPI.setToken(data.token);
    if (path === 'logout' || (path === 'account' && method === 'DELETE')) SupokuAPI.setToken('');
    return data;
  },
  async loadDaily() {
    if (this.busy) return;
    this.busy = true;
    try {
      const { game } = await this.api('game');
      this.ranked = true;
      this.restore(game);
    } catch (e) { toast(e.message); }
    finally { this.busy = false; }
  },
  restore(game) {
    this.state = game;
    grid = {
      kind: 'daily', day: game.day,
      rows: game.rows.map(i => CATS[i]), cols: game.cols.map(i => CATS[i]),
      cells: game.cells.map((id,i) => {
        if (id === null) return null;
        const r = game.rarities?.[i];
        return { ok: true, p: POKE.find(p => p.id === id), ...(r ? {rarity:r.percent,firstPick:r.first,tier:tierFor(r.percent)} : {}) };
      }),
      retried: game.retried.slice(), spent: game.spent.slice()
    };
    guessesLeft = game.guesses;
    undoUsed = game.undoUsed || game.over;
    over = game.over;
    pendingUndo = null;
    closeSheet();
    $('confirm-overlay').hidden = true;
    $('done-overlay').hidden = true;
    setModeUI('daily', game.day);
    $('puzzle-id').textContent = game.day + ' · ranked daily';
    render();
    if (game.over) {
      finish();
      $('done-score').textContent = game.points + ' leaderboard points · ' + game.mistakes + ' wrong guesses';
      $('done-hint').textContent = 'Saved to your account. This daily result is final. A new puzzle arrives at midnight UTC.';
    }
  },
  async play(action, cell, pokemon) {
    if (this.busy) return;
    this.busy = true;
    try {
      const { game } = await this.api('game', 'POST', {
        action, cell, pokemon, day: this.state.day, revision: this.state.revision
      });
      const missed = game.mistakes > this.state.mistakes;
      this.restore(game);
      if (missed) toast('Not a match. Your first miss on each square uses its free retry.');
    } catch (e) { toast(e.message); }
    finally { this.busy = false; }
  }
};

(() => {
  const dialog = document.createElement('dialog');
  dialog.className = 'social-dialog';
  dialog.setAttribute('aria-labelledby', 'social-title');
  dialog.innerHTML = `<button type="button" class="sheet-close" id="social-close" aria-label="Close community">×</button>
    <h2 id="social-title">The common room</h2><p id="social-identity">Play together, one grid at a time.</p>
    <nav class="social-tabs" aria-label="Community"><button data-page="leaderboard">Scores</button><button data-page="friends">Friends</button><button data-page="stats">My stats</button><button data-page="account">Account</button></nav>
    <p id="social-message" role="status" aria-live="polite"></p><section id="social-content"></section>`;
  document.body.append(dialog);
  const content = $('social-content'), message = $('social-message');
  let page = 'leaderboard', scope = 'today', request = 0;
  const esc = s => String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const button = (text, fn) => {
    const b = document.createElement('button'); b.textContent = text; b.type = 'button';
    b.addEventListener('click', fn); return b;
  };
  function identity() {
    $('social-identity').textContent = Social.user ? 'Signed in as ' + Social.user.username : 'Guest play is always available. Sign in to save your daily scores.';
  }
  function table(headers, rows) {
    const wrap = document.createElement('div'); wrap.className = 'social-table-wrap';
    const t = document.createElement('table');
    t.innerHTML = '<thead><tr>' + headers.map(h => '<th scope="col">' + esc(h) + '</th>').join('') + '</tr></thead>';
    const body = t.createTBody();
    for (const row of rows) {
      const tr = body.insertRow();
      for (const value of row) {
        const td = tr.insertCell();
        if (value instanceof Node) td.append(value); else td.textContent = value;
      }
    }
    wrap.append(t); return wrap;
  }
  async function run(fn) {
    message.textContent = '';
    try { await fn(); } catch (e) { message.textContent = e.message; }
  }
  async function show(next = page) {
    page = next;
    const ticket = ++request;
    identity();
    message.textContent = '';
    dialog.querySelectorAll('[data-page]').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.page === page)));
    content.innerHTML = '<p>Opening the notebook…</p>';
    try {
      if (!Social.user && page !== 'leaderboard') { account(); return; }
      if (page === 'account') { account(); return; }
      if (page === 'leaderboard') {
        const data = await Social.api('leaderboard?scope=' + scope);
        if (ticket !== request) return;
        content.innerHTML = `<h3>Leaderboard</h3><p>100 points per filled square, minus 10 per wrong guess (including free retries). Undo does not erase mistakes. Only signed-in daily games count. Equal scores share a rank.</p>`;
        const tabs = document.createElement('div'); tabs.className = 'social-tabs';
        for (const [key, label] of [['today','Today'],['all','Personal bests'],['friends','Friends today'],['streaks','Streaks']]) {
          const b = button(label, () => { scope = key; show(); });
          b.setAttribute('aria-pressed', String(scope === key)); tabs.append(b);
        }
        content.append(tabs);
        if (!data.entries.length) content.insertAdjacentHTML('beforeend', '<p>No finished games here yet. Finish today’s grid to leave your mark.</p>');
        else {
          let rank = 0, previous;
          content.append(table(['Rank','Player',scope === 'streaks' ? 'Best streak' : 'Points','Wins'], data.entries.map((e,i) => {
            const value = scope === 'streaks' ? e.bestStreak : e.points;
            if (value !== previous) rank = i+1;
            previous = value;
            return [rank,e.username,value,e.wins];
          })));
        }
        content.insertAdjacentHTML('beforeend','<p class="social-note">Daily resets at midnight UTC. Personal bests show each player’s highest single-game score.</p>');
      } else if (page === 'friends') {
        const data = await Social.api('friends');
        if (ticket !== request) return;
        content.innerHTML = `<h3>Your friends</h3><p>Add a player by username to follow their public scores. This is a one-way friends list; no invitation or message is sent.</p>
          <form id="friend-form" class="social-form"><label>Username<input name="username" required minlength="3" maxlength="20" autocomplete="off"></label><button class="primary">Add friend</button></form>`;
        $('friend-form').onsubmit = e => { e.preventDefault(); run(async () => { await Social.api('friends','POST', {username: new FormData(e.target).get('username')}); await show(); }); };
        if (data.entries.length) content.append(table(['Player','Best score','Streak',''],data.entries.map(e => [e.username,e.bestScore,e.currentStreak,button('Remove', () => run(async () => {await Social.api('friends','DELETE',{username:e.username});await show();}))])));
        else content.insertAdjacentHTML('beforeend','<p>Your friends list is empty. Share your username so your friends can find you.</p>');
      } else if (page === 'stats') {
        const st = await Social.api('stats');
        if (ticket !== request) return;
        content.innerHTML = '<h3>Your daily notebook</h3>';
        const metrics = document.createElement('div'); metrics.className = 'social-metrics';
        for (const [label,value] of [['Played',st.played],['Win rate',st.played ? Math.round(st.wins/st.played*100)+'%' : '—'],['Current streak',st.currentStreak],['Best streak',st.bestStreak],['Best score',st.bestScore]]) {
          const metric = document.createElement('p'); metric.innerHTML = '<strong>' + esc(value) + '</strong><span>' + label + '</span>'; metrics.append(metric);
        }
        content.append(metrics);
        content.insertAdjacentHTML('beforeend','<h4>The last 12 weeks</h4><p class="social-note">A darker square marks a completed grid. Streaks count consecutive 9/9 days.</p>');
        const heatmap = document.createElement('div'); heatmap.className = 'social-heatmap';
        const history = new Map(st.history.map(h => [h.day,h]));
        for (let i=83;i>=0;i--) {
          const date = new Date(); date.setUTCDate(date.getUTCDate()-i);
          const day = date.toISOString().slice(0,10), game = history.get(day);
          const cell = document.createElement('span'); cell.className = game ? (game.filled === 9 ? 'won' : 'played') : '';
          cell.title = day + ': ' + (game ? game.points + ' points, ' + game.filled + '/9' : 'Not played');
          cell.setAttribute('aria-label',cell.title); heatmap.append(cell);
        }
        content.append(heatmap);
        content.insertAdjacentHTML('beforeend','<h4>Recent games</h4>');
        if (st.history.length) content.append(table(['Day','Filled','Points'],st.history.slice(-30).reverse().map(g => [g.day,g.filled+'/9',g.points])));
        else content.insertAdjacentHTML('beforeend','<p>Your first finished daily game will appear here.</p>');
      }
    } catch (e) {
      if (ticket !== request) return;
      content.innerHTML = '';
      message.textContent = e.message;
      content.append(button('Back to scores', () => {scope='today';show('leaderboard');}));
      if (!Social.user) content.append(button('Sign in', () => show('account')));
    }
  }
  function account() {
    if (Social.user) {
      content.innerHTML = `<h3>Your account</h3><p>Your username and score statistics are public. Your friends list and game history are only available to you.</p><p>Daily progress saves with every move. Finished games are final, so use your undo before the last guess. Signing in starts or resumes your account’s daily game; guest games are not imported.</p>`;
      content.append(button('Sign out', () => run(async () => {
        await Social.api('logout','POST',{}); Social.user = null; Social.ranked = false; newGame('daily'); await show('account');
      })));
      const details = document.createElement('details');
      details.innerHTML = `<summary>Delete my account</summary><p>This permanently removes your login, friends, daily history and leaderboard entries.</p><form id="delete-account" class="social-form"><label>Current password<input name="password" type="password" autocomplete="current-password" required maxlength="128"></label><label class="social-check"><input type="checkbox" required> I understand my account will be permanently deleted.</label><button>Delete account permanently</button></form>`;
      content.append(details);
      $('delete-account').onsubmit = e => {e.preventDefault();run(async () => {
        await Social.api('account','DELETE',{password:new FormData(e.target).get('password')});
        Social.user=null;Social.ranked=false;newGame('daily');await show('account');message.textContent='Your account has been deleted.';
      });};
      return;
    }
    content.innerHTML = `<h3>Save your place</h3><form id="auth-form" class="social-form">
      <label>Username<input name="username" required minlength="3" maxlength="20" pattern="[A-Za-z0-9_.\\-]+" autocomplete="username" autocapitalize="none" spellcheck="false"></label>
      <label>Password<input name="password" type="password" required minlength="8" maxlength="128" autocomplete="current-password"></label>
      <p class="social-note">Use 3–20 letters, numbers, dots, hyphens or underscores for your public username. Passwords need at least 8 characters. Keep yours safe: email password recovery is not configured.</p>
      <p class="social-note">Creating an account saves your daily progress and publishes your username and score statistics. See <a href="privacy.html">Privacy</a> and <a href="terms.html">Terms</a>.</p>
      <div class="social-tabs"><button name="action" value="login" class="primary">Sign in</button><button name="action" value="register">Create account</button></div></form>`;
    $('auth-form').onsubmit = e => {
      e.preventDefault(); const form = e.target, action = e.submitter?.value || 'login';
      const data = Object.fromEntries(new FormData(form));
      form.querySelectorAll('button').forEach(b=>b.disabled=true);
      run(async () => {
        try {
          Social.user = (await Social.api(action,'POST',data)).user;
          await Social.loadDaily(); await show('account');
        } finally {form.querySelectorAll('button').forEach(b=>b.disabled=false);}
      });
    };
  }
  $('btn-community').onclick = () => { dialog.showModal(); show(); };
  $('social-close').onclick = () => dialog.close();
  dialog.addEventListener('click', e => { if (e.target === dialog) { const r=dialog.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)dialog.close(); } });
  dialog.querySelectorAll('[data-page]').forEach(b => b.onclick = () => show(b.dataset.page));
  const share = button('Copy result', async () => {
    const cells = grid.cells.map(c => c?.ok ? '🟩' : '⬜');
    const lines = [cells.slice(0,3).join(''),cells.slice(3,6).join(''),cells.slice(6).join('')];
    const filled = grid.cells.filter(c => c?.ok).length;
    const text = 'SuPoku · ' + $('puzzle-id').textContent + ' · ' + filled + '/9\n' + lines.join('\n') + (Social.ranked ? '\n' + Social.state.points + ' points' : '') + '\n' + new URL('index.html', location.href).href;
    try {await navigator.clipboard.writeText(text);share.textContent='Copied!';setTimeout(()=>share.textContent='Copy result',2000);}
    catch {const area=document.createElement('textarea');area.value=text;area.readOnly=true;area.setAttribute('aria-label','Shareable result');share.after(area);area.select();}
  });
  share.className = 'ghost'; $('btn-again').before(share);
  const boot = async () => {
    try {
      Social.user = (await Social.api('me')).user;
      // An expired or revoked stored token is useless; drop it.
      if (!Social.user) SupokuAPI.setToken('');
      if (Social.user && (!grid || grid.kind === 'daily')) await Social.loadDaily();
    }
    catch { /* Guest play remains usable if the account service is offline. */ }
  };
  if (window.supokuReady) boot();
  else window.addEventListener('supoku-ready',boot,{once:true});
})();
