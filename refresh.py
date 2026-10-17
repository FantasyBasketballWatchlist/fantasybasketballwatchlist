"""Daily data refresh for the live site. Run it on a machine that can reach stats.nba.com.

stats.nba.com doesn't answer cloud servers, so the live site runs offline (NBA_OFFLINE=1) and
reads data/live/. This script:

1. Calls every API route, which rebuilds the ratings and fetches whatever is out of date into
   data/cache/ (and saves a snapshot when one is due).
2. Copies exactly the cache files those routes read into data/live/.
3. Logs this run's in-season predictions and scores the ones whose games are done (analysis/live_checks.py,
   data/tracking/).
4. Checks before publishing: sanity checks on the new ratings, then a full offline copy of the site run against
   data/live/ exactly as the server will (every route must answer, and the rankings must match). If a check
   fails, nothing is published and the live site keeps its current data.
5. Commits data/live/, data/snapshots/, data/preseason/ and data/tracking/ (only if they changed), pushes, asks
   Render to redeploy (deploy hook from RENDER_DEPLOY_HOOK or the gitignored file .render_deploy_hook), then
   checks that hoopothesis.cc is serving the new data.

Problems (a failed check, a failed deploy, a new flag from the in-season checks) are logged and shown as a
Windows notification. Exit code 1 on failure, so Task Scheduler's "Last Run Result" shows it too.

    python refresh.py            # refresh, check, commit, push, deploy, verify
    python refresh.py --no-push  # refresh and check only
"""
import datetime
import json
import math
import os
import shutil
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVE_DIR = os.path.join(ROOT, "data", "live")
VERSION_FILE = os.path.join(LIVE_DIR, "VERSION")
HOOK_FILE = os.path.join(ROOT, ".render_deploy_hook")
SITE = "https://hoopothesis.cc"
COMMIT_PATHS = ["data/live", "data/snapshots", "data/preseason", "data/tracking"]   # the site rescores accuracy itself
ROUTES = ["/api/meta", "/api/players", "/api/rankings", "/api/positions", "/api/waiver", "/api/accuracy"]
PAGES = ["/", "/draft", "/league", "/trade-analyzer", "/waiver-wires"]
DEPLOY_WAIT_SECONDS = 10 * 60

# Same routes, run against data/live/ with the network off, the way the server runs.
OFFLINE_CHECK = """
import json, os, sys
sys.path.insert(0, os.getcwd())
import app
c = app.app.test_client()
status = {r: c.get(r).status_code for r in %r}
ranks = c.get("/api/rankings?limit=50").get_json()
print(json.dumps({"status": status, "top50": [p["id"] for p in ranks["players"]] if ranks and "players" in ranks else None}))
"""


def log(msg):
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def notify(message):
    """Windows notification (best effort; the log has everything either way)."""
    log(f"NOTICE: {message}")
    if os.name != "nt":
        return
    text = message.replace("'", "''")[:240]
    script = (
        "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
        "$x = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$t = $x.GetElementsByTagName('text'); $t.Item(0).AppendChild($x.CreateTextNode('Hoopothesis')) > $null;"
        f"$t.Item(1).AppendChild($x.CreateTextNode('{text}')) > $null;"
        "$app = '{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\\WindowsPowerShell\\v1.0\\powershell.exe';"
        "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($app).Show([Windows.UI.Notifications.ToastNotification]::new($x))")
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30)
    except Exception:
        pass


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def rebuild():
    """Hit every data route the site serves; returns (cache dir, files read, players, meta)."""
    os.environ.pop("NBA_OFFLINE", None)
    sys.path.insert(0, ROOT)
    import app
    import nba_data
    import ratings
    client = app.app.test_client()
    for route in ROUTES:
        resp = client.get(route)
        if resp.status_code != 200:
            raise RuntimeError(f"{route} returned {resp.status_code}: {resp.get_data(as_text=True)[:300]}")
    players, meta = ratings.get()
    return nba_data.CACHE_DIR, sorted(nba_data.used), players, meta


def sync_live(cache_dir, names):
    """Make data/live/ hold exactly the files the site read (plus the VERSION stamp)."""
    os.makedirs(LIVE_DIR, exist_ok=True)
    keep = {n for n in names if os.path.exists(os.path.join(cache_dir, n))}
    for n in keep:
        shutil.copy2(os.path.join(cache_dir, n), os.path.join(LIVE_DIR, n))
    for n in set(os.listdir(LIVE_DIR)) - keep - {"VERSION"}:
        os.remove(os.path.join(LIVE_DIR, n))
    log(f"data/live: {len(keep)} files")


