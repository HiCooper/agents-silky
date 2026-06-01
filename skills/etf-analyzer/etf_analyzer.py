#!/usr/bin/env python3
"""
Fetch ETF 516510 (华泰柏瑞中证云计算与大数据ETF) historical data via akshare
and generate an interactive HTML chart with ECharts.

Charts:
  1. 净值走势 (收盘价 + 单位净值 overlay)
  2. 成交量 (柱状图)
  3. 成交额 (柱状图)
"""

import akshare as ak
import pandas as pd
import json
import os
from datetime import datetime

# ---------------------------------------------------------------------------
# 0. Bypass macOS system proxy (ClashX) — eastmoney API blocked through it
# ---------------------------------------------------------------------------
os.environ["no_proxy"] = "*"
os.environ["NO_PROXY"] = "*"

import requests as _requests

_original_get = _requests.get


def _patched_get(url, **kwargs):
    if "proxies" not in kwargs:
        kwargs["proxies"] = {"http": None, "https": None}
    return _original_get(url, **kwargs)


_requests.get = _patched_get

# Accept ETF code from command line, e.g.: python etf_chart.py 159852
import sys

ETF_CODE = sys.argv[1] if len(sys.argv) > 1 else "516510"
OUTPUT_HTML = f"etf_{ETF_CODE}_chart.html"

# Auto-detect exchange by trying both (some 51xxxx ETFs are on SZ)
EXCHANGE = None
for trial in ["sh", "sz"]:
    try:
        test_url = (
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
            f"?param={trial}{ETF_CODE},day,,,5,qfq"
        )
        r = _requests.get(test_url, timeout=10)
        d = r.json()
        if "day" in d.get("data", {}).get(f"{trial}{ETF_CODE}", {}):
            EXCHANGE = trial
            break
    except Exception:
        continue
if EXCHANGE is None:
    EXCHANGE = "sh" if ETF_CODE.startswith("51") else "sz"
    print(f"  Warning: could not auto-detect exchange, using {EXCHANGE}")
else:
    print(f"  Exchange: {EXCHANGE}")

# Try to get ETF name from akshare, with fallback
ETF_NAME = None
try:
    df_spot = ak.fund_etf_spot_em()
    row = df_spot[df_spot["代码"] == ETF_CODE]
    if len(row) > 0:
        ETF_NAME = row["名称"].values[0]
        print(f"ETF: {ETF_CODE} = {ETF_NAME}")
except Exception:
    pass
if ETF_NAME is None:
    ETF_NAME = f"ETF{ETF_CODE}"

# ---------------------------------------------------------------------------
# 1. Fetch daily data via Tencent API (eastmoney push API unreliable behind proxy)
# ---------------------------------------------------------------------------
print(f"Fetching daily data for {ETF_CODE} via Tencent API...")
TENCENT_URL = (
    "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
    "?param={exch}{code},day,,,400,qfq"
)
resp = _requests.get(TENCENT_URL.format(exch=EXCHANGE, code=ETF_CODE), timeout=15)
data = resp.json()
raw_days = data["data"][f"{EXCHANGE}{ETF_CODE}"]["day"]

# Parse: ["date","open","close","high","low","volume"]
rows = []
for r in raw_days:
    rows.append({
        "日期": pd.to_datetime(r[0]),
        "开盘": float(r[1]),
        "收盘": float(r[2]),
        "最高": float(r[3]),
        "最低": float(r[4]),
        "成交量": float(r[5]),
        # estimate turnover: volume * 100 shares * avg(open,close,high,low)
        "成交额": float(r[5]) * 100 * (float(r[1]) + float(r[2]) + float(r[3]) + float(r[4])) / 4,
        "涨跌幅": None, "振幅": None, "涨跌额": None, "换手率": None,
    })
df_daily = pd.DataFrame(rows).sort_values("日期")
df_daily["涨跌幅"] = df_daily["收盘"].pct_change() * 100
df_daily["振幅"] = (df_daily["最高"] - df_daily["最低"]) / df_daily["收盘"].shift(1) * 100
df_daily["涨跌额"] = df_daily["收盘"] - df_daily["收盘"].shift(1)
print(f"  Daily rows: {len(df_daily)} (last: {df_daily['日期'].max().date()})")

# ---------------------------------------------------------------------------
# 2. Derive weekly / monthly K-lines from daily (resample)
# ---------------------------------------------------------------------------
def resample_ohlcv(df, freq):
    """Resample daily OHLCV to weekly ('W') or monthly ('M')."""
    df = df.set_index("日期")
    ohlcv = df.resample(freq).agg({
        "开盘": "first",
        "最高": "max",
        "最低": "min",
        "收盘": "last",
        "成交量": "sum",
        "成交额": "sum",
    }).dropna()
    ohlcv["涨跌幅"] = ohlcv["收盘"].pct_change() * 100
    ohlcv["振幅"] = (ohlcv["最高"] - ohlcv["最低"]) / ohlcv["收盘"].shift(1) * 100
    ohlcv["涨跌额"] = ohlcv["收盘"] - ohlcv["收盘"].shift(1)
    ohlcv["换手率"] = None
    return ohlcv.reset_index()

df_weekly = resample_ohlcv(df_daily, "W-FRI")
df_monthly = resample_ohlcv(df_daily, "ME")
print(f"  Weekly rows: {len(df_weekly)}")
print(f"  Monthly rows: {len(df_monthly)}")

