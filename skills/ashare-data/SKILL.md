---
name: ashare-data
version: 1.4.0
description: Fetch A-share index quotes (上证指数/深证成指/创业板指/科创50/沪深300等), ETF quotes (半导体/芯片/科技/科创50等), China/US/Japan/Germany/UK treasury yields (global bond via Sina), A50 index futures, margin trading / 融资融券 (两融余额、融资买入额、个股融资余额排行), and US index/stock daily quotes (标普/道指/纳指/费城半导体SOX、AVGO/NVDA/TSM等美股) via akshare. Use when the user asks for 指数点位、指数涨跌、A股行情、ETF行情、半导体ETF、国债收益率(10年美债/中债/日债/德债/英债)、两融余额/融资融券、美股行情/美股指数/费半/隔夜美股收盘，或需要这些标的的实时/最新行情数据.
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
$SKILLS/ashare-data/fetch gbond               # 全球国债收益率 EOD（默认美/中/日/德/英 10Y）
$SKILLS/ashare-data/fetch gbond 日本 德国       # 按国别（默认 10 年）
$SKILLS/ashare-data/fetch gbond JP2YT DE2YT   # 直接给符号：<国别><期限>YT|MT
$SKILLS/ashare-data/fetch a50                 # A50 期指（富时中国A50，全期限 + 持仓量，★ 标主力）
$SKILLS/ashare-data/fetch margin              # 融资融券因子：沪深北余额 + 1/5/20日变动 + 维持担保比例
$SKILLS/ashare-data/fetch margin hist 30      # 近 30 日两融合计序列
$SKILLS/ashare-data/fetch margin top 20260914 15   # 个股融资余额排行（拥挤度）
$SKILLS/ashare-data/fetch margin ratio 沪市 中芯    # 标的证券融资/融券比例（保证金参数）
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
| **A50 期指**（富时中国A50） | `fetch a50` | 东财外盘期货源；主力 `CN26U`（A50期指2609），含全期限与持仓量 |
| **全球国债收益率** | `fetch gbond` | 新浪全球国债源（**akshare 未封装日/德**）；国别 `US/CN/JP/DE/GB/FR/IT/CA/AU`，期限 `1M~30Y` |
| **融资融券（两融）** | `fetch margin` | 子命令：汇总 / hist / top / ratio；数据为交易所 T+1 口径（EOD） |
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
3. **债收益率是 EOD**：`bond` / `gbond` 输出的是上一个交易日的收盘收益率（滞后一天）。盘中想拿「现在 10 年美债 4.768%」这类实时值，仍以用户提供的实时报价或 WebSearch 为准。
4. **两融数据有三个单位陷阱**（`margin` 已统一折算为**亿元**）：`macro_china_market_margin_sh/sz` 是**元**、`stock_margin_bse` 是**万元**、`stock_margin_account_info` 是**亿元**。且两融是 **T+1 EOD**（当日收盘后由交易所公布，当天盘中拿不到当天值）。
5. **`stock_margin_ratio_pa` 不是情绪因子**：它给的是**标的证券的融资/融券保证金比例**（能不能两融、杠杆档位），**不代表资金流入**；判断杠杆资金进出要看 `margin` 的**余额与买入额**。
6. **日/德国债 akshare 没封装，走的是新浪端点**：akshare 只有中/美（`bond_zh_us_rate`）和**美国各期限**（`bond_gb_us_sina`，symbol_map 仅列美国）。日本/德国/英国等的底层是同一处新浪全球国债端点 `bond.finance.sina.com.cn/hq/gb/daily?symbol=JP10YT`，实测 `US/CN/JP/DE/GB/FR/IT` 各国各期限全通（约 1000 条日线），**`fetch gbond` 已封装**。所以「日债/德债能不能拿」的答案是**能，但别去 akshare 找**。
4. **`bond` 的美债列时通时不通**（实测 2026-09-15：08:45 三列全 `nan`，08:55 又正常返回 10 年 **4.97%** / 2 年 4.65% / 30 年 5.34%）。中债部分一直正常。**所以：美债优先用 `bond`，但必须核对是否为 `nan`**——是 nan 就转 WebSearch 或用户给的实时报价，别把 `nan` 当成「数据缺失」写进结论。
5. **`etf` 是 ETF 全市场扫描，实测 18–20 秒**（按代码查单只同价）：盘中急用就直接给已知代码（`fetch etf 512480`），别用关键词扫描等 20 秒。
6. **`a50` 走东财外盘期货源**，与 `etf`/`bond` 同属东财系，可能被本机代理间歇拦截；被挡时兜底用 `economic-analysis-expert` 的 `scripts/quote.py`（新浪 `hf_CHA50CFD`，免 venv、单合约 CFD）。另外**远月合约常无成交**，此时最新价/涨跌幅是空值——脚本已显示为 `-`，看主力合约即可。
7. **本 skill 只给「最新/收盘报价」，不给历史日K**：要看趋势、回撤、支撑位，去 `economic-analysis-expert` 的 `references/data-sources.md` §4（走腾讯 `fqkline`；东财**指数**日K 在本机稳定失败，别用）。
8. 数据源为第三方接口，盘中可能有秒级时延，收盘后最准。
