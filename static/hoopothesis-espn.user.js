// ==UserScript==
// @name         Hoopothesis: live ESPN draft picks
// @namespace    https://hoopothesis.cc/
// @version      0.1.1
// @description  Reads picks from ESPN's fantasy basketball draft room as they happen and sends them to the Hoopothesis draft tracker (open in another tab). Beta: shows a debug panel you can copy if it misses picks.
// @match        https://fantasy.espn.com/*
// @match        https://hoopothesis.cc/*
// @match        http://localhost/*
// @match        http://127.0.0.1/*
// @run-at       document-start
// @grant        unsafeWindow
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM.setValue
// @grant        GM.getValue
// @updateURL    https://hoopothesis.cc/hoopothesis-espn.user.js
// @downloadURL  https://hoopothesis.cc/hoopothesis-espn.user.js
// ==/UserScript==

/*
 * Why this exists: ESPN's public league API shows no picks until a draft is over (recorded 2026-10-21: 0 picks for the
 * whole draft, then all 130 at once when it ended). The draft room itself gets every pick live, so this script runs
 * inside it and passes the picks on.
 *
 * How it finds picks (three ways, because ESPN's draft room isn't documented and this was written without seeing it):
 *   1. WebSocket messages: the draft room's live feed. Any text like "SELECTED <team> <player>" counts as a pick.
 *   2. JSON the page fetches (fetch / XHR): any object with a playerId and a pick number counts.
 *   3. Nothing is parsed from the page's HTML yet; the debug export records what the pick list looks like so a parser
 *      can be written from a real draft.
 * The debug panel (bottom right of the draft room) shows what each way has seen; "Copy debug" puts it all on the
 * clipboard (long tokens and query strings removed) to send over.
 *
 * Hand-off: picks are written to the userscript manager's storage (GM_setValue); the copy of this script running on the
 * Hoopothesis draft page reads them every 1.5 s and hands them to the page with window.postMessage.
 */
