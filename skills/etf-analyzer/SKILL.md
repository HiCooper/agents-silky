---
name: etf-analyzer
description: Analyze A-share ETFs with interactive charts. Generates multi-panel HTML with K-line (daily/weekly/monthly), volume, turnover, 5-day MA overlays, and next-week trend prediction. Use when users want to analyze a specific ETF, view price/volume trends, or compare ETFs.
---

# ETF Analyzer

## Pre-flight check (run once if script fails)

```bash
cd /Users/xueancao/Projects/QoderProjects/invest-memory
# Ensure venv exists
python3 -m venv .venv 2>/dev/null
# Ensure akshare is installed
source .venv/bin/activate && pip install akshare -q -i https://pypi.org/simple/
# Ensure script exists (one-time copy from skill to project)
cp ~/.claude/skills/etf-analyzer/etf_analyzer.py scripts/etf_analyzer.py
```

## Usage

When user asks to analyze an ETF (e.g., "分析ETF 512800", "看一下159852走势"):

```bash
cd /Users/xueancao/Projects/QoderProjects/invest-memory
source .venv/bin/activate && python3 scripts/etf_analyzer.py <ETF_CODE> && open etf_<ETF_CODE>_chart.html
```

### Style consistency guarantee

The HTML output is entirely self-contained — inline CSS + ECharts@5.5.0 CDN + generated data. No external stylesheets, no config files. The Python script IS the template. As long as `scripts/etf_analyzer.py` is not modified between runs, every generated HTML will have identical styling regardless of which ETF is analyzed.

If the script is ever lost or modified, re-copy it from the skill directory:
```bash
cp ~/.claude/skills/etf-analyzer/etf_analyzer.py scripts/etf_analyzer.py
```

## Output

- HTML file: `etf_<CODE>_chart.html` in project root
- Opens automatically in browser
- Console prints: ETF name, date range, total return, price range, avg volume/turnover, prediction result

## What to tell the user

After running, summarize:
1. ETF name and date range
2. Total return over the period
3. Price range
4. Avg daily volume & turnover
5. Prediction: trend label, confidence, projected prices
6. Brief interpretation comparing to any previously analyzed ETFs if applicable

## Data sources

- Daily OHLCV: Tencent API (`web.ifzq.gtimg.cn`)
- NAV data: Eastmoney via akshare (`fund_open_fund_info_em`)
- Exchange auto-detection: tries both SH and SZ

## Limitations

- NAV fetch may fail behind certain proxies (gracefully skipped)
- Prediction uses pure technical factors (no fundamental/policy info)
- Low confidence predictions (<20%) should be noted as unreliable
- Weekly/monthly K-lines are derived from daily data via pandas resample
