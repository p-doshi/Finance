#!/usr/bin/env python3
"""Phase 4: real-time monitor. A local-first project doesn't have a
server to host a continuously-live page, so "real-time" here means what
it realistically can: an HTML dashboard regenerated from the latest data
each time this script runs (same convention as the quantstats tearsheets,
scripts/generate_tearsheet.py) -- current prices, current vs. target
weights, and a clear alert banner for any position outside its drift
band. Read-only, same execution boundary as every other part of this
project: this generates a status page, not an order.

Run: .venv/bin/python scripts/generate_monitor_dashboard.py
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from portfolio_pipeline.research.optimizers import risk_parity_weight
from portfolio_pipeline.decision.trade_ticket import load_holdings, current_weights

TICKERS = ["NVDA", "JNJ", "KO", "PG", "WMT", "VZ", "XOM", "RY", "ENB", "UL", "NVO", "ASML"]
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "results"
WINDOW_DAYS = 756
DRIFT_ALERT_BAND = 0.02


def load_series(ticker: str) -> pd.Series:
    d = json.load(open(DATA_DIR / f"{ticker}.json"))
    s = pd.Series({r["t"]: r["a"] for r in d["data"]}, name=ticker)
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def main():
    holdings_path = ROOT / "portfolio_state.json"
    using_template = not holdings_path.exists()
    if using_template:
        holdings_path = ROOT / "portfolio_state.example.json"
    holdings = load_holdings(holdings_path)

    prices_series, latest_prices, day_change = {}, {}, {}
    for t in TICKERS:
        s = load_series(t)
        latest_prices[t] = float(s.iloc[-1])
        day_change[t] = float(s.iloc[-1] / s.iloc[-2] - 1) if len(s) > 1 else 0.0
        prices_series[t] = np.log(s / s.shift(1)).dropna()

    log_ret_df = pd.concat(prices_series, axis=1, join="inner").tail(WINDOW_DAYS)
    cov = log_ret_df.cov().values * 252
    target_w = dict(zip(TICKERS, risk_parity_weight(cov).tolist()))

    cur_w, total_value = current_weights(holdings, latest_prices)
    drift = {t: cur_w.get(t, 0.0) - target_w[t] for t in TICKERS}
    alerts = [t for t in TICKERS if abs(drift[t]) * total_value >= DRIFT_ALERT_BAND * total_value
              and abs(drift[t]) >= DRIFT_ALERT_BAND]

    rows = []
    for t in TICKERS:
        rows.append({
            "ticker": t, "price": latest_prices[t], "day_change": day_change[t],
            "current_weight": cur_w.get(t, 0.0), "target_weight": target_w[t], "drift": drift[t],
            "alert": t in alerts,
        })

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    html = _render(rows, total_value, holdings["cash"], alerts, generated_at, using_template)

    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / "monitor_dashboard.html"
    out_path.write_text(html)
    print(f"Saved {out_path}")
    print(f"{len(alerts)} name(s) outside the {DRIFT_ALERT_BAND*100:.0f}% drift band: {alerts or 'none'}")


def _render(rows, total_value, cash, alerts, generated_at, using_template) -> str:
    def bar_row(r):
        cur_pct, tgt_pct = r["current_weight"] * 100, r["target_weight"] * 100
        alert_cls = " alert" if r["alert"] else ""
        chg_cls = "up" if r["day_change"] >= 0 else "down"
        return f"""
        <div class="row{alert_cls}">
          <div class="ticker">{r['ticker']}{' ⚠' if r['alert'] else ''}</div>
          <div class="price">${r['price']:,.2f} <span class="chg {chg_cls}">{r['day_change']*100:+.1f}%</span></div>
          <div class="bars">
            <div class="bar-track"><div class="bar-cur" style="width:{min(cur_pct,100):.1f}%"></div>
            <div class="bar-tgt-marker" style="left:{min(tgt_pct,100):.1f}%"></div></div>
          </div>
          <div class="weights">{cur_pct:.1f}% <span class="muted">/ {tgt_pct:.1f}% target</span></div>
          <div class="drift {'alert-text' if r['alert'] else ''}">{r['drift']*100:+.1f}pp</div>
        </div>"""

    rows_html = "".join(bar_row(r) for r in rows)
    alert_banner = (
        f'<div class="banner">⚠ {len(alerts)} name(s) outside the {DRIFT_ALERT_BAND*100:.0f}% drift band: '
        f'{", ".join(alerts)} — consider running generate_decision_ticket.py</div>'
        if alerts else
        '<div class="banner ok">✓ All positions within the drift band — no rebalancing flagged</div>'
    )
    template_notice = (
        '<div class="banner warn">Using portfolio_state.example.json (all zeros) — '
        'copy to portfolio_state.json with real holdings for a real monitor.</div>'
        if using_template else ""
    )

    return f"""<title>Portfolio Monitor</title>
