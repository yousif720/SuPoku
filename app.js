/* SuPoku - a 3x3 Pokemon trivia grid.
 * Pick a Pokemon for each square that satisfies both its row and column category.
 * Nine guesses, no repeats. */

'use strict';

const SPRITE_BASE = 'https://raw.githubusercontent.com/PokeAPI/sprites/master/sprites/pokemon';
const SPRITE = id => `${SPRITE_BASE}/${id}.png`;
const ART = id => `${SPRITE_BASE}/other/official-artwork/${id}.png`;

// Official 2D artwork by default, pixel sprites behind the settings cog.
let pixelArt = false;

// Newest first; the rest are keys earlier project names wrote under.
const PIXEL_KEYS = ['supoku:pixelArt', 'supokeku:pixelArt', 'pokegrid:pixelArt'];

// `p` needs an id and a dex number, so a form with no image of its own can fall
// back to its base species. `spriteOnly` forces the small pixel sprite: artwork
// files run 100-500KB against 2-10KB for a sprite, far too heavy for a search
// list that can show thirty results at once.
function pokeImg(p, cls, spriteOnly) {
  const pixel = spriteOnly || pixelArt;
  const c = 'poke' + (cls ? ' ' + cls : '') + (spriteOnly ? ' is-sprite' : '');
  const src = pixel ? SPRITE(p.id) : ART(p.id);
  return `<img class="${c}" data-id="${p.id}" data-dex="${p.dex}"` +
    `${spriteOnly ? ' data-sprite="1"' : ''} src="${src}" alt="" loading="lazy">`;
}

// Not every form has every image. Eleven have no official artwork, and the eight
// Koraidon/Miraidon travel builds have no image of any kind, so walk a chain:
// this form's artwork, then its sprite, then the base species. Image errors do
// not bubble, hence the capture-phase listener.
document.addEventListener('error', e => {
  const img = e.target;
  if (!(img instanceof HTMLImageElement) || !img.classList.contains('poke')) return;
  const step = (+img.dataset.step || 0) + 1;
  const { id, dex } = img.dataset;
  const pixel = img.dataset.sprite === '1' || pixelArt;
  img.dataset.step = step;

  if (step === 1 && !pixel && id !== dex) {
    img.classList.add('is-sprite');
    img.src = SPRITE(id);
  } else if (step <= 2 && id !== dex) {
    if (!pixel) img.classList.remove('is-sprite');
    img.src = pixel ? SPRITE(dex) : ART(dex);
  }
}, true);

// Official Scarlet/Violet type icons, mirrored locally in assets/type-icons.
const typeIcon = (t, cls) =>
  `<img class="${cls || 'ticon'}" src="assets/type-icons/${t}.png" alt="${t}" title="${t}">`;

// Rarity tiers, by the share of other players who gave the same answer.
const TIERS = [
  { under: 1, name: 'Legendary', cls: 'tier-legendary' },
  { under: 5, name: 'Epic', cls: 'tier-epic' },
  { under: 10, name: 'Rare', cls: 'tier-rare' },
  { under: 25, name: 'Uncommon', cls: 'tier-uncommon' },
  { under: Infinity, name: 'Common', cls: 'tier-common' },
];
const tierFor = pct => TIERS.find(t => pct < t.under);
const fmtPct = v => (v >= 10 ? `${Math.round(v)}%` : v >= 0.1 ? `${v.toFixed(1)}%` : '<0.1%');

// A Pokemon's home region. A regional form belongs to the region it comes from,
// anything else to the region its species debuted in, so Alolan Meowth counts
// as Alola, while Mega Emboar stays Unova with the rest of its line.
const REGIONS = ['Kanto', 'Johto', 'Hoenn', 'Sinnoh', 'Unova', 'Kalos',
                 'Alola', 'Galar', 'Hisui', 'Paldea'];
const GEN_REGION = ['', 'Kanto', 'Johto', 'Hoenn', 'Sinnoh', 'Unova', 'Kalos',
                    'Alola', 'Galar', 'Paldea'];
const FORM_REGION = { Alolan: 'Alola', Galarian: 'Galar', Hisuian: 'Hisui', Paldean: 'Paldea' };
const homeRegion = p => FORM_REGION[p.region] || GEN_REGION[p.gen];

/* ---------------------------------------------------------------- state --- */
let DATA, POKE, CATS, POOL, POKE_BY_ID;
// { kind: 'daily'|'archive'|'random', day, seed, rows: [cat x3], cols: [cat x3], cells: [9] }
let grid = null;
let guessesLeft = 9;
let over = false;
let active = null;        // index of the cell the sheet was opened for
let undoUsed = false;     // the single undo is available once per grid
let pendingUndo = null;   // square awaiting undo confirmation
let selIndex = 0;         // highlighted row in the search results

/* ------------------------------------------------------------- utility --- */