# ---------------------------------------------------------------------------
# 3. Fetch NAV data (单位净值) — from eastmoney, may fail behind proxy
# ---------------------------------------------------------------------------
print(f"Fetching NAV data for {ETF_CODE}...")
df_nav = None
try:
    df_nav = ak.fund_open_fund_info_em(symbol=ETF_CODE, indicator="单位净值走势")
    df_nav["净值日期"] = pd.to_datetime(df_nav["净值日期"])
    df_nav = df_nav.sort_values("净值日期")
    print(f"  NAV rows: {len(df_nav)}")
except Exception as e:
    print(f"  NAV fetch failed (will skip): {e}")
    df_nav["净值日期"] = pd.to_datetime(df_nav["净值日期"])
    df_nav = df_nav.sort_values("净值日期")
    print(f"  NAV rows: {len(df_nav)}")
except Exception as e:
    print(f"  NAV fetch failed (will skip): {e}")
# ---------------------------------------------------------------------------
# 4. Merge NAV on daily data
# ---------------------------------------------------------------------------
if df_nav is not None:
    start = df_daily["日期"].min()
    end = df_daily["日期"].max()
    df_nav = df_nav[(df_nav["净值日期"] >= start) & (df_nav["净值日期"] <= end)]
    print(f"  NAV rows (filtered): {len(df_nav)}")
    df_daily_idx = df_daily.set_index("日期")
    df_nav_idx = df_nav.set_index("净值日期")
    df_merged = df_daily_idx.join(df_nav_idx, how="left")
    df_merged = df_merged.reset_index().rename(columns={"index": "日期"})
else:
    df_merged = df_daily.copy()
    df_merged["单位净值"] = None
    print("  Skipping NAV merge")

# ---------------------------------------------------------------------------
# 5. Compute 5-day moving averages (on daily data)
# ---------------------------------------------------------------------------
WINDOW = 5
df_merged["成交量_MA5"] = df_merged["成交量"].rolling(window=WINDOW, min_periods=1).mean()
df_merged["成交额_MA5"] = df_merged["成交额"].rolling(window=WINDOW, min_periods=1).mean()

# ---------------------------------------------------------------------------
# 5. Prepare OHLC data for daily / weekly / monthly K-line
# ---------------------------------------------------------------------------
def make_ohlc(df):
    """Return (dates, ohlc) where ohlc = [[open, close, low, high], ...] for ECharts candlestick."""
    d = df[["日期", "开盘", "收盘", "最低", "最高"]].copy()
    d = d.dropna()
    dates = d["日期"].dt.strftime("%Y-%m-%d").tolist()
    ohlc = d[["开盘", "收盘", "最低", "最高"]].round(4).values.tolist()
    return dates, ohlc

k_dates_daily,   k_ohlc_daily   = make_ohlc(df_merged)
k_dates_weekly,  k_ohlc_weekly  = make_ohlc(df_weekly)
k_dates_monthly, k_ohlc_monthly = make_ohlc(df_monthly)

# Default zoom: show last 3 months
from datetime import timedelta


def zoom_start_pct(dates_list, months=3):
    """Return dataZoom start% so that last `months` of data is visible."""
    if len(dates_list) < 2:
        return 0
    last_date = pd.Timestamp(dates_list[-1])
    cutoff = last_date - pd.DateOffset(months=months)
    idx = 0
    for i, d in enumerate(dates_list):
        if pd.Timestamp(d) >= cutoff:
            idx = i
            break
    return round(idx / len(dates_list) * 100, 1)


zoom_daily = zoom_start_pct(k_dates_daily)
zoom_weekly = zoom_start_pct(k_dates_weekly)
zoom_monthly = zoom_start_pct(k_dates_monthly)
zoom_map = {"daily": zoom_daily, "weekly": zoom_weekly, "monthly": zoom_monthly}
print(f"  Default zoom (last 3mo): daily={zoom_daily}% weekly={zoom_weekly}% monthly={zoom_monthly}%")

# ---------------------------------------------------------------------------
# 6. Prepare chart data (JSON) – daily for volume / turnover sub-charts
# ---------------------------------------------------------------------------
dates = df_merged["日期"].dt.strftime("%Y-%m-%d").tolist()
close_prices = df_merged["收盘"].round(4).tolist()
nav_values = df_merged["单位净值"].round(4).tolist()
volumes = df_merged["成交量"].tolist()  # 成交量 (手)
amounts = df_merged["成交额"].tolist()  # 成交额 (元)
vol_ma5 = df_merged["成交量_MA5"].round(0).tolist()
amt_ma5 = df_merged["成交额_MA5"].round(0).tolist()
change_pct = df_merged["涨跌幅"].round(2).tolist()

# Stats
total_return = (close_prices[-1] / close_prices[0] - 1) * 100
max_price = max(close_prices)
min_price = min(close_prices)
avg_volume = sum(volumes) / len(volumes)
max_turnover = max(amounts)
avg_turnover = sum(amounts) / len(amounts)

print(f"\n=== Summary ===")
print(f"Date range: {dates[0]} ~ {dates[-1]}")
print(f"Price start: {close_prices[0]:.4f} → end: {close_prices[-1]:.4f}")
print(f"Total return: {total_return:.2f}%")
print(f"Price range: {min_price:.4f} ~ {max_price:.4f}")
print(f"Avg volume (shares): {avg_volume:,.0f}")
print(f"Avg turnover (CNY): {avg_turnover:,.0f}")

# ===========================================================================
# 7. PREDICTION: Multi-factor model for next-week trend
# ===========================================================================
import numpy as np


