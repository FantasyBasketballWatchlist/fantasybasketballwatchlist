"""Daily data refresh for the live site. Run it on a machine that can reach stats.nba.com.

stats.nba.com doesn't answer cloud servers, so the live site runs offline (NBA_OFFLINE=1) and
reads data/live/. This script:

1. Calls every API route, which rebuilds the ratings and fetches whatever is out of date into
   data/cache/ (and saves a snapshot when one is due).
2. Copies exactly the cache files those routes read into data/live/.
3. Commits data/live/, data/snapshots/, data/preseason/ and data/accuracy.json, pushes, and asks Render to redeploy
   (the deploy hook URL is read from RENDER_DEPLOY_HOOK or the gitignored file .render_deploy_hook).

    python refresh.py            # refresh, commit, push, deploy
    python refresh.py --no-push  # refresh and update data/live/ only
"""
import datetime
import os
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
LIVE_DIR = os.path.join(ROOT, "data", "live")
HOOK_FILE = os.path.join(ROOT, ".render_deploy_hook")
COMMIT_PATHS = ["data/live", "data/snapshots", "data/preseason", "data/accuracy.json"]
ROUTES = ["/api/meta", "/api/players", "/api/rankings", "/api/positions", "/api/waiver", "/api/accuracy"]


def log(msg):
    print(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def rebuild():
    """Hit every data route the site serves; returns the cache files they read."""
    os.environ.pop("NBA_OFFLINE", None)
    sys.path.insert(0, ROOT)
    import app
    import nba_data
    client = app.app.test_client()
    for route in ROUTES:
        resp = client.get(route)
        if resp.status_code != 200:
            raise RuntimeError(f"{route} returned {resp.status_code}: {resp.get_data(as_text=True)[:300]}")
    return nba_data.CACHE_DIR, sorted(nba_data.used)


def sync_live(cache_dir, names):
    """Make data/live/ hold exactly the files the site read."""
    os.makedirs(LIVE_DIR, exist_ok=True)
    keep = {n for n in names if os.path.exists(os.path.join(cache_dir, n))}
    for n in keep:
        shutil.copy2(os.path.join(cache_dir, n), os.path.join(LIVE_DIR, n))
    for n in set(os.listdir(LIVE_DIR)) - keep:
        os.remove(os.path.join(LIVE_DIR, n))
    log(f"data/live: {len(keep)} files")


def deploy_hook():
    url = os.environ.get("RENDER_DEPLOY_HOOK")
    if not url and os.path.exists(HOOK_FILE):
        with open(HOOK_FILE, encoding="utf-8") as f:
            url = f.read().strip()
    return url


def publish():
    git("add", "-A", "--", *COMMIT_PATHS)
    if not git("diff", "--cached", "--name-only", "--", *COMMIT_PATHS).strip():
        log("no data changes; nothing to publish")
        return
    git("commit", "-m", f"Data refresh {datetime.date.today().isoformat()}", "--", *COMMIT_PATHS)  # only the data
    git("push", "origin", "HEAD")
    log("pushed")
    url = deploy_hook()
    if not url:
        log("no deploy hook set; deploy manually in Render")
        return
    import requests
    requests.post(url, timeout=30).raise_for_status()
    log("Render deploy triggered")


def main():
    log("refresh started")
    cache_dir, names = rebuild()
    sync_live(cache_dir, names)
    if "--no-push" not in sys.argv:
        publish()
    log("refresh done")


if __name__ == "__main__":
    main()
