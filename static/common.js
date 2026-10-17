// Helpers shared by all pages.
const fmt = (value, digits = 1) => (value === null || value === undefined || Number.isNaN(value)) ? 'N/A' : Number(value).toFixed(digits);
const pct = (value) => (value === null || value === undefined) ? 'N/A' : `${Math.round(value * 100)}%`;
const escapeHtml = (text) => String(text ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const normalizeString = (str) => str.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Tiers by overall rank. 130 = every roster spot in a 10-team, 13-player league.
function tierOf(rank) {
  if (rank == null) return { key: 'waiver', label: 'Unranked' };
  if (rank <= 5) return { key: 'super', label: 'Superstar' };
  if (rank <= 20) return { key: 'allstar', label: 'All-Star' };
  if (rank <= 60) return { key: 'starter', label: 'Starter' };
  if (rank <= 130) return { key: 'roster', label: 'Rosterable' };
  return { key: 'waiver', label: 'Waiver wire' };
}

// Hot/cold chip from the last 5 games vs the season average.
function formChip(recent, season) {
  if (recent == null || season == null) return '';
  const d = recent - season;
  if (d >= 5) return `<span class="chip hot" title="Last 5 games: ${fmt(recent)} vs ${fmt(season)} season"><span class="flame">🔥</span>+${fmt(d)}</span>`;
  if (d <= -5) return `<span class="chip cold" title="Last 5 games: ${fmt(recent)} vs ${fmt(season)} season">❄ ${fmt(d)}</span>`;
  return '';
}

// Count a number up from 0 (short, requestAnimationFrame, skipped for reduced motion).
function countUp(el, to, digits = 1, ms = 700) {
  if (to == null || Number.isNaN(to)) { el.textContent = 'N/A'; return; }
  if (reducedMotion) { el.textContent = fmt(to, digits); return; }
  const start = performance.now();
  const step = (now) => {
    const t = Math.min(1, (now - start) / ms);
    el.textContent = fmt(to * (1 - Math.pow(1 - t, 3)), digits);
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

// Starting lineups. G = PG/SG, F = SF/PF, UTIL = anyone.
const LINEUP_FITS = { PG: ['PG'], SG: ['SG'], SF: ['SF'], PF: ['PF'], C: ['C'], G: ['PG', 'SG'], F: ['SF', 'PF'] };
const slotFits = (slot, ps) => slot === 'UTIL' || (LINEUP_FITS[slot] || []).some(x => ps.includes(x));

// Put players into starting slots, highest value first (augmenting paths so a dual-position player can move over).
// posOf(id) -> ['PG', 'SG'], valueOf(id) -> number. Returns the slot each starter fills and the slots left open.
function fillSlots(ids, slots, posOf, valueOf) {
  const owner = Array(slots.length).fill(null);
  const sorted = ids.slice().sort((a, b) => valueOf(b) - valueOf(a));
  const tryPlace = (id, seen) => {
    const ps = posOf(id);
    for (let i = 0; i < slots.length; i++) {
      if (seen.has(i) || !slotFits(slots[i], ps)) continue;
      seen.add(i);
      if (owner[i] == null || tryPlace(owner[i], seen)) { owner[i] = id; return true; }
    }
    return false;
  };
  sorted.forEach(id => tryPlace(id, new Set()));
  const slotOf = new Map(owner.map((id, i) => [id, slots[i]]).filter(([id]) => id != null));
  const open = slots.filter((_, i) => owner[i] == null);
  return { slotOf, open, openSpecific: open.filter(s => s !== 'UTIL') };
}

// Autocomplete with arrow keys. onPick(player) is called with the chosen player.
function wireAutocomplete(input, list, getPlayers, onPick, limit = 8) {
  let items = [], sel = -1;
  const render = () => {
    list.innerHTML = items.map((p, i) => `<div data-i="${i}" class="${i === sel ? 'sel' : ''}"><span>${escapeHtml(p.name)}</span><span class="team">${escapeHtml(p.team || '')}</span></div>`).join('');
  };
  const matches = () => {
    const q = normalizeString(input.value.trim());
    if (!q) return [];
    const all = getPlayers().filter(p => normalizeString(p.name).includes(q));
    return all.sort((a, b) => (normalizeString(b.name).startsWith(q) - normalizeString(a.name).startsWith(q)) || ((a.rank ?? 1e9) - (b.rank ?? 1e9))).slice(0, limit);
  };
  const pick = (p) => { if (!p) return; items = []; sel = -1; list.innerHTML = ''; onPick(p); };
  input.addEventListener('input', () => { items = matches(); sel = items.length ? 0 : -1; render(); });
  input.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown' && items.length) { sel = (sel + 1) % items.length; render(); e.preventDefault(); }
    else if (e.key === 'ArrowUp' && items.length) { sel = (sel - 1 + items.length) % items.length; render(); e.preventDefault(); }
    else if (e.key === 'Enter') { pick(items[sel] || matches()[0]); }
    else if (e.key === 'Escape') { items = []; list.innerHTML = ''; }
  });
  list.addEventListener('mousedown', e => {
    const row = e.target.closest('[data-i]');
    if (row) { e.preventDefault(); pick(items[+row.dataset.i]); }
  });
  input.addEventListener('blur', () => setTimeout(() => { list.innerHTML = ''; }, 100));
}