(function () {
  'use strict';
  const VERSION = '0.1.1';
  const KEY = 'hoop-espn-bridge-v1';
  const W = typeof unsafeWindow !== 'undefined' ? unsafeWindow : window;
  const host = location.hostname;

  const gmSet = (k, v) => (typeof GM_setValue === 'function' ? Promise.resolve(GM_setValue(k, v))
    : typeof GM !== 'undefined' && GM.setValue ? GM.setValue(k, v) : Promise.resolve(localStorage.setItem(k, v)));
  const gmGet = (k) => (typeof GM_getValue === 'function' ? Promise.resolve(GM_getValue(k, null))
    : typeof GM !== 'undefined' && GM.getValue ? GM.getValue(k, null) : Promise.resolve(localStorage.getItem(k)));

  // Long tokens, query strings and e-mail-like strings never go into the debug export.
  const redact = (s) => String(s).replace(/\?[^\s"']*/g, '?…').replace(/[A-Za-z0-9%+/=_-]{32,}/g, '[long-token]')
    .replace(/[\w.+-]+@[\w-]+\.[\w.]+/g, '[email]');
  const clip = (s, n = 300) => { s = String(s); return s.length > n ? s.slice(0, n) + `…(+${s.length - n})` : s; };

  if (host === 'fantasy.espn.com') espnSide();
  else hoopSide();

  // ------------------------------------------------------------------ ESPN draft room
  function espnSide() {
    const isDraftRoom = () => /\/draft/i.test(location.pathname);
    const params = new URLSearchParams(location.search);
    const dbg = {
      version: VERSION, started: new Date().toISOString(), page: location.pathname, league: params.get('leagueId'),
      hooks: {}, sockets: [], wsMessages: 0, wsSamples: [], wsKeywords: {}, http: [], picks: [], errors: [], dom: null,
    };
    const picks = new Map();            // key -> {overall, teamId, playerId, name, source, at}
    let seq = 0;

    const note = (where, e) => { dbg.errors.push(`${where}: ${clip(e && e.message || e, 200)}`); if (dbg.errors.length > 50) dbg.errors.shift(); };

    function addPick(p, source) {
      if (!p.playerId && !p.name) return;
      const key = p.playerId ? `id:${p.playerId}` : `name:${p.name}`;
      if (picks.has(key)) {                                   // already known: keep it, fill in a missing pick number
        const old = picks.get(key);
        if (old.overall == null && p.overall != null) old.overall = p.overall;
        return;
      }
      seq += 1;
      const pick = { overall: p.overall ?? null, seq, teamId: p.teamId ?? null, playerId: p.playerId ?? null,
        name: p.name ?? null, source, at: new Date().toISOString() };
      picks.set(key, pick);
      dbg.picks.push({ ...pick });
      if (dbg.picks.length > 400) dbg.picks.shift();
      publish();
    }

    // Way 1: text messages. "SELECTED <teamId> <playerId> ..." is the guess; any JSON message is searched too.
    function scanText(text, source) {
      const t = String(text);
      for (const kw of ['SELECTED', 'SELECTING', 'AUTODRAFT', 'PICK', 'CLOCK', 'DRAFT', 'TOKEN', 'JOINED', 'PING']) {
        if (t.includes(kw)) dbg.wsKeywords[kw] = (dbg.wsKeywords[kw] || 0) + 1;
      }
      const re = /\bSELECTED\s+(\d+)\s+(\d+)/g;
      let m;
      while ((m = re.exec(t))) addPick({ teamId: +m[1], playerId: +m[2] }, source);
      if (/^\s*[[{]/.test(t)) { try { scanJson(JSON.parse(t), source); } catch (e) { /* not JSON */ } }
    }

    // Way 2: any object with a playerId plus a pick number (overallPickNumber / pickNumber / overall).
    function scanJson(o, source, depth = 0) {
      if (!o || typeof o !== 'object' || depth > 12) return 0;
      let found = 0;
      if (Array.isArray(o)) { for (const x of o) found += scanJson(x, source, depth + 1); return found; }
      const pid = o.playerId ?? o.player_id;
      const num = o.overallPickNumber ?? o.overallPick ?? o.pickNumber ?? o.overall;
      if (Number(pid) > 0 && num != null && Number(num) > 0) {
        addPick({ playerId: +pid, overall: +num, teamId: o.teamId ?? null }, source);
        found += 1;
      }
      for (const k in o) if (o[k] && typeof o[k] === 'object') found += scanJson(o[k], source, depth + 1);
      return found;
    }

    function hookWebSocket() {
      const Orig = W.WebSocket;
      if (!Orig || Orig.__hoopHooked) return;
      function Hooked(url, protocols) {
        const ws = protocols === undefined ? new Orig(url) : new Orig(url, protocols);
        const rec = { url: redact(url), opened: new Date().toISOString(), messages: 0, sent: 0 };
        dbg.sockets.push(rec);
        ws.addEventListener('message', (ev) => {
          rec.messages += 1; dbg.wsMessages += 1;
          const data = typeof ev.data === 'string' ? ev.data : `[${Object.prototype.toString.call(ev.data)}]`;
          if (dbg.wsSamples.length < 60 || /SELECT|PICK/i.test(data)) {
            dbg.wsSamples.push(`${new Date().toISOString().slice(11, 19)} ${clip(redact(data))}`);
            if (dbg.wsSamples.length > 200) dbg.wsSamples.splice(60, 1);
          }
          try { scanText(data, 'websocket'); } catch (e) { note('ws scan', e); }
        });
        const send = ws.send;
        ws.send = function (d) {
          rec.sent += 1;
          if (rec.sent <= 15) dbg.wsSamples.push(`${new Date().toISOString().slice(11, 19)} SENT ${clip(redact(d), 160)}`);
          return send.apply(this, arguments);
        };
        return ws;
      }
      Hooked.prototype = Orig.prototype;
      Object.setPrototypeOf(Hooked, Orig);
      Hooked.__hoopHooked = true;
      W.WebSocket = Hooked;
      dbg.hooks.websocket = true;
    }

    function hookFetch() {
      const orig = W.fetch;
      if (!orig || orig.__hoopHooked) return;
      const hooked = function (input, init) {
        const url = typeof input === 'string' ? input : input && input.url;
        return orig.apply(this, arguments).then((res) => {
          try {
            const entry = { url: redact(url), status: res.status, picks: 0 };
            dbg.http.push(entry); if (dbg.http.length > 120) dbg.http.shift();
            if (/json/i.test(res.headers.get('content-type') || '')) {
              res.clone().json().then((j) => { entry.picks = scanJson(j, 'fetch'); }).catch(() => {});
            }
          } catch (e) { note('fetch', e); }
          return res;
        });
      };
      hooked.__hoopHooked = true;
      W.fetch = hooked;
      dbg.hooks.fetch = true;
    }

    function hookXhr() {
      const X = W.XMLHttpRequest;
      if (!X || X.prototype.__hoopHooked) return;
      const open = X.prototype.open;
      X.prototype.open = function (method, url) { this.__hoopUrl = url; return open.apply(this, arguments); };
      const send = X.prototype.send;
      X.prototype.send = function () {
        this.addEventListener('load', () => {
          try {
            const entry = { url: redact(this.__hoopUrl), status: this.status, picks: 0, xhr: true };
            dbg.http.push(entry); if (dbg.http.length > 120) dbg.http.shift();
            const text = typeof this.responseText === 'string' ? this.responseText : '';
            if (/^\s*[[{]/.test(text)) entry.picks = scanJson(JSON.parse(text), 'xhr');
          } catch (e) { note('xhr', e); }
        });
        return send.apply(this, arguments);
      };
      X.prototype.__hoopHooked = true;
      dbg.hooks.xhr = true;
    }

    // Way 3 (record only): what the page shows, for writing a parser later.
    function snapshotDom() {
      const out = { title: document.title, at: new Date().toISOString(), candidates: [] };
      const seen = new Set();
      document.querySelectorAll('[class]').forEach((el) => {
        const cls = String(el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className);
        if (!/pick|draft|roster|selected|board|queue|clock/i.test(cls)) return;
        const sig = cls.split(/\s+/).slice(0, 3).join('.');
        if (seen.has(sig) || out.candidates.length >= 80) return;
        seen.add(sig);
        out.candidates.push({ tag: el.tagName.toLowerCase(), cls: clip(cls, 120), children: el.children.length,
          text: clip(redact((el.textContent || '').replace(/\s+/g, ' ').trim()), 200) });
      });
      dbg.dom = out;
      return out;
    }

    function publish() {
      const list = [...picks.values()].sort((a, b) => (a.overall ?? 1e9) - (b.overall ?? 1e9) || a.seq - b.seq);
      const payload = { v: 1, version: VERSION, at: new Date().toISOString(), started: dbg.started, league: dbg.league, page: dbg.page,
        picks: list.map(({ overall, seq, teamId, playerId, name, source }) => ({ overall, seq, teamId, playerId, name, source })),
        summary: { sockets: dbg.sockets.length, wsMessages: dbg.wsMessages, http: dbg.http.length, hooks: dbg.hooks, errors: dbg.errors.length } };
      gmSet(KEY, JSON.stringify(payload)).catch((e) => note('storage', e));
      render();
    }

    // Debug panel (bottom right).
    let panel;
    function render() {
      if (!document.body) return;
      dbg.page = location.pathname;
      if (!panel) {
        panel = document.createElement('div');
        panel.style.cssText = 'position:fixed;right:12px;bottom:12px;z-index:2147483647;background:#0f1628;color:#eef2f8;' +
          'border:1px solid #ff7a1a;border-radius:10px;padding:8px 10px;font:12px/1.4 system-ui,sans-serif;max-width:260px;box-shadow:0 4px 18px rgba(0,0,0,.4)';
        panel.innerHTML = '<b style="color:#ffb020">Hoopothesis bridge</b> <span id="hoop-v"></span><div id="hoop-s"></div>' +
          '<button id="hoop-copy" style="margin-top:6px;background:#ff7a1a;color:#1a0d00;border:0;border-radius:6px;padding:4px 8px;font-weight:600;cursor:pointer">Copy debug</button>' +
          ' <button id="hoop-hide" style="margin-top:6px;background:none;color:#94a3b8;border:0;cursor:pointer">hide</button>' +
          '<textarea id="hoop-t" readonly style="display:none;width:100%;height:90px;margin-top:6px;font:10px monospace"></textarea>';
        document.body.appendChild(panel);
        panel.querySelector('#hoop-v').textContent = `v${VERSION}`;
        panel.querySelector('#hoop-hide').onclick = () => { panel.style.display = 'none'; };
        panel.querySelector('#hoop-copy').onclick = copyDebug;
      }
      const ids = [...picks.values()];
      panel.querySelector('#hoop-s').textContent = (isDraftRoom() || dbg.sockets.length ? '' :
        `Running, but this doesn't look like a draft room (${location.pathname}). `) +
        `${ids.length} pick${ids.length === 1 ? '' : 's'} seen · ${dbg.sockets.length} live feed${dbg.sockets.length === 1 ? '' : 's'}, ` +
        `${dbg.wsMessages} messages · ${dbg.http.length} data requests` + (dbg.errors.length ? ` · ${dbg.errors.length} errors` : '');
    }

    async function copyDebug() {
      snapshotDom();
      const text = `Hoopothesis bridge debug ${VERSION}, ${new Date().toString()}\n${navigator.userAgent}\n` + JSON.stringify(dbg, null, 1);
      const t = panel.querySelector('#hoop-t');
      try { await navigator.clipboard.writeText(text); panel.querySelector('#hoop-copy').textContent = 'Copied!'; }
      catch (e) { t.style.display = 'block'; t.value = text; t.select(); panel.querySelector('#hoop-copy').textContent = 'Select + copy below'; }
    }

    try { hookWebSocket(); } catch (e) { note('hook ws', e); }
    try { hookFetch(); } catch (e) { note('hook fetch', e); }
    try { hookXhr(); } catch (e) { note('hook xhr', e); }
    // The panel needs <body>; ESPN's app can also change the page without a reload, so check every 2 s.
    setInterval(() => { try { render(); } catch (e) { note('render', e); } }, 2000);
    setTimeout(() => { try { snapshotDom(); } catch (e) { note('dom', e); } }, 15000);
    W.__hoopBridge = { dbg, picks, scanText, scanJson, snapshotDom, publish };   // for testing in the console
  }

  // ------------------------------------------------------------------ Hoopothesis draft page
  function hoopSide() {
    if (!/\/draft/.test(location.pathname)) return;
    let last = null;
    const tick = async () => {
      try {
        const raw = await gmGet(KEY);
        if (raw && raw !== last) {
          last = raw;
          window.postMessage({ type: 'hoop-espn-bridge', payload: JSON.parse(raw) }, location.origin);
        }
      } catch (e) { /* storage unavailable: nothing to forward */ }
    };
    // Tell the page the script is installed even before any pick arrives.
    const hello = () => window.postMessage({ type: 'hoop-espn-bridge-hello', version: VERSION }, location.origin);
    document.readyState === 'loading' ? document.addEventListener('DOMContentLoaded', hello) : hello();
    setInterval(tick, 1500);
    setInterval(hello, 10000);
    tick();
  }
})();
