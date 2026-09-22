#!/usr/bin/env python3
"""
Account X-Ray
Obludzyner & Co. | Post-sales advisory for B2B SaaS | https://obludzyner.com

Turns a findings JSON (produced by an LLM reading structured account data
plus unstructured sources: call transcripts, CSM notes, emails) into a
self-contained HTML radiography report and a text summary.

This script does NOT read transcripts or classify findings itself -- that
is a judgment call an LLM makes, following the method in rubric.md, not a
deterministic calculation. What this script does is take the findings once
extracted, apply consistent formatting and severity rollups, and render a
report -- the same division of labor as the other tools in this series.

Zero dependencies. Python 3.8+. Pure stdlib, including the HTML output --
no templating library, no charting library needed.

Usage:
    python3 radiography.py examples/sample_findings.json examples/sample_radiography.html
    python3 radiography.py examples/sample_findings.json --text
"""

import argparse
import html
import json
import sys

CLASSIFICATION_LABEL = {"fact": "FACT", "hypothesis": "HYPOTHESIS", "unknown": "UNKNOWN"}
CLASSIFICATION_COLOR = {"fact": "#0ca30c", "hypothesis": "#fab219", "unknown": "#898781"}
SEVERITY_COLOR = {"risk": "#d03b3b", "watch": "#fab219", "opportunity": "#2a78d6", "neutral": "#898781"}

INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#898781"
SURFACE = "#fcfcfb"
GRIDLINE = "#e1e0d9"


def summarize(data):
    findings = data["findings"]
    by_classification = {"fact": 0, "hypothesis": 0, "unknown": 0}
    by_severity = {"risk": 0, "watch": 0, "opportunity": 0, "neutral": 0}
    for f in findings:
        by_classification[f["classification"]] = by_classification.get(f["classification"], 0) + 1
        by_severity[f.get("severity", "neutral")] = by_severity.get(f.get("severity", "neutral"), 0) + 1

    risk_count = by_severity.get("risk", 0)
    opp_count = by_severity.get("opportunity", 0)
    if risk_count >= 3:
        overall = "Critical"
    elif risk_count >= 1:
        overall = "Watch"
    elif opp_count >= 1:
        overall = "Healthy, with upside"
    else:
        overall = "Healthy"

    conflicts = data.get("conflicts", [])
    if conflicts and overall.startswith("Healthy"):
        overall = "Watch"

    return {
        "by_classification": by_classification,
        "by_severity": by_severity,
        "overall": overall,
        "total_findings": len(findings),
        "unknowns": [f for f in findings if f["classification"] == "unknown"],
        "conflicts": conflicts,
    }


def render_text(data, summary):
    a = data["account"]
    lines = []
    lines.append("=" * 64)
    lines.append(f"ACCOUNT X-RAY: {a['name']}")
    lines.append("=" * 64)
    lines.append(f"ARR ${a['arr']:,}  |  Segment: {a['segment']}  |  CSM: {a['csm']}  |  Health: {a['health_score']}/100")
    lines.append(f"Renews in {a['days_to_renewal']} days")
    lines.append("")
    lines.append(f"OVERALL: {summary['overall']}")
    conflict_note = f", {len(summary['conflicts'])} conflict(s)" if summary["conflicts"] else ""
    lines.append(
        f"  {summary['total_findings']} findings -- "
        f"{summary['by_classification']['fact']} fact, "
        f"{summary['by_classification']['hypothesis']} hypothesis, "
        f"{summary['by_classification']['unknown']} unknown{conflict_note}"
    )
    lines.append("")
    for category in sorted(set(f["category"] for f in data["findings"])):
        lines.append(f"-- {category} " + "-" * max(1, 50 - len(category)))
        for f in data["findings"]:
            if f["category"] != category:
                continue
            tag = CLASSIFICATION_LABEL[f["classification"]]
            lines.append(f"  [{tag}] {f['claim']}")
            lines.append(f"      Source: {f['source']}")
        lines.append("")
    if summary["conflicts"]:
        lines.append("CONFLICTING INFORMATION (shown, not silently resolved)")
        for c in summary["conflicts"]:
            lines.append(f"  - {c['topic']}")
            lines.append(f"      A: {c['claim_a']}  [{c['source_a']}]")
            lines.append(f"      B: {c['claim_b']}  [{c['source_b']}]")
            lines.append(f"      Question to validate: {c['question_to_validate']}")
        lines.append("")
    if summary["unknowns"]:
        lines.append("OPEN QUESTIONS (unknowns, stated openly rather than guessed)")
        for f in summary["unknowns"]:
            lines.append(f"  - {f['claim']}")
        lines.append("")
    lines.append("=" * 64)
    lines.append("This is the open-source, directional version of the account x-ray")
    lines.append("used inside a SHIFT Method engagement.")
    lines.append("For a Revenue Audit built on your real accounts and data:")
    lines.append("  https://obludzyner.com")
    lines.append("=" * 64)
    return "\n".join(lines)


