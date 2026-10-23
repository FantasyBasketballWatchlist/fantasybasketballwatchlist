"""Calibration of the steal rule's lasting chance on the six real drafts.

    python analysis/draft_steal_calib.py <dir from analysis.draft_steal_data>

For every slot s and each of its picks n (except its last), and every player still on the board at n who is among the
top K by our BPV (the kind of player the engine would suggest) and has an ESPN ADP: did he last to s's next pick N?
"""
import json, math, sys, unicodedata, re
import numpy as np

SP = sys.argv[1]
P = json.load(open(f"{SP}/players.json"))
L = json.load(open(f"{SP}/leagues.json"))
DESIGN = ["538977698", "1854297225", "1503540199"]
TEST = ["34650931", "1192115637", "2029687819"]
K = 10
MU, SD = -0.095, 0.211


def key(n):
    n = unicodedata.normalize("NFD", n)
    n = re.sub(r"[̀-ͯ]", "", n).lower().replace(".", "").replace("-", " ").replace("'", "")
    n = re.sub(r"\s+(jr|sr|ii|iii|iv)$", "", n)
    return re.sub(r"\s+", " ", n).strip()


byname = {key(p["name"]): p for p in P["players"]}
players = sorted(P["players"], key=lambda p: -p["bpv"])
Phi = lambda z: 0.5 * (1 + math.erf(z / math.sqrt(2)))


def team_of(n, T=10):
    r, i = (n - 1) // T, (n - 1) % T
    return i + 1 if r % 2 == 0 else T - i


def rows(leagues):
    out = []
    for lg in leagues:
        picks = L[lg]["picks"]
        pick_of = {}
        for n, name in picks:
            p = byname.get(key(name))
            if p: pick_of[p["id"]] = n
        for s in range(1, 11):
            mine = [n for n in range(1, 131) if team_of(n) == s]
            for n, N in zip(mine, mine[1:]):
                board = [p for p in players if pick_of.get(p["id"], 999) >= n][:K]
                for p in board:
                    if p["adp"] is None: continue
                    lasted = pick_of.get(p["id"], 999) > N
                    prior = 1 - Phi((math.log(N / p["adp"]) - MU) / SD)
                    out.append(dict(lg=lg, n=n, N=N, adp=p["adp"], lasted=lasted, prior=prior,
                                    x1=math.log(N / p["adp"]), x2=math.log(n / p["adp"])))
    return out


def table(rs, col):
    bins = [0, .1, .3, .5, .7, .9, 1.01]
    for a, b in zip(bins, bins[1:]):
        g = [r for r in rs if a <= r[col] < b]
        if g:
            print(f"  {col} {a:.1f}-{min(b,1):.1f}: n={len(g):4d}  predicted {np.mean([r[col] for r in g]):.2f}  actual {np.mean([r['lasted'] for r in g]):.2f}")


def fit(rs):
    """Logistic regression lasted ~ x1 + x2 (Newton)."""
    X = np.array([[1, r["x1"], r["x2"]] for r in rs]); y = np.array([r["lasted"] for r in rs], float)
    w = np.zeros(3)
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w)); W = p * (1 - p)
        w += np.linalg.solve(X.T @ (X * W[:, None]) + 1e-6 * np.eye(3), X.T @ (y - p))
    return w


def apply(w, rs, col):
    for r in rs: r[col] = 1 / (1 + math.exp(-(w[0] + w[1] * r["x1"] + w[2] * r["x2"])))


def brier(rs, col): return np.mean([(r[col] - r["lasted"]) ** 2 for r in rs])


A, B = rows(DESIGN), rows(TEST)
print("current formula, all six leagues:"); table(A + B, "prior")
wA, wB = fit(A), fit(B)
apply(wA, B, "fit"); apply(wB, A, "fit")       # cross-fitted: each half scored by the other half's fit
print("logistic, cross-fitted:"); table(A + B, "fit")
print("brier prior", round(brier(A + B, "prior"), 4), "fit", round(brier(A + B, "fit"), 4))
print("fit on design", wA.round(3), "on test", wB.round(3), "on all", fit(A + B).round(3))
