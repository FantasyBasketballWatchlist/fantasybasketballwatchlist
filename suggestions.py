"""Suggestions for one team in a league: what to target, watch and fix.

Everything here is arithmetic on numbers the site already shows (BPV, availability, the injury report, minutes and
per-minute changes, ESPN positions), so nothing in it is a new prediction that needs its own test. A team's strength is
the BPV of its best starting lineup (ESPN slots, dual-position players move to where they help most).
"""
import itertools

POSITIONS = ["PG", "SG", "SF", "PF", "C"]
DEFAULT_LINEUP = "PG,SG,SF,PF,C,G,F,UTIL,UTIL,UTIL"
CHANGE = 4.0                 # FPTS/game: same threshold as the waiver page's default
FRAGILE = 0.75               # availability under this = expected to miss a quarter of the remaining games
MAX_TRADES = 5
ESPN_EDGE = 0.85             # "ESPN ranks the player they get higher": his ADP at least 15% earlier (picks wander ~20%)
MAX_LIST = 6


def fits(slot, ps):
    if slot == "UTIL":
        return True
    if slot == "G":
        return "PG" in ps or "SG" in ps
    if slot == "F":
        return "SF" in ps or "PF" in ps
    return slot in ps


def lineup(ids, info, slots):
    """(value, starters): the best starting lineup's BPV, filled best player first with dual-position players moved
    over when that frees a slot (augmenting paths, as on the draft page)."""
    order = sorted((i for i in ids if i in info), key=lambda i: -info[i]["bpv"])
    owner = [None] * len(slots)

    def place(i, seen):
        for s, slot in enumerate(slots):
            if seen[s] or not fits(slot, info[i]["pos"]):
                continue
            seen[s] = True
            if owner[s] is None or place(owner[s], seen):
                owner[s] = i
                return True
        return False

    for i in order:
        place(i, [False] * len(slots))
    starters = [i for i in owner if i is not None]
    return sum(info[i]["bpv"] for i in starters), set(starters)


def position_strength(ids, info):
    """Per position: mean BPV of the team's best two players who can play it (0 for an empty spot)."""
    out = {}
    for p in POSITIONS:
        vals = sorted((info[i]["bpv"] for i in ids if i in info and p in info[i]["pos"]), reverse=True)[:2]
        vals += [0.0] * (2 - len(vals))
        out[p] = sum(vals) / 2
    return out