def esc(s):
    return html.escape(str(s), quote=True)


def render_html(data, summary, out_path):
    a = data["account"]
    categories = sorted(set(f["category"] for f in data["findings"]))

    def finding_row(f):
        color = CLASSIFICATION_COLOR[f["classification"]]
        sev = f.get("severity", "neutral")
        sev_color = SEVERITY_COLOR.get(sev, SEVERITY_COLOR["neutral"])
        return f'''
        <div class="finding">
          <div class="finding-bar" style="background:{sev_color}"></div>
          <div class="finding-body">
            <span class="tag" style="color:{color};border-color:{color}">{CLASSIFICATION_LABEL[f["classification"]]}</span>
            <p class="claim">{esc(f["claim"])}</p>
            <p class="source">Source: {esc(f["source"])}</p>
          </div>
        </div>'''

    category_blocks = []
    for cat in categories:
        rows = "".join(finding_row(f) for f in data["findings"] if f["category"] == cat)
        category_blocks.append(f'<h2>{esc(cat)}</h2>{rows}')

    conflicts_block = ""
    if summary["conflicts"]:
        rows = "".join(f'''
        <div class="conflict">
          <p class="conflict-topic">{esc(c["topic"])}</p>
          <p class="conflict-side"><span class="conflict-tag">A</span>{esc(c["claim_a"])} <span class="source">({esc(c["source_a"])})</span></p>
          <p class="conflict-side"><span class="conflict-tag">B</span>{esc(c["claim_b"])} <span class="source">({esc(c["source_b"])})</span></p>
          <p class="conflict-question">To validate: {esc(c["question_to_validate"])}</p>
        </div>''' for c in summary["conflicts"])
        conflicts_block = f'''
        <h2>Conflicting information</h2>
        <p class="muted">Two sources disagree. Shown as a conflict to resolve, never silently picked one way.</p>
        {rows}'''

    unknowns_block = ""
    if summary["unknowns"]:
        items = "".join(f"<li>{esc(f['claim'])}</li>" for f in summary["unknowns"])
        unknowns_block = f'''
        <h2>Open questions</h2>
        <p class="muted">Stated openly rather than guessed. Answering these is usually the fastest way to move this account forward.</p>
        <ul class="unknowns">{items}</ul>'''

    stat_html = "".join(
        f'<div class="stat"><div class="stat-value" style="color:{CLASSIFICATION_COLOR[k]}">{v}</div>'
        f'<div class="stat-label">{CLASSIFICATION_LABEL[k]}</div></div>'
        for k, v in summary["by_classification"].items()
    )
    if summary["conflicts"]:
        stat_html += (
            f'<div class="stat"><div class="stat-value" style="color:#eb6834">{len(summary["conflicts"])}</div>'
            f'<div class="stat-label">CONFLICT</div></div>'
        )

    html_doc = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Account X-Ray: {esc(a["name"])}</title>
