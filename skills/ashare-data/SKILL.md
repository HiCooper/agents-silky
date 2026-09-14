---
name: ashare-data
version: 1.2.0
description: Fetch A-share index quotes (上证指数/深证成指/创业板指/科创50/沪深300等), ETF quotes (半导体/芯片/科技/科创50等), China/US treasury yields, and US index/stock daily quotes (标普/道指/纳指/费城半导体SOX、AVGO/NVDA/TSM等美股) via akshare. Use when the user asks for 指数点位、指数涨跌、A股行情、ETF行情、半导体ETF、国债收益率(10年美债/中债)、美股行情/美股指数/费半/隔夜美股收盘，或需要这些标的的实时/最新行情数据.
name_zh: A股/美股行情数据
category: finance-data
---

# A股行情数据（akshare）

用 akshare 拉取 A 股指数、ETF、中美债收益率，以及**美股指数/个股（日线）**的最新行情。数据源为新浪/东方财富，收盘后为当日收盘价，盘中为实时价（美股见下方边界第 2 条）。

> **路径约定**：`$SKILLS` = 本机 skill 仓库根 `/Users/xueancao/Projects/QoderProjects/agents-silky/skills`（本 skill 即 `$SKILLS/ashare-data`）。脚本用 `BASH_SOURCE` 相对定位，所以仓库整体搬家不用改；换机器只需改这一处。

## 前置

- 依赖装在 skill 自带的虚拟环境里：`$SKILLS/ashare-data/.venv/`（已装 akshare 1.18.x）。
- 入口脚本：`$SKILLS/ashare-data/fetch`（可直接执行，会自动用 .venv 里的 python）。
- 新机器缺 `.venv` 时，跑一次 `$SKILLS/ashare-data/setup.sh` 重建（`.venv` 不入库）。
- 不要用系统 `python3` 直接跑 `fetch.py`（系统 Python 没装 akshare）。

## 用法

```bash
$SKILLS/ashare-data/fetch indices            # 核心指数一览（上证/深成/创业板/科创50/沪深300/上证50/中证500/中证1000）
$SKILLS/ashare-data/fetch index  000688      # 单个指数（数字自动补 sh/sz 前缀）
$SKILLS/ashare-data/fetch index  科创50       # 也支持名称关键词
$SKILLS/ashare-data/fetch etf    半导体       # 按名称关键词搜 ETF
$SKILLS/ashare-data/fetch etf    512480      # 按代码查单只 ETF
$SKILLS/ashare-data/fetch bond                # 中美债收益率（10年/2年/30年）
$SKILLS/ashare-data/fetch us                  # 美股指数（标普/道指/纳指/费半，新浪源，日线）
$SKILLS/ashare-data/fetch us semis            # 美股半导体一篮子（AVGO/NVDA/TSM/AMD/ASML/INTC）
$SKILLS/ashare-data/fetch us stock AVGO NVDA  # 指定美股个股（日线；**任意美股代码，不限半导体篮子**）
```

## 关键代码速查

| 标的 | 代码 | 备注 |
|---|---|---|
| 上证指数 | sh000001 | |
| 深证成指 | sz399001 | |
| 创业板指 | sz399006 | |
| 科创50 | sh000688 | 用户核心持仓方向 |
| 沪深300 | sh000300 | |
| 科创50ETF | 588000 | 华夏，科创50 最大权重 |
| 半导体ETF | 512480 | 国联安 |
| 芯片ETF | 159995 / 512760 | |
| 科创芯片ETF | 588200 | |
| 标普500/道指/纳指/费半 | .INX / .DJI / .IXIC / .SOX | `fetch us`，走新浪源 |
| 美股半导体 | AVGO / NVDA / TSM / AMD / ASML / INTC | `fetch us semis` |

ETF 名称里有「半导体 / 芯片 / 科创50 / 科创芯片 / 半导体设备」等关键词的，用 `fetch etf <关键词>` 一次拉全，再按成交额挑主流的那几只。

> **在 `economic-analysis-expert` 工作流中，本 skill 是 A 股指数/ETF 与美股行情的首选入口**；它不覆盖的（跨市场实时面板：港股/韩国/期货/油金/美元、美股盘前盘中价、历史日K）由那个 skill 的 `scripts/` 与 `references/data-sources.md` 补齐。

## 输出含义

- `涨跌幅` 已是百分数（如 `-2.10%`），直接读。
- ETF 的 `成交额(亿)`、`换手率` 用于判断是否放量/活跃。
- 指数 `成交额(亿)` 是全天累计成交。

## 边界与限制（重要）

1. **美股能拿，但必须走新浪源**（2026-09 更正）：`us` 子命令用 `index_us_stock_sina` / `stock_us_daily`，实测稳定（0.1–0.6s），**费半 `.SOX` 与半导体个股日线都能拉到**。此前「美股不行」的说法**已作废**——被代理挡的是**东财**那几个接口（`stock_us_spot_em` / `stock_us_hist` / `famous_spot_em`，打 `63/69/72.push2*.eastmoney.com`，时通时不通），**不要依赖东财源**。
2. **美股是日线，不是实时**：`us` 给的是截至**最近一个美股收盘**的日线。要**盘前/盘中实时价**（如「AVGO 盘前 −3%」），走新浪 `hq.sinajs.cn`（见 `economic-analysis-expert` skill 的 `scripts/market_panel.sh us`）或 WebSearch。
3. **债收益率是 EOD**：`bond` 输出的是上一个交易日的收盘收益率（滞后一天）。盘中想拿「现在 10 年美债 4.768%」这类实时值，仍以用户提供的实时报价或 WebSearch 为准。
4. **`bond` 的美债列返回 `nan`**（实测 2026-09-15：中债 10 年 1.6888% 正常，**美债 10/2/30 年全为 nan**）。中债部分可照常使用；**10Y 美债一律走 WebSearch 或用户给的实时报价**，别把 `nan` 当成「数据缺失」写进报告。
5. **`etf` 是 ETF 全市场扫描，实测 18–20 秒**（按代码查单只同价）：盘中急用就直接给已知代码（`fetch etf 512480`），别用关键词扫描等 20 秒。
6. **本 skill 只给「最新/收盘报价」，不给历史日K**：要看趋势、回撤、支撑位，去 `economic-analysis-expert` 的 `references/data-sources.md` §4（走腾讯 `fqkline`；东财**指数**日K 在本机稳定失败，别用）。
7. 数据源为第三方接口，盘中可能有秒级时延，收盘后最准。