def predict_next_week(df):
    """
    Predict next 5 trading days based on price, volume, and turnover.

    Multi-factor scoring model:
      - Momentum: short/medium-term price trend
      - Volume: volume trend and volume-price divergence
      - Money-flow: turnover trend and large-order bias
      - Position: price relative to moving averages & volatility bands

    Returns dict with projected path, confidence bands, and factor scores.
    """
    n = len(df)
    close = df["收盘"].values
    vol = df["成交量"].values
    amt = df["成交额"].values
    high = df["最高"].values
    low = df["最低"].values
    last_date = df["日期"].iloc[-1]

    # ---- daily returns & volatility ----
    rets = np.diff(close) / close[:-1]
    rets = np.append(rets, rets[-1])  # pad to same length
    vol20_std = np.std(rets[-20:])
    avg_abs_ret = np.mean(np.abs(rets[-20:]))

    # ---- 1. Momentum score (0-1, higher = more bullish) ----
    ret5 = (close[-1] / close[-6] - 1) if n >= 6 else 0
    ret10 = (close[-1] / close[-11] - 1) if n >= 11 else 0
    ret20 = (close[-1] / close[-21] - 1) if n >= 21 else 0
    # Normalize by volatility
    mom5_norm = ret5 / (vol20_std * np.sqrt(5) + 1e-9)
    mom10_norm = ret10 / (vol20_std * np.sqrt(10) + 1e-9)
    momentum_raw = 0.5 * mom5_norm + 0.3 * mom10_norm + 0.2 * (0 if ret20 == 0 else ret20 / abs(ret20 + 1e-9))
    momentum_score = 1.0 / (1.0 + np.exp(-momentum_raw))  # sigmoid → 0-1

    # ---- 2. Volume score ----
    ma5_vol = np.mean(vol[-5:])
    ma20_vol = np.mean(vol[-20:]) if n >= 20 else ma5_vol
    vol_ratio = ma5_vol / (ma20_vol + 1)
    # Rising volume + rising price = bullish; rising volume + falling price = distribution
    vol_trend = (vol_ratio - 1) * 3  # scale
    price_vol_corr = np.corrcoef(rets[-20:], vol[-20:])[0, 1] if n >= 20 else 0
    volume_raw = vol_trend * (0.5 + 0.5 * price_vol_corr)  # volume confirmed by price
    volume_score = 1.0 / (1.0 + np.exp(-volume_raw))

    # ---- 3. Money-flow score (turnover-based) ----
    ma5_amt = np.mean(amt[-5:])
    ma20_amt = np.mean(amt[-20:]) if n >= 20 else ma5_amt
    amt_ratio = ma5_amt / (ma20_amt + 1)
    amt_trend = (amt_ratio - 1) * 3
    # Large turnover days: weighted by relative size
    amt_rets = np.array([rets[i] * (1 + amt[i] / (ma20_amt + 1)) for i in range(max(n - 10, 0), n)])
    flow_bias = np.mean(amt_rets)
    flow_raw = amt_trend * 0.4 + flow_bias / (vol20_std + 1e-9) * 0.6
    flow_score = 1.0 / (1.0 + np.exp(-flow_raw))

    # ---- 4. Position score (MA & volatility envelope) ----
    ma20_close = np.mean(close[-20:]) if n >= 20 else np.mean(close)
    bollinger_upper = ma20_close + 2 * vol20_std * close[-1]
    bollinger_lower = ma20_close - 2 * vol20_std * close[-1]
    # Position within BB: 0 = at lower, 1 = at upper
    bb_position = (close[-1] - bollinger_lower) / (bollinger_upper - bollinger_lower + 1e-9)
    bb_position = max(0, min(1, bb_position))
    # Distance from 20MA in std units
    ma_distance = (close[-1] - ma20_close) / (vol20_std * close[-1] + 1e-9)
    position_raw = -0.3 * ma_distance + 0.5  # revert slightly toward mean
    position_score = 1.0 / (1.0 + np.exp(-position_raw))

    # ---- 5. Composite score ----
    weights = {"momentum": 0.30, "volume": 0.25, "flow": 0.25, "position": 0.20}
    composite = (
        weights["momentum"] * momentum_score
        + weights["volume"] * volume_score
        + weights["flow"] * flow_score
        + weights["position"] * position_score
    )
    # Map 0-1 to directional bias: 0→bearish, 0.5→neutral, 1→bullish
    direction = (composite - 0.5) * 2  # -1 to +1
    bias_pct = direction * 100

    # ---- Project next 5 trading days ----
    predict_days = 5
    drift_per_day = direction * avg_abs_ret * 0.3  # modest signal-to-drift ratio
    last_close = close[-1]

    projected = [last_close]
    for i in range(1, predict_days + 1):
        projected.append(projected[-1] * (1 + drift_per_day))

    projected_prices = projected[1:]  # 5 predicted closes

    # Confidence bands based on random-walk volatility
    vol_daily = vol20_std * last_close  # absolute daily volatility in yuan
    upper1 = [projected_prices[i] + vol_daily * np.sqrt(i + 1) for i in range(predict_days)]
    lower1 = [projected_prices[i] - vol_daily * np.sqrt(i + 1) for i in range(predict_days)]
    upper2 = [projected_prices[i] + 2 * vol_daily * np.sqrt(i + 1) for i in range(predict_days)]
    lower2 = [projected_prices[i] - 2 * vol_daily * np.sqrt(i + 1) for i in range(predict_days)]

    # Generate future dates (skip weekends)
    from pandas.tseries.offsets import BDay
    future_dates = pd.date_range(start=last_date + BDay(1), periods=predict_days, freq="B")

    # Trend label
    if composite > 0.65:
        trend = "bullish"
        trend_cn = "看涨 ↑"
    elif composite < 0.35:
        trend = "bearish"
        trend_cn = "看跌 ↓"
    else:
        trend = "neutral"
        trend_cn = "震荡 ↔"

    return {
        "trend": trend,
        "trend_cn": trend_cn,
        "confidence": round(float(abs(composite - 0.5) * 2), 3),
        "direction": round(float(direction), 3),
        "bias_pct": round(float(bias_pct), 1),
        "scores": {
            "momentum": round(float(momentum_score), 3),
            "volume": round(float(volume_score), 3),
            "flow": round(float(flow_score), 3),
            "position": round(float(position_score), 3),
        },
        "projected_prices": [round(float(p), 4) for p in projected_prices],
        "projected_dates": [d.strftime("%m-%d") for d in future_dates],
        "upper1": [round(float(p), 4) for p in upper1],
        "lower1": [round(float(p), 4) for p in lower1],
        "upper2": [round(float(p), 4) for p in upper2],
        "lower2": [round(float(p), 4) for p in lower2],
        "vol_daily_pct": round(float(vol20_std * 100), 2),
    }