def build(players, positions, teams, mine, lineup_text=None):
    """players: the ratings frame (with the waiver page's effective minutes/efficiency changes); positions: id -> "PG/SG";
    teams: list of id lists; mine: index of the user's team."""
    slots = [s.strip().upper() for s in (lineup_text or DEFAULT_LINEUP).split(",") if s.strip()]
    info = {}
    for r in players.itertuples():
        pos = positions.get(int(r.id))
        info[int(r.id)] = {
            "id": int(r.id), "name": r.name, "team": r.team, "bpv": float(r.bpv),
            "availability": float(r.availability) if r.availability == r.availability else None,
            "pos": pos.split("/") if pos else [], "positions": pos or "",
            "status": r.report_status if isinstance(r.report_status, str) else None,
            "reason": r.report_reason if isinstance(r.report_reason, str) else None,
            "note": r.injury_note if isinstance(r.injury_note, str) else None,
            "mc": _num(getattr(r, "minutes_change_fpts", None)), "ec": _num(getattr(r, "efficiency_change_fpts", None)),
            "basis": getattr(r, "basis", None), "games": int(r.games) if r.games == r.games else 0,
            "adp": _num(getattr(r, "adp", None)),
        }
    teams = [[i for i in t if i in info] for t in teams]
    my = teams[mine]
    rostered = set(itertools.chain.from_iterable(teams))
    card = lambda i, **extra: {**{k: info[i][k] for k in ("id", "name", "team", "bpv", "positions", "availability", "status")}, **extra}

    # Standing: every team's lineup value.
    values = [lineup(t, info, slots)[0] for t in teams]
    my_value, my_starters = lineup(my, info, slots)
    rank = 1 + sum(v > my_value for v in values)
    avg = sum(values) / len(values)

    # Positions: mine vs the league average, per position.
    strength = [position_strength(t, info) for t in teams]
    league_pos = {p: sum(s[p] for s in strength) / len(strength) for p in POSITIONS}
    pos_rank = {p: 1 + sum(s[p] > strength[mine][p] for s in strength) for p in POSITIONS}
    gaps = sorted(POSITIONS, key=lambda p: strength[mine][p] - league_pos[p])
    pos_rows = [{"pos": p, "mine": strength[mine][p], "league": league_pos[p], "rank": pos_rank[p]} for p in POSITIONS]
    needs = [p for p in gaps if strength[mine][p] < league_pos[p]][:2]
    surplus = [p for p in reversed(gaps) if strength[mine][p] > league_pos[p]][:2]

    # Injuries: availability weighted by BPV over the starters, vs the league's teams.
    def health(ids):
        start = lineup(ids, info, slots)[1]
        w = [(info[i]["bpv"], info[i]["availability"]) for i in start if info[i]["availability"] is not None]
        return sum(b * a for b, a in w) / sum(b for b, _ in w) if w and sum(b for b, _ in w) > 0 else None
    healths = [health(t) for t in teams]
    known = [h for h in healths if h is not None]
    my_health = healths[mine]
    injury = {
        "availability": my_health, "league": sum(known) / len(known) if known else None,
        "rank": 1 + sum(h > my_health for h in known) if my_health is not None else None, "teams": len(teams),
        "out_now": [card(i, reason=info[i]["reason"] or info[i]["note"], starter=i in my_starters)
                    for i in my if info[i]["status"] in ("Out", "Doubtful", "Questionable")
                    or (info[i]["note"] and not info[i]["status"])],
        "fragile": [card(i, starter=i in my_starters) for i in sorted(my, key=lambda i: info[i]["availability"] or 1)
                    if info[i]["availability"] is not None and info[i]["availability"] < FRAGILE][:MAX_LIST],
    }

    # Trades: one-for-one swaps that raise my lineup. Ones they have a reason to accept first (by my gain), then the rest
    # by the value the swap creates for both lineups together.
    trades = []
    for t, ids in enumerate(teams):
        if t == mine or not ids:
            continue
        their_value = values[t]
        for a in my:
            for b in ids:
                if abs(info[a]["bpv"] - info[b]["bpv"]) > 6:      # lopsided by BPV alone: nobody accepts
                    continue
                mine_after = lineup([x for x in my if x != a] + [b], info, slots)[0]
                gain = mine_after - my_value
                if gain < 0.5:
                    continue
                theirs = lineup([x for x in ids if x != b] + [a], info, slots)[0] - their_value
                # Why they might say yes: their lineup gets better ("lineup"), it doesn't get worse and they get at
                # least as much BPV back ("bpv"), or ESPN's draft ranking (how most owners value players) has the
                # player they get clearly ahead of the one they give ("espn").
                adp_a, adp_b = info[a]["adp"], info[b]["adp"]
                reason = ("lineup" if theirs >= 0.25 else
                          "bpv" if theirs >= -0.25 and info[a]["bpv"] >= info[b]["bpv"] - 0.25 else
                          "espn" if adp_a is not None and (adp_b is None or adp_a <= ESPN_EDGE * adp_b) else None)
                trades.append({"team": t, "give": card(a, adp=adp_a), "get": card(b, adp=adp_b), "gain": gain,
                               "their_gain": theirs, "fair": reason is not None, "reason": reason})
    trades.sort(key=lambda x: (not x["fair"], -x["gain"] if x["fair"] else -(x["gain"] + x["their_gain"])))
    seen, per_give, per_team, best_trades = set(), {}, {}, []
    for x in trades:          # variety: one idea per player we'd get, at most two per player we give and per team
        g, t = x["give"]["id"], x["team"]
        if x["get"]["id"] in seen or per_give.get(g, 0) >= 2 or per_team.get(t, 0) >= 2:
            continue
        seen.add(x["get"]["id"])
        per_give[g], per_team[t] = per_give.get(g, 0) + 1, per_team.get(t, 0) + 1
        best_trades.append(x)
        if len(best_trades) >= MAX_TRADES:
            break
    partners = []
    for t, ids in enumerate(teams):
        if t == mine or not ids:
            continue
        fit = sum(max(0, strength[t][p] - league_pos[p]) for p in needs) + sum(max(0, league_pos[p] - strength[t][p]) for p in surplus)
        partners.append({"team": t, "fit": fit, "strong": [p for p in needs if strength[t][p] > league_pos[p]],
                         "weak": [p for p in surplus if strength[t][p] < league_pos[p]]})
    partners = [p for p in sorted(partners, key=lambda p: -p["fit"]) if p["fit"] > 0][:3]

    # Players: sell high (mine, hot shooting at the same minutes), buy low (theirs, cold shooting), free agents.
    team_of = {i: t for t, ids in enumerate(teams) for i in ids}
    sell = [card(i, change=info[i]["ec"], basis=info[i]["basis"]) for i in my
            if info[i]["ec"] is not None and info[i]["ec"] >= CHANGE and abs(info[i]["mc"] or 0) < CHANGE / 2]
    buy = sorted([card(i, change=info[i]["ec"], basis=info[i]["basis"], owner=team_of[i]) for i in rostered
                  if team_of[i] != mine and info[i]["ec"] is not None and info[i]["ec"] <= -CHANGE
                  and abs(info[i]["mc"] or 0) < CHANGE / 2], key=lambda c: c["change"])[:MAX_LIST]
    losing = [card(i, change=info[i]["mc"], basis=info[i]["basis"]) for i in my if info[i]["mc"] is not None and info[i]["mc"] <= -CHANGE]
    free = [i for i in info if i not in rostered]
    rising = sorted([card(i, change=info[i]["mc"], basis=info[i]["basis"]) for i in free
                     if info[i]["mc"] is not None and info[i]["mc"] >= CHANGE], key=lambda c: -c["change"])[:MAX_LIST]
    fa_needs = {p: [card(i) for i in sorted((i for i in free if p in info[i]["pos"]), key=lambda i: -info[i]["bpv"])[:3]]
                for p in needs}
    # Pickups: the best free agents against your weakest bench players, one for one (as on the Waiver Wire page), kept
    # when the free agent is worth 1+ BPV more or the swap improves the starting lineup.
    bench = sorted((i for i in my if i not in my_starters), key=lambda i: info[i]["bpv"])
    pickups = []
    for add, drop in zip(sorted(free, key=lambda i: -info[i]["bpv"])[:3], bench[:3]):
        gain = lineup([x for x in my if x != drop] + [add], info, slots)[0] - my_value
        if gain < 0.5 and info[add]["bpv"] - info[drop]["bpv"] < 1.0:
            break
        pickups.append({"add": card(add), "drop": card(drop), "gain": gain})

    return {
        "team": mine, "teams": len(teams), "players": len(my), "lineup": slots,
        "standing": {"value": my_value, "rank": rank, "average": avg, "best": max(values), "values": values},
        "positions": pos_rows, "needs": needs, "surplus": surplus,
        "injury": injury, "trades": best_trades, "partners": partners,
        "sell_high": sell, "buy_low": buy, "losing_minutes": losing, "rising_free_agents": rising,
        "free_agents_at_needs": fa_needs, "pickups": pickups,
        "starters": sorted(my_starters, key=lambda i: -info[i]["bpv"]),
    }


def _num(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return None if v != v else v
