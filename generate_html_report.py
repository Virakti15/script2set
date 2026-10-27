#!/usr/bin/env python3
"""Generate a presentable, dark-themed HTML dashboard report for a Meta Ads audit.

Turns audit data into a single self-contained .html file (no external network
calls, no CDN) styled like a modern paid-social report: a daily-spend bar chart,
a "spend share by campaign" panel, a narrative, and a creative leaderboard with
scale / fatiguing / cut-fix status pills.

Usage:
    # From a JSON data file (see schema below):
    python3 generate_html_report.py --data report-data.json --output META-REPORT.html

    # Render the built-in demo (matches the reference design) to preview the look:
    python3 generate_html_report.py --demo --output demo-report.html

Input JSON schema (all fields optional; sensible fallbacks applied):
{
  "title": "Meta Ads — Account Report",
  "period": "Last 30 days",
  "currency": "£",
  "health_score": 74,
  "grade": "C",
  "daily_spend":  [ {"day": 1, "spend": 420, "roas": 3.1}, ... ],
  "spend_share":  [ {"campaign": "ugc — blush hero (advantage+)",
                     "spend": 19300, "roas": 3.7, "status": "scale"}, ... ],
  "narrative": "One or two sentences of analysis...",
  "creatives":    [ {"name": "rio-blush-asmr-application",
                     "type": "ugc video 9:16", "status": "fatiguing",
                     "metrics": {"roas": "4.1×", "spend": "£11,200",
                                 "ctr": "2.3%", "cpa": "£6.40",
                                 "freq": "4.2", "hook rate": "31%"},
                     "flag": ["freq"]}, ... ]
}

status values: "scale" (green), "fatiguing" (amber), "cut" / "cut/fix" (red).
The `flag` list names metric keys to highlight in amber on a creative card.

Exit codes: 0 success, 1 bad input.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from html import escape

__version__ = "1.0.0"

# ── Design tokens (mirrors the reference dashboard) ──────────────────────────
BG        = "#0b0b0d"
PANEL     = "#141417"
PANEL_2   = "#1a1a1f"
INK       = "#ece9e2"
MUTED     = "#8a8880"
PINK      = "#f77fb0"   # daily spend bars
GREEN     = "#38d39a"   # scale / healthy
AMBER     = "#e8a83a"   # fatiguing / warning
RED       = "#f2547d"   # cut / fix
TRACK     = "#2a2a30"   # empty bar track

STATUS = {
    "scale":     ("scale",     GREEN, "#12281f"),
    "fatiguing": ("fatiguing", AMBER, "#2a2410"),
    "cut":       ("cut / fix", RED,   "#2a1218"),
    "cut/fix":   ("cut / fix", RED,   "#2a1218"),
}


def _status(key: str):
    return STATUS.get((key or "").lower().strip(), ("scale", GREEN, "#12281f"))


def _demo() -> dict:
    return {
        "title": "Meta Ads — Account Report",
        "period": "Last 30 days",
        "currency": "£",
        "health_score": 74,
        "grade": "C",
        "daily_spend": [
            {"day": d, "spend": s, "roas": r}
            for d, s, r in zip(
                range(1, 31),
                [420, 440, 410, 455, 470, 460, 480, 500, 495, 510, 505, 520,
                 540, 535, 560, 555, 575, 590, 600, 610, 625, 640, 650, 665,
                 680, 690, 705, 720, 735, 750],
                [3.1, 3.2, 3.0, 3.3, 3.1, 3.2, 3.0, 3.1, 2.9, 3.0, 2.8, 2.9,
                 2.7, 2.8, 2.6, 2.7, 2.5, 2.6, 2.4, 2.5, 2.3, 2.4, 2.2, 2.3,
                 2.1, 2.2, 2.0, 2.1, 1.9, 2.0],
            )
        ],
        "narrative": (
            "The pattern's clear: spend is up 18% but ROAS is sliding as I scale "
            "into weaker creative. Now the creative leaderboard — this is where "
            "the decisions live."
        ),
        "spend_share": [
            {"campaign": "ugc — blush hero (advantage+)", "spend": 19300, "roas": 3.7, "status": "scale"},
            {"campaign": "shade range — prospecting",      "spend": 14100, "roas": 2.4, "status": "fatiguing"},
            {"campaign": "retargeting — site visitors",     "spend": 8640,  "roas": 4.9, "status": "scale"},
            {"campaign": "feature/benefit — static push",   "spend": 6200,  "roas": 1.3, "status": "cut"},
        ],
        "creatives": [
            {"name": "rio-blush-asmr-application", "type": "ugc video 9:16", "status": "fatiguing",
             "metrics": {"roas": "4.1×", "spend": "£11,200", "ctr": "2.3%", "cpa": "£6.40",
                         "freq": "4.2", "hook rate": "31%"}, "flag": ["freq"]},
            {"name": "retargeting — site visitors", "type": "mixed", "status": "scale",
             "metrics": {"roas": "4.9×", "spend": "£8,640", "ctr": "2.0%", "cpa": "£5.10",
                         "freq": "3.1"}, "flag": []},
            {"name": "rio-blush-grwm-desk", "type": "ugc video 9:16", "status": "scale",
             "metrics": {"roas": "3.9×", "spend": "£7,400", "ctr": "2.6%", "cpa": "£6.90",
                         "freq": "2.4", "hook rate": "38%"}, "flag": []},
            {"name": "feature/benefit — static push", "type": "static 4:5", "status": "cut",
             "metrics": {"roas": "1.3×", "spend": "£6,200", "ctr": "0.8%", "cpa": "£18.40",
                         "freq": "5.6", "hook rate": "—"}, "flag": ["roas", "cpa", "freq"]},
        ],
    }


def _daily_chart(daily, currency: str) -> str:
    """Inline SVG bar chart (pink bars) with a ROAS y-axis on the right."""
    if not daily:
        return ""
    W, H = 820, 210
    pad_l, pad_r, pad_t, pad_b = 44, 40, 12, 26
    plot_w, plot_h = W - pad_l - pad_r, H - pad_t - pad_b
    max_spend = max(d.get("spend", 0) for d in daily) or 1
    n = len(daily)
    gap = 3
    bw = (plot_w - gap * (n - 1)) / n
    bars = []
    for i, d in enumerate(daily):
        x = pad_l + i * (bw + gap)
        bh = (d.get("spend", 0) / max_spend) * plot_h
        y = pad_t + (plot_h - bh)
        bars.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="1.5" fill="{PINK}"/>')
    # left axis labels (spend)
    yl = []
    for frac, lab in [(1.0, f"{currency}{max_spend/1000:.1f}k".replace('.0k','k')),
                      (0.5, f"{currency}{max_spend/2000:.1f}k".replace('.0k','k')),
                      (0.0, f"{currency}0")]:
        y = pad_t + (1 - frac) * plot_h
        yl.append(f'<text x="6" y="{y+4:.1f}" fill="{MUTED}" font-size="11">{escape(lab)}</text>')
    # right axis labels (roas)
    max_roas = max((d.get("roas", 0) for d in daily), default=1) or 1
    yr = []
    for frac in (1.0, 0.66, 0.33, 0.0):
        y = pad_t + (1 - frac) * plot_h
        yr.append(f'<text x="{W-34}" y="{y+4:.1f}" fill="{MUTED}" font-size="11">{max_roas*frac:.1f}×</text>')
    # x labels every 4th day
    xl = []
    for i, d in enumerate(daily):
        if i % 4 == 0:
            x = pad_l + i * (bw + gap) + bw / 2
            xl.append(f'<text x="{x:.1f}" y="{H-8}" fill="{MUTED}" font-size="11" text-anchor="middle">day {d.get("day", i+1)}</text>')
    return (f'<svg viewBox="0 0 {W} {H}" width="100%" role="img" aria-label="Daily spend">'
            + "".join(yl) + "".join(yr) + "".join(bars) + "".join(xl) + "</svg>")


def _share_rows(share, currency: str) -> str:
    if not share:
        return ""
    max_spend = max(s.get("spend", 0) for s in share) or 1
    rows = []
    for s in share:
        label, color, _ = _status(s.get("status", "scale"))
        pct = (s.get("spend", 0) / max_spend) * 100
        spend = f'{currency}{s.get("spend", 0):,.0f}'
        roas = s.get("roas")
        roas_txt = f' · roas {roas:.1f}×' if roas is not None else ""
        rows.append(f'''
        <div class="share-row">
          <div class="share-top">
            <span class="share-name">{escape(str(s.get("campaign","")))}</span>
            <span class="share-val">{escape(spend)}{escape(roas_txt)}</span>
          </div>
          <div class="track"><div class="fill" style="width:{pct:.1f}%;background:{color}"></div></div>
        </div>''')
    return "".join(rows)


def _creative_cards(creatives) -> str:
    cards = []
    for c in creatives:
        label, color, pill_bg = _status(c.get("status", "scale"))
        flags = set(c.get("flag", []))
        metrics = c.get("metrics", {})
        mhtml = []
        for k, v in metrics.items():
            hl = ' style="color:%s;font-weight:600"' % AMBER if k in flags else ""
            mhtml.append(f'<span class="m"><span class="mk">{escape(str(k))}</span> <span class="mv"{hl}>{escape(str(v))}</span></span>')
        cards.append(f'''
      <div class="card" style="border-left-color:{color}">
        <div class="card-top">
          <div><span class="card-name">{escape(str(c.get("name","")))}</span>
               <span class="card-type"> · {escape(str(c.get("type","")))}</span></div>
          <span class="pill" style="color:{color};background:{pill_bg}">{escape(label)}</span>
        </div>
        <div class="metrics">{"".join(mhtml)}</div>
      </div>''')
    return "".join(cards)


def render(data: dict) -> str:
    currency = data.get("currency", "£")
    title = escape(data.get("title", "Meta Ads — Account Report"))
    period = escape(data.get("period", ""))
    score = data.get("health_score")
    grade = escape(str(data.get("grade", "")))
    score_badge = ""
    if score is not None:
        gcolor = GREEN if score >= 75 else (AMBER if score >= 60 else RED)
        score_badge = (f'<div class="score" style="border-color:{gcolor}">'
                       f'<span class="score-n" style="color:{gcolor}">{int(score)}</span>'
                       f'<span class="score-l">/100 · {grade}</span></div>')
    filters = "".join(
        f'<span class="filt" style="color:{col};border-color:{col}44">{escape(lab)}</span>'
        for lab, col in (("↗ scale", GREEN), ("◐ fatiguing", AMBER), ("↘ cut / fix", RED))
    )
    narrative = escape(data.get("narrative", ""))
    generated = datetime.now().strftime("%B %d, %Y")

    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root{{color-scheme:dark}}
  *{{box-sizing:border-box}}
  body{{margin:0;background:{BG};color:{INK};
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif;
    -webkit-font-smoothing:antialiased;line-height:1.5}}
  .wrap{{max-width:920px;margin:0 auto;padding:32px 24px 64px}}
  .head{{display:flex;justify-content:space-between;align-items:flex-start;gap:16px;margin-bottom:24px}}
  h1{{font-size:22px;margin:0 0 4px;font-weight:650;letter-spacing:-.01em}}
  .sub{{color:{MUTED};font-size:13px}}
  .score{{border:1.5px solid;border-radius:12px;padding:8px 14px;text-align:center;white-space:nowrap}}
  .score-n{{font-size:26px;font-weight:700}}
  .score-l{{color:{MUTED};font-size:12px;display:block}}
  .panel{{background:{PANEL};border:1px solid #ffffff10;border-radius:14px;padding:20px;margin:16px 0}}
  .label{{color:{MUTED};font-size:13px;margin-bottom:12px}}
  .share-row{{margin:14px 0}}
  .share-top{{display:flex;justify-content:space-between;font-size:14px;margin-bottom:6px}}
  .share-name{{color:{INK}}}
  .share-val{{color:{MUTED}}}
  .track{{height:8px;background:{TRACK};border-radius:6px;overflow:hidden}}
  .fill{{height:100%;border-radius:6px}}
  .narrative{{font-family:Georgia,"Times New Roman",serif;font-size:19px;line-height:1.5;
    color:{INK};margin:28px 4px}}
  .filters{{display:flex;gap:10px;margin:18px 0 10px}}
  .filt{{border:1px solid;border-radius:8px;padding:5px 12px;font-size:13px}}
  .card{{background:{PANEL_2};border:1px solid #ffffff10;border-left:3px solid;border-radius:12px;
    padding:16px 18px;margin:12px 0}}
  .card-top{{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:10px}}
  .card-name{{font-weight:600;font-size:15px}}
  .card-type{{color:{MUTED};font-size:13px}}
  .pill{{border-radius:7px;padding:3px 10px;font-size:12px;font-weight:600;white-space:nowrap}}
  .metrics{{display:flex;flex-wrap:wrap;gap:18px}}
  .m{{font-size:14px}} .mk{{color:{MUTED}}} .mv{{color:{INK};font-weight:600}}
  .foot{{color:{MUTED};font-size:12px;text-align:center;margin-top:40px;
    border-top:1px solid #ffffff10;padding-top:16px}}
</style></head>
<body><div class="wrap">
  <div class="head">
    <div><h1>{title}</h1><div class="sub">{period}</div></div>
    {score_badge}
  </div>

  <div class="panel">
    <div class="label">daily spend</div>
    {_daily_chart(data.get("daily_spend", []), currency)}
  </div>

  <div class="panel">
    <div class="label">spend share by campaign</div>
    {_share_rows(data.get("spend_share", []), currency)}
  </div>

  <p class="narrative">{narrative}</p>

  <div class="filters">{filters}</div>
  {_creative_cards(data.get("creatives", []))}

  <div class="foot">Generated {generated} · Meta Ads report by Bizwit AI · https://bizwit.ai</div>
</div></body></html>'''


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate a presentable HTML Meta Ads report.")
    ap.add_argument("--data", help="Path to report-data.json")
    ap.add_argument("--output", "-o", default="META-REPORT.html", help="Output .html path")
    ap.add_argument("--demo", action="store_true", help="Render the built-in demo dataset")
    ap.add_argument("--version", action="version", version=f"generate_html_report {__version__}")
    args = ap.parse_args()

    if args.demo or not args.data:
        data = _demo()
        if not args.demo and not args.data:
            print("No --data provided; rendering the built-in demo. Use --data report-data.json for real data.",
                  file=sys.stderr)
    else:
        try:
            data = json.loads(open(args.data, encoding="utf-8").read())
        except (OSError, json.JSONDecodeError) as e:
            print(f"Error reading --data: {e}", file=sys.stderr)
            return 1

    html = render(data)
    try:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(html)
    except OSError as e:
        print(f"Error writing output: {e}", file=sys.stderr)
        return 1
    print(f"✓ Wrote presentable report: {args.output}  ({len(html):,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
