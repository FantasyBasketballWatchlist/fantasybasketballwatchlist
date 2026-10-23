// Replays the six real drafts (docs/prereg-draft-steal.md) on the draft page's own engine (templates/draft.html, from
// `const totalPicks` to `// ---------- team evaluation`) and scores each slot-draft by the 400-night season simulation.
//   python -m analysis.draft_steal_data <dir>; node analysis/draft_steal_replay.js <dir> . <variant> [leagues]
// variants: current (STEAL off), page (the page as is), steal / logit (lasting chance overridden: old normal / logistic),
//           commit / logitcommit (the harness takes T at the next pick if he's there). Writes <dir>/replay_<variant>.json.
const fs = require('fs');
const [SP, REPO, VARIANT, LGS] = process.argv.slice(2);
const P = JSON.parse(fs.readFileSync(`${SP}/players.json`, 'utf8'));
const L = JSON.parse(fs.readFileSync(`${SP}/leagues.json`, 'utf8'));
const W = JSON.parse(process.env.LOGIT_W || '[-0.334,-13.743,1.751]');

const html = fs.readFileSync(`${REPO}/templates/draft.html`, 'utf8');
const common = fs.readFileSync(`${REPO}/static/common.js`, 'utf8');
const grab = (src, a, b) => src.slice(src.indexOf(a), src.indexOf(b));
let engine = grab(html, 'const totalPicks', '// ---------- team evaluation');
const sub = (a, b) => { if (!engine.includes(a)) throw new Error('missing: ' + a); engine = engine.replace(a, b); };
sub('if (steal) {', 'if (steal) { H.lastSteal = steal;');
if (VARIANT !== 'page') {          // the first version: no follow-through, lasting chance from H.pLast
  sub('const plan = STEAL ? stealPlan(pool, at) : null;', 'const plan = null;');
  sub('const p = lastChance(t.adp, now, next);', 'const p = H.pLast(t, now, next);');
}
const helpers = grab(common, 'const LINEUP_FITS', '// Autocomplete');
const pre = `const normalizeString = (s) => s.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
  const DEFAULT_LINEUP = 'PG,SG,SF,PF,C,G,F,UTIL,UTIL,UTIL', POSITIONS = ['PG','SG','SF','PF','C'];
  let players = H.players, byId = new Map(players.map(p => [p.id, p])), positions = H.positions;
  let state = { teams: 10, slot: 1, rounds: 13, lineup: DEFAULT_LINEUP, picks: {}, history: [], names: {} };
  const requestAnimationFrame = () => 0, performance = { now: () => 0 }, save = () => {}, render = () => {}, fmt = (x) => (+x).toFixed(1);`;
const H = { players: P.players.slice().sort((a, b) => b.bpv - a.bpv), positions: P.positions };
const E = new Function('H', helpers + pre + engine + `
  return { set: (s) => { state = s; lookCache = { key: null, value: null }; }, lookAhead, fillLineup, fillSlots, posOf, teamOf, fits,
           setSteal: (v) => { STEAL = v; } };`)(H);

const key = (n) => n.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/\./g, '').replace(/-/g, ' ')
  .replace(/'/g, '').replace(/\s+(jr|sr|ii|iii|iv)$/, '').replace(/\s+/g, ' ').trim();
const byKey = new Map(H.players.map(p => [key(p.name), p]));
const logit = (t, now, next) => 1 / (1 + Math.exp(-(W[0] + W[1] * Math.log(next / t.adp) + W[2] * Math.log(now / t.adp))));
E.setSteal(VARIANT !== 'current');
// The first version's lasting chance: ln(actual pick / ESPN ADP) ~ Normal(-0.095, 0.211) in the design leagues.
const normCdf = (z) => { const t = 1 / (1 + 0.2316419 * Math.abs(z)), d = 0.3989423 * Math.exp(-z * z / 2);
  const q = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274)))); return z > 0 ? 1 - q : q; };
H.pLast = VARIANT.startsWith('logit') ? logit : (t, now, next) => 1 - normCdf((Math.log(next / t.adp) + 0.095) / 0.211);
const COMMIT = VARIANT.endsWith('commit');

// Season score (docs/prereg-draft-suggestion-v2.md): 400 nights, game with prob 0.5, plays with prob availability,
// best lineup by per-game production, empty spots 0. Seeded per (night, player) so every version sees the same nights.
const SLOTS = 'PG,SG,SF,PF,C,G,F,UTIL,UTIL,UTIL'.split(',');
function rnd(a, b) { let t = (Math.imul(a, 2654435761) ^ Math.imul(b + 0x9E3779B9, 2246822519)) >>> 0;
  t = Math.imul(t ^ (t >>> 15), 1 | t); t ^= t + Math.imul(t ^ (t >>> 7), 61 | t); return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
function season(ids) {
  const byId = new Map(H.players.map(p => [p.id, p]));
  let total = 0;
  for (let night = 0; night < 400; night++) {
    const on = ids.filter(id => rnd(night, id) < 0.5 && rnd(night + 100000, id) < (byId.get(id).availability ?? 1));
    const f = E.fillSlots(on, SLOTS, E.posOf, id => byId.get(id).production ?? 0);
    f.slotOf.forEach((_, id) => { total += byId.get(id).production ?? 0; });
  }
  return total / 400;
}

const out = [];
for (const lg of (LGS || Object.keys(L).join(',')).split(',')) {
  const order = L[lg].picks.map(([, name]) => byKey.get(key(name))?.id).filter(id => id != null);
  for (let slot = 1; slot <= 10; slot++) {
    const st = { teams: 10, slot, rounds: 13, lineup: 'PG,SG,SF,PF,C,G,F,UTIL,UTIL,UTIL', picks: {}, history: [], names: {} };
    const taken = new Set(), mine = [], others = {}, events = [];
    let plan = null;                       // the steal we're following: {t, next}
    for (let n = 1; n <= 130; n++) {
      const t = E.teamOf(n);
      let id;
      if (t === slot) {
        E.set(st);
        const avail = H.players.filter(p => !taken.has(p.id));
        if (plan && plan.next === n) {
          const there = !taken.has(plan.t.id);
          events.at(-1).lasted = there;
          if (there && COMMIT) { id = plan.t.id; events.at(-1).took = true; }
        }
        if (id == null) {
          H.lastSteal = null;
          id = E.lookAhead(avail, mine, n).pick.id;
          if (plan && plan.next === n) events.at(-1).took = id === plan.t.id;
          plan = null;
          if (H.lastSteal) { plan = { t: H.lastSteal.t, next: H.lastSteal.next };
            events.push({ n, next: plan.next, adp: plan.t.adp, p: H.lastSteal.p, gain: H.lastSteal.gain }); }
        } else plan = null;
        mine.push(id);
      } else {
        const ros = others[t] = others[t] || [];
        const left = order.filter(x => !taken.has(x));
        const open = E.fillLineup(ros).openSpecific;
        id = (open.length && left.slice(0, 6).find(x => open.some(s => E.fits(s, E.posOf(x))))) ?? left[0]
          ?? H.players.find(p => !taken.has(p.id)).id;
        ros.push(id);
      }
      taken.add(id); st.picks[n] = id; st.history.push(n);
    }
    out.push({ lg, slot, v: season(mine), events });
    process.stderr.write(`${lg} ${slot} ${out.at(-1).v.toFixed(2)} steals ${events.length}\n`);
  }
}
fs.writeFileSync(`${SP}/replay_${VARIANT}.json`, JSON.stringify(out));
