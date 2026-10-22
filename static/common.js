// Helpers shared by all pages.
const fmt = (value, digits = 1) => (value === null || value === undefined || Number.isNaN(value)) ? 'N/A' : Number(value).toFixed(digits);
const pct = (value) => (value === null || value === undefined) ? 'N/A' : `${Math.round(value * 100)}%`;
const escapeHtml = (text) => String(text ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
const normalizeString = (str) => str.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

// Tiers by overall rank. 130 = every roster spot in a 10-team, 13-player league.
// name: Stephen Curry gets his own tier while ratings.CURRY_MODE is on (he only ranks first when it is).
function tierOf(rank, name) {
  if (name === 'Stephen Curry' && rank === 1) return { key: 'chef', label: 'Stephen Curry' };
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

// ---------- Your leagues
// Every league (its draft and its teams) is saved in this browser's localStorage, so each computer keeps its own.
// One league is active at a time; the Draft and Teams pages read and write the active one.
const LEAGUES_KEY = 'hoop-leagues-v1';
const OLD_KEYS = { draft: 'bpv-draft-v1', teams: 'bpv-league-v1' };   // before leagues existed: one draft, one league

const Leagues = {
  read() {
    let data = null;
    try { data = JSON.parse(localStorage.getItem(LEAGUES_KEY)); } catch (e) {}
    if (!data || !Array.isArray(data.leagues) || !data.leagues.length) {
      // First visit since leagues were added: whatever draft and teams this browser had become "My league".
      const old = {};
      for (const [kind, key] of Object.entries(OLD_KEYS)) {
        try { old[kind] = JSON.parse(localStorage.getItem(key)) || null; } catch (e) { old[kind] = null; }
      }
      const first = Leagues.blank('My league');
      first.draft = old.draft; first.teams = old.teams;
      data = { active: first.id, leagues: [first] };
      Leagues.write(data);
    }
    if (!data.leagues.some(l => l.id === data.active)) data.active = data.leagues[0].id;
    return data;
  },
  write(data) { try { localStorage.setItem(LEAGUES_KEY, JSON.stringify(data)); return true; } catch (e) { return false; } },
  blank(name) {
    const now = new Date().toISOString();
    return { id: `L${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, name, created: now, updated: now, draft: null, teams: null };
  },
  active() { const d = Leagues.read(); return d.leagues.find(l => l.id === d.active); },
  get(kind) { return Leagues.active()[kind] || null; },
  set(kind, value) {
    const d = Leagues.read(), l = d.leagues.find(x => x.id === d.active);
    l[kind] = value; l.updated = new Date().toISOString();
    return Leagues.write(d);
  },
  uniqueName(d, base) {
    let name = base, k = 2;
    while (d.leagues.some(l => l.name === name)) name = `${base} ${k++}`;
    return name;
  },
  create(name) {
    const d = Leagues.read();
    const l = Leagues.blank(Leagues.uniqueName(d, (name || '').trim() || `League ${d.leagues.length + 1}`));
    d.leagues.push(l); d.active = l.id; Leagues.write(d);
    return l;
  },
  switchTo(id) { const d = Leagues.read(); if (d.leagues.some(l => l.id === id)) { d.active = id; Leagues.write(d); } },
  rename(id, name) {
    const d = Leagues.read(), l = d.leagues.find(x => x.id === id);
    if (l && name.trim()) { l.name = name.trim().slice(0, 40); Leagues.write(d); }
  },
  // Write one kind (draft / teams) of any league, active or not.
  setFor(id, kind, value) {
    const d = Leagues.read(), l = d.leagues.find(x => x.id === id);
    if (!l) return false;
    l[kind] = value; l.updated = new Date().toISOString();
    return Leagues.write(d);
  },
  // The drafted rosters as teams: pick n belongs to the team in draft slot owners[n] (ESPN's record, which handles traded
  // picks) or else to the snake order. Team names are ESPN's when the draft was synced with ESPN.
  teamsFromDraft(d, lineup) {
    const n = d.teams;
    const snake = (k) => { const r = Math.floor((k - 1) / n), i = (k - 1) % n; return r % 2 === 0 ? i + 1 : n - i; };
    const slotOf = (k) => (d.owners && d.owners[k]) || snake(k);
    const teams = [];
    for (let t = 1; t <= n; t++) {
      const ids = Object.entries(d.picks || {}).filter(([k, id]) => slotOf(+k) === t && id > 0)
        .sort((a, b) => a[0] - b[0]).map(([, id]) => id);
      teams.push({ name: (d.teamNames && d.teamNames[t - 1]) || (t === d.slot ? 'Your team' : `Team ${t}`), ids });
    }
    return { teams, lineup: lineup || d.lineup || 'PG,SG,SF,PF,C,G,F,UTIL,UTIL,UTIL', mine: Math.max(0, (d.slot || 1) - 1),
      trades: [], draftIds: teams.map(t => t.ids), draftNames: teams.map(t => t.name) };
  },
  // A league's teams, filled from its draft automatically: when there are none yet, or when they still are exactly what
  // an earlier version of the draft produced (no trades or roster edits since) and the draft has moved on. Teams someone
  // edited are left alone (the Your leagues page can still replace them).
  teamsFor(l) {
    if (!l) return null;
    const t = l.teams, d = l.draft;
    if (!d || !d.picks || !Object.keys(d.picks).length || (t && t.manual)) return t;
    const has = t && Array.isArray(t.teams) && t.teams.some(x => x.ids && x.ids.length);
    const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
    const untouched = has && t.draftIds && !(t.trades || []).length && same(t.teams.map(x => x.ids), t.draftIds);
    if (has && !untouched) return t;
    const built = Leagues.teamsFromDraft(d, t && t.lineup);
    if (untouched) {
      if (same(built.draftIds, t.draftIds) && same(built.draftNames, t.draftNames)) return t;
      built.mine = t.mine ?? built.mine;
      // Keep names someone typed; take the draft's new names (e.g. ESPN's) for the rest.
      built.teams.forEach((x, i) => { if (t.teams[i] && t.draftNames && t.teams[i].name !== t.draftNames[i]) x.name = t.teams[i].name; });
    }
    Leagues.setFor(l.id, 'teams', built);
    return built;
  },
  remove(id) {
    const d = Leagues.read();
    d.leagues = d.leagues.filter(l => l.id !== id);
    if (!d.leagues.length) d.leagues.push(Leagues.blank('My league'));
    if (d.active === id) d.active = d.leagues[0].id;
    Leagues.write(d);
  },
};

// League switcher shown at the top of the Draft and Teams pages. onSwitch() is called after the active league changes.
function leagueBar(el, onSwitch) {
  const draw = () => {
    const d = Leagues.read();
    el.innerHTML = `<label>League <select aria-label="Active league">${d.leagues.map(l =>
        `<option value="${l.id}"${l.id === d.active ? ' selected' : ''}>${escapeHtml(l.name)}</option>`).join('')}</select></label>
      <input class="lb-name" value="${escapeHtml(Leagues.active().name)}" maxlength="40" aria-label="League name" title="Rename this league">
      <button class="btn small ghost lb-new" type="button">+ New league</button>
      <a class="lb-all" href="/leagues">Your leagues →</a>
      <span class="lb-note">Saved in this browser</span>`;
  };
  draw();
  el.addEventListener('change', e => {
    if (e.target.matches('select')) { Leagues.switchTo(e.target.value); draw(); onSwitch(); }
    else if (e.target.matches('.lb-name')) { Leagues.rename(Leagues.read().active, e.target.value); draw(); }
  });
  el.addEventListener('click', e => {
    if (e.target.closest('.lb-new')) { Leagues.create(); draw(); onSwitch(); el.querySelector('.lb-name').select(); }
  });
  // Another tab switched or renamed leagues.
  window.addEventListener('storage', e => { if (e.key === LEAGUES_KEY) draw(); });
  return { redraw: draw };
}

// ---------- Team updates (Teams and Waiver pages)
// News for one fantasy team: injury-report statuses, minutes and shooting changes over the last 5 games (minutes
// changes tend to last, shooting streaks fade), and free agents worth more than the team's weakest players.
// team / freeAgents: player objects from /api/rankings or /api/waiver. Returns [{cls, text}] (cls: urgent/warn/ok/'').
const UPDATE_THRESHOLD = 4, UPGRADE_MIN = 1, MAX_UPGRADES = 3;
function teamUpdates(team, freeAgents, threshold = UPDATE_THRESHOLD) {
  const out = [];
  const statusOrder = { Out: 0, Doubtful: 1, Questionable: 2, Probable: 3 };
  team.filter(p => p.report_status && p.report_status in statusOrder)
    .sort((a, b) => statusOrder[a.report_status] - statusOrder[b.report_status])
    .forEach(p => out.push({ cls: p.report_status === 'Out' || p.report_status === 'Doubtful' ? 'urgent' : 'warn',
      text: `${p.name}: ${p.report_status}${p.report_reason ? ` (${p.report_reason.replace(/^Injury\/Illness - /, '')})` : ''}.` }));
  team.filter(p => !p.report_status && p.injury_note).forEach(p => out.push({ cls: 'warn', text: `${p.name}: ${p.injury_note}.` }));
  team.forEach(p => {
    const mc = p.minutes_change_fpts, ec = p.efficiency_change_fpts;
    if (mc == null || ec == null) return;
    const when = p.basis === 'last_season' ? 'than last season' : 'lately';
    if (mc >= threshold) out.push({ cls: 'ok', text: `${p.name}: more minutes ${when} (+${fmt(mc)} FPTS/G from minutes). These gains tend to last.` });
    else if (mc <= -threshold) out.push({ cls: 'warn', text: `${p.name}: fewer minutes ${when} (${fmt(mc)} FPTS/G). Losing minutes usually lasts; check the news.` });
    else if (ec >= threshold) out.push({ cls: '', text: `${p.name}: hot shooting ${when} (+${fmt(ec)} FPTS/G at the same minutes). Usually fades: a sell-high chance.` });
    else if (ec <= -threshold) out.push({ cls: '', text: `${p.name}: cold shooting ${when} (${fmt(ec)} FPTS/G at the same minutes). Usually bounces back: hold.` });
  });
  const worst = team.filter(p => p.bpv != null).sort((a, b) => a.bpv - b.bpv);
  const best = (freeAgents || []).filter(p => p.bpv != null).sort((a, b) => b.bpv - a.bpv);
  for (let k = 0; k < Math.min(MAX_UPGRADES, worst.length, best.length); k++) {
    if (best[k].bpv - worst[k].bpv < UPGRADE_MIN) break;
    out.push({ cls: 'ok', text: `Free agent upgrade: ${best[k].name} (${fmt(best[k].bpv)} BPV) for ${worst[k].name} (${fmt(worst[k].bpv)}).` });
  }
  return out;
}

const renderUpdates = (items) => items.length
  ? items.map(a => `<div class="alert-item ${a.cls}">${escapeHtml(a.text)}</div>`).join('')
  : '<p class="help" style="margin:0">No news for this team.</p>';
