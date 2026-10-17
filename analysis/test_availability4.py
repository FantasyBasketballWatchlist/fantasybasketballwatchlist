"""Availability, round 4 (in season), on top of the absence-streak adjustment now in the app.

Run:  python -m analysis.test_availability4     (writes analysis/test_availability4.json)

Base: the app's in-season estimate including the absence-streak adjustment (fitted leave-one-season-out).
Candidates, for players not listed Out with an injury:
  D1 latest report status (within 3 days): Probable / Questionable / Doubtful indicators
  D2 listed Out for a non-injury reason (rest, personal, G League...)
  D3 just returned from a 5+ game absence in the last 14 days
Same rule: 95% interval excludes 0 in favor AND better in most held-out seasons, checked on both
absolute and squared error.
"""
import json
import os
import warnings

import numpy as np

from analysis import test_availability3 as t3

warnings.filterwarnings("ignore")
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_availability4.json")


def main():
    d = t3.build_rows()
    free = d[~d.report_out].copy()
    free["probable"] = (free.status == "Probable").astype(float)
    free["questionable"] = (free.status == "Questionable").astype(float)
    free["doubtful"] = (free.status == "Doubtful").astype(float)
    free["out_other"] = ((free.status == "Out") & (free.status_category != "injury")).astype(float)
    base, _ = t3.correct(free, ["streak"])
    free["base"] = base["new"]
    res = {"n": len(free), "status_counts": free.status.value_counts().to_dict(),
           "recent_returns": int(free.recent_return.sum())}
    for name, feats in (("D1_status", ["probable", "questionable", "doubtful"]), ("D2_out_non_injury", ["out_other"]),
                        ("D3_recent_return", ["recent_return"])):
        s, coefs = t3.correct(free, feats, base="base")
        j = t3.judge(s, "new", "base")
        res[name] = {"coefs": coefs, **j}
        print(name, coefs.get("2025-26"), "| abs", j["abs"]["verdict"], round(j["abs"]["minus_base"]["diff"], 5),
              j["abs"]["minus_base"]["ci95"], j["abs"]["seasons_better"], "| sq", j["squared"]["verdict"],
              round(j["squared"]["minus_base"]["diff"], 5), j["squared"]["seasons_better"], flush=True)
    print({k: res[k] for k in ("n", "status_counts", "recent_returns")})
    with open(OUT, "w") as f:
        json.dump(res, f, indent=2, default=float)


if __name__ == "__main__":
    main()
