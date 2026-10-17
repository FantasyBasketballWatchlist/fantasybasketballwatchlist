"""Build docs/BPV-report.pdf: the full write-up of BPV, the website, and every test.

Run:  python -m analysis.report_charts CHART_DIR
      python -m analysis.report_pdf CHART_DIR
(CHART_DIR also holds the website screenshots site_watchlist.jpg, site_trade.jpg, site_waiver.jpg.)
"""
import datetime
import json
import os
import sys

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "BPV-report.pdf")

FONT_DIR = r"C:\Windows\Fonts"
pdfmetrics.registerFont(TTFont("Body", os.path.join(FONT_DIR, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", os.path.join(FONT_DIR, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Body-Italic", os.path.join(FONT_DIR, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Body-BoldItalic", os.path.join(FONT_DIR, "arialbi.ttf")))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-BoldItalic")

NAVY = colors.HexColor("#1f3b63")
BLUE = colors.HexColor("#2f5d9e")
LIGHT = colors.HexColor("#eef2f8")
GREEN_BG = colors.HexColor("#e8f3ec")
AMBER_BG = colors.HexColor("#fbf2e3")
RED_BG = colors.HexColor("#f8e7e5")
GRID = colors.HexColor("#c9d1dd")

S = {
    "title": ParagraphStyle("title", fontName="Body-Bold", fontSize=26, leading=31, textColor=NAVY, alignment=TA_CENTER),
    "subtitle": ParagraphStyle("subtitle", fontName="Body", fontSize=13, leading=18, textColor=BLUE, alignment=TA_CENTER),
    "h1": ParagraphStyle("h1", fontName="Body-Bold", fontSize=16, leading=20, textColor=NAVY, spaceBefore=6, spaceAfter=8, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Body-Bold", fontSize=12, leading=15, textColor=BLUE, spaceBefore=8, spaceAfter=4, keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Body", fontSize=9.6, leading=13.4, spaceAfter=5),
    "bullet": ParagraphStyle("bullet", fontName="Body", fontSize=9.6, leading=13.2, leftIndent=14, bulletIndent=4, spaceAfter=2),
    "formula": ParagraphStyle("formula", fontName="Body-Bold", fontSize=11, leading=15, alignment=TA_CENTER,
                              textColor=NAVY, spaceBefore=4, spaceAfter=6),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.4, leading=10.6),
    "cellb": ParagraphStyle("cellb", fontName="Body-Bold", fontSize=8.4, leading=10.6, textColor=colors.white),
    "caption": ParagraphStyle("caption", fontName="Body-Italic", fontSize=8.2, leading=10.5, textColor=colors.HexColor("#555555"),
                              alignment=TA_CENTER, spaceAfter=8),
    "box": ParagraphStyle("box", fontName="Body", fontSize=9.4, leading=13),
}


class Doc:
    def __init__(self, chart_dir):
        self.story = []
        self.charts = chart_dir

    def h1(self, text):
        self.story.append(Paragraph(text, S["h1"]))

    def h2(self, text):
        self.story.append(Paragraph(text, S["h2"]))

    def p(self, text):
        self.story.append(Paragraph(text, S["body"]))

    def bullets(self, items):
        for item in items:
            self.story.append(Paragraph(item, S["bullet"], bulletText="•"))
        self.story.append(Spacer(1, 3))

    def formula(self, text):
        self.story.append(Paragraph(text, S["formula"]))

    def table(self, rows, widths, header=True, zebra=True):
        data = [[Paragraph(str(c), S["cellb"] if (header and i == 0) else S["cell"]) for c in row]
                for i, row in enumerate(rows)]
        t = Table(data, colWidths=[w * inch for w in widths], repeatRows=1 if header else 0)
        style = [("GRID", (0, 0), (-1, -1), 0.4, GRID), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                 ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
        if header:
            style.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
        if zebra:
            for i in range(1 if header else 0, len(rows)):
                if i % 2 == 0:
                    style.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
        t.setStyle(TableStyle(style))
        self.story.append(t)
        self.story.append(Spacer(1, 8))

    def box(self, label, text, kind="green"):
        bg = {"green": GREEN_BG, "amber": AMBER_BG, "red": RED_BG, "blue": LIGHT}[kind]
        t = Table([[Paragraph(f"<b>{label}</b> {text}", S["box"])]], colWidths=[6.9 * inch])
        t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.6, GRID),
                               ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                               ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        self.story.append(KeepTogether([t, Spacer(1, 8)]))

    def image(self, name, width, caption=None):
        path = os.path.join(self.charts, name)
        from reportlab.lib.utils import ImageReader
        w, h = ImageReader(path).getSize()
        img = Image(path, width=width * inch, height=width * inch * h / w)
        parts = [img]
        if caption:
            parts.append(Paragraph(caption, S["caption"]))
        else:
            parts.append(Spacer(1, 6))
        self.story.append(KeepTogether(parts))

    def space(self, h=6):
        self.story.append(Spacer(1, h))

    def page(self):
        self.story.append(PageBreak())


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 8)
    canvas.setFillColor(colors.HexColor("#777777"))
    canvas.drawString(0.8 * inch, 0.5 * inch, "BPV: Measuring Fantasy Basketball Value")
    canvas.drawRightString(7.7 * inch, 0.5 * inch, f"Page {doc.page}")
    canvas.restoreState()


def build(chart_dir):
    res = json.load(open(os.path.join(HERE, "results.json")))
    rob = json.load(open(os.path.join(HERE, "robustness.json")))
    pre = json.load(open(os.path.join(HERE, "preseason_production.json")))
    cox = json.load(open(os.path.join(HERE, "test_cox.json")))
    misc = json.load(open(os.path.join(HERE, "test_misc.json")))
    mm = json.load(open(os.path.join(HERE, "test_minutes_model.json")))
    inj = json.load(open(os.path.join(HERE, "test_injury_reports.json")))
    fol = json.load(open(os.path.join(HERE, "test_research_followup.json")))
    round3 = json.load(open(os.path.join(HERE, "test_round3.json")))
    et = json.load(open(os.path.join(HERE, "test_espn_totals.json")))
    d = Doc(chart_dir)
    A = res["A_recent_form"]["A_ros"]["last5_played"]["train_mae_by_weight"]
    r4 = rob["R4"]
    draft_avg = {m: sum(r4[s]["draft_sim_total"][m] for s in r4) / len(r4) for m in next(iter(r4.values()))["draft_sim_total"]}
    sp_avg = {m: sum(r4[s]["spearman_total"][m] for s in r4) / len(r4) for m in next(iter(r4.values()))["spearman_total"]}
    wins = {m: sum(1 for s in r4 if max(r4[s]["draft_sim_total"], key=r4[s]["draft_sim_total"].get) == m) for m in draft_avg}
    age_sig = sum(1 for s in r4 if r4[s]["bpv_age_minus_bpv_ci95"][0] > 0)
    rb = res["D_early_season"]["rookie_baselines"]

    # ------------------------------------------------------------ cover
    d.space(120)
    d.story.append(Paragraph("BPV: Measuring Fantasy Basketball Value", S["title"]))
    d.space(10)
    d.story.append(Paragraph("The method, the website, and every test behind the numbers", S["subtitle"]))
    d.space(40)
    d.table([
        ["What this report covers"],
        ["1. The final BPV formula and a verdict on every question we tested"],
        ["2. The website: Watchlist, Trade Analyzer and Waiver Wires, and how each number is computed"],
        ["3. The ideas: availability, replacement level, types of missed games, recent form, new roles, rookies, injury risk"],
        ["4. How we tested: data, backtest design, error measures, resampling, and no-peeking model comparisons"],
        ["5. The ideal percentages: recent-form weight, New Role haircut and weight, availability settings, early-season blending"],
        ["6. Which method was best, how sure we are, what's still open, and what to try next"],
    ], [6.9])
    d.space(30)
    d.story.append(Paragraph(f"Data: NBA regular seasons 2019-20 through 2025-26 (every player-game and team-game), plus all NBA drafts. "
                             f"Generated {datetime.date.today():%B %d, %Y}.", S["caption"]))
    d.page()

    # ------------------------------------------------------------ 1 summary
    d.h1("1. Summary")
    d.p("BPV (Basketball Performance Value) estimates how many fantasy points per team game you get from having a player "
        "on your roster in an ESPN points league. It is built on one idea: <b>fantasy value is not the same as basketball "
        "value.</b> A fantasy manager gets a player's production when he plays, and can often stream a free agent when "
        "he doesn't. The final formula is:")
    d.formula("BPV = p × F + (1 − p) × q × R")
    d.table([
        ["Symbol", "Meaning", "How it's computed"],
        ["F", "Production: fantasy points per game played",
         "Season average + 0.3 × recent minutes change + 0.1 × recent per-minute change (last 5 games). New Role Value "
         "for players whose minutes jumped. Early in the season, blended (8 games' worth) with the saved preseason projection, or last season, or a draft-slot baseline (10 games). Between seasons: last season + age and roster adjustments, blended 37.5% with ESPN's preseason projection. In season: recalibrated."],
        ["p", "Availability: share of team games he's expected to play",
         "Recent seasons, each older season counting half as much, blended with 123 games of league-average availability (about 74%). Before a season: ESPN projected games × 0.86 / 82 where available. In season: adjusted for injuries on the official report, by injury type."],
        ["q", "Share of missed games that come in long, IR-able stretches (5+ straight games)", "League average, about 72%"],
        ["R", "Replacement level: what a free agent gives you",
         "Fantasy points per game of the 130th-best player (10 teams × 13 roster spots); about 27.5 in 2025-26"],
    ], [0.6, 2.2, 4.1])
    d.h2("Verdicts")
    d.p("Every question below was tested on real data. \"Established\" means the result held up on a season the method "
        "never saw and under resampling. \"Not established\" is also a firm answer: the data cannot distinguish the options.")
    d.table([
        ["Question", "Best method found", "Verdict"],
        ["Should recent games count extra?", "Yes: 10–20% weight on the last 5 games played", "<b>Established</b> (cuts error about 3%)"],
        ["Is 20% the ideal weight?", "Anything from 10% to 20% is equally good; 15% fit best most often", "<b>Not established</b>: 20% and 15% are a statistical tie"],
        ["Last 5 games played, or the team's last 5?", "Last 5 games played", "Slightly better; small difference"],
        ["Do recent minutes changes last more than hot/cold shooting?", "Yes: about 30% of a minutes change lasts vs about 10% of a shooting change", "<b>Established</b>"],
        ["Does splitting minutes from shooting predict better than plain 80/20?", "Split is at least as good", "<b>Not established</b> (gain too small to confirm)"],
        ["Does New Role Value beat 80/20 after a minutes jump?", "Yes, by about 1 FPTS per game", "<b>Established</b>"],
        ["Is the 90% haircut right?", "0.90 with 60% weight fit best, but 0.80–1.10 all fit about equally", "<b>Not established</b>"],
        ["Best availability estimate?", "Recent seasons weighted, shrunk heavily to the league average", "<b>Established</b>, but only about 1 point of games better than the average"],
        ["Is career GP% useful?", "No better than assuming every player is average", "<b>Established</b> (no significant difference)"],
        ["Should missed games count as zero?", "No: count streamed free-agent points for long absences", "Logical argument; supports how managers actually play"],
        ["Are erratic vs long absences a player trait?", "Can't be measured reliably from box scores", "<b>Not determinable</b> with this data"],
        ["How to value players early in the season?", "Blend with last season (8 games) or a draft-slot baseline for rookies (10 games)", "<b>Established</b> (large error reduction)"],
        ["Does age matter between seasons?", "Yes: young players gain up to +2.1 FPTS/game, 33+ lose about 3.7", "<b>Established</b> (4.7% less error, all 4 seasons)"],
        ["Do older seasons help a projection?", "No: last season alone is best (tested two ways)", "<b>Established</b> (no gain)"],
        ["Does BPV beat a published baseline?", "Last season + age beat Basketball-Reference's projection system", "<b>Established</b> for preseason production"],
        ["Exponential decay instead of last 5 games?", "Ties the current method", "No gain; recent form is at its ceiling"],
        ["Which preseason model ranks players best?", "The BPV + ESPN hybrid (0.686), ahead of ESPN (0.671) and plain BPV (0.664)", "<b>Established</b> vs ESPN (+0.016, interval +0.007 to +0.024)"],
        ["Does BPV beat ESPN?", "Per game, yes; on season-total rankings and drafts, plain BPV lost to ESPN", "<b>Honest answer: only the hybrid beats ESPN</b>"],
        ["Which preseason model drafts best?", f"A BPV version won all 4 seasons of simulated drafts ({wins['BPV + age']} with age, {wins['BPV (replacement-level)']} without)", "<b>Suggestive, not conclusive</b>"],
        ["Does a Cox injury-risk model improve availability?", "Built from box-score absences and tested: it doesn't beat the current estimate", "<b>No</b> (not added)"],
        ["Does next season's roster matter?", "Yes: more minutes of competition on the new team lowers production", "<b>Established</b> (added)"],
        ["Does a teammate's long-term injury raise a player's value?", "Yes, when the injury is known (+0.034 FPTS/g per lost minute)", "<b>Established</b> for known injuries only"],
        ["Are the 80% likely ranges trustworthy?", "In season 79.8% coverage; between seasons 72–82%", "<b>Calibrated</b> (added)"],
        ["Do official injury reports help?", "Yes: a serious injury listing predicts a long absence with no hindsight", "<b>Established</b> (automatic in season)"],
        ["Are BPV's in-season projections biased?", "Slightly too extreme (young players improve in season); recalibration fixes it", "<b>Established</b> (added)"],
        ["Do bad teams rest regulars in the fantasy playoffs?", "Yes: veterans on bad teams play 44 points less of their games", "<b>Established</b> (added to expected playoff FPTS)"],
    ], [2.2, 2.7, 2.0])

    # ------------------------------------------------------------ 2 website
    d.h1("2. The website")
    d.p("The site runs locally (<b>python app.py</b>, then open http://127.0.0.1:8080). It downloads whole seasons of NBA "
        "game logs from stats.nba.com, one request per season, and caches them on disk. Completed seasons are kept "
        "permanently, and the current season refreshes every 6 hours. All BPV math runs on the server, so every page "
        "shows the same numbers.")
    d.h2("Season modes")
    d.bullets([
        "<b>In-season:</b> a game was played in the last 14 days. Recent form, role-change detection and early-season blending are on.",
        "<b>Offseason:</b> the season has ended (today's state: 2025-26 is over). Values use the full season with recent form turned off, "
        "because a team's last 5 games of a season are distorted by resting and tanking, plus age and roster-crowding adjustments "
        "(Section 14). These values project to next season.",
        "<b>Preseason:</b> a new season has no games yet. The previous season is used until games are played.",
    ])
    d.h2("Watchlist (home page)")
    d.image("site_watchlist.jpg", 6.4, "The Watchlist: BPV, Heat Check Index, the full breakdown, likely range and fantasy-playoff games. Between seasons the note shows the age and roster adjustments.")
    d.bullets([
        "<b>BPV</b> and <b>rank</b> among all players.",
        "<b>Heat Check Index (HCI):</b> BPV as a percentage of the league's best BPV (the best player = 100).",
        "<b>Production, season average and last-5 average</b>, with a note on how production was computed "
        "(season average, recent form, new role detected, blended with last season, or draft-slot baseline).",
        "<b>Expected availability</b>, games missed this season, and <b>value over a free agent</b> (BPV − R).",
        "The full formula with the player's own numbers filled in, and his per-game box-score averages.",
        "A <b>top-25 table</b>; clicking a row opens that player.",
        "Newly drafted players with no NBA games show a projection from their draft range instead of 0.",
        "<b>Likely range (80%)</b> for production, and <b>fantasy-playoff games</b> (his team's games in the last 4 weeks; 13–16 in 2026-27).",
        "Between seasons, players are shown on <b>next season's team</b> (from current NBA rosters), and unsigned players as FA.",
        "League size and roster size are settings (LEAGUE_TEAMS, LEAGUE_ROSTER_SIZE; default 10 and 13), which set the replacement level.",
        "In season: the <b>official injury report</b> status and reason, with the chance of playing (Probable 91%, Questionable 49%, "
        "Doubtful 2%), <b>this week's expected FPTS</b>, and <b>expected fantasy-playoff FPTS</b>, which allows for late-season resting on bad teams.",
        "Between seasons: <b>ESPN's projection</b> (per game and games) next to BPV's, blended into BPV as tested.",
    ])
    d.h2("Trade Analyzer")
    d.image("site_trade.jpg", 6.4, "A 2-for-1: the receiving side has 31.6 more raw BPV, but after accounting for the roster spot the edge is 4.1 FPTS per game.")
    d.p("Add players to each side and press Analyze. The verdict compares <b>value over replacement</b> (BPV − R) instead "
        "of raw BPV. Why: in a 2-for-1, the side that gets fewer players frees a roster spot, and that spot is filled by a "
        "free agent worth R. Summing raw BPV ignores this and always favors the side getting more players. Clicking a "
        "player removes him (this also fixed a bug where names with apostrophes, like De'Aaron Fox, couldn't be removed).")
    d.box("Caution:", "BPV's typical error predicting a single player's rest-of-season average is about 4 FPTS per game. "
          "A trade edge of 1–3 points per game is within that noise. Treat small edges as \"about even.\"", "amber")
    d.h2("Waiver Wires")
    d.image("site_waiver.jpg", 6.4, "Waiver Wires, split by why a player's last 5 games changed.")
    d.p("Each player's last-5 change is split into a <b>minutes part</b> (per-minute production × change in minutes) and a "
        "<b>per-minute part</b> (everything else: shooting and luck). Four lists follow from the finding in Section 11 that "
        "minutes changes last and shooting swings fade:")
    d.table([
        ["List", "Rule", "Why"],
        ["Pick up: minutes rising", "Minutes part ≥ threshold", "More playing time usually sticks"],
        ["Sell high: hot shooting", "Per-minute part ≥ threshold, minutes steady", "Hot shooting in the same minutes tends to fade"],
        ["Buy low: cold shooting", "Per-minute part ≤ −threshold, minutes steady", "Cold shooting in the same minutes tends to recover"],
        ["Drop candidates: minutes falling", "Minutes part ≤ −threshold", "Lost playing time usually lasts; check the news first"],
    ], [1.9, 2.5, 2.5])
    d.p("The threshold (default 4 FPTS per game) is adjustable. The site can't see your league's rosters, so the lists cover the whole league.")
    d.h2("Manual inputs")
    d.p("<b>data/overrides.json</b> holds what box scores can't know. Injuries use <b>{\"out_for_season\": true}</b> or "
        "<b>{\"out_games\": 10}</b>; those games are treated as one long, IR-able absence, so they earn the free-agent credit. "
        "Role changes use <b>{\"since\": \"2026-01-15\"}</b>, which applies New Role Value from that date. This replaces the first "
        "version's hard-coded list of 40 players forced to BPV 0, which described 2024-25 injuries. A known injury also helps his "
        "teammates: in season they get +0.034 FPTS per game for each minute per game he played; between seasons his minutes are "
        "removed from his team's roster crowding (Section 14).")

    # ------------------------------------------------------------ 3 core ideas
    d.h1("3. The core idea")
    d.p("Imagine a player who is great at his job and gets the crowd hyped, but misses a lot of games. Fans love him, "
        "but a fantasy manager doesn't get production worth the hype. Now imagine a slightly worse player who stays quiet "
        "but consistently produces and shows up to nearly every game. The fans wouldn't go crazy over him, but a fantasy "
        "manager would. The goal isn't to find the best basketball player; it's to find the player who gives a manager "
        "the most expected value.")
    d.h2("Terms")
    d.table([
        ["Term", "Meaning"],
        ["ADP", "Average draft position: a player's average pick number across many drafts. It shows where players are taken, not where they should be."],
        ["FPTS", "Fantasy points, using ESPN's default points scoring (Section 4)."],
        ["Roster", "ESPN standard: 13 players, of which 10 start (PG, SG, SF, PF, C, G, F and 3 UTIL) and 3 sit on the bench."],
        ["IR", "Injured reserve: a slot outside the 13. Only players with the O (Out), IR or IL tag can be placed there, so "
               "Questionable and Day-to-Day players can't. The number of IR slots varies by league."],
        ["Free agent / waivers", "Undrafted or dropped players anyone can add. A recently dropped player goes through waivers; ESPN "
                                 "orders claims either by resetting weekly to reverse standings or by moving a team to the back after each claim."],
        ["Replacement level (R)", "What a typical free agent produces. With 10 teams × 13 spots, 130 players are rostered; "
                                  "the 130th-best averages about 25–27.5 FPTS per game."],
    ], [1.5, 5.4])
    d.h1("4. The scoring formula")
    d.formula("FPTS = PTS + REB + 2·AST + 4·STL + 4·BLK − 2·TO + 2·FGM − FGA + FTM − FTA + 3PM")
    d.p("This is ESPN's default points scoring. It values points, rebounds and assists, and it also rewards efficiency: "
        "a made two is worth +3, a made three +5, a made free throw +1, and every miss −1. BPV never changes these "
        "weights. The point is not \"what the scoring should be\" but \"given the real scoring, what is a player worth.\" "
        "BPV always works in <b>FPTS per game</b>; season totals already include games missed, so multiplying a total by "
        "availability would count absences twice.")

    # ------------------------------------------------------------ 5 availability & replacement
    d.h1("5. Availability and replacement level")
    d.p("Player A averages 45 FPTS and plays 60% of games: 45 × 0.60 = 27. Player B averages 30 and plays 90%: "
        "30 × 0.90 = 27. They look identical, but a missed game isn't worth zero. When A is out, you can put him on IR and "
        "pick up a free agent. If a free agent gives you 20 FPTS:")
    d.bullets(["Player A: 45 × 0.60 + 20 × 0.40 = <b>35</b>", "Player B: 30 × 0.90 + 20 × 0.10 = <b>29</b>"])
    d.formula("Value = p × F + (1 − p) × R  =  R + p × (F − R)")
    d.p("Multiplying production by availability is the special case R = 0, which assumes you get nothing when a player "
        "sits. The second form shows what really drives value: how far a player is above a free agent, times how often he "
        "plays. Two limits apply: leagues have only one or two IR slots (if one is already used, the next injured player's "
        "missed games really are worth zero), and benching a player doesn't open a roster spot.")
    d.h1("6. Types of missed games")
    d.p("Player D misses 30 straight games with one injury; Player E misses 30 scattered games. Their availability is "
        "identical, but D goes on IR once and you stream free agents in his place, while E cycles between Questionable "
        "and Out, can't be placed on IR while Questionable, and forces awkward lineup decisions. So only long absences get "
        "the free-agent credit, through q: the share of missed games that come in stretches of 5 or more straight team games.")
    d.p("<b>How we measured it.</b> For every player-season we walked his games against his team's schedule and recorded "
        "every run of consecutive team games he missed. Around a trade, the gap is measured on whichever team's schedule "
        "gives the shorter gap; in a debut season, games before his first appearance aren't counted. Spot checks: Giannis "
        "Antetokounmpo 2025-26 played 36 and missed 46 (82 possible); Nikola Jokić played 65 and missed 17; traded players "
        "came out at 80–83 possible games.")
    d.image("q_reliability.png", 6.6, "Blue: does a player's q repeat the next season? Orange: does q even agree between the two halves of one season?")
    d.p("Across rotation players, about <b>72%</b> of missed games come in long stretches. But a player's own q barely "
        "repeats from one season to the next (correlation 0.03–0.13 depending on the definition). That alone would suggest "
        "\"not a trait,\" but the orange bars show the measure is too noisy to judge: the two halves of the same season "
        "barely agree either, which puts the reliability of one season's q at about 0.05–0.23. Box scores can't separate "
        "injuries from rest days, suspensions or coach's decisions, which adds noise.")
    d.box("Verdict:", "Whether a player tends to miss games erratically is <b>not determinable</b> from box-score data. "
          "BPV therefore uses the league-average q (72%) for everyone, which is the right choice for an unreliable measure. "
          "Known long injuries can be entered manually. Injury-report data would be needed to test the Player D vs E idea properly.", "amber")

    # ------------------------------------------------------------ 7 availability estimation
    d.h1("7. Estimating availability")
    d.p("We tested how best to predict a regular player's (20+ minutes per game) share of games played next season from "
        "his history. Settings tried: how much each older season counts (all equal; 0.85, 0.7 or 0.5 per year back; or "
        "last season only) and how many games of league-average availability to blend in (k = 0 to 246).")
    d.image("availability.png", 6.8, "Left: error for each setting (lighter is better). Right: methods compared on seasons they weren't tuned on.")
    r6 = rob["R6"]
    d.table([
        ["Method", "Avg error (share of games)", "Result"],
        ["Last season only", f"{res['C_availability']['mae_last_season_only']:.3f}", "Worst"],
        ["Career GP% (first version of BPV)", f"{r6['mae_career_gp']:.3f}", "Not significantly different from the league average"],
        ["Everyone gets the league average", f"{r6['mae_league_average']:.3f}", "Baseline"],
        ["Recent seasons weighted + shrunk to the league average", f"{r6['mae_shrunk_out_of_sample']:.3f}",
         f"Best; better than the average by 0.004–0.013 (95% interval)"],
    ], [2.9, 1.6, 2.4])
    d.p("The error surface is flat near the best: decay 0.5–0.7 per season with k = 123–164 games all perform within "
        "0.001. BPV uses decay 0.5 and k = 123. Blending in 123 games (about a season and a half) means a player's own record "
        "needs more than that before it outweighs the league average. The formula also uses real schedules (66, 64–75 and "
        "72 games in 2011-12, 2019-20 and 2020-21), handles trades, and counts a whole missed season (like a torn Achilles) "
        "as fully missed.")
    d.box("Verdict:", "Weighted-and-shrunk history is the best method, but <b>availability is mostly unpredictable</b>: "
          "this season's and next season's availability correlate at only 0.24, and the best method beats simply assuming "
          "every player is average by about one percentage point of games. Career GP% adds nothing over the average.", "green")

    # ------------------------------------------------------------ 8 Cox
    d.h1("8. Injury risk and the Cox model")
    d.p("Aryan Jha's article \"Figuring out why NBA players get injured using Cox Proportional Hazards\" (Medium, September 28, 2025) "
        "studied every All-Star since 2005-06: 120 players, 1,420 player-seasons and 70 season-ending injuries. Significant "
        "factors were height, season, field goals made, rebounds, blocks, fouls committed, fouls drawn and points. Each extra "
        "inch of height carried about 31% more hazard; a 6'3\" player had about a 98.7% chance of finishing 82 games without "
        "a season-ending injury vs 89.4% for a 6'11\" player.")
    d.formula("h(t | x) = h<sub>0</sub>(t) × e<super>β<sub>1</sub>x<sub>1</sub> + β<sub>2</sub>x<sub>2</sub> + … + β<sub>p</sub>x<sub>p</sub></super>")
    d.bullets([
        "<b>How it works:</b> the model fits one weight β per trait across all players at once. It does not match a player to similar historical players.",
        "<b>Why it can't be multiplied into BPV:</b> e<super>βx</super> is a relative risk; above 1 means riskier. Multiplying FPTS by it would raise risky players' values.",
        "<b>Correct use:</b> convert risk to a probability of staying healthy, S(t | x) = S<sub>0</sub>(t) raised to the power e<super>βx</super>, and use it as availability p. "
        "Or rank players by risk into percentile buckets and give each bucket its historically observed games-played share. "
        "Multiplying by the raw percentile doesn't work: it would give the riskiest player about ×0.05 and ignores how large the gaps really are.",
        "<b>Limits:</b> it models only season-ending injuries in All-Stars, it uses minutes and points as inputs (partly penalizing production), "
        "and the article text reports no out-of-sample accuracy.",
    ])
    d.h2("We built and tested it")
    d.p("Injury reports aren't needed to try it: box scores record absences, which is what costs a fantasy manager. The model "
        "predicts when a player's first long absence of the season starts (10+ straight missed team games, any cause) from height, "
        "weight, age, last season's minutes, usage, games played and production, BPV's availability estimate, and his history of long "
        "absences. Each season 2022-23 to 2025-26 was predicted with a model fitted only on earlier seasons; risk was converted to "
        "availability through percentile buckets.")
    cp = cox["pooled"]
    d.table([
        ["Measure", "Cox model", "BPV's current estimate"],
        ["Ranking who misses time (C-index, 0.5 = random)",
         f"{min(v['c_index_test'] for v in cox['per_target'].values()):.2f}–{max(v['c_index_test'] for v in cox['per_target'].values()):.2f}",
         f"{min(v['c_index_current_p_hat'] for v in cox['per_target'].values()):.2f}–{max(v['c_index_current_p_hat'] for v in cox['per_target'].values()):.2f}"],
        ["Availability error", f"{cp['mae_cox_bucket']:.3f}", f"{cp['mae_current']:.3f}"],
        ["Cox added on top of current", f"{cp['mae_combined']:.3f} (difference {cp['combined_minus_current']['diff']:+.4f}, "
         f"interval {cp['combined_minus_current']['ci95'][0]:+.4f} to {cp['combined_minus_current']['ci95'][1]:+.4f})", "—"],
    ], [2.6, 2.6, 1.7])
    hr = cox["hazard_ratios_per_sd"]["height"]
    d.p(f"The same happened with long absences defined as 5+ or 20+ games. Height was the only factor with a hint of signal "
        f"({(hr['hr'] - 1) * 100:.0f}% more risk per standard deviation, p = {hr['p']:.2f}), in the same direction as Jha's finding.")
    d.box("Verdict:", "The Cox model <b>doesn't beat</b> BPV's current availability estimate, alone or combined, so it isn't used.", "amber")
    d.h2("Official injury reports")
    i12 = inj["I1_I2"]
    reasons = i12["regulars_out_games_by_reason"]
    conv = i12["status_played_share"]
    d.p("We added the NBA's official injury reports: one per game day, 2021-22 to 2025-26 (816 days, about 60,000 listings), read "
        "with the nbainjuries package. Unlike box scores, they give a status and a reason.")
    d.table([
        ["Finding", "Result"],
        ["Why regulars (20+ mpg) miss games", f"injury {reasons['injury']:.0%}, rest {reasons['rest']:.0%}, G League {reasons['g_league']:.1%}, "
                                             f"COVID protocols {reasons['health_protocols']:.1%}, personal {reasons['personal']:.0%}"],
        ["Rest over time", f"{i12['by_season']['2021-22']['rest']:.1%} of absences in 2021-22 → {i12['by_season']['2025-26']['rest']:.1%} in 2025-26, "
                           "despite the 2023 Player Participation Policy"],
        ["Share who played, by status", f"Probable {conv['Probable']['mean']:.0%}, Questionable {conv['Questionable']['mean']:.0%}, "
                                        f"Doubtful {conv['Doubtful']['mean']:.1%}, Out {conv['Out']['mean']:.1%}"],
        ["Out with a serious injury", f"played a median 7% of remaining games; {inj['I3']['flags']['serious_share_missing_80pct_plus']:.0%} missed 80%+"],
        ["Their own availability", "error 0.60 with BPV's usual estimate → 0.16 using the report (gain interval 0.18–0.60)"],
        ["Teammate boost from those listings (no hindsight)", f"{inj['I3']['lost_serious']['affected']['diff']:+.2f} for affected players "
                                                              f"({inj['I3']['lost_serious']['affected']['ci95'][0]:+.2f} to {inj['I3']['lost_serious']['affected']['ci95'][1]:+.2f})"],
        ["Any \"Out\" listing as the trigger", f"{inj['I3']['lost_any']['affected']['diff']:+.2f} (tie)"],
        ["Injury and rest history → next season's availability", f"{inj['I4']['new_minus_current']['diff']:+.4f} (tie)"],
        ["Resting as a habit", f"year-to-year correlation {inj['I5']['rest_games_yoy_corr_25mpg']:.2f}; under 1 rest game per regular per season"],
    ], [2.4, 4.5])
    d.box("Verdict:", "In season, BPV now <b>reads the latest official injury report automatically</b>: a player Out with a serious injury is "
          "treated as missing about 93% of remaining games, and his 20+ minute teammates get +0.029 FPTS/game per lost minute. "
          "Statuses and chances of playing are shown on the site.", "green")

    # ------------------------------------------------------------ 9 testing method
    d.h1("9. How we tested")
    d.p("Every percentage in BPV was chosen by <b>backtesting</b>: pretending to stand at a point in a past season, "
        "making a prediction with only the information available then, and checking it against what actually happened.")
    d.h2("Data")
    d.bullets([
        "Every regular-season player-game and team-game from 2019-20 through 2025-26 (about 26,000 player-games per season), from stats.nba.com via nba_api.",
        "Every NBA draft pick, for rookie baselines.",
        "NBA Cup championship games don't count as regular-season games and are excluded; earlier Cup games are included.",
    ])
    d.h2("In-season tests (recent form, New Role Value, early season)")
    d.bullets([
        "<b>Checkpoints:</b> every 7 days, from 4 weeks into each season until 3 weeks before the end.",
        "<b>At each checkpoint,</b> for each player with at least 10 games before and 10 after, and at least 12 minutes per game: "
        "season-to-date average, last-5 average, minutes, and the <b>answer</b>: his actual average over the rest of the season.",
        "<b>Error</b> = average absolute difference between the prediction and the answer, in FPTS per game.",
        "<b>Tuning seasons</b> 2021-22 to 2024-25 (21,427 player-checkpoints) choose the percentages. The <b>test season</b> 2025-26 "
        "(5,404 checkpoints) is never used for tuning; results there show whether a choice really works.",
    ])
    d.h2("Resampling (how sure are we?)")
    d.p("A single number like \"15% is best\" can be luck. To measure uncertainty we used the <b>bootstrap</b>: redraw the "
        "players at random (with replacement), keeping all of each player's checkpoints together, and redo the calculation "
        "300 times. The spread of the answers gives a <b>95% interval</b>. If the interval for a difference includes zero, the "
        "two options are statistically tied.")
    d.h2("Preseason tests (model comparison)")
    d.bullets([
        "Each model ranks players using only seasons before the target season. Its settings are tuned only on even earlier seasons, so no model sees the answers.",
        "<b>Rank correlation:</b> how well each model's order matches the actual order of total FPTS (1 = perfect).",
        "<b>Simulated drafts:</b> 1,000 drafts per season, 10 teams, 13 rounds, snake order. Each model gets 2 randomly placed seats and takes the best player left on its list. Teams are scored by their players' actual season FPTS.",
        "Players who never played again after the predicted season (mostly retirements) are left out, since a preseason ranker would know about retirements.",
        "<b>Preseason production</b> (Section 14): 1,151 player-seasons, each target season predicted with settings fitted only on the other three (leave-one-season-out).",
    ])

    # ------------------------------------------------------------ 10 recent form
    d.h1("10. Recent form: finding the ideal percentage")
    d.p("The proposal: <b>BPV = 80% season performance + 20% last 5 games</b>. We tested every weight from 0% to 60% in steps of 5%.")
    d.image("recent_weight.png", 6.8, "Left: error across the tuning seasons for two definitions of the last 5 games. Right: each season separately.")
    d.table([
        ["Weight on last 5", "0%", "10%", "15%", "20%", "30%", "50%"],
        ["Avg error (FPTS/game)"] + [f"{A[w]:.3f}" for w in ["0.0", "0.1", "0.15", "0.2", "0.3", "0.5"]],
    ], [1.5, 0.9, 0.9, 0.9, 0.9, 0.9, 0.9])
    d.image("weight_bootstrap.png", 3.3, "Across 300 resamples of players, the best weight was 15% 88% of the time.")
    bs = rob["R1_best_weight_by_season"]
    d.bullets([
        f"<b>Recent form helps:</b> on the unseen 2025-26 season, 20% beat 0% by {-rob['R1_test_diff_20_minus_0']['point']:.2f} FPTS per game "
        f"(95% interval {-rob['R1_test_diff_20_minus_0']['ci95'][1]:.2f}–{-rob['R1_test_diff_20_minus_0']['ci95'][0]:.2f}), about 3% less error.",
        "<b>The exact weight is flat:</b> the best weight in each season was " + ", ".join(f"{s} {v * 100:.0f}%" for s, v in bs.items()) + ".",
        f"<b>20% vs 15% on the unseen season:</b> difference {rob['R1_test_diff_20_minus_15']['point']:+.3f} (interval "
        f"{rob['R1_test_diff_20_minus_15']['ci95'][0]:+.3f} to {rob['R1_test_diff_20_minus_15']['ci95'][1]:+.3f}), a tie.",
        "<b>Next two weeks only</b> (start/sit decisions): the best weight was 20–25%, since short-term predictions lean more on recent games.",
        "<b>Which 5 games:</b> the player's last 5 games played beat \"the team's last 5 games, counting only the ones he played\" "
        "(the first draft's definition), and avoids basing recent form on 1–2 games. Absences are handled by availability instead.",
        "<b>Offseason:</b> in preseason tests, the 80/20 blend predicted the next season no better than the plain season "
        "average, because the end of a season is distorted by resting and tanking. BPV turns recent form off between seasons.",
        "<b>Exponential decay</b> (every game counting a little less than the next, as DARKO and EPM do) tied the current method on the unseen season "
        "(4.10 for a 20-game half-life vs 4.10 for BPV). The best version updated minutes fast (12-game half-life) and per-minute production slowly (30), "
        "which independently supports the minutes/shooting split in Section 11. Its gain over BPV was not significant (−0.013, interval −0.046 to +0.020).",
    ])
    d.box("Verdict:", "Giving the last 5 games played <b>10–20%</b> weight is best; the data cannot choose between values in that range. "
          "20% is a sound choice. Recent form counts at about 28% by midseason, because the last 5 games are also part of the season average.", "green")

    # ------------------------------------------------------------ 11 minutes vs efficiency
    d.h1("11. Minutes vs shooting: which streaks last")
    d.p("Any last-5 change can be split into a <b>minutes part</b> (per-minute production × change in minutes) and a "
        "<b>per-minute part</b> (everything else: shooting, efficiency, luck). We estimated how much of each part carries "
        "into the rest of the season.")
    r3 = rob["R3_weights"]
    d.image("minutes_vs_efficiency.png", 3.4, "Weights with 95% intervals. The intervals don't overlap.")
    d.bullets([
        f"<b>Minutes:</b> {r3['minutes']:.2f} of the change lasts (interval {r3['minutes_ci95'][0]:.2f}–{r3['minutes_ci95'][1]:.2f}).",
        f"<b>Per-minute:</b> {r3['efficiency']:.2f} lasts (interval {r3['efficiency_ci95'][0]:.2f}–{r3['efficiency_ci95'][1]:.2f}).",
        "This matches outside research: minutes are mostly a coach's decision and stabilize within about 1.5 games, while "
        "three-point percentage takes about 240 attempts to stabilize (Medvedovsky, 2020). Research on the hot hand finds "
        "a real but small effect (about 1–2 percentage points on the next shot).",
        f"As a prediction method, the split beat plain 80/20 on the unseen season by only {-rob['R3_test_split_minus_8020']['point']:.2f} FPTS "
        f"per game (interval {rob['R3_test_split_minus_8020']['ci95'][0]:+.3f} to {rob['R3_test_split_minus_8020']['ci95'][1]:+.3f}), which is not significant.",
    ])
    d.box("Verdict:", "Minutes changes last about three times more than shooting swings: <b>established</b>. This is the basis for "
          "buy-low / sell-high decisions and the Waiver Wires page. BPV uses the split (0.3 minutes, 0.1 per-minute) for production; plain 80/20 would be nearly as accurate.", "green")
    d.h2("Buy low, sell high")
    d.p("Sell a player who is hot <b>in the same minutes</b> (his streak will likely fade) and buy one who is cold in the same "
        "minutes (he'll likely recover). A player whose <b>minutes jumped</b> is a real pickup. The reason to accept short-term "
        "losses for long-term value is the fantasy playoffs at the end of the season, where the championship is decided.")
    d.p("<b>Example.</b> Player L had a hot week but has never been that good; player M, a 2nd-round pick, played like a "
        "5th-rounder for a week. BPV valued L at 23.0 and M at 25.2, and the trade for M was accepted. The direction fits the "
        "evidence (M's longer record should count more), but the 2.2-point gap is within BPV's typical error of about 4 points "
        "per game, so the example supports the method's logic rather than proving it.")

    # ------------------------------------------------------------ 12 new role
    d.h1("12. New roles: testing the 90% and 50/50")
    d.p("Player N plays 10 minutes a game for 50 games, then a starter gets hurt and N plays 30. His first 50 games understate his new value. Proposal:")
    d.formula("New Role Value = FPTS per minute × new minutes per game × haircut")
    d.formula("BPV = (1 − w) × previous value + w × New Role Value")
    d.p("We tested every haircut from 0.60 to 1.10 and every weight w from 0% to 100% on the 703 cases where a player's "
        "last-5 minutes were at least 8 above his season average (from 24 minutes or less). These averaged 17.5 minutes before "
        "and 28.1 in their last 5 games.")
    d.image("new_role_grid.png", 4.6, "Star: best fit (0.90 haircut, 60% weight). Circles: every pair within 1% of the best.")
    r2 = rob["R2"]
    d.table([
        ["Method (unseen 2025-26 season)", "Avg error (FPTS/game)"],
        ["Season average only", f"{res['B_new_role']['test_mae']['season_only (Model 1)']:.2f}"],
        ["80/20 recent form", f"{res['B_new_role']['test_mae']['80/20 (Model 2)']:.2f}"],
        ["New Role Value, 0.90 haircut, 50/50 (first draft)", f"{res['B_new_role']['test_mae']['paper NRV: 90% haircut, 50/50']:.2f}"],
        ["New Role Value, 0.90 haircut, 60/40 (best fit)", f"{res['B_new_role']['test_mae']['fitted: 0.90 haircut, 0.6 on new role']:.2f}"],
    ], [4.5, 2.4])
    d.bullets([
        f"New Role Value beat 80/20 by {-r2['test_nrv_minus_8020']['point']:.1f} FPTS per game on the unseen season "
        f"(95% interval {-r2['test_nrv_minus_8020']['ci95'][1]:.1f}–{-r2['test_nrv_minus_8020']['ci95'][0]:.1f}), and cut error by a third compared with the season average.",
        "The haircut and the weight trade off: a smaller haircut with more weight fits about as well as a bigger haircut with less weight. "
        f"Resampling players, the best haircut ranged over {r2['bootstrap_best_haircut_ci95'][0]:.2f}–{r2['bootstrap_best_haircut_ci95'][1]:.2f} "
        f"and was 0.90 only {r2['bootstrap_best_haircut_share_0.90'] * 100:.0f}% of the time.",
        "<b>Detection:</b> the site applies New Role Value automatically when a player has 10+ games, averaged 24 minutes or less, "
        "and his last-5 minutes are 8+ above his average (these thresholds define the test group; they weren't tuned). A role change "
        "can also be entered manually with a start date, since an algorithm can't tell a one-week absence from a season-long one.",
    ])
    d.box("Verdict:", "New Role Value is <b>clearly better</b> than 80/20 after a minutes jump: established. The exact haircut is "
          "<b>not established</b>; anything from about 0.80 to 1.10 with a matching weight works. BPV uses the best fit, 0.90 with 60/40.", "green")

    # ------------------------------------------------------------ 13 early season & rookies
    d.h1("13. Early season, rookies, and players with no games")
    d.p("Five games tell you little. We tested blending a player's current average with k games' worth of a prior: last "
        "season's average for returning players, and the average rookie from his draft range for rookies.")
    d.image("early_season_k.png", 3.8, "Error at checkpoints with 20 or fewer games played, by games of prior blended in.")
    d.table([
        ["Group", "No blending (k = 0)", "Best k", "Error at best k", "Observations"],
        ["Returning players", "5.12", "8 games", "4.07", "14,278"],
        ["Rookies", "6.46", "10 games (8 ties)", "4.90", "3,312"],
    ], [1.5, 1.4, 1.3, 1.3, 1.4])
    d.p("Rookie baselines (average rookie season by draft range, drafts 2020–2025):")
    order = ["1-3", "4-10", "11-20", "21-30", "31-60", "undrafted"]
    d.table([["Pick range", "Rookies", "FPTS/game", "Minutes/game", "FPTS per minute", "Avg games played"]] +
            [[b.capitalize() if b == "undrafted" else b, rb[b]["rookies"], f"{rb[b]['fpts_per_game']:.1f}", f"{rb[b]['minutes_per_game']:.1f}",
              f"{rb[b]['fpts_per_minute']:.2f}", f"{rb[b]['games_played_avg']:.0f}"] for b in order],
            [1.2, 0.9, 1.1, 1.2, 1.3, 1.2])
    d.bullets([
        "By about game 24, a returning player's current season carries 75% of the weight (24 of 32 games).",
        "Players with no NBA games yet (new draftees) get their draft range's baseline, league-average availability and a \"projection only\" label. The first version of the site gave them 0.",
    ])
    d.box("Verdict:", "Blending cuts early-season error by about 20–25%: <b>established</b>. BPV uses 8 games of last season for returning players and 10 games of the draft baseline for rookies.", "green")

    # ------------------------------------------------------------ 14 between seasons
    d.h1("14. Between seasons: age matters, older seasons don't")
    d.p("Before a season, BPV projects each player's production from what he did before. We compared six ways of doing that "
        "on 1,151 player-seasons (20+ games in both seasons, 15+ minutes per game), predicting each season from 2022-23 to 2025-26 "
        "with settings fitted only on the other three.")
    d.image("age_curve.png", 6.8, "Left: the age curve BPV uses. Right: preseason error of each approach.")
    m = pre["mae"]
    d.table([
        ["Preseason production model", "Error (FPTS/game)", "Result"],
        ["Last season's FPTS per game (BPV before this test)", f"{m['last']:.2f}", "Baseline"],
        ["Last three seasons blended, shrunk toward the average", f"{m['fpg multi']:.2f}", "Tuning chose last season only"],
        ["Three seasons of per-minute production × last season's minutes", f"{m['rate x min']:.2f}", "Significantly worse"],
        ["Basketball-Reference's Simple Projection System", f"{m['sps']:.2f}", "Slightly better than baseline (not significant)"],
        ["<b>Last season + age adjustment</b>", f"<b>{m['last+age']:.2f}</b>", "<b>Best</b>"],
    ], [3.6, 1.2, 2.1])
    la = pre["last+age minus last"]
    ls = pre["last+age minus sps"]
    d.bullets([
        f"<b>Age:</b> cut error by {-la['diff']:.2f} FPTS per game (95% interval {-la['ci95'][1]:.2f}–{-la['ci95'][0]:.2f}), about 4.7%, "
        "and helped in all four seasons.",
        f"<b>Benchmark:</b> it beat Basketball-Reference's projection system by {-ls['diff']:.2f} FPTS per game (interval {-ls['ci95'][1]:.2f}–{-ls['ci95'][0]:.2f}).",
        "<b>Flat vs proportional:</b> adding a fixed number of points by age beat scaling by a percentage (4.40 vs 4.43), and did better for stars.",
        "<b>Stability:</b> the curve fitted only on seasons before 2022-23 is nearly the same as the final one.",
        "<b>Older seasons don't help,</b> tested two ways. This goes against standard practice (Basketball-Reference and baseball's Marcel blend three seasons). "
        "A likely reason: a fantasy player's value is mostly his current role, and older seasons describe roles he no longer has.",
        "<b>Caveat:</b> players who fell out of the league were excluded, which probably understates the decline at older ages.",
        f"<b>Early season too:</b> age-adjusting last season's level in the early-season blend (Section 13) cut error by "
        f"{-misc['T1_early_season_age']['new_minus_current']['diff']:.2f} FPTS per game (interval "
        f"{-misc['T1_early_season_age']['new_minus_current']['ci95'][1]:.2f}–{-misc['T1_early_season_age']['new_minus_current']['ci95'][0]:.2f}).",
    ])
    d.h2("Roster competition")
    c = mm["crowding"]["minus_current"]
    ch = mm["changed_team"]["minus_current"]
    d.p("Next season's rosters are public before the season. For each player we measured <b>crowding</b>: the total last-season "
        "minutes per game of his new teammates who played 10+ minutes, minus the league-average team.")
    d.bullets([
        f"Crowding cut preseason error by a further {-c['diff']:.2f} FPTS per game (interval {-c['ci95'][1]:.2f}–{-c['ci95'][0]:.2f}), "
        f"with the same coefficient in all four held-out seasons: <b>{mm['final_crowding_coef']:.4f} FPTS per game per minute</b>. "
        "Joining a team with 40 more rotation minutes than average costs about 0.7 FPTS per game.",
        f"Just knowing he changed teams didn't help ({ch['diff']:+.2f}, interval {ch['ci95'][0]:+.2f} to {ch['ci95'][1]:+.2f}); "
        "the competition for minutes is what matters.",
        "Preseason rosters carry about 20 players per team vs about 15 on opening night, but only 10+ minute players count, so the "
        "scale matches the test closely.",
    ])
    d.box("Verdict:", "Between seasons, BPV uses <b>last season + a flat age adjustment + roster crowding</b> (for players with 20+ "
          "games and 15+ minutes). Established: better in every season, and better than a published projection system.", "green")

    d.h2("Head to head with ESPN")
    mt, sp = et["mae_total"], et["spearman_mean"]
    dm = et["draft_sim_mean"]
    d.p("ESPN's public fantasy API still serves its preseason projections for past seasons (2021-22 and 2023-24 to 2025-26; its "
        "2022-23 file was frozen mid-season and is excluded). This is the competitor comparison that was missing. Everyone who "
        "qualified the season before is included, scored on actual season totals (0 if he then missed the season).")
    d.table([
        ["Preseason projection", "Error on season totals", "Ranking accuracy", "Draft sims (avg team FPTS)"],
        ["ESPN", f"{mt['espn_fpg|espn_gp']:.0f}", f"{sp['espn_fpg|espn_gp']:.3f}", f"{dm['espn_fpg|espn_gp']:,.0f} (won {et['draft_sim_wins']['espn_fpg|espn_gp']} of 4)"],
        ["BPV alone", f"{mt['bpv_fpg|bpv_gp']:.0f}", f"{sp['bpv_fpg|bpv_gp']:.3f}", f"{dm['bpv_fpg|bpv_gp']:,.0f} (won {et['draft_sim_wins']['bpv_fpg|bpv_gp']})"],
        ["<b>BPV + ESPN hybrid</b>", "496", f"<b>{sp['blend_fpg|espn_gp']:.3f}</b>", f"<b>{dm['blend_fpg|espn_gp']:,.0f} (won {et['draft_sim_wins']['blend_fpg|espn_gp']} of 4)</b>"],
    ], [2.2, 1.4, 1.4, 1.9])
    d.bullets([
        "Per game, BPV beats ESPN (4.36 vs 4.55 error; ESPN over-projects by about 1.6 FPTS/game), but a 62.5/37.5 blend beats both.",
        "ESPN's projected games carry preseason injury, suspension and holdout news that BPV can't see, so ESPN out-ranked plain BPV on "
        "season totals. But it projects too many games (median 66–72), which hurts its totals.",
        "The hybrid uses the per-game blend with ESPN's projected games scaled by 0.86: it ties BPV on total error, beats ESPN by 80, "
        "ranks best, and won 3 of 4 draft seasons.",
    ])
    d.box("Verdict:", "Plain BPV was <b>not</b> the best preseason ranking; ESPN was. BPV now uses the <b>BPV + ESPN hybrid</b> before each "
          "season (veterans with 20+ games and 15+ minutes). It isn't used in season, where ESPN switches to rest-of-season projections.", "amber")

    # ------------------------------------------------------------ 15 model comparison
    d.h1("15. Which preseason model is best?")
    d.p("Each model below predicts a season using only earlier seasons, for four seasons (2022-23 to 2025-26).")
    names = [("Last season total FPTS", "Last season's total FPTS (like a naive consensus)"),
             ("M1 season FPTS", "Model 1: season FPTS per game"),
             ("M3 x career GP%", "Model 3: × career GP% (first version of BPV)"),
             ("M5 80/20 x career GP%", "Model 5: 80/20 × career GP%"),
             ("BPV (replacement-level)", "Revised BPV: p × F + (1 − p) × q × R"),
             ("BPV + age", "<b>Revised BPV + age (Section 14)</b>")]
    d.table([["Model", "Rank correlation (avg)", "Draft sim: avg team FPTS", "Draft-sim wins"]] +
            [[label, f"{sp_avg[k]:.3f}", f"{draft_avg[k]:,.0f}" if k in draft_avg else "not simulated",
              f"{wins[k]} of 4" if k in wins else "—"] for k, label in names],
            [3.1, 1.3, 1.5, 1.0])
    d.p("BPV here uses the league-average q, as the site does, and each season's age curve was fitted only on earlier seasons. "
        "Roster crowding was added after these simulations; its accuracy gain was tested separately (Section 14).")
    d.image("draft_sims.png", 6.8, "Average team FPTS per model in 1,000 simulated drafts per season.")
    d.bullets([
        f"<b>Ranking:</b> BPV + age has the best average rank correlation. It beats BPV without age significantly in {age_sig} of 4 seasons "
        "(tied in the rest), but beats Model 5 significantly in only 1 of 4.",
        "<b>Drafts:</b> a BPV version (with or without age) came first in all four seasons, and the two versions split the wins. "
        "The age curve added nothing in drafts.",
        "<b>Limits:</b> four seasons is a small sample, and the simulations shuffle draft order but can't replay how players actually performed.",
        "A \"managed\" score that credited free-agent points for long absences was dropped from the evidence because it builds in BPV's own assumption.",
    ])
    d.box("Verdict:", "BPV + age is <b>at least as good</b> as every alternative and best on average, and a BPV version won every "
          "season of simulated drafts. Evidence that it is <b>better</b> is growing but not conclusive.", "amber")
    d.h2("The original preseason experiments")
    d.p("Before 2025-26, five sources were compared. <b>Experiment 1</b> (each drafts its ideal 13 alone): ESPN 43,565; BPV 43,113; "
        "professionals 41,851; my rankings 41,119; ADP 40,904. <b>Experiment 2</b> (all five in one draft, random order): BPV 39,096; "
        "my rankings 38,058; ESPN 37,420; ADP 32,752; professionals 27,891.")
    d.bullets([
        "Experiment 1 is essentially a tie (a 1% gap). Experiment 2 is a single draft, where draft position alone can swing results by thousands of points.",
        "Even a nearly perfect list doesn't guarantee the best team, because you don't know who will be left at your pick.",
        "If the preseason BPV came from the first version of the site, it was season FPTS × career GP% plus a hand-made list of 40 players set to 0, and its \"last 5 games\" came from the end of 2024-25.",
        "Summing 13 players' totals ignores that only 10 start each day and that leagues are decided by head-to-head playoffs.",
        "To redo the experiments properly: save each ranking (ESPN, ADP, experts, personal) as a CSV of names and run "
        "<b>python -m analysis.draft_sim --ranking ESPN=espn.csv ...</b>, which runs 1,000 simulated drafts.",
    ])

    # ------------------------------------------------------------ 16 every improvement
    d.h1("16. Every improvement we tested")
    d.p("The rule was set before testing: a change is added only if it beats current BPV on seasons it wasn't fitted on, with a "
        "95% interval (resampling whole players) that excludes zero. Display features are added only if they are correct and harmless.")
    d.table([
        ["Candidate", "Result vs current BPV (FPTS/game)", "Decision"],
        ["Age adjustment between seasons", "−0.21 (−0.31 to −0.12)", "<b>Added</b>"],
        ["Roster crowding between seasons", "−0.06 (−0.10 to −0.02)", "<b>Added</b>"],
        ["Age-adjusted early-season blend", "−0.05 (−0.08 to −0.02)", "<b>Added</b>"],
        ["Known long-term teammate absence (in season)", "−0.52 for affected players (−0.79 to −0.24)", "<b>Added</b> (manual injuries)"],
        ["Same, guessed from missed games", "+0.00 (−0.03 to +0.03)", "Not added"],
        ["Teammate out for one game", "−0.10 per game (−0.14 to −0.06)", "Not added: needs a live injury feed"],
        ["Cox injury model", "+0.004 alone; +0.0002 combined", "Not added"],
        ["Averaging with Basketball-Reference's projections", "−0.03 (−0.06 to +0.01)", "Not added (tie)"],
        ["Blending older seasons (two ways)", "+0.00 and +0.05", "Not added"],
        ["Exponential decay instead of last 5", "−0.01 (−0.05 to +0.02)", "Not added (tie)"],
        ["Last 3, 7, 10 or 15 games", "all within ±0.02", "Not added (tie)"],
        ["Separate recency per stat", "+0.03 (+0.00 to +0.05)", "Not added (worse)"],
        ["Separate age curve per stat", "identical, or +0.03 if proportional", "Not added"],
        ["Changed-team flag", "−0.02 (−0.04 to +0.00)", "Not added (tie)"],
        ["Positional replacement levels", "gaps under 0.3; drafts +1.4% (−3% to +4%)", "Not added"],
        ["80% likely range", "79.8% coverage in season; 72–82% between seasons", "<b>Added</b> (display)"],
        ["Fantasy-playoff game counts", "−0.8% error on playoff totals (−1.7% to −0.04%)", "<b>Added</b> (display)"],
        ["League and roster size settings", "sets the replacement level", "<b>Added</b>"],
        ["Serious injury on the report → long absence", "availability error 0.60 → 0.16", "<b>Added</b> (automatic)"],
        ["Teammate boost from serious-injury listings", "−0.25 for affected (−0.40 to −0.11)", "<b>Added</b> (automatic)"],
        ["Teammate boost from any Out listing", "−0.02 (−0.11 to +0.06)", "Not added (tie)"],
        ["Injury/rest history → next season availability", "−0.0004 (−0.0014 to +0.0005)", "Not added (tie)"],
        ["Status → chance of playing", "60,000 listings", "<b>Added</b> (display)"],
        ["In-season recalibration", "−0.07 pooled (−0.12 to −0.02); 3 of 5 seasons better, none worse", "<b>Added</b>"],
        ["In-season age drift", "−0.06 (−0.16 to +0.04)", "Not added (tie)"],
        ["Per-stat stabilization padding", f"{fol['F1']['padded_minus_current']['diff']:+.2f} ({fol['F1']['padded_minus_current']['ci95'][0]:+.2f} to {fol['F1']['padded_minus_current']['ci95'][1]:+.2f})", "Not added (tie)"],
        ["Lighter shrinkage for stars", "+0.00 (−0.01 to +0.01)", "Not added (tie)"],
        ["Late-season tanking/resting", f"{fol['F3']['status_minus_league_drop']['diff']:+.1f} FPTS per playoff total (all 5 seasons better)", "<b>Added</b> (expected playoff FPTS)"],
        ["Rookie draft age", "−0.02 (−0.07 to +0.04)", "Not added (tie)"],
        ["Usage-weighted teammate boost", "+0.08 (−0.00 to +0.17)", "Not added (tie)"],
        ["Contract-year effects", "not tested: no free contract data", "—"],
        ["BPV + ESPN hybrid (before the season)", "ranking +0.016 vs ESPN; totals −80 vs ESPN, tie vs BPV; drafts 3 of 4", "<b>Added</b>"],
        ["Preseason minutes, veterans", f"{round3['P1']['minus_current']['diff']:+.2f} ({round3['P1']['minus_current']['ci95'][0]:+.2f} to {round3['P1']['minus_current']['ci95'][1]:+.2f})", "Not added (tie)"],
        ["Preseason minutes, rookies", f"{round3['P1_rookies']['minus_current']['diff']:+.2f} ({round3['P1_rookies']['minus_current']['ci95'][0]:+.2f} to {round3['P1_rookies']['minus_current']['ci95'][1]:+.2f})", "<b>Added</b>"],
        ["Return timelines by injury type", "−0.02 absolute, −0.04 squared error", "<b>Added</b> (means)"],
        ["Team minutes scaled proportionally", f"{round3['P3']['scaled_minus_additive_crowding']['diff']:+.3f} (tie)", "Not added"],
        ["Weekly totals with the injury report", f"{round3['P4']['minus_current']['diff']:+.1f} per week ({round3['P4']['minus_current']['ci95'][0]:+.1f} to {round3['P4']['minus_current']['ci95'][1]:+.1f})", "<b>Added</b> (this week)"],
        ["One-IR-slot draft simulation", "current streaming credit drafted best", "Formula confirmed"],
        ["Coaching changes", "−0.005 (−0.016 to +0.009)", "Not added (tie)"],
        ["Weekly consistency", "weak trait; <1 point of H2H win odds", "Not added"],
        ["Weekly: team-aware report lookup + sat recently", "−2.2/week (−2.5 to −2.0), 5 of 5 seasons", "<b>Added</b>"],
        ["In-season shooting regression (own level)", "−0.064 (−0.096 to −0.036), 4 of 5; better for stars", "<b>Added</b>"],
        ["Shooting regression toward league average", "−0.048 but hurt elite players (4.12 → 4.65)", "Rejected"],
        ["Shooting regression between seasons; FT% regression", "ties", "Not added"],
        ["This week's opponents", "−0.04/week, 5 of 5 (negligible)", "<b>Added</b>"],
        ["Tracking: deflections, potential assists, rebound chances, contests", "stat-level gains; FPTS tie", "Not added"],
        ["Shot quality by defender distance", "nothing beyond plain eFG%", "Not added"],
        ["Stat-specific crowding; scorekeeper generosity; forecast disagreement", "ties / negligible", "Not added"],
        ["Post-injury ramp-up; participation policy; back-to-backs; schedule strength", "ties", "Not added"],
        ["Returning teammate; mid-season trades; second-year jump; pick development; second-half weighting; 65-game rule", "ties", "Not added"],
        ["Preseason projection (BPV + ESPN) as early-season prior", "−0.064 (−0.102 to −0.025), 3 of 4 seasons", "<b>Added</b>"],
        ["Rookie preseason minutes in-season; smooth age curve", "ties", "Not added"],
        ["Replacement level 100th/160th/190th/220th player", "all below 130th in standard draft sims", "Not changed"],
        ["In season: current absence streak", "−0.0034 (−0.0049 to −0.0023); 4 of 5, squared 5 of 5", "<b>Added</b>"],
        ["Next-season availability: 23 injury-proneness signs (age, minutes, playoff minutes, past injuries, body parts, size, usage, ...)", "all ties or worse, vs history and vs ESPN", "Not added"],
        ["In season: this season 2–5×, age, report status, non-injury Out, recent return", "ties or worse", "Not added"],
    ], [2.6, 2.6, 1.7])
    d.box("Holdout test (2014-15 to 2018-19, never used before):", "Today's formula, frozen, with pass criteria written first. "
          "8 of 9 checks passed: preseason ranking beat last season's totals (4 of 5 seasons); age + crowding helped in 5 of 5 "
          "(per-game error -0.19); in-season BPV beat the original 80/20 in 5 of 5 (3.64 vs 3.84 FPTS/game); recalibration 4 of 5, "
          "shooting regression 5 of 5, early prior 5 of 5, availability 5 of 5, absence streak 5 of 5; drafts beat naive 4 of 5 and "
          "the original 3 of 5. Failed: preseason ranking vs the original formula, better in only 3 of 5 (0.708 vs 0.697). "
          "The ESPN blend and injury-report features couldn't be tested on those years.", "green")
    d.box("Stopping point:", "The loop stopped when the last round added nothing and the remaining ideas couldn't be tested: xFG% and "
          "gravity exist only from 2025-26; referees, travel, altitude and play-type matchups are single-game effects; betting props and "
          "ESPN in-season projections have no free history; college, G League and contract data have no free source. About 105 ideas "
          "were tested on the same five seasons, so some small wins may be luck; 2026-27 is the real test.", "amber")
    d.p("Candidates came from our own ideas and two rounds of research into published systems (DARKO, EPM, FiveThirtyEight, "
        "Basketball-Reference, SCHOENE) and peer-reviewed work. Public out-of-sample evidence on season-long fantasy projections is scarce. "
        "Notable: BPV was slightly too extreme in season (players under 24 improve during a season by 1.9–2.7 FPTS/game); on bad teams, young "
        "regulars play 24 points less of their games in the fantasy playoffs and veterans 44 points less.")

    # ------------------------------------------------------------ 17 final constants
    d.h1("17. The final model: every setting and where it came from")
    d.table([
        ["Setting", "Value", "How it was chosen", "Confidence"],
        ["Scoring weights", "ESPN default", "ESPN's published scoring", "Fact"],
        ["Recent window", "Last 5 games played", "Beat the team-window version; 3, 7, 10, 15 games tied", "Strong (flat)"],
        ["Recent weight", "0.3 minutes / 0.1 per-minute (≈ 20% overall)", "Fitted on 2021-22 to 2024-25", "Range 10–20% supported"],
        ["Recent form in offseason", "Off", "Preseason tests: no benefit", "Moderate"],
        ["New role detection", "10+ games, ≤ 24 min, last-5 minutes +8", "Definition (not tuned)", "Judgment call"],
        ["New role haircut / weight", "0.90 / 60%", "Best fit on 546 cases", "Haircut anywhere 0.80–1.10"],
        ["Early-season prior", "8 games of last season", "Best of k = 0–30", "Strong"],
        ["Between-season production", "Last season + flat age adjustment (+2.1 at ≤21 to −3.7 at 33+)", "Leave-one-season-out, 6 approaches compared", "Strong"],
        ["Roster crowding", "−0.0177 FPTS/g per minute of competition", "Leave-one-season-out", "Strong (same in all 4 seasons)"],
        ["Injured-teammate boost", "+0.034 FPTS/g per lost minute (in season, known injuries)", "Fitted 2021-22 to 2024-25, tested 2025-26", "Strong for known injuries"],
        ["Early-season prior age", "Last season + age adjustment", "11,587 checkpoints", "Strong"],
        ["80% range", "In season −5.5 to −5.8 / +7.2 to +8.2 by games; between seasons −7.3 / +6.2", "Out-of-sample residuals", "Calibrated"],
        ["In-season recalibration", "2.96 + 0.91 × projection (10+ games)", "Leave-one-season-out", "Moderate (3 of 5 seasons)"],
        ["Early-season prior", "Saved preseason BPV + ESPN projection, 8 games' weight", "ESPN seasons 2021-22..2025-26", "Moderate (3 of 4 seasons)"],
        ["Absence streak (in season)", "+0.0075 − 0.0242 × team games missed in a row (max 20), 20+ mpg, not listed Out injured, 10+ games left", "10,139 checkpoints, leave-one-season-out", "Strong (4 of 5; squared 5 of 5)"],
        ["In-season shooting regression", "−1.85 × (eFG% − his last-season eFG%) × FGA/g", "All weekly checkpoints, leave-one-season-out", "Strong (4 of 5; stars improved)"],
        ["Weekly status lookup", "Latest report with his team's game + sat-in-last-3-days factor", "Leave-one-season-out", "Strong (5 of 5)"],
        ["Serious injury on report", "Teammates +0.029/min (own availability: see injury-type timelines)", "Fitted 2021-22 to 2024-25, tested 2025-26", "Strong"],
        ["Fantasy-playoff games played", "Share change by team status and age (bad veterans −44 points)", "Leave-one-season-out", "Strong (5 of 5 seasons)"],
        ["ESPN blend (before the season)", "37.5% of per-game; games = ESPN × 0.86", "Leave-one-season-out, 4 seasons", "Strong on ranking"],
        ["Injury-type timelines", "Share of remaining played: serious 24%, sprain 53%, strain 58%, soreness 54%, other 40%", "5 seasons of reports", "Strong"],
        ["This week's value", "Production × games × share × status factor (e.g. Out-serious 0.09, Questionable 0.94)", "Fitted 2021-22 to 2024-25, tested 2025-26", "Strong"],
        ["Rookie preseason minutes", "+0.31 FPTS/g per preseason minute above his draft range's typical", "Leave-one-season-out", "Moderate"],
        ["Rookie prior", "10 games of draft baseline", "Best of k = 0–30 (8 ties)", "Strong"],
        ["Availability history", "Each older season × 0.5", "Best of 5 options", "Flat: 0.5–0.7 equivalent"],
        ["Availability shrinkage", "123 games of league average", "Best of k = 0–246", "Flat: 123–164 equivalent"],
        ["Long absence", "5+ straight games", "Judgment (3 and 10 also tested)", "Choice"],
        ["q (IR-able share)", "League average ≈ 72%", "Measured", "Per-player values unreliable"],
        ["Replacement rank", "Teams × roster size (130 by default)", "League settings", "Depends on league size"],
        ["History used", "Last 5 seasons (availability); last season (production)", "Older seasons tested: no gain for production", "Moderate"],
        ["Heat Check Index", "BPV ÷ best BPV × 100", "Display measure", "—"],
    ], [1.6, 1.8, 1.9, 1.6])

    # ------------------------------------------------------------ 16 limitations & next
    d.h1("18. Limitations and what to try next")
    d.h2("Limitations")
    d.bullets([
        "Box scores can't tell injuries from rest, suspensions or coach's decisions, which limits every availability measure.",
        "Availability is mostly unpredictable (year-to-year correlation 0.24); BPV can only price it on average.",
        "BPV's typical error for one player's rest-of-season average is about 4 FPTS per game, so close comparisons are uncertain.",
        "Positions are ignored (tested: positional replacement levels differ by under 0.3 FPTS/game with guard/forward/center data).",
        "Injury reports exist only on game days and don't give return dates; long absences are inferred from the injury type.",
        "stats.nba.com blocks many cloud hosts, so the site runs locally (hosting would need a proxy or a pre-filled cache).",
    ])
    d.h2("What to try next")
    d.bullets([
        "<b>1. Score the BPV + ESPN hybrid against competitors in 2026-27.</b> About 105 ideas were tested on the same five seasons, "
        "so a fresh season is the real test. Run <b>python -m analysis.snapshot</b> before October 20 and save ESPN's and other "
        "rankings the same week; score them all after the season with analysis/draft_sim.py. A peer-reviewed study found professional "
        "fantasy projections beat naive ones only moderately, so expect small differences between good systems.",
        "<b>2. A full minutes model</b> (depth charts, as FiveThirtyEight built). Crowding is a first step; projecting each player's minutes "
        "directly could capture role changes without roster changes.",
        "<b>3. A fuller weekly view</b> adding the game-level teammate effect (tested at game level, not yet built).",
        "<b>4. Finer injury types</b> (e.g. hamstring vs calf) once more seasons of reports accumulate.",
        "<b>5. Contract-year effects</b>, if clean contract data can be found (published evidence is mixed).",
        "<b>6. Rest-of-season trade values</b> weighted by each team's remaining schedule.",
        "Everything else on the earlier list was tested (Section 16).",
    ])

    # ------------------------------------------------------------ appendices
    d.page()
    d.h1("Appendix A: What changed from the first version")
    d.table([
        ["First version", "Now", "Why"],
        ["BPV = FPTS × career GP%", "BPV = p × F + (1 − p) × q × R", "Missed games aren't worth zero"],
        ["Career GP%, assuming 82 games", "Weighted, shrunk, real schedules", "Career GP% wasn't better than the average; shortened seasons and trades were miscounted"],
        ["Reliability score undefined", "League-average q + manual injuries", "Per-player absence patterns can't be measured reliably"],
        ["Cox × FPTS", "Cox → availability (future)", "Hazard ratio above 1 means riskier"],
        ["Team's last 5 games", "Last 5 games played", "Tested slightly better"],
        ["20% (informal)", "Tested: 10–20% supported; minutes/per-minute split", "Measured, with intervals"],
        ["NRV 90%, 50/50, manual", "0.90, 60/40, automatic + manual", "Idea confirmed; haircut range 0.80–1.10"],
        ["Rookies = 0", "Draft-slot baselines", "Players without history were ignored"],
        ["40 players hard-coded to 0", "Manual overrides file", "The list was stale and name-matching failed"],
        ["One draft per experiment", "1,000 simulated drafts × 4 seasons, no peeking", "One trial can't separate skill from luck"],
        ["Last season, no age", "Last season + age adjustment between seasons", "4.7% less preseason error; beat Basketball-Reference's system"],
        ["Last season's team shown", "Next season's rosters + roster crowding", "Offseason moves were invisible; 1.4% less error"],
        ["Cox proposed", "Cox built and tested", "Didn't beat the current availability estimate"],
        ["No uncertainty shown", "80% likely range + fantasy-playoff games", "Calibrated; playoff counts matter for head-to-head"],
        ["Injuries entered by hand only", "Official injury report read automatically in season", "Serious injuries predict long absences with no hindsight"],
        ["No competitor comparison", "Compared with ESPN; BPV + ESPN hybrid before the season", "ESPN out-ranked plain BPV; the hybrid beat both"],
        ["Client-side math, two conflicting copies", "One server-side calculation", "Pages disagreed; the 80/20 blend never actually ran"],
        ["nba_api 1.7.0", "nba_api 1.11.4", "The NBA site had started rejecting the old version, so no data loaded"],
    ], [2.0, 2.3, 2.6])
    d.h1("Appendix B: Reproducing everything")
    d.bullets([
        "<b>python -m analysis.backtest</b>: all tuning results (analysis/results.json).",
        "<b>python -m analysis.robustness</b>: intervals, per-season results, no-peeking comparison, absence-pattern reliability (analysis/robustness.json).",
        "<b>python -m analysis.draft_sim</b>: simulated drafts, optionally with your own ranking CSVs.",
        "<b>python -m analysis.preseason_production</b>: the between-season comparison and age curve (analysis/preseason_production.json).",
        "<b>python -m analysis.decay_test</b>: exponential decay vs the last-5 rule.",
        "<b>python -m analysis.snapshot</b>: saves today's rankings to data/snapshots/ for scoring after the season.",
        "<b>python -m analysis.test_espn_projections</b>, <b>test_espn_totals</b>, <b>test_round3</b>, <b>test_coach_consistency</b>, "
        "<b>test_injury_reports</b>, <b>test_research_ideas</b>, <b>test_research_followup</b>, "
        "<b>test_cox</b>, <b>test_minutes_model</b>, <b>test_misc</b>, <b>test_teammates_perstat</b>, "
        "<b>test_schedule_positions_uncertainty</b>: the Section 16 tests.",
        "<b>python -m analysis.report_charts DIR</b> and <b>python -m analysis.report_pdf DIR</b>: this report.",
        "Shrinkage formula used throughout: estimate = (n × own + k × prior) ÷ (n + k), standard empirical-Bayes weighting.",
    ])
    d.h1("References")
    for ref in [
        "ESPN. \"ESPN Fantasy's default points-league scoring explained\" (2025); \"ESPN Fantasy Basketball 101: Adjusting the settings\"; ESPN Fan Support articles on IR eligibility and waiver order.",
        "Jha, A. (2025, September 28). \"Figuring out why NBA players get injured using Cox Proportional Hazards.\" Medium.",
        "Herzog, M. M., Brink, A., Gondalia, R., DiFiori, J. P., & Mack, C. D. (2026). The relationship between games missed for rest or load management and injury in the NBA, 2014–15 through 2022–23. Sports Medicine 56(9), 2313–2323.",
        "Menon, A. et al. (2024). Season-ending injuries in the NBA. Arthroscopy 40(9), 2468–2473.",
        "Medvedovsky, K. (2020, August 6). \"NBA stabilization rates and the padding approach.\" kmedved.com.",
        "Miller, J. & Sanjurjo, A. (2018). Surprised by the hot hand fallacy? A truth in the law of small numbers. Econometrica 86(6), 2019–2047.",
        "Bocskocsky, A., Ezekowitz, J. & Stein, C. (2014). The hot hand: a new approach to an old \"fallacy.\" MIT Sloan Sports Analytics Conference.",
        "Efron, B. & Morris, C. (1975). Data analysis using Stein's estimator and its generalizations. JASA 70(350), 311–319.",
        "Davidson-Pilon, C. lifelines documentation (CoxPHFitter; proportional hazards checks).",
        "Bryant, J. \"Principles of Value Based Drafting.\" Footballguys.",
        "Basketball-Reference. \"Simple Projection System.\" basketball-reference.com/about/projections.html.",
        "Döpke, J., Köhler, T. & Tegtmeier, L. (2024). Forecasting performance of NBA daily fantasy projections. Journal of Economics and Finance 48(1).",
        "Medvedovsky, K. DARKO documentation, darko.app/about; Dunks & Threes, EPM methodology, dunksandthrees.com/about/epm.",
        "nbainjuries (Python package, v1.1.1); lifelines (v0.30.3); NBA official injury reports (ak-static.cms.nba.com/referee/injury).",
        "Pelton, K. SCHOENE projection system (ESPN); Basketball-Reference, SCHOENE vs SPS comparison (2009).",
        "ESPN Fantasy public API (lm-api-reads.fantasy.espn.com), preseason player projections 2021-22 to 2026-27.",
        "swar/nba_api (v1.11.4) and stats.nba.com.",
    ]:
        d.story.append(Paragraph(ref, S["bullet"], bulletText="•"))

    doc = SimpleDocTemplate(OUT, pagesize=letter, leftMargin=0.8 * inch, rightMargin=0.8 * inch,
                            topMargin=0.75 * inch, bottomMargin=0.8 * inch,
                            title="BPV: Measuring Fantasy Basketball Value", author="Fantasy Basketball Watchlist")
    doc.build(d.story, onFirstPage=footer, onLaterPages=footer)
    print(OUT)


if __name__ == "__main__":
    build(sys.argv[1])