prediction = predict_next_week(df_merged)
print(f"\n=== Prediction ===")
print(f"Trend: {prediction['trend_cn']} (confidence: {prediction['confidence']:.2f})")
print(f"Scores: momentum={prediction['scores']['momentum']:.3f} "
      f"volume={prediction['scores']['volume']:.3f} "
      f"flow={prediction['scores']['flow']:.3f} "
      f"position={prediction['scores']['position']:.3f}")
print(f"Projected: {[f'{p:.4f}' for p in prediction['projected_prices']]}")
print(f"Dates: {prediction['projected_dates']}")

# Prepare last-30d data for prediction chart context
LOOKBACK = 30
pred_context = {
    "dates": dates[-LOOKBACK:],
    "close": close_prices[-LOOKBACK:],
    "vol_ma5": vol_ma5[-LOOKBACK:],
    "amt_ma5": amt_ma5[-LOOKBACK:],
}

# ---------------------------------------------------------------------------
# 5. Generate HTML
# ---------------------------------------------------------------------------
html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{ETF_NAME} ({ETF_CODE}) — 走势图</title>
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC',
      'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
    background: #0f1419; color: #e7e9ea; padding: 24px;
  }}
  .container {{ max-width: 1200px; margin: 0 auto; }}
  h1 {{ font-size: 24px; margin-bottom: 4px; }}
  .subtitle {{ color: #71767b; font-size: 14px; margin-bottom: 24px; }}
  .stats {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 24px;
  }}
  .stat-card {{
    background: #1a1f26; border: 1px solid #2f3336;
    border-radius: 10px; padding: 16px;
  }}
  .stat-label {{ font-size: 12px; color: #71767b; margin-bottom: 4px; }}
  .stat-value {{ font-size: 20px; font-weight: 700; }}
  .stat-value.up {{ color: #00b368; }} .stat-value.down {{ color: #f91880; }}
  .chart-row {{ display: flex; gap: 20px; margin-bottom: 20px; }}
  .chart-box {{
    flex: 1; background: #1a1f26; border: 1px solid #2f3336;
    border-radius: 10px; padding: 16px; min-height: 420px;
  }}
  .chart-box.full {{ width: 100%; }}
  .chart-title {{ font-size: 15px; font-weight: 600; margin-bottom: 8px; color: #e7e9ea; }}
  .chart-wrap {{ width: 100%; height: 380px; }}
  .chart-wrap.combined {{ height: 420px; }}
  .chart-wrap.sub {{ height: 130px; }}
  @media (max-width: 768px) {{ .chart-row {{ flex-direction: column; }} }}
  /* K-line toggle */
  .toggle-group {{
    display: inline-flex; background: #1a1f26; border: 1px solid #2f3336;
    border-radius: 8px; overflow: hidden; margin-bottom: 12px;
  }}
  .toggle-btn {{
    padding: 6px 18px; font-size: 13px; cursor: pointer;
    background: transparent; color: #71767b; border: none;
    transition: all 0.15s; font-family: inherit;
  }}
  .toggle-btn:hover {{ color: #e7e9ea; }}
  .toggle-btn.active {{
    background: #1d9bf0; color: #fff; font-weight: 600;
  }}
  .toggle-btn + .toggle-btn {{ border-left: 1px solid #2f3336; }}
  /* Prediction chart */
  .prediction-badge {{
    display: inline-block; padding: 3px 12px; border-radius: 12px;
    font-size: 13px; font-weight: 600; margin-left: 8px;
  }}
  .prediction-badge.bullish {{ background: rgba(249,24,128,0.15); color: #f91880; }}
  .prediction-badge.bearish {{ background: rgba(0,179,104,0.15); color: #00b368; }}
  .prediction-badge.neutral {{ background: rgba(247,177,37,0.15); color: #f7b125; }}
  .signal-bar {{
    height: 6px; border-radius: 3px; margin-top: 4px;
    background: #2f3336; overflow: hidden;
  }}
  .signal-fill {{ height: 100%; border-radius: 3px; transition: width 0.5s; }}
</style>
</head>
<body>
<div class="container">

<h1>{ETF_NAME} · {ETF_CODE}</h1>
<p class="subtitle">
  {ETF_NAME} · 数据来源: 腾讯行情 (via akshare) ·
  生成时间: {datetime.now().strftime("%Y-%m-%d %H:%M")}
</p>

<div class="stats">
  <div class="stat-card">
    <div class="stat-label">区间涨幅</div>
    <div class="stat-value {"up" if total_return >= 0 else "down"}">{total_return:+.2f}%</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">价格区间</div>
    <div class="stat-value">{min_price:.4f} ~ {max_price:.4f}</div>
  </div>
  <div class="stat-card">
    <div class="stat-label">日均成交量</div>
    <div class="stat-value">{avg_volume/10000:,.0f}<span style="font-size:13px;color:#71767b"> 万手</span></div>
  </div>
  <div class="stat-card">
    <div class="stat-label">日均成交额</div>
    <div class="stat-value">{avg_turnover/10000:,.0f}<span style="font-size:13px;color:#71767b"> 万元</span></div>
  </div>
  <div class="stat-card">
    <div class="stat-label">峰值成交额</div>
    <div class="stat-value">{max_turnover/1e8:,.2f}<span style="font-size:13px;color:#71767b"> 亿</span></div>
  </div>
  <div class="stat-card">
    <div class="stat-label">交易日数</div>
    <div class="stat-value">{len(dates)}</div>
  </div>
</div>

<div class="chart-box full" style="margin-bottom:20px;padding-bottom:4px;">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;margin-bottom:2px;">
    <div class="chart-title" style="margin-bottom:0;">📈 K线走势 + 成交量/成交额副图</div>
    <div class="toggle-group" id="ktype-toggle">
      <button class="toggle-btn active" data-k="daily">日K</button>
      <button class="toggle-btn" data-k="weekly">周K</button>
      <button class="toggle-btn" data-k="monthly">月K</button>
    </div>
  </div>
  <div id="chart-price" class="chart-wrap combined"></div>
  <div id="chart-volume" class="chart-wrap sub"></div>
  <div id="chart-amount" class="chart-wrap sub"></div>
</div>

<!-- Prediction Section -->
<div class="chart-box full" style="margin-bottom:20px;">
  <div class="chart-title">
    🔮 下周走势预测
    <span class="prediction-badge {prediction['trend']}" id="pred-badge">
      {prediction['trend_cn']} · 置信度 {prediction['confidence']:.0%}
    </span>
  </div>
  <div style="display:flex;gap:16px;margin-bottom:12px;flex-wrap:wrap;" id="signal-cards">
    <div style="flex:1;min-width:160px;background:#0f1419;border-radius:8px;padding:10px 14px;">
      <div style="font-size:11px;color:#71767b;">📈 动量因子 (30%)</div>
      <div style="font-size:16px;font-weight:700;color:#1d9bf0;">{prediction['scores']['momentum']:.0%}</div>
      <div class="signal-bar"><div class="signal-fill" style="width:{prediction['scores']['momentum']*100}%;background:#1d9bf0;"></div></div>
    </div>
    <div style="flex:1;min-width:160px;background:#0f1419;border-radius:8px;padding:10px 14px;">
      <div style="font-size:11px;color:#71767b;">📊 量能因子 (25%)</div>
      <div style="font-size:16px;font-weight:700;color:#26de81;">{prediction['scores']['volume']:.0%}</div>
      <div class="signal-bar"><div class="signal-fill" style="width:{prediction['scores']['volume']*100}%;background:#26de81;"></div></div>
    </div>
    <div style="flex:1;min-width:160px;background:#0f1419;border-radius:8px;padding:10px 14px;">
      <div style="font-size:11px;color:#71767b;">💰 资金流因子 (25%)</div>
      <div style="font-size:16px;font-weight:700;color:#a55eea;">{prediction['scores']['flow']:.0%}</div>
      <div class="signal-bar"><div class="signal-fill" style="width:{prediction['scores']['flow']*100}%;background:#a55eea;"></div></div>
    </div>
    <div style="flex:1;min-width:160px;background:#0f1419;border-radius:8px;padding:10px 14px;">
      <div style="font-size:11px;color:#71767b;">📍 位置因子 (20%)</div>
      <div style="font-size:16px;font-weight:700;color:#f4a261;">{prediction['scores']['position']:.0%}</div>
      <div class="signal-bar"><div class="signal-fill" style="width:{prediction['scores']['position']*100}%;background:#f4a261;"></div></div>
    </div>
  </div>
  <div id="chart-predict" class="chart-wrap" style="height:400px;"></div>
</div>

</div>

<script>
const dates = {json.dumps(dates, ensure_ascii=False)};
const closePrices = {json.dumps(close_prices)};
const navValues = {json.dumps(nav_values)};
const volumes = {json.dumps(volumes)};
const amounts = {json.dumps(amounts)};
const volMa5 = {json.dumps(vol_ma5)};
const amtMa5 = {json.dumps(amt_ma5)};
const changePct = {json.dumps(change_pct)};

// OHLC data per period
const kData = {{
  daily:   {{ dates: {json.dumps(k_dates_daily)},   ohlc: {json.dumps(k_ohlc_daily)} }},
  weekly:  {{ dates: {json.dumps(k_dates_weekly)},  ohlc: {json.dumps(k_ohlc_weekly)} }},
  monthly: {{ dates: {json.dumps(k_dates_monthly)}, ohlc: {json.dumps(k_ohlc_monthly)} }},
}};

// Default zoom percentages (last 3 months)
const zoomMap = {json.dumps(zoom_map)};

// Prediction data
const predData = {{
  trend: '{prediction["trend"]}',
  trendCn: '{prediction["trend_cn"]}',
  confidence: {prediction["confidence"]},
  direction: {prediction["direction"]},
  biasPct: {prediction["bias_pct"]},
  scores: {json.dumps(prediction["scores"])},
  projectedPrices: {json.dumps(prediction["projected_prices"])},
  projectedDates: {json.dumps(prediction["projected_dates"])},
  upper1: {json.dumps(prediction["upper1"])},
  lower1: {json.dumps(prediction["lower1"])},
  upper2: {json.dumps(prediction["upper2"])},
  lower2: {json.dumps(prediction["lower2"])},
  volDailyPct: {prediction["vol_daily_pct"]},
}};
const predCtx = {{
  dates: {json.dumps(pred_context["dates"])},
  close: {json.dumps(pred_context["close"])},
}};

// Color theme
const upColor = '#f91880';   // A-share: red = up
const downColor = '#00b368'; // A-share: green = down
const gridColor = '#2f3336';
const textColor = '#71767b';

// --- 3-Chart Vertical Layout: Price + Volume + Turnover (echarts.connect sync) ---
const GROUP_ID = 'etf' + Date.now();

(function(){{
  // ---- Shared data ----
  const barColors = changePct.map(v => v >= 0 ? upColor : downColor);
  const volBars = volumes.map((v, i) => ({{ value: v, itemStyle: {{ color: barColors[i] }} }}));
  const amtBars = amounts.map((v, i) => ({{ value: v, itemStyle: {{ color: barColors[i] }} }}));
  const hasNav = navValues.some(v => v !== null);
  let currentK = 'daily';

  // ---- Chart instances ----
  const chartPrice  = echarts.init(document.getElementById('chart-price'));
  const chartVol    = echarts.init(document.getElementById('chart-volume'));
  const chartAmt    = echarts.init(document.getElementById('chart-amount'));
  chartPrice.group = GROUP_ID;
  chartVol.group   = GROUP_ID;
  chartAmt.group   = GROUP_ID;

  // Scale MA5 for right-axis overlay (volume→万手, turnover→百万)
  const volMa5Scaled = volMa5.map(v => v / 10000);
  const amtMa5Scaled = amtMa5.map(v => v / 1000000);

  function buildPriceOption(ktype) {{
    const kd = kData[ktype];
    const isDaily = ktype === 'daily';
    const series = [{{
      name: 'K线', type: 'candlestick', data: kd.ohlc,
        yAxisIndex: 0,
      itemStyle: {{ color: upColor, color0: downColor, borderColor: upColor, borderColor0: downColor }},
    }}];
    if (hasNav && isDaily) {{
      series.push({{
        name: '单位净值', type: 'line', data: navValues,
        yAxisIndex: 0,
        smooth: true, symbol: 'none',
        lineStyle: {{ width: 1.5, color: '#f4a261', type: 'dashed' }},
      }});
    }}
    // Overlay 5-day MA lines on right axis (daily only)
    if (isDaily) {{
      series.push({{
        name: '5日均量', type: 'line', data: volMa5Scaled,
        yAxisIndex: 1, smooth: true, symbol: 'none',
        lineStyle: {{ width: 1.5, color: '#26de81', opacity: 0.8 }},
      }});
      series.push({{
        name: '5日均额', type: 'line', data: amtMa5Scaled,
        yAxisIndex: 1, smooth: true, symbol: 'none',
        lineStyle: {{ width: 1.5, color: '#a55eea', opacity: 0.8 }},
      }});
    }}
    return {{
      tooltip: {{
        trigger: 'axis',
        backgroundColor: 'rgba(26,31,38,0.96)', borderColor: gridColor,
        textStyle: {{ color: '#e7e9ea', fontSize: 12 }},
        formatter: function(params) {{
          let s = '<b>' + params[0].axisValue + '</b><br/>';
          params.forEach(p => {{
            if (p.seriesName === 'K线') {{
              const d = p.data;
              s += '开 <b>' + d[1].toFixed(4) + '</b> 收 <b>' + d[2].toFixed(4) + '</b><br/>' +
                   '高 <b style="color:' + upColor + '">' + d[4].toFixed(4) + '</b> 低 <b style="color:' + downColor + '">' + d[3].toFixed(4) + '</b><br/>';
              const chg = ((d[2]-d[1])/d[1]*100);
              s += '涨跌 <b style="color:' + (chg>=0?upColor:downColor) + '">' + (chg>=0?'+':'') + chg.toFixed(2) + '%</b>';
            }} else if (p.seriesName === '单位净值') {{
              s += p.marker + ' 净值: <b>' + Number(p.value).toFixed(4) + '</b>';
            }} else if (p.seriesName === '5日均量') {{
              s += p.marker + ' 5日均量: <b>' + Number(p.value).toFixed(1) + ' 万手</b>';
            }} else if (p.seriesName === '5日均额') {{
              const v = Number(p.value);
              s += p.marker + ' 5日均额: <b>' + (v >= 100 ? (v/100).toFixed(2)+'亿' : v.toFixed(1)+'百万') + '</b>';
            }}
          }});
          return s;
        }}
      }},
      grid: {{ left: 66, right: 68, top: 12, bottom: 28 }},
      xAxis: {{
        type: 'category', data: kd.dates, boundaryGap: true,
        axisLine: {{ lineStyle: {{ color: gridColor }} }},
        axisTick: {{ show: false }},
        axisLabel: {{ show: false }},
      }},
      yAxis: [
        {{
          type: 'value', scale: true, position: 'left',
          name: '价格', nameTextStyle: {{ color: textColor, fontSize: 10 }},
          axisLabel: {{ color: textColor, fontSize: 11, formatter: v => v.toFixed(3) }},
          splitLine: {{ lineStyle: {{ color: gridColor, type: 'dashed', opacity: 0.4 }} }},
          axisLine: {{ show: false }},
        }},
        {{
          type: 'value', scale: true, position: 'right',
          name: '量(万手)/额(百万)', nameTextStyle: {{ color: textColor, fontSize: 9 }},
          axisLabel: {{ color: textColor, fontSize: 9 }},
          splitLine: {{ show: false }},
          axisLine: {{ show: false }},
        }}
      ],
      dataZoom: [
        {{ type: 'inside', start: zoomMap[ktype], end: 100 }},
        {{ type: 'slider', start: zoomMap[ktype], end: 100, height: 22, bottom: 2,
           borderColor: gridColor, backgroundColor: '#1a1f26',
           fillerColor: 'rgba(29,155,240,0.15)', handleStyle: {{ color: '#1d9bf0' }},
           textStyle: {{ color: textColor, fontSize: 10 }} }}
      ],
      series: series
    }};
  }}

  function buildSubOption(dataBars, dataMa, maName, yFormatter, yName, showXLabel) {{
    return {{
      tooltip: {{
        trigger: 'axis',
        backgroundColor: 'rgba(26,31,38,0.96)', borderColor: gridColor,
        textStyle: {{ color: '#e7e9ea', fontSize: 11 }},
        formatter: function(params) {{
          let s = '<b>' + params[0].axisValue + '</b><br/>';
          params.forEach(p => {{
            if (p.seriesName === '成交量' || p.seriesName === '成交额') {{
              s += p.marker + ' ' + p.seriesName + ': <b>' + yFormatter(p.value, false) + '</b><br/>';
            }} else {{
              s += p.marker + ' ' + maName + ': <b>' + yFormatter(p.value, false) + '</b><br/>';
            }}
          }});
          return s;
        }}
      }},
      grid: {{ left: 66, right: 18, top: 4, bottom: showXLabel ? 22 : 2 }},
      xAxis: {{
        type: 'category', data: dates, boundaryGap: true,
        axisLine: {{ lineStyle: {{ color: gridColor }} }},
        axisTick: {{ show: false }},
        axisLabel: showXLabel ? {{ color: textColor, fontSize: 10, formatter: v => v.slice(5) }} : {{ show: false }},
      }},
      yAxis: {{
        type: 'value', scale: true, position: 'left',
        name: yName, nameTextStyle: {{ color: textColor, fontSize: 9 }},
        axisLabel: {{ color: textColor, fontSize: 9, formatter: v => yFormatter(v, true) }},
        splitLine: {{ lineStyle: {{ color: gridColor, type: 'dashed', opacity: 0.3 }} }},
        axisLine: {{ show: false }},
      }},
      dataZoom: [{{ type: 'inside', start: zoomMap.daily, end: 100 }}],
      series: [
        {{ name: dataBars === volBars ? '成交量' : '成交额', type: 'bar',
           data: dataBars, barWidth: '70%',
           emphasis: {{ itemStyle: {{ color: '#1d9bf0' }} }} }},
        {{ name: maName, type: 'line', data: dataMa,
           smooth: true, symbol: 'none',
           lineStyle: {{ width: 2, color: maName.includes('量') ? '#26de81' : '#a55eea' }} }},
      ]
    }};
  }}

  // Volume formatter: raw 手 → 万手
  function volFmt(v, isAxis) {{ return (v / 10000).toFixed(isAxis ? 0 : 1) + (isAxis ? '万' : ' 万手'); }}
  // Turnover formatter: raw 元 → 亿 / 万
  function amtFmt(v, isAxis) {{
    if (v >= 1e8) return (v / 1e8).toFixed(isAxis ? 1 : 2) + '亿';
    return (v / 10000).toFixed(isAxis ? 0 : 1) + '万';
  }}

  chartPrice.setOption(buildPriceOption('daily'));
  chartVol.setOption(buildSubOption(volBars, volMa5, '5日均量', volFmt, '量(手)', false));
  chartAmt.setOption(buildSubOption(amtBars, amtMa5, '5日均额', amtFmt, '额(元)', true));

  // K-type toggle
  document.querySelectorAll('#ktype-toggle .toggle-btn').forEach(btn => {{
    btn.addEventListener('click', function() {{
      const ktype = this.dataset.k;
      if (ktype === currentK) return;
      currentK = ktype;
      document.querySelectorAll('#ktype-toggle .toggle-btn').forEach(b => b.classList.remove('active'));
      this.classList.add('active');
      chartPrice.setOption(buildPriceOption(ktype), true);
      // Show/hide volume & turnover sub-charts
      const showSub = ktype === 'daily';
      document.getElementById('chart-volume').style.display = showSub ? '' : 'none';
      document.getElementById('chart-amount').style.display = showSub ? '' : 'none';
    }});
  }});

  // Connect all three for synchronized zoom
  echarts.connect(GROUP_ID);
  window.addEventListener('resize', () => {{ chartPrice.resize(); chartVol.resize(); chartAmt.resize(); }});
}})();

// --- Prediction Chart ---
(function(){{
  const chart = echarts.init(document.getElementById('chart-predict'));

  const lastActual = predCtx.close[predCtx.close.length - 1];
  const actualDates = predCtx.dates.slice();
  const actualClose = predCtx.close.slice();
  const futureDates = predData.projectedDates;
  const projected = predData.projectedPrices;
  const N_ACTUAL = actualDates.length;
  const N_FUTURE = futureDates.length;

  const allDates = actualDates.concat(futureDates);

  // Build padded arrays (null where not applicable)
  function padFuture(arr) {{
    const a = new Array(N_ACTUAL).fill(null).concat(arr);
    a[N_ACTUAL - 1] = lastActual;  // anchor
    return a;
  }}
  const upper1 = padFuture(predData.upper1);
  const lower1 = padFuture(predData.lower1);
  const upper2 = padFuture(predData.upper2);
  const lower2 = padFuture(predData.lower2);

  const actualLine = actualClose.concat(new Array(N_FUTURE).fill(null));
  const projLine = (new Array(N_ACTUAL).fill(null)).concat(projected);
  actualLine[N_ACTUAL - 1] = lastActual;
  projLine[N_ACTUAL - 1] = lastActual;

  const trend = predData.trend;
  const bgColor = '#0f1419';
  const band68Color = trend === 'bullish' ? 'rgba(249,24,128,0.15)' :
                      trend === 'bearish' ? 'rgba(0,179,104,0.15)' :
                      'rgba(247,177,37,0.15)';
  const band95Color = trend === 'bullish' ? 'rgba(249,24,128,0.06)' :
                      trend === 'bearish' ? 'rgba(0,179,104,0.06)' :
                      'rgba(247,177,37,0.06)';
  const projColor = trend === 'bullish' ? '#f91880' :
                    trend === 'bearish' ? '#00b368' : '#f7b125';

  chart.setOption({{
    tooltip: {{
      trigger: 'axis',
      backgroundColor: 'rgba(26,31,38,0.96)',
      borderColor: gridColor,
      textStyle: {{ color: '#e7e9ea', fontSize: 12 }},
      formatter: function(params) {{
        const axisVal = params[0].axisValue;
        const idx = allDates.indexOf(axisVal);
        const isFuture = idx >= N_ACTUAL;
        let s = '<b>' + axisVal + '</b>';
        if (isFuture) s += ' 📅预测';
        s += '<br/>';
        params.forEach(p => {{
          if (p.value == null) return;
          if (p.seriesName === '实际收盘') {{
            s += p.marker + ' 实际: <b>' + Number(p.value).toFixed(4) + '</b><br/>';
          }} else if (p.seriesName === '预测路径') {{
            s += p.marker + ' 预测: <b>' + Number(p.value).toFixed(4) + '</b><br/>';
          }}
        }});
        if (isFuture) {{
          const i = idx - N_ACTUAL;
          if (predData.lower1[i] != null) {{
            s += '<span style="color:#71767b;">68%区间:</span> ' +
                 predData.lower1[i].toFixed(4) + ' ~ ' + predData.upper1[i].toFixed(4) + '<br/>';
            s += '<span style="color:#71767b;">95%区间:</span> ' +
                 predData.lower2[i].toFixed(4) + ' ~ ' + predData.upper2[i].toFixed(4) + '<br/>';
          }}
        }}
        return s;
      }}
    }},
    grid: {{ left: 60, right: 24, top: 20, bottom: 40 }},
    xAxis: {{
      type: 'category', data: allDates, boundaryGap: false,
      axisLine: {{ lineStyle: {{ color: gridColor }} }},
      axisTick: {{ show: false }},
      axisLabel: {{ color: textColor, fontSize: 10, formatter: v => v.slice(5) }}
    }},
    yAxis: {{
      type: 'value', scale: true,
      name: '价格 (元)',
      nameTextStyle: {{ color: textColor, fontSize: 10 }},
      axisLabel: {{ color: textColor, fontSize: 11, formatter: v => v.toFixed(3) }},
      splitLine: {{ lineStyle: {{ color: gridColor, type: 'dashed', opacity: 0.4 }} }},
      axisLine: {{ show: false }},
    }},
    series: [
      // --- 95% band: lower fills with bg, upper fills with 95% color ---
      {{
        name: '95%带底', type: 'line', data: lower2,
        lineStyle: {{ opacity: 0 }}, symbol: 'none',
        areaStyle: {{ color: bgColor }},
        stack: 'band95', silent: true,
      }},
      {{
        name: '95%置信带', type: 'line', data: upper2,
        lineStyle: {{ opacity: 0 }}, symbol: 'none',
        areaStyle: {{ color: band95Color }},
        stack: 'band95', silent: true,
      }},
      // --- 68% band: same stacking pattern ---
      {{
        name: '68%带底', type: 'line', data: lower1,
        lineStyle: {{ opacity: 0 }}, symbol: 'none',
        areaStyle: {{ color: bgColor }},
        stack: 'band68', silent: true,
      }},
      {{
        name: '68%置信带', type: 'line', data: upper1,
        lineStyle: {{ opacity: 0 }}, symbol: 'none',
        areaStyle: {{ color: band68Color }},
        stack: 'band68', silent: true,
      }},
      // --- Actual close line ---
      {{
        name: '实际收盘', type: 'line', data: actualLine,
        smooth: true, symbol: 'none',
        lineStyle: {{ width: 2, color: '#1d9bf0' }},
        areaStyle: {{
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            {{ offset: 0, color: 'rgba(29,155,240,0.10)' }},
            {{ offset: 1, color: 'rgba(29,155,240,0.00)' }}
          ])
        }},
        markLine: {{
          silent: true, symbol: 'none',
          lineStyle: {{ color: '#71767b', type: 'dotted', width: 1.5 }},
          data: [{{ xAxis: actualDates[N_ACTUAL - 1] }}],
          label: {{ show: true, position: 'start', color: '#71767b', fontSize: 10,
            formatter: '← 历史 | 预测 →', distance: 6 }}
        }}
      }},
      // --- Projected line ---
      {{
        name: '预测路径', type: 'line', data: projLine,
        smooth: true, symbol: 'emptyCircle', symbolSize: 7,
        lineStyle: {{ width: 2.5, color: projColor, type: 'dashed' }},
        itemStyle: {{ color: projColor, borderWidth: 2.5 }},
      }}
    ]
  }});
  window.addEventListener('resize', () => chart.resize());
}})();
</script>

</body>
</html>
"""

# ---------------------------------------------------------------------------
# 6. Save
# ---------------------------------------------------------------------------
with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
    f.write(html)

print(f"\n✅ HTML saved to: {OUTPUT_HTML}")
print(f"   Open with: open {OUTPUT_HTML}")