// Deterministic PRNG so a given day always yields the same grid.
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashStr(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function shuffled(rng, arr) {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

const norm = s => s.toLowerCase().replace(/[^a-z0-9]/g, '');

// Daily puzzles roll over at midnight UTC, matching the server's ranked day.
const todayUTC = () => new Date().toISOString().slice(0, 10);
const escHtml = s => String(s).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* ---------------------------------------------------------- local save ---
 * Guest, archive and random games are kept in localStorage so a reload does
 * not lose the board. Signed-in ranked dailies are saved by the server instead.
 * Each daily date has its own slot; random games share one slot. */
const SAVE_PREFIX = 'supoku:game:';
const CURRENT_KEY = 'supoku:current';

const saveKeyFor = g => (g.kind === 'random' ? 'random' : 'daily:' + g.day);

function readSave(key) {
  try { return JSON.parse(localStorage.getItem(SAVE_PREFIX + key) || 'null'); } catch (e) { return null; }
}

function saveGame() {
  if (!grid || grid.kind == null || window.Social?.ranked) return;
  const data = {
    v: 1, kind: grid.kind, day: grid.day, seed: grid.seed,
    rows: grid.rows.map(c => CATS.indexOf(c)), cols: grid.cols.map(c => CATS.indexOf(c)),
    cells: grid.cells.map(st => (st && st.ok
      ? { id: st.p.id, rarity: st.rarity ?? null, first: !!st.firstPick } : null)),
    retried: grid.retried, spent: grid.spent,
    guessesLeft, undoUsed, over, reveal: grid.reveal || null,
  };
  try {
    const key = saveKeyFor(grid);
    localStorage.setItem(SAVE_PREFIX + key, JSON.stringify(data));
    localStorage.setItem(CURRENT_KEY, key);
  } catch (e) { /* storage full or blocked: the game still plays */ }
}

// Rebuilds a saved game. The grid is regenerated from its seed and compared
// with the saved clues, so a save made against an older Pokédex is discarded
// rather than restored onto different categories.
function loadSaved(key) {
  const s = readSave(key);
  if (!s || s.v !== 1) return false;
  const g = generateGrid(hashStr('pokegrid-' + s.seed));
  if (!g) return false;
  const same = (a, b) => a.length === b.length && a.every((c, k) => CATS.indexOf(c) === b[k]);
  if (!same(g.rows, s.rows) || !same(g.cols, s.cols)) return false;
  const cells = s.cells.map(c => {
    if (!c) return null;
    const p = POKE_BY_ID.get(c.id);
    if (!p) return undefined;
    const st = { ok: true, p };
    if (c.rarity != null) { st.rarity = c.rarity; st.firstPick = c.first; st.tier = tierFor(c.rarity); }
    return st;
  });
  if (cells.includes(undefined)) return false;

  startGrid({ kind: s.kind, day: s.day, seed: s.seed }, g);
  grid.cells = cells;
  grid.retried = s.retried.slice();
  grid.spent = s.spent.slice();
  grid.reveal = s.reveal;
  guessesLeft = s.guessesLeft;
  undoUsed = s.undoUsed;
  over = s.over;
  render();
  if (over) showDone();
  return true;
}

/* ------------------------------------------------------------ bitsets ---
 * Category membership is stored as a bitset over the Pokedex index so grid
 * generation can count intersections cheaply. */
let WORDS;

function makeBitset(test) {
  const bs = new Uint32Array(WORDS);
  let n = 0;
  for (let i = 0; i < POKE.length; i++) {
    if (test(POKE[i])) { bs[i >>> 5] |= 1 << (i & 31); n++; }
  }
  return { bs, n };
}

function popcount(x) {
  x -= (x >>> 1) & 0x55555555;
  x = (x & 0x33333333) + ((x >>> 2) & 0x33333333);
  x = (x + (x >>> 4)) & 0x0f0f0f0f;
  return (x * 0x01010101) >>> 24;
}

function intersectCount(a, b) {
  let n = 0;
  for (let i = 0; i < WORDS; i++) n += popcount(a.bs[i] & b.bs[i]);
  return n;
}

function intersectList(a, b) {
  const out = [];
  for (let i = 0; i < POKE.length; i++) {
    if ((a.bs[i >>> 5] >>> (i & 31)) & (b.bs[i >>> 5] >>> (i & 31)) & 1) out.push(POKE[i]);
  }
  return out;
}

/* --------------------------------------------------------- categories --- */

function buildCategories() {
  const cats = [];
  const add = (family, top, main, test, icon) =>
    cats.push({ key: family + '|' + main, family, top, main, test, icon: icon || null });

  for (const t of DATA.types) {
    add('type', 'Type', t, p => p.types.includes(t), t);
    add('weak', 'Weak to', t, p => p.weakTo.includes(t), t);
    add('resist', 'Resists', t, p => p.resists.includes(t), t);
    // Immunities are ability-aware: Levitate, Flash Fire, Wonder Guard, etc.
    add('immune', 'Immune to', t, p => p.immuneTo.includes(t), t);
  }

  for (const r of REGIONS) {
    add('region', 'From', r, p => p.homeRegion === r);
  }

  add('slots', 'Typing', 'Mono-type', p => p.types.length === 1);
  add('slots', 'Typing', 'Dual-type', p => p.types.length === 2);

  for (const [id, name] of Object.entries(DATA.categoryMoves)) {
    const mid = +id;
    add('move', 'Can learn', name, p => p.moveSet.has(mid));
  }

  add('rare', 'Status', 'Legendary', p => p.legendary);
  add('rare', 'Status', 'Mythical', p => p.mythical);
  add('rare', 'Status', 'Baby Pokémon', p => p.baby);
  add('rare', 'Status', 'Not legendary', p => !p.legendary && !p.mythical);

  add('form', 'Form', 'Mega Evolution', p => p.mega);
  add('form', 'Form', 'Gigantamax', p => p.gmax);
  add('form', 'Form', 'Regional form', p => !!p.region);
  for (const r of ['Alolan', 'Galarian', 'Hisuian', 'Paldean']) {
    add('form', 'Form', r + ' form', p => p.region === r);
  }
  add('form', 'Has a', 'Mega Evolution', p => p.hasMega);

  add('evo', 'Evolution', 'First in line', p => p.stage === 1 && p.evolves);
  add('evo', 'Evolution', 'Last in line', p => !p.evolves && p.stage > 1);
  add('evo', 'Evolution', 'Never evolves', p => p.stage === 1 && !p.evolves);
  add('evo', 'Evolution', 'Middle stage', p => p.stage === 2 && p.evolves);

  add('size', 'Weight', '100 kg or more', p => p.weight >= 1000);
  add('size', 'Weight', 'Under 10 kg', p => p.weight < 100);
  add('size', 'Height', '2 m or taller', p => p.height >= 20);
  add('size', 'Height', 'Under 1 m', p => p.height < 10);

  for (const c of cats) {
    const { bs, n } = makeBitset(c.test);
    c.bs = bs; c.n = n;
  }
  return cats;
}

/* ---------------------------------------------------- grid generation --- */
const MIN_ANS = 3;  // every square must have at least this many valid answers
                    // (there is deliberately no upper bound)

function generateGrid(seed) {
  const rng = mulberry32(seed);

  for (let attempt = 0; attempt < 600; attempt++) {
    const bag = shuffled(rng, POOL);
    const rows = [];
    for (const c of bag) {
      if (rows.length === 3) break;
      if (rows.some(r => r.key === c.key || r.family === c.family)) continue;
      rows.push(c);
    }
    if (rows.length < 3) continue;

    const cols = [];
    for (const c of shuffled(rng, POOL)) {
      if (cols.length === 3) break;
      if (rows.some(r => r.key === c.key)) continue;
      if (cols.some(x => x.key === c.key || x.family === c.family)) continue;
      const ok = rows.every(r => intersectCount(r, c) >= MIN_ANS);
      if (ok) cols.push(c);
    }
    if (cols.length !== 3) continue;

    // Final guard: all nine squares must clear the minimum. The column loop
    // above already checks each candidate against all three rows, so this is
    // belt and braces, but it states the invariant in one place and stops a
    // later change to that loop from silently shipping an unsolvable square
    // (e.g. "Weak to Ground" against "Immune to Ground", which is empty).
    if (rows.every(r => cols.every(c => intersectCount(r, c) >= MIN_ANS))) {
      return { rows, cols };
    }
  }
  return null;
}

/* -------------------------------------------------------------- render --- */
const $ = id => document.getElementById(id);

function catCell(cat) {
  const el = document.createElement('div');
  el.className = 'cat';
  el.innerHTML = cat.family === 'type'
    ? typeIcon(cat.main, 'cat-icon-solo')
    : (cat.icon ? typeIcon(cat.icon, 'cat-icon') : '') +
      `<span class="cat-top">${cat.top}</span>` +
      `<span class="cat-main">${cat.main}</span>`;
  el.title = `${cat.top} ${cat.main} (${cat.n} Pokémon)`;
  return el;
}

function render() {
  const board = $('board');
  board.innerHTML = '';

  const corner = document.createElement('div');
  corner.className = 'corner';
  board.appendChild(corner);

  grid.cols.forEach(c => board.appendChild(catCell(c)));

  for (let r = 0; r < 3; r++) {
    board.appendChild(catCell(grid.rows[r]));
    for (let c = 0; c < 3; c++) {
      const i = r * 3 + c;
      const cell = document.createElement('div');
      cell.className = 'cell' + (grid.retried[i] ? ' used-retry' : '');
      const st = grid.cells[i];
      if (st) {
        cell.classList.add(st.ok ? 'filled' : 'miss');
        if (st.ok) cell.classList.add(`cutout-${i % 6}`);
        if (st.ok && st.tier) cell.classList.add(st.tier.cls);
        let badge = '';
        if (st.ok && st.firstPick) {
          badge = '<span class="rarity" title="Legendary: nobody else has answered this square">1st</span>';
        } else if (st.ok && st.rarity != null) {
          badge = `<span class="rarity" title="${st.tier.name}">${fmtPct(st.rarity)}</span>`;
        }
        const cutoutSrc = st.ok ? (pixelArt ? SPRITE(st.p.id) : ART(st.p.id)) : '';
        cell.innerHTML = st.ok
          ? `<span class="poke-cutout" style="--cutout-image: url('${cutoutSrc}')">${pokeImg(st.p)}</span><span class="cname">${st.p.name}</span>${badge}`
          : `<span class="cname">${st.label}</span>`;
        if (st.ok && !undoUsed) {
          cell.classList.add('undoable');
          cell.title = 'Tap to undo this square';
          cell.addEventListener('click', () => requestUndo(i));
        }
      } else {
        cell.addEventListener('click', () => openSheet(i));
      }
      board.appendChild(cell);
    }
  }

  $('guesses').textContent = guessesLeft;
  const pips = $('pips');
  pips.innerHTML = '';
  for (let k = 0; k < 9; k++) {
    const bar = document.createElement('span');
    bar.className = 'pip' + (k < guessesLeft ? '' : ' spent');
    pips.appendChild(bar);
  }

  const card = $('undo-card');
  card.classList.toggle('is-ready', !undoUsed);
  card.classList.toggle('is-spent', undoUsed);
  $('undo-note').textContent = undoUsed ? 'Undo spent' : 'One undo: tap a square';
  const filled = grid.cells.filter(x => x && x.ok).length;
  $('hint').textContent = over
    ? `Finished with ${filled} of 9.`
    : 'Tap an empty square to name a Pokémon that satisfies both categories.';
  saveGame();
}

let toastTimer = null;
function toast(html) {
  const t = $('toast');
  t.innerHTML = html;
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
}

/* -------------------------------------------------------------- rarity --- */

// Squares are keyed by their category pair rather than by puzzle, so answers
// pool across every grid that poses the same question. Sorted, so a pair counts
// the same whichever axis each half landed on.
function squareKey(i) {
  return [grid.rows[Math.floor(i / 3)].key, grid.cols[i % 3].key].sort().join(' & ');
}

async function tally(body) {
  const res = await SupokuAPI.request('/api/pick', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(res.status);
  return res.json();
}

// The server answers with the counts as they were before this pick, so your own
// answer never feeds the percentage you are shown. Rarity is decoration: if the
// API is unreachable (opened as a plain file, say) the game plays on without it.
// The two category indices let the server work out the square's valid answers
// and blend its survey prior with players' picks (rarity.py).
const squareIndices = i => ({
  row: CATS.indexOf(grid.rows[Math.floor(i / 3)]),
  col: CATS.indexOf(grid.cols[i % 3]),
});

async function recordPick(i, p) {
  try {
    const { percent } = await tally({ square: squareKey(i), pick: String(p.id), ...squareIndices(i) });
    const st = grid.cells[i];
    if (!st || !st.ok || st.p.id !== p.id) return;   // undone or replaced meanwhile
    if (typeof percent !== 'number') return;
    st.rarity = percent;
    st.tier = tierFor(st.rarity);
    render();
    if (!$('done-overlay').hidden) renderDone();
  } catch (e) { /* no tally API available */ }
}

function unrecordPick(i, p) {
  tally({ square: squareKey(i), pick: String(p.id), undo: true, ...squareIndices(i) }).catch(() => {});
}

function renderLegend() {
  $('legend').innerHTML = TIERS.map(t =>
    `<span class="legend-item"><i class="${t.cls}"></i>${t.name}</span>`).join('');
}

/* --------------------------------------------------------- guess sheet --- */

function openSheet(i) {
  if (over) return;
  active = i;
  const row = grid.rows[Math.floor(i / 3)];
  const col = grid.cols[i % 3];
  critFill('c-row', row);
  critFill('c-col', col);

  sheetMeta(i);
  $('sheet-miss').hidden = true;
  $('btn-undo-square').hidden = undoUsed || !touched(i);
  $('search').value = '';
  $('results').innerHTML = '';
  $('overlay').hidden = false;
  $('search').focus();
}

// Mirrors catCell: a plain type clue shows its icon alone.
function critFill(id, cat) {
  const solo = cat.family === 'type';
  $(id + '-icon').innerHTML =
    cat.icon ? typeIcon(cat.icon, solo ? 'crit-icon-solo' : 'crit-icon') : '';
  $(id + '-top').textContent = solo ? '' : cat.top;
  $(id).textContent = solo ? '' : cat.main;
}

function sheetMeta(i) {
  const n = intersectCount(grid.rows[Math.floor(i / 3)], grid.cols[i % 3]);
  $('answer-count').textContent =
    `${n} possible answer${n === 1 ? '' : 's'} · ` +
    (grid.retried[i] ? 'retry spent' : 'one free retry here');
}

function closeSheet() { $('overlay').hidden = true; active = null; }

function searchPokemon(q) {
  const n = norm(q);
  if (!n) return [];
  const starts = [], contains = [];
  for (const p of POKE) {
    if (p.searchKey.startsWith(n)) starts.push(p);
    else if (p.searchKey.includes(n)) contains.push(p);
    if (starts.length > 40) break;
  }
  return starts.concat(contains).slice(0, 30);
}

function renderResults(list) {
  const ul = $('results');
  ul.innerHTML = '';
  selIndex = 0;
  if (!list.length) {
    ul.innerHTML = '<li class="empty">No Pokémon found.</li>';
    return;
  }
  list.forEach((p, i) => {
    const li = document.createElement('li');
    if (i === 0) li.className = 'sel';
    li.innerHTML =
      pokeImg(p, null, true) +
      `<span><span class="rname">${p.name}</span><br>` +
      `<span class="rmeta">#${p.dex}</span></span>`;
    li.addEventListener('click', () => submit(p));
    ul.appendChild(li);
  });
}

function submit(p) {
  if (active === null || over) return;
  if (window.Social?.ranked) { Social.play('guess', active, p.id); return; }
  const i = active;

  if (grid.cells.some(c => c && c.ok && c.p.id === p.id)) {
    $('search').value = '';
    renderResults([]);
    $('results').innerHTML = '<li class="empty">Already used on this grid.</li>';
    return;
  }

  const row = grid.rows[Math.floor(i / 3)];
  const col = grid.cols[i % 3];
  const missRow = !row.test(p), missCol = !col.test(p);
  const ok = !missRow && !missCol;

  if (ok) {
    grid.cells[i] = { ok: true, p };
    guessesLeft--;
    grid.spent[i]++;
    recordPick(i, p);
    closeSheet();
    render();
    const why = [row, col]
      .filter(c => c.family === 'immune' && p.immuneVia[c.main])
      .map(c => `${c.main} via ${p.immuneVia[c.main]}`);
    toast(`<b>${p.name}</b> fits${why.length ? ': immune to ' + why.join(' and ') : ''}.`);
  } else if (!grid.retried[i]) {
    // First miss on a square is free: spend its retry and stay open for another go.
    // The note deliberately does not say which half failed.
    grid.retried[i] = true;
    render();
    sheetMeta(i);
    $('btn-undo-square').hidden = undoUsed || !touched(i);
    $('sheet-miss').textContent = `${p.name} is not a match. Retry used, try again.`;
    $('sheet-miss').hidden = false;
    $('search').value = '';
    $('results').innerHTML = '';
    $('search').focus();
    return;
  } else {
    guessesLeft--;
    grid.spent[i]++;
    closeSheet();
    render();
    const cell = $('board').children[5 + Math.floor(i / 3) * 4 + (i % 3)];
    if (cell) { cell.classList.add('shake'); setTimeout(() => cell.classList.remove('shake'), 300); }
  }

  if (guessesLeft <= 0 || grid.cells.filter(x => x && x.ok).length === 9) finish();
}

/* ---------------------------------------------------------------- undo --- */
// One undo per grid. You choose which filled square it applies to, finished
// board or not, and confirm before it is spent.
// A square is worth undoing once it has been filled, missed on, or has spent
// its free retry.
function touched(i) {
  return !!grid.cells[i] || grid.spent[i] > 0 || grid.retried[i];
}

function requestUndo(i) {
  if (undoUsed || !touched(i)) return;
  pendingUndo = i;

  const st = grid.cells[i];
  const n = grid.spent[i];
  const gains = [];
  if (n) gains.push(`${n} guess${n === 1 ? '' : 'es'} handed back`);
  if (grid.retried[i]) gains.push('its free retry restored');

  const what = st && st.ok ? `${st.p.name} will be cleared` : 'This square resets to untouched';
  $('confirm-sub').textContent =
    `${what}, with ${gains.join(' and ')}. You only get one undo.`;
  $('confirm-overlay').hidden = false;
}

function cancelUndo() { pendingUndo = null; $('confirm-overlay').hidden = true; }

function applyUndo() {
  if (pendingUndo === null || undoUsed) return;
  if (window.Social?.ranked) { Social.play('undo', pendingUndo); return; }
  const i = pendingUndo;
  const st = grid.cells[i];
  if (st && st.ok) unrecordPick(i, st.p);   // an undone answer should not count
  guessesLeft += grid.spent[i];   // refund everything this square cost
  grid.cells[i] = null;
  grid.spent[i] = 0;
  grid.retried[i] = false;
  grid.reveal = null;
  undoUsed = true;
  closeSheet();
  over = false;            // an undone square reopens a finished board
  pendingUndo = null;
  $('confirm-overlay').hidden = true;
  $('done-overlay').hidden = true;
  render();
}

/* -------------------------------------------------------------- finish --- */

function finish() {
  over = true;
  grid.reveal = grid.cells.map((st, i) => {
    if (st && st.ok) return null;
    const opts = intersectList(grid.rows[Math.floor(i / 3)], grid.cols[i % 3]);
    if (!opts.length) return null;
    const pick = opts[Math.floor(Math.random() * opts.length)];
    return { id: pick.id, dex: pick.dex, name: pick.name, n: opts.length };
  });
  render();   // also saves, reveal included, so a reload shows the same answers
  showDone();
}

function showDone() {
  const filled = grid.cells.filter(x => x && x.ok).length;
  $('done-title').textContent = filled === 9 ? 'Perfect grid!' : `${filled} / 9`;
  $('done-sub').textContent = filled === 9
    ? 'Every square filled.'
    : 'Out of guesses. Here is one answer for each empty square.';
  closeAnswers();
  renderDone();
  $('done-hint').textContent = undoUsed
    ? ''
    : 'Still have your undo. Close this and tap a filled square to take one back.';
  $('done-overlay').hidden = false;
}

/* ---------------------------------------------------------- all answers ---
 * After a game, any square of the summary opens every valid answer for that
 * clue pair, most-picked first when the tally service is reachable. */
let answersTicket = 0;

async function showAnswers(i) {
  const row = grid.rows[Math.floor(i / 3)], col = grid.cols[i % 3];
  const opts = intersectList(row, col);
  const mine = grid.cells[i] && grid.cells[i].ok ? grid.cells[i].p.id : null;
  const label = c => escHtml(c.family === 'type' ? c.main : `${c.top} ${c.main}`);
  $('answers-title').innerHTML = `${label(row)} <span class="crit-x">&times;</span> ${label(col)}`;
  $('answers-meta').textContent = `${opts.length} valid answer${opts.length === 1 ? '' : 's'}`;
  $('done-main').hidden = true;
  $('done-answers').hidden = false;
  $('answers-list').scrollTop = 0;

  // `shares` maps id -> percent; null while loading or when unavailable.
  const draw = shares => {
    const s = shares || {};
    const list = opts.slice().sort((a, b) =>
      (s[b.id] || 0) - (s[a.id] || 0) || a.dex - b.dex || a.id - b.id);
    $('answers-list').innerHTML = list.map(p => {
      const pct = shares ? s[p.id] || 0 : null;
      const tier = pct == null ? '' : ` ${tierFor(pct).cls}`;
      const share = pct == null ? '' : `<span class="ans-pct${tier}">${fmtPct(pct)}</span>`;
      return `<li class="${p.id === mine ? 'mine' : ''}">${pokeImg(p, null, true)}` +
        `<span class="rname">${escHtml(p.name)}${p.id === mine ? ' <em>your pick</em>' : ''}</span>${share}</li>`;
    }).join('');
  };
  draw(null);
  $('answers-note').textContent = 'Loading how often each answer is picked…';

  const ticket = ++answersTicket;
  try {
    const { row, col } = squareIndices(i);
    const res = await SupokuAPI.request(`/api/answers?row=${row}&col=${col}`);
    if (!res.ok) throw new Error(res.status);
    const { shares, total } = await res.json();
    if (ticket !== answersTicket || $('done-answers').hidden) return;
    const byId = {};
    for (const [id, v] of Object.entries(shares || {})) byId[+id] = v;
    draw(byId);
    $('answers-note').textContent = total
      ? `Estimated pick rates: a 2025 fan survey of Pokémon popularity, adjusted by ${total} real pick${total === 1 ? '' : 's'} here.`
      : 'Estimated pick rates from a 2025 fan survey of Pokémon popularity. Nobody has answered this square yet.';
  } catch (e) {
    if (ticket === answersTicket) $('answers-note').textContent = 'Pick rates are unavailable right now.';
  }
}

function closeAnswers() {
  answersTicket++;
  $('done-answers').hidden = true;
  $('done-main').hidden = false;
}

function renderDone() {
  // Tallies arrive after the grid is finished, so the score is computed here
  // rather than once in finish() -- renderDone re-runs when each one lands.
  const scored = grid.cells.filter(c => c && c.ok && c.rarity != null);
  $('done-score').textContent = scored.length
    ? `Rarity score ${scored.reduce((sum, c) => sum + c.rarity, 0).toFixed(1)} ` +
      `across ${scored.length} scored square${scored.length === 1 ? '' : 's'} (lower is rarer)`
    : '';
  if (window.Social?.ranked && Social.state) {
    $('done-score').textContent = `${Social.state.points} leaderboard points · ${Social.state.mistakes} wrong guesses`;
  }

  const dg = $('done-grid');
  dg.innerHTML = '';
  for (let i = 0; i < 9; i++) {
    const st = grid.cells[i];
    const d = document.createElement('button');
    d.type = 'button';
    d.title = 'See every answer for this square';
    d.addEventListener('click', () => showAnswers(i));
    if (st && st.ok) {
      d.innerHTML = `${pokeImg(st.p)}<span>${st.p.name}</span>`;
    } else {
      const r = grid.reveal && grid.reveal[i];
      d.innerHTML = r
        ? `${pokeImg(r, 'faded')}<span class="miss-txt">${r.name}<br>(${r.n} worked)</span>`
        : '<span class="miss-txt">None</span>';
    }
    dg.appendChild(d);
  }
}

/* ------------------------------------------------------------ settings --- */

function setPixelArt(on) {
  pixelArt = on;
  document.body.classList.toggle('pixel-art', on);
  $('opt-sprites').checked = on;
  try { localStorage.setItem(PIXEL_KEYS[0], on ? '1' : '0'); } catch (e) { /* blocked */ }

  render();
  if (!$('overlay').hidden) renderResults(searchPokemon($('search').value));
  if (!$('done-overlay').hidden) renderDone();
}

function toggleSettings(show) {
  const pop = $('settings-pop');
  const open = show === undefined ? pop.hidden : show;
  pop.hidden = !open;
  $('btn-settings').setAttribute('aria-expanded', open ? 'true' : 'false');
}

/* --------------------------------------------------------- new puzzle --- */

// Highlights the mode button and labels the puzzle.
function setModeUI(kind, day) {
  $('btn-daily').classList.toggle('is-active', kind === 'daily');
  $('btn-archive').classList.toggle('is-active', kind === 'archive');
  $('btn-random').classList.toggle('is-active', kind === 'random');
  $('puzzle-id').textContent =
    kind === 'random' ? 'random grid' : kind === 'archive' ? `${day} · archive` : day;
}

function startGrid(meta, g) {
  pendingUndo = null;
  grid = {
    ...meta,
    rows: g.rows, cols: g.cols,
    cells: new Array(9).fill(null),
    retried: new Array(9).fill(false),
    spent: new Array(9).fill(0),   // guesses this square has consumed
  };
  guessesLeft = 9;
  over = false;
  undoUsed = false;
  closeSheet();
  $('confirm-overlay').hidden = true;
  $('done-overlay').hidden = true;
  setModeUI(meta.kind, meta.day);
}

// mode 'daily' plays today's grid, or the archived grid for `day`. A daily or
// archive grid resumes from its save; Random always deals a fresh grid.
function newGame(mode, day) {
  const today = todayUTC();
  if (mode === 'daily' && (!day || day > today)) day = today;
  if (window.Social?.user && mode === 'daily' && day === today) { Social.loadDaily(); return; }
  if (window.Social) Social.ranked = false;

  const kind = mode === 'random' ? 'random' : day === today ? 'daily' : 'archive';
  if (kind !== 'random' && loadSaved('daily:' + day)) {
    if (grid.kind !== kind) { grid.kind = kind; setModeUI(kind, day); saveGame(); }
    return;
  }
  // The seed prefix stays on the old name on purpose: changing it would
  // reshuffle every daily puzzle, including ones already played.
  const seed = kind === 'random' ? String(Math.random()) : day;
  const g = generateGrid(hashStr('pokegrid-' + seed));
  if (!g) { $('hint').textContent = 'Could not build a grid. Try again.'; return; }
  startGrid({ kind, day: kind === 'random' ? null : day, seed }, g);
  render();
}

// On load, return to whatever was being played, unless it was a daily that
// has since rolled over: that becomes today's daily instead.
function resumeOrStart() {
  let key = null;
  try { key = localStorage.getItem(CURRENT_KEY); } catch (e) { /* blocked */ }
  if (key === 'random' && loadSaved('random')) return;
  if (key && key.startsWith('daily:')) {
    const day = key.slice(6);
    const s = readSave(key);
    if (s && s.kind === 'archive') { newGame('daily', day); return; }
  }
  newGame('daily');
}

/* ------------------------------------------------------------- archive --- */
// Earliest date the archive offers. Any date generates a grid; this keeps the
// picker to a sensible range.
const ARCHIVE_START = '2025-01-01';
const ARCHIVE_LIST_DAYS = 30;

function dayStatus(day) {
  const s = readSave('daily:' + day);
  if (!s) return { cls: '', text: 'Not played' };
  const filled = s.cells.filter(Boolean).length;
  if (s.over) return { cls: filled === 9 ? 'won' : 'done', text: filled === 9 ? '9/9 ✓' : `${filled}/9` };
  return { cls: 'progress', text: `In progress · ${filled}/9` };
}

function openArchive() {
  const today = todayUTC();
  const input = $('archive-date');
  input.min = ARCHIVE_START;
  input.max = today;
  if (!input.value) input.value = today;
  const ul = $('archive-list');
  ul.innerHTML = '';
  const d = new Date(today + 'T00:00:00Z');
  for (let k = 0; k < ARCHIVE_LIST_DAYS; k++) {
    const day = d.toISOString().slice(0, 10);
    if (day < ARCHIVE_START) break;
    const st = dayStatus(day);
    const ranked = k === 0 && window.Social?.user;
    const li = document.createElement('li');
    li.innerHTML = `<button type="button"><span class="arch-day">${k === 0 ? 'Today' : day}` +
      `${k === 0 ? ` <small>${day}</small>` : ''}</span>` +
      `<span class="arch-status ${ranked ? '' : st.cls}">${ranked ? 'Ranked daily' : st.text}</span></button>`;
    li.firstChild.addEventListener('click', () => { closeArchive(); newGame('daily', day); });
    ul.appendChild(li);
    d.setUTCDate(d.getUTCDate() - 1);
  }
  $('archive-overlay').hidden = false;
}

function closeArchive() { $('archive-overlay').hidden = true; }

/* ----------------------------------------------------------- countdown --- */
function tickCountdown() {
  const now = new Date();
  const next = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + 1);
  const s = Math.max(0, Math.floor((next - now.getTime()) / 1000));
  const pad = n => String(n).padStart(2, '0');
  const text = `Next daily in ${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}`;
  $('next-daily').textContent = text;
  $('done-next').textContent = text;
}

/* ----------------------------------------------------------- bootstrap --- */

async function init() {
  DATA = await (await fetch('data/pokedex.json')).json();
  POKE = DATA.pokemon;
  POKE_BY_ID = new Map(POKE.map(p => [p.id, p]));
  WORDS = Math.ceil(POKE.length / 32);

  // Species that have at least one Mega form, for the "Has a Mega Evolution" clue.
  const megaSpecies = new Set(POKE.filter(p => p.mega).map(p => p.dex));
  for (const p of POKE) {
    p.moveSet = new Set(p.moves);
    p.searchKey = norm(p.name + p.slug);
    p.hasMega = megaSpecies.has(p.dex);
    p.homeRegion = homeRegion(p);
  }

  CATS = buildCategories();
  POOL = CATS.filter(c => c.n >= 8);

  let saved = null;
  try {
    for (const k of PIXEL_KEYS) {
      saved = localStorage.getItem(k);
      if (saved !== null) break;
    }
  } catch (e) { /* blocked */ }
  pixelArt = saved === '1';
  document.body.classList.toggle('pixel-art', pixelArt);
  $('opt-sprites').checked = pixelArt;

  $('loading').hidden = true;
  $('app').hidden = false;

  $('opt-sprites').addEventListener('change', e => setPixelArt(e.target.checked));
  $('btn-settings').addEventListener('click', e => { e.stopPropagation(); toggleSettings(); });
  document.addEventListener('click', e => {
    if (!$('settings-pop').hidden && !$('settings-pop').contains(e.target)) toggleSettings(false);
  });
  document.addEventListener('keydown', e => { if (e.key === 'Escape') toggleSettings(false); });

  $('btn-daily').addEventListener('click', () => newGame('daily'));
  $('btn-random').addEventListener('click', () => newGame('random'));
  $('btn-archive').addEventListener('click', openArchive);
  $('archive-close').addEventListener('click', closeArchive);
  $('archive-overlay').addEventListener('click', e => {
    if (e.target === $('archive-overlay')) closeArchive();
  });
  $('archive-form').addEventListener('submit', e => {
    e.preventDefault();
    const day = $('archive-date').value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(day) || day < ARCHIVE_START || day > todayUTC()) {
      $('archive-date').reportValidity();
      return;
    }
    closeArchive();
    newGame('daily', day);
  });
  $('answers-back').addEventListener('click', closeAnswers);
  $('btn-again').addEventListener('click', () => newGame('random'));
  $('btn-undo-square').addEventListener('click', () => {
    if (active !== null) requestUndo(active);
  });
  $('btn-confirm-yes').addEventListener('click', applyUndo);
  $('btn-confirm-no').addEventListener('click', cancelUndo);
  $('confirm-overlay').addEventListener('click', e => {
    if (e.target === $('confirm-overlay')) cancelUndo();
  });
  $('done-close').addEventListener('click', () => { $('done-overlay').hidden = true; });
  $('done-overlay').addEventListener('click', e => {
    if (e.target === $('done-overlay')) $('done-overlay').hidden = true;
  });
  $('btn-giveup').addEventListener('click', () => {
    if (window.Social?.ranked) { if (!over) Social.play('giveup'); return; }
    if (!over) { guessesLeft = 0; finish(); }
  });
  $('sheet-close').addEventListener('click', closeSheet);
  document.addEventListener('keydown', e => {
    if (e.key !== 'Escape') return;
    if (!$('archive-overlay').hidden) closeArchive();
    else if (!$('done-answers').hidden) closeAnswers();
  });
  $('overlay').addEventListener('click', e => { if (e.target === $('overlay')) closeSheet(); });

  const input = $('search');
  input.addEventListener('input', () => renderResults(searchPokemon(input.value)));
  input.addEventListener('keydown', e => {
    const items = [...$('results').querySelectorAll('li:not(.empty)')];
    if (e.key === 'Escape') return closeSheet();
    if (!items.length) return;
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      items[selIndex].classList.remove('sel');
      selIndex = (selIndex + (e.key === 'ArrowDown' ? 1 : items.length - 1)) % items.length;
      items[selIndex].classList.add('sel');
      items[selIndex].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      e.preventDefault();
      items[selIndex].click();
    }
  });

  renderLegend();
  tickCountdown();
  setInterval(tickCountdown, 1000);
  resumeOrStart();
  window.supokuReady = true;
  window.dispatchEvent(new Event('supoku-ready'));
}

init();