<style>
  .viz-root {{
    color-scheme: light;
    --surface-1: #fcfcfb; --page-plane: #f9f9f7; --text-primary: #0b0b0b;
    --text-secondary: #52514e; --muted: #898781; --grid: #e1e0d9; --border: rgba(11,11,11,0.10);
    --series-1: #2a78d6; --good: #0ca30c; --critical: #d03b3b; --warn-bg: #fff8e6; --warn-border: #eda100;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:where(:not([data-theme="light"])) .viz-root {{
      color-scheme: dark;
      --surface-1: #1a1a19; --page-plane: #0d0d0d; --text-primary: #ffffff;
      --text-secondary: #c3c2b7; --muted: #898781; --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
      --series-1: #3987e5; --good: #0ca30c; --critical: #e66767; --warn-bg: #2a2410; --warn-border: #c98500;
    }}
  }}
  :root[data-theme="dark"] .viz-root {{
    color-scheme: dark;
    --surface-1: #1a1a19; --page-plane: #0d0d0d; --text-primary: #ffffff;
    --text-secondary: #c3c2b7; --muted: #898781; --grid: #2c2c2a; --border: rgba(255,255,255,0.10);
    --series-1: #3987e5; --good: #0ca30c; --critical: #e66767; --warn-bg: #2a2410; --warn-border: #c98500;
  }}
  * {{ box-sizing: border-box; }}
  body {{ background: var(--page-plane); margin: 0; }}
  .viz-root {{ font-family: system-ui, -apple-system, "Segoe UI", sans-serif; background: var(--page-plane);
    color: var(--text-primary); padding: 20px 16px 40px; max-width: 760px; margin: 0 auto; }}
  h1 {{ font-size: 19px; font-weight: 650; margin: 0 0 4px; }}
  .meta {{ color: var(--text-secondary); font-size: 12px; margin: 0 0 16px; }}
  .summary {{ display: flex; gap: 24px; margin-bottom: 16px; flex-wrap: wrap; }}
  .stat {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 12px 16px; }}
  .stat .label {{ font-size: 11px; color: var(--muted); text-transform: uppercase; }}
  .stat .value {{ font-size: 20px; font-weight: 650; }}
  .banner {{ background: var(--surface-1); border: 1px solid var(--good); color: var(--good);
    border-radius: 8px; padding: 10px 14px; font-size: 13px; font-weight: 600; margin-bottom: 10px; }}
  .banner:not(.ok):not(.warn) {{ border-color: var(--critical); color: var(--critical); }}
  .banner.warn {{ border-color: var(--warn-border); color: var(--warn-border); background: var(--warn-bg); }}
  .card {{ background: var(--surface-1); border: 1px solid var(--border); border-radius: 10px; padding: 8px 16px; }}
  .row {{ display: grid; grid-template-columns: 56px 110px 1fr 110px 60px; align-items: center;
    gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--grid); font-size: 13px; }}
  .row:last-child {{ border-bottom: none; }}
  .row.alert {{ background: var(--warn-bg); margin: 0 -16px; padding: 10px 16px; border-radius: 6px; }}
  .ticker {{ font-weight: 650; }}
  .price {{ font-variant-numeric: tabular-nums; color: var(--text-secondary); font-size: 12px; }}
  .chg.up {{ color: var(--good); }} .chg.down {{ color: var(--critical); }}
  .bar-track {{ position: relative; height: 10px; background: var(--grid); border-radius: 5px; }}
  .bar-cur {{ position: absolute; left: 0; top: 0; bottom: 0; background: var(--series-1); border-radius: 5px; }}
  .bar-tgt-marker {{ position: absolute; top: -2px; bottom: -2px; width: 2px; background: var(--text-primary); }}
  .weights {{ font-size: 12px; text-align: right; font-variant-numeric: tabular-nums; }}
  .muted {{ color: var(--muted); }}
  .drift {{ text-align: right; font-size: 12px; font-variant-numeric: tabular-nums; font-weight: 600; }}
  .alert-text {{ color: var(--critical); }}
  @media (max-width: 480px) {{ .row {{ grid-template-columns: 44px 1fr 70px; }} .price, .weights {{ display: none; }} }}
</style>
<div class="viz-root">
  <h1>Portfolio Monitor</h1>
  <p class="meta">Generated {generated_at} from the latest price data on disk. Read-only — submits nothing.</p>
  {template_notice}
  <div class="summary">
    <div class="stat"><div class="label">Total value</div><div class="value">${total_value:,.2f}</div></div>
    <div class="stat"><div class="label">Cash</div><div class="value">${cash:,.2f}</div></div>
  </div>
  {alert_banner}
  <div class="card">{rows_html}
  </div>
  <p class="meta" style="margin-top:14px;">Bar = current weight; vertical mark = target weight (fresh risk-parity, same 3-year window as the rest of this project). Run scripts/generate_decision_ticket.py for an actual trade ticket.</p>
</div>
"""


if __name__ == "__main__":
    main()
