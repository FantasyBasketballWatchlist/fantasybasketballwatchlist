"""Charts for the PDF report (docs/BPV-report.pdf). Reads analysis/results.json and robustness.json.

Run:  python -m analysis.report_charts OUTPUT_DIR
"""
import json
import os
import sys
import warnings

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from analysis import backtest as bt  # noqa: E402

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
BLUE, ORANGE, GRAY, GREEN, RED = "#2f5d9e", "#d9822b", "#8a8f98", "#3c8d5a", "#b8443a"
plt.rcParams.update({"font.family": "Arial", "font.size": 9, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.titlesize": 10, "axes.titleweight": "bold"})


def save(fig, out, name):
    fig.tight_layout()
    fig.savefig(os.path.join(out, name), dpi=200)
    plt.close(fig)


def main(out):
    os.makedirs(out, exist_ok=True)
    res = json.load(open(os.path.join(HERE, "results.json")))
    rob = json.load(open(os.path.join(HERE, "robustness.json")))

    # 1. Recent-form weight curves.
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.8))
    for label, key, color in [("Last 5 games played", "last5_played", BLUE), ("Team's last 5 (games played only)", "team_last5", ORANGE)]:
        g = res["A_recent_form"]["A_ros"][key]["train_mae_by_weight"]
        a.plot([float(w) * 100 for w in g], list(g.values()), marker="o", ms=3, color=color, label=label)
    a.set(title="Error by recent-form weight (tuning seasons)", xlabel="Weight on last 5 games (%)",
          ylabel="Avg error, FPTS/game")
    a.axvline(20, color=GRAY, ls=":", lw=1)
    a.legend(frameon=False, fontsize=7)
    for season, grid in rob["R1_mae_by_season"].items():
        w = [float(x) * 100 for x in grid]
        v = np.array(list(grid.values()))
        b.plot(w, v - v.min(), label=season, lw=1.2)
    b.set(title="Each season separately (relative to its best)", xlabel="Weight on last 5 games (%)",
          ylabel="Extra error vs. best weight")
    b.legend(frameon=False, fontsize=7)
    save(fig, out, "recent_weight.png")

    # 2. Bootstrap distribution of the best weight.
    dist = rob["R1_best_weight_bootstrap"]["distribution"]
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    ax.bar([f"{float(k) * 100:.0f}%" for k in dist], list(dist.values()), color=BLUE)
    ax.set(title="Best weight across 300 resamples", ylabel="Share of resamples")
    save(fig, out, "weight_bootstrap.png")

    # 3. Minutes vs efficiency weights with intervals.
    r3 = rob["R3_weights"]
    fig, ax = plt.subplots(figsize=(3.4, 2.3))
    vals = [r3["minutes"], r3["efficiency"]]
    errs = [[vals[0] - r3["minutes_ci95"][0], vals[1] - r3["efficiency_ci95"][0]],
            [r3["minutes_ci95"][1] - vals[0], r3["efficiency_ci95"][1] - vals[1]]]
    ax.bar(["Minutes change", "Per-minute change"], vals, yerr=errs, capsize=5, color=[GREEN, ORANGE])
    ax.set(title="Share of a last-5 change that lasts", ylabel="Weight (95% interval)")
    save(fig, out, "minutes_vs_efficiency.png")

    # 4. New Role Value grid (recomputed on the tuning seasons).
    pg, tg = bt.load()
    cp = pd.concat([bt.checkpoint_rows(s, pg[s], tg[s]) for s in bt.TRAIN], ignore_index=True)
    _, cp = bt.section_recent_form(cp)
    role = cp[(cp.mpg_L5 - cp.mpg_S >= 8) & (cp.mpg_S <= 24)].dropna(subset=["A_ros"]).copy()
    role["M2"] = 0.8 * role.S + 0.2 * role.L5
    hs, bs = np.round(np.arange(0.6, 1.11, 0.05), 2), np.round(np.arange(0, 1.01, 0.1), 1)
    grid = np.array([[np.mean(np.abs((1 - b_) * role.M2 + b_ * role.fpm_S * role.mpg_L5 * h - role.A_ros))
                      for b_ in bs] for h in hs])
    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    im = ax.imshow(grid, cmap="viridis_r", aspect="auto", origin="lower")
    ax.set_xticks(range(len(bs)), [f"{b_:.0%}" for b_ in bs], fontsize=7)
    ax.set_yticks(range(len(hs)), [f"{h:.2f}" for h in hs], fontsize=7)
    ax.set(xlabel="Weight on New Role Value", ylabel="Haircut", title="New Role Value: error by haircut and weight")
    best = np.unravel_index(grid.argmin(), grid.shape)
    ax.plot(best[1], best[0], "w*", ms=10)
    for i, j in zip(*np.where(grid <= grid.min() * 1.01)):
        ax.plot(j, i, "o", mfc="none", mec="white", ms=6, lw=0.8)
    fig.colorbar(im, ax=ax, label="Avg error, FPTS/game")
    save(fig, out, "new_role_grid.png")

    # 5. Early-season shrinkage curves.
    d = res["D_early_season"]
    fig, ax = plt.subplots(figsize=(3.6, 2.4))
    for key, label, color in [("returning_player_mae_by_k", "Returning players (prior = last season)", BLUE),
                              ("rookie_mae_by_k", "Rookies (prior = draft-slot baseline)", ORANGE)]:
        ax.plot([int(k) for k in d[key]], list(d[key].values()), marker="o", ms=3, color=color, label=label)
    ax.set(title="Early season: games of prior to blend in", xlabel="k (games of prior)", ylabel="Avg error, FPTS/game")
    ax.legend(frameon=False, fontsize=7)
    save(fig, out, "early_season_k.png")

    # 6. Availability: decay x k grid and method comparison.
    c = res["C_availability"]
    g = pd.DataFrame(c["grid"]).pivot(index="decay", columns="k", values="mae").sort_index(ascending=False)
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.6), gridspec_kw={"width_ratios": [1.2, 1]})
    im = a.imshow(g.values, cmap="viridis_r", aspect="auto")
    a.set_xticks(range(len(g.columns)), g.columns)
    a.set_yticks(range(len(g.index)), ["equal" if x == 1 else ("last only" if x < 0.01 else f"{x:g}") for x in g.index])
    a.set(xlabel="k (games of league average)", ylabel="Decay per older season", title="Availability error by setting")
    fig.colorbar(im, ax=a)
    r6 = rob["R6"]
    names = ["Last season\nonly", "Career GP%", "League\naverage", "Weighted +\nshrunk"]
    vals = [c["mae_last_season_only"], r6["mae_career_gp"], r6["mae_league_average"], r6["mae_shrunk_out_of_sample"]]
    b.bar(names, vals, color=[GRAY, RED, GRAY, GREEN])
    b.set_ylim(0.15, 0.19)
    b.set(title="Predicting next season's availability", ylabel="Avg error (share of games)")
    b.tick_params(axis="x", labelsize=7)
    save(fig, out, "availability.png")

    # 7. Absence-pattern reliability.
    r5 = rob["R5"]
    labels = list(r5)
    fig, ax = plt.subplots(figsize=(7.2, 2.5))
    x = np.arange(len(labels))
    ax.bar(x - 0.2, [r5[k]["yoy_corr"] for k in labels], 0.4, label="Season-to-season correlation", color=BLUE)
    ax.bar(x + 0.2, [r5[k]["full_season_reliability"] for k in labels], 0.4, label="Reliability of one season's measure", color=ORANGE)
    ax.set_xticks(x, [k.split(" (")[0] for k in labels], fontsize=7)
    ax.set(title="Long-vs-scattered absence share (q): too noisy to measure per player", ylabel="Correlation")
    ax.legend(frameon=False, fontsize=7)
    save(fig, out, "q_reliability.png")

    # 8. Between seasons: age curve and model comparison.
    pp = json.load(open(os.path.join(HERE, "preseason_production.json")))
    curve = pp["final"]["age_curve"]
    fig, (a, b) = plt.subplots(1, 2, figsize=(7.2, 2.6))
    vals = list(curve.values())
    a.bar(list(curve), vals, color=[GREEN if v > 0 else RED for v in vals])
    a.axhline(0, color=GRAY, lw=0.8)
    a.set(title="Change in FPTS/game the next season, by age", xlabel="Age during the season just played", ylabel="FPTS/game")
    names = {"last": "Last season", "fpg multi": "3 seasons\nblended", "rate x min": "3 seasons\nper-minute",
             "sps": "Basketball-\nReference SPS", "last+age": "Last season\n+ age"}
    b.bar([names[m] for m in names], [pp["mae"][m] for m in names],
          color=[GRAY, GRAY, GRAY, ORANGE, GREEN])
    b.set_ylim(4.2, 4.75)
    b.set(title="Preseason error (4 held-out seasons)", ylabel="Avg error, FPTS/game")
    b.tick_params(axis="x", labelsize=7)
    save(fig, out, "age_curve.png")

    # 9. Draft simulations by season (no leakage).
    r4 = rob["R4"]
    models = list(next(iter(r4.values()))["draft_sim_total"])
    fig, ax = plt.subplots(figsize=(7.2, 2.8))
    x = np.arange(len(r4))
    colors = {"BPV (replacement-level)": GREEN, "M5 80/20 x career GP%": ORANGE, "M3 x career GP%": RED,
              "M1 season FPTS": BLUE, "Last season total FPTS": GRAY, "BPV + age": "#1b5e3a"}
    for i, m in enumerate(models):
        ax.bar(x + (i - 2) * 0.16, [r4[s]["draft_sim_total"][m] for s in r4], 0.16, label=m, color=colors[m])
    ax.set_xticks(x, list(r4))
    ax.set_ylim(22000, 31500)
    ax.set(title="Simulated drafts: average team FPTS (1,000 drafts per season)", ylabel="Team FPTS")
    ax.legend(frameon=False, fontsize=7, ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.12))
    save(fig, out, "draft_sims.png")


if __name__ == "__main__":
    main(sys.argv[1])
