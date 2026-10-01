"""HTML deal report: ranked listings, red-flag badges, score chart."""
from __future__ import annotations

import base64
import html
import io
from datetime import datetime, timezone
from pathlib import Path


def _score_chart(results: list[dict]) -> str | None:
    """Horizontal bar chart of the top deals as a base64 PNG (or None)."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return None

    top = results[:10]
    if not top:
        return None
    labels = [(r["listing"]["title"][:38] + "…") if len(r["listing"]["title"]) > 39
              else r["listing"]["title"] for r in top]
    scores = [r["score"] for r in top]
    colors = ["#22c55e" if s >= 80 else "#eab308" if s >= 65 else "#f97316" if s >= 50 else "#64748b"
              for s in scores]

    fig, ax = plt.subplots(figsize=(8, max(2.5, 0.55 * len(top))))
    bars = ax.barh(labels[::-1], scores[::-1], color=colors[::-1], edgecolor="#1e293b")
    ax.bar_label(bars, fmt="%.0f", padding=4, fontsize=9, color="#e2e8f0")
    ax.set_xlim(0, 105)
    ax.set_xlabel("Deal score", color="#94a3b8")
    ax.set_title("Top deals by score", color="#f1f5f9", fontsize=13, pad=12)
    ax.tick_params(colors="#94a3b8", labelsize=9)
    for spine in ax.spines.values():
        spine.set_visible(False)
    ax.set_facecolor("#0f172a")
    fig.patch.set_facecolor("#0f172a")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _flag_badge(flag: dict) -> str:
    color = {"high": "#ef4444", "medium": "#f59e0b", "low": "#94a3b8"}[flag.get("severity", "low")]
    label = html.escape(flag["code"].replace("_", " ").title())
    detail = html.escape(flag["detail"])
    return (f'<span class="flag" style="border-color:{color};color:{color}" '
            f'title="{detail}">{label}</span>')


def generate_report(profile: dict, scored: list[dict], alerts: list[dict],
                    output_path: str | Path) -> Path:
    """Write a self-contained HTML report ranking the best deals."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    matched = [r for r in scored if r["is_match"]]
    skipped = len(scored) - len(matched)
    generated = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    chart = _score_chart(matched)

    verdict_color = {"HOT DEAL": "#22c55e", "Good deal": "#eab308",
                     "Fair": "#f97316", "Skip": "#64748b"}

    rows = []
    for rank_no, r in enumerate(matched, start=1):
        listing = r["listing"]
        flags = " ".join(_flag_badge(f) for f in r["red_flags"]) or '<span class="clean">clean</span>'
        color = verdict_color.get(r["verdict"], "#94a3b8")
        rows.append(f"""
        <tr>
          <td class="rank">#{rank_no}</td>
          <td>
            <div class="title">{html.escape(listing['title'])}</div>
            <div class="sub">{html.escape(listing.get('city', ''))} · {listing.get('distance_km', 0):.0f} km away · {html.escape(listing.get('seller_type', ''))}</div>
            <div class="flags">{flags}</div>
          </td>
          <td class="num">${listing['price']:,.0f}</td>
          <td class="num">${r['market_value']:,.0f}</td>
          <td class="num">{listing.get('mileage_km', 0):,} km</td>
          <td class="num">{listing.get('year', '')}</td>
          <td><span class="verdict" style="background:{color}22;color:{color};border:1px solid {color}">{r['verdict']}</span></td>
          <td>
            <div class="bar"><div class="fill" style="width:{r['score']}%;background:{color}"></div></div>
            <div class="score">{r['score']:.0f}</div>
          </td>
        </tr>""")

    alert_items = "".join(
        f"<li><strong>{html.escape(a['rule'].replace('_', ' ').title())}:</strong> "
        f"{html.escape(a['message'])}</li>" for a in alerts
    ) or "<li>No alerts fired.</li>"

    chart_html = (f'<img class="chart" src="data:image/png;base64,{chart}" alt="Top deals chart">' if chart
                  else "")

    profile_name = html.escape(profile.get("name", profile.get("slug", "report")))
    description = html.escape(profile.get("description", ""))

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AutoHunt report — {profile_name}</title>
<style>
  body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; background:#0f172a; color:#e2e8f0; margin:0; }}
  .wrap {{ max-width: 1080px; margin: 0 auto; padding: 32px 20px 64px; }}
  header {{ border-bottom: 1px solid #1e293b; padding-bottom: 20px; margin-bottom: 24px; }}
  h1 {{ margin: 0 0 6px; font-size: 30px; }}
  h1 .brand {{ color:#f59e0b; }}
  .desc {{ color:#94a3b8; margin: 0 0 8px; }}
  .meta {{ color:#64748b; font-size: 13px; }}
  .stats {{ display:flex; gap:12px; margin: 20px 0; flex-wrap: wrap; }}
  .stat {{ background:#1e293b; border-radius:10px; padding:12px 18px; }}
  .stat .n {{ font-size:22px; font-weight:700; }}
  .stat .l {{ font-size:12px; color:#94a3b8; }}
  h2 {{ margin-top: 32px; font-size: 20px; }}
  table {{ width:100%; border-collapse: collapse; background:#111c33; border-radius:12px; overflow:hidden; }}
  th, td {{ text-align:left; padding:12px 14px; border-bottom:1px solid #1e293b; vertical-align:top; }}
  th {{ color:#94a3b8; font-size:12px; text-transform:uppercase; letter-spacing:.04em; }}
  .rank {{ color:#64748b; font-weight:700; white-space:nowrap; }}
  .title {{ font-weight:600; }}
  .sub {{ color:#94a3b8; font-size:12px; margin-top:2px; }}
  .num {{ white-space:nowrap; font-variant-numeric: tabular-nums; }}
  .verdict {{ padding:3px 10px; border-radius:999px; font-size:12px; font-weight:700; white-space:nowrap; }}
  .bar {{ width:110px; height:8px; background:#1e293b; border-radius:99px; overflow:hidden; }}
  .fill {{ height:100%; border-radius:99px; }}
  .score {{ font-size:12px; color:#94a3b8; margin-top:3px; }}
  .flag {{ display:inline-block; font-size:11px; border:1px solid; border-radius:999px; padding:2px 8px; margin:4px 4px 0 0; }}
  .clean {{ font-size:11px; color:#22c55e; }}
  .chart {{ max-width:100%; border-radius:12px; margin-top:8px; }}
  ul.alerts {{ background:#111c33; border-radius:12px; padding:18px 18px 18px 36px; }}
  ul.alerts li {{ margin:6px 0; }}
  footer {{ margin-top:40px; color:#475569; font-size:12px; }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1><span class="brand">AutoHunt</span> deal report</h1>
    <p class="desc">{profile_name} — {description}</p>
    <p class="meta">Generated {generated} · {len(matched)} matching listings{ f' · {skipped} filtered out by profile criteria' if skipped else ''}</p>
  </header>

  <div class="stats">
    <div class="stat"><div class="n">{len(matched)}</div><div class="l">matching listings</div></div>
    <div class="stat"><div class="n">{sum(1 for r in matched if r['score'] >= 80)}</div><div class="l">hot deals</div></div>
    <div class="stat"><div class="n">{sum(1 for r in matched if r['red_flags'])}</div><div class="l">with red flags</div></div>
    <div class="stat"><div class="n">{len(alerts)}</div><div class="l">alerts fired</div></div>
  </div>

  <h2>Alerts</h2>
  <ul class="alerts">{alert_items}</ul>

  <h2>Ranked deals</h2>
  {chart_html}
  <table>
    <thead><tr>
      <th>#</th><th>Listing</th><th>Price</th><th>Market&nbsp;value</th>
      <th>Mileage</th><th>Year</th><th>Verdict</th><th>Score</th>
    </tr></thead>
    <tbody>{''.join(rows) if rows else '<tr><td colspan="8">No matching listings.</td></tr>'}</tbody>
  </table>

  <footer>AutoHunt {html.escape(profile.get('slug', ''))} · market values are estimates from comparable listings, not appraisals.</footer>
</div>
</body>
</html>"""

    output_path.write_text(page, encoding="utf-8")
    return output_path