def sanity_problems(players, meta):
    """Things that should never be true of a good build."""
    problems = []
    if len(players) < 400:
        problems.append(f"only {len(players)} players rated")
    for col in ["bpv", "production", "availability"]:
        bad = players[col].isna() | ~players[col].map(lambda v: math.isfinite(v) if v is not None else False)
        if bad.any():
            problems.append(f"{int(bad.sum())} players with a missing or infinite {col}")
    if not players["availability"].between(0, 1).all():
        problems.append("availability outside 0-1")
    if players["rank"].duplicated().any():
        problems.append("duplicate ranks")
    if not 10 <= (meta.get("replacement_level") or 0) <= 45:
        problems.append(f"replacement level {meta.get('replacement_level')} looks wrong")
    if meta.get("mode") == "in-season":
        regulars = players[(players["games"] >= 10) & (players["minutes"].fillna(0) >= 20)]
        if len(regulars) and players["week_games"].fillna(0).max() > 0 and regulars["week_fpts"].notna().mean() < 0.8:
            problems.append("most regulars have no projection for this week")
    return problems


def offline_problems(players):
    """Run the site against data/live/ with the network off, as the server does."""
    env = {**os.environ, "NBA_OFFLINE": "1", "NBA_CACHE_DIR": LIVE_DIR}
    r = subprocess.run([sys.executable, "-c", OFFLINE_CHECK % (ROUTES,)], cwd=ROOT, env=env,
                       capture_output=True, text=True, timeout=600)
    try:
        out = json.loads(r.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return [f"offline copy of the site failed to run: {(r.stderr or r.stdout)[-400:]}"]
    problems = [f"offline {route} returned {code}" for route, code in out["status"].items() if code != 200]
    online = players.sort_values("rank")["id"].head(50).astype(int).tolist()
    if out["top50"] != online:
        problems.append("offline rankings differ from the online build (a data file is probably missing)")
    return problems


def deploy_hook():
    url = os.environ.get("RENDER_DEPLOY_HOOK")
    if not url and os.path.exists(HOOK_FILE):
        with open(HOOK_FILE, encoding="utf-8") as f:
            url = f.read().strip()
    return url


def publish():
    """Commit and push the data if it changed; returns the new data version, or None if nothing changed."""
    git("add", "-A", "--", *COMMIT_PATHS)
    if not git("diff", "--cached", "--name-only", "--", *COMMIT_PATHS).strip():
        log("no data changes; nothing to publish")
        return None
    version = datetime.datetime.now().isoformat(timespec="seconds")
    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        f.write(version)
    git("add", "--", *COMMIT_PATHS)
    git("commit", "-m", f"Data refresh {datetime.date.today().isoformat()}", "--", *COMMIT_PATHS)  # only the data
    git("push", "origin", "HEAD")
    log("pushed")
    url = deploy_hook()
    if not url:
        log("no deploy hook set; deploy manually in Render")
        return None
    import requests
    requests.post(url, timeout=30).raise_for_status()
    log("Render deploy triggered")
    return version


def verify_live(version):
    """Wait for hoopothesis.cc to serve this data version, then check every page and route answers."""
    import requests
    deadline = time.time() + DEPLOY_WAIT_SECONDS
    while time.time() < deadline:
        try:
            if requests.get(f"{SITE}/api/meta", timeout=30).json().get("data_version") == version:
                break
        except (requests.RequestException, ValueError):
            pass
        time.sleep(20)
    else:
        return [f"the live site still isn't serving the new data after {DEPLOY_WAIT_SECONDS // 60} minutes"]
    problems = []
    for path in PAGES + ROUTES:
        try:
            code = requests.get(SITE + path, timeout=60).status_code
        except requests.RequestException as e:
            code = type(e).__name__
        if code != 200:
            problems.append(f"live {path} returned {code}")
    return problems


def main():
    log("refresh started")
    try:
        cache_dir, names, players, meta = rebuild()
        sync_live(cache_dir, names)

        from analysis import live_checks
        live_checks.record(players, meta)
        summary, old_flags = live_checks.score(meta.get("target_season") or meta["season"])
        for flag in summary.get("flags", []):
            log(f"in-season check: {flag}")
            if flag not in old_flags:
                notify(f"In-season check: {flag}")

        problems = sanity_problems(players, meta) + offline_problems(players)
        if problems:
            notify("Refresh stopped before publishing: " + "; ".join(problems))
            return 1
        log("checks passed")

        if "--no-push" not in sys.argv:
            version = publish()
            if version:
                problems = verify_live(version)
                if problems:
                    notify("Published, but the live site has a problem: " + "; ".join(problems))
                    return 1
                log(f"live site is serving data version {version}")
    except Exception as e:
        notify(f"Refresh failed: {type(e).__name__}: {e}")
        raise
    log("refresh done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