<style>
  body {{ background:{SURFACE}; color:{INK}; font-family: -apple-system, "Segoe UI", sans-serif;
         max-width: 760px; margin: 0 auto; padding: 40px 24px; }}
  .eyebrow {{ color:{INK_MUTED}; font-weight:700; font-size:13px; letter-spacing:0.03em; }}
  h1 {{ font-size: 30px; margin: 6px 0 2px 0; }}
  .meta {{ color:{INK_SECONDARY}; font-size:15px; margin-bottom: 18px; }}
  .overall-card {{ background:#f4f3ef; border-radius:16px; padding:20px 24px; margin: 18px 0 28px 0;
                    display:flex; align-items:center; justify-content:space-between; flex-wrap:wrap; gap:16px; }}
  .overall-label {{ color:{INK_MUTED}; font-weight:700; font-size:12px; }}
  .overall-value {{ font-size:26px; font-weight:700; }}
  .stats {{ display:flex; gap:22px; }}
  .stat {{ text-align:center; }}
  .stat-value {{ font-size:22px; font-weight:700; }}
  .stat-label {{ color:{INK_MUTED}; font-size:11px; font-weight:700; }}
  h2 {{ font-size:18px; border-top:1px solid {GRIDLINE}; padding-top:18px; margin-top:28px; }}
  .finding {{ display:flex; gap:12px; margin: 10px 0; }}
  .finding-bar {{ width:4px; border-radius:2px; flex-shrink:0; }}
  .finding-body {{ background:#f9f9f7; border-radius:10px; padding:12px 16px; flex:1; }}
  .tag {{ display:inline-block; font-size:10px; font-weight:700; border:1px solid; border-radius:10px;
          padding:2px 8px; margin-bottom:6px; }}
  .claim {{ margin: 4px 0; font-size:15px; }}
  .source {{ margin:0; color:{INK_MUTED}; font-size:12.5px; }}
  .muted {{ color:{INK_SECONDARY}; font-size:14px; }}
  ul.unknowns {{ padding-left: 20px; }}
  ul.unknowns li {{ margin: 6px 0; }}
  .legend {{ display:flex; gap:18px; flex-wrap:wrap; margin: 4px 0 22px 0; }}
  .legend-item {{ display:flex; align-items:center; gap:6px; font-size:12px; color:{INK_SECONDARY}; }}
  .legend-swatch {{ width:10px; height:10px; border-radius:3px; flex-shrink:0; }}
  .conflict {{ background:#fdf1e9; border-left:4px solid #eb6834; border-radius:8px; padding:12px 16px; margin:10px 0; }}
  .conflict-topic {{ font-weight:700; margin:0 0 6px 0; }}
  .conflict-side {{ margin:4px 0; font-size:14.5px; }}
  .conflict-tag {{ display:inline-block; font-weight:700; font-size:11px; background:#eb6834; color:#ffffff;
                    border-radius:4px; padding:1px 6px; margin-right:6px; }}
  .conflict-question {{ margin:8px 0 0 0; font-size:13.5px; color:{INK_SECONDARY}; font-style:italic; }}
  footer {{ margin-top: 40px; padding-top: 16px; border-top:1px solid {GRIDLINE};
            color:{INK_MUTED}; font-size:12.5px; }}
  footer a {{ color:{INK_SECONDARY}; }}
</style>
</head>
<body>
  <div class="eyebrow">OBLUDZYNER &amp; CO. - OPEN-SOURCE ACCOUNT X-RAY</div>
  <h1>{esc(a["name"])}</h1>
  <div class="meta">ARR ${a["arr"]:,} | {esc(a["segment"])} | CSM: {esc(a["csm"])} | Health {a["health_score"]}/100 | Renews in {a["days_to_renewal"]} days</div>

  <div class="overall-card">
    <div>
      <div class="overall-label">OVERALL</div>
      <div class="overall-value">{esc(summary["overall"])}</div>
    </div>
    <div class="stats">{stat_html}</div>
  </div>

  <div class="legend">
    <span class="legend-item"><span class="legend-swatch" style="background:{SEVERITY_COLOR['risk']}"></span>Risk</span>
    <span class="legend-item"><span class="legend-swatch" style="background:{SEVERITY_COLOR['watch']}"></span>Watch</span>
    <span class="legend-item"><span class="legend-swatch" style="background:{SEVERITY_COLOR['opportunity']}"></span>Opportunity</span>
    <span class="legend-item"><span class="legend-swatch" style="background:{SEVERITY_COLOR['neutral']}"></span>Neutral (the left bar on each finding)</span>
  </div>

  {"".join(category_blocks)}
  {conflicts_block}
  {unknowns_block}

  <footer>
    This is the open-source, directional version of the account x-ray used inside a SHIFT Method engagement.
    For a Revenue Audit built on your real accounts and data: <a href="https://obludzyner.com">obludzyner.com</a>
  </footer>
</body>
</html>'''

    with open(out_path, "w") as f:
        f.write(html_doc)


def main():
    parser = argparse.ArgumentParser(description="Account X-Ray renderer (open-source)")
    parser.add_argument("findings_json", help="path to a findings JSON file")
    parser.add_argument("out_path", nargs="?", help="path to write the HTML report to")
    parser.add_argument("--text", action="store_true", help="print the text report instead of writing HTML")
    args = parser.parse_args()

    with open(args.findings_json) as f:
        data = json.load(f)

    summary = summarize(data)

    if args.text or not args.out_path:
        print(render_text(data, summary))
        return

    render_html(data, summary, args.out_path)
    print(f"Wrote {args.out_path}")


if __name__ == "__main__":
    main()
