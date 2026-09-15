#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股指数 / ETF / 中美债收益率 / A50期指 / 美股（日线） 行情获取脚本（基于 akshare）。

用法：
    fetch.py index   <代码或名称>   单个指数实时行情
    fetch.py indices              核心指数一览
    fetch.py etf     <关键词或代码> ETF 实时行情（按名称模糊搜索）
    fetch.py bond                 中美国债收益率（最新，EOD 滞后一个交易日）
    fetch.py gbond [国别...]      全球国债收益率（美/中/日/德/英/法/意，EOD）
    fetch.py margin [子命令]      融资融券因子（汇总/历史/个股排行/标的比例）
    fetch.py a50                  A50 期指（富时中国A50，东财外盘期货源；含全期限与持仓量）
    fetch.py us                  美股指数（标普/道指/纳指/费半，新浪源，日线）
    fetch.py us semis            美股半导体一篮子（日线）
    fetch.py us stock AVGO NVDA  指定美股个股（日线）

示例：
    fetch.py index 000688        # 科创50（数字代码自动补 sh/sz 前缀）
    fetch.py index 科创50
    fetch.py etf 半导体
    fetch.py etf 512480
    fetch.py bond
    fetch.py gbond 日本 德国 JP2YT
    fetch.py margin
    fetch.py margin hist 30
    fetch.py a50                 # A50 期指（夜盘时段可用；★ 标出主力合约）
    fetch.py us
    fetch.py us semis
"""
import os
import sys

# 静默 akshare 内部 tqdm 进度条，保持 stdout 干净
os.environ.setdefault("TQDM_DISABLE", "1")

import warnings
warnings.filterwarnings("ignore")

import akshare as ak
import pandas as pd
import requests


# ---------------- 格式化工具 ----------------

def _f(v, nd=3):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def _pct(v):
    """百分比格式化；NaN / 非数值 → '-'（远月无成交合约常见 NaN）。"""
    try:
        f = float(v)
        return "-" if f != f else f"{f:+.2f}%"
    except (TypeError, ValueError):
        return "-"


def _w(s):
    """显示宽度：中日韩字符按 2 列计。"""
    return sum(2 if ord(c) > 0x2E80 else 1 for c in str(s))


def _pad(s, n):
    s = str(s)
    return s + " " * max(0, n - _w(s))


def _num(v, nd=1):
    """数值格式化：NaN / 非数值 → '-'（远月无成交的合约常见 NaN）。"""
    try:
        f = float(v)
        return "-" if f != f else round(f, nd)
    except (TypeError, ValueError):
        return "-"


def _int(v):
    try:
        f = float(v)
        return "-" if f != f else int(f)
    except (TypeError, ValueError):
        return "-"


# ---------------- A50 期指（东财外盘期货源） ----------------

def cmd_a50(_args=None):
    """A50 期指（富时中国A50，新加坡）。全期限 + 持仓量，★ 标出主力（持仓量最大）。

    数据源为东财 `futures_global_spot_em`（本机代理对东财间歇性拦截）；
    若被挡，兜底走 `economic-analysis-expert/scripts/quote.py`（新浪 hf_CHA50CFD，免 venv）。
    """
    df = ak.futures_global_spot_em()
    hit = df[df["名称"].astype(str).str.contains("A50", na=False)].copy()
    if hit.empty:
        print("未取到 A50 期指。可能原因：东财源被代理拦截——兜底用 "
              "`economic-analysis-expert/scripts/quote.py`（新浪 hf_CHA50CFD）。")
        sys.exit(1)
    main = hit.loc[hit["持仓量"].astype(float).idxmax(), "代码"]
    print(f"{'名称':<16}{'代码':<9}{'最新价':>10}{'涨跌额':>9}{'涨跌幅':>9}"
          f"{'今开':>10}{'最高':>10}{'最低':>10}{'昨结':>10}{'成交量':>9}{'持仓量':>10}")
    for _, r in hit.iterrows():
        print(f"{_pad(r['名称'], 16)}{_pad(r['代码'], 9)}{_num(r['最新价']):>10}{_num(r['涨跌额']):>9}"
              f"{_pct(r['涨跌幅']):>9}{_num(r['今开']):>10}{_num(r['最高']):>10}{_num(r['最低']):>10}"
              f"{_num(r['昨结']):>10}{_int(r['成交量']):>9}{_int(r['持仓量']):>10}"
              f"{'  ★主力' if r['代码'] == main else ''}")


# ---------------- 指数 ----------------

_INDEX_COLS = ["代码", "名称", "最新价", "涨跌幅", "涨跌额", "今开", "最高", "最低", "昨收", "成交额"]


def _load_indices():
    return ak.stock_zh_index_spot_sina()


def _resolve_index(df, query):
    """把用户输入（sina代码 / 6位数字 / 名称关键词）解析成一行。"""
    q = str(query).strip()
    # 1) 已带 sh/sz 前缀
    if q.lower().startswith(("sh", "sz")) and len(q) == 8:
        hit = df[df["代码"].str.lower() == q.lower()]
        if not hit.empty:
            return hit.iloc[0]
    # 2) 纯 6 位数字 -> 先试沪 sh，再试深 sz
    if q.isdigit() and len(q) == 6:
        for pref in ("sh", "sz"):
            hit = df[df["代码"].str.lower() == pref + q]
            if not hit.empty:
                return hit.iloc[0]
    # 3) 名称关键词
    hit = df[df["名称"].str.contains(q, na=False)]
    if not hit.empty:
        return hit.iloc[0]
    return None


def _print_index(row):
    print(f"{row['名称']}（{row['代码']}）")
    print(f"  最新价  {_f(row['最新价'])}   {_pct(row['涨跌幅'])}")
    print(f"  涨跌额  {_f(row['涨跌额'])}")
    print(f"  今开    {_f(row['今开'])}   最高 {_f(row['最高'])}   最低 {_f(row['最低'])}   昨收 {_f(row['昨收'])}")
    try:
        amt = float(row.get("成交额", 0) or 0) / 1e8
        print(f"  成交额  {amt:.1f} 亿")
    except (TypeError, ValueError):
        pass


_CORE = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000688", "科创50"),
    ("sh000300", "沪深300"),
    ("sh000016", "上证50"),
    ("sh000905", "中证500"),
    ("sh000852", "中证1000"),
]


def cmd_index(args):
    df = _load_indices()
    if not args:
        cmd_indices([])
        return
    row = _resolve_index(df, args[0])
    if row is None:
        print(f"未找到指数：{args[0]}")
        sys.exit(1)
    _print_index(row)


def cmd_indices(_args):
    df = _load_indices()
    print(f"{'名称':<8}{'代码':<10}{'最新价':>10}{'涨跌幅':>10}")
    for code, name in _CORE:
        hit = df[df["代码"].str.lower() == code]
        if hit.empty:
            continue
        r = hit.iloc[0]
        print(f"{r['名称']:<8}{r['代码']:<10}{_f(r['最新价']):>10}{_pct(r['涨跌幅']):>10}")


# ---------------- ETF ----------------

_ETF_COLS = ["代码", "名称", "最新价", "涨跌幅", "涨跌额", "成交额", "换手率", "量比", "主力净流入-净额"]


def cmd_etf(args):
    if not args:
        print("用法：fetch.py etf <关键词或代码>，如 半导体 / 芯片 / 科创50 / 512480")
        sys.exit(1)
    q = str(args[0]).strip()
    df = ak.fund_etf_spot_em()
    if q.isdigit():
        hit = df[df["代码"] == q]
    else:
        hit = df[df["名称"].str.contains(q, na=False)]
    if hit.empty:
        print(f"未找到ETF：{q}")
        sys.exit(1)
    print(f"{'代码':<8}{'名称':<20}{'最新价':>8}{'涨跌幅':>9}{'成交额(亿)':>12}{'换手率':>8}")
    for _, r in hit.head(15).iterrows():
        try:
            amt = float(r.get("成交额", 0) or 0) / 1e8
            amt_s = f"{amt:.1f}"
        except (TypeError, ValueError):
            amt_s = "-"
        print(f"{r['代码']:<8}{r['名称']:<20}{_f(r['最新价']):>8}{_pct(r['涨跌幅']):>9}{amt_s:>12}{_f(r.get('换手率'), 2):>8}")


# ---------------- 债券 ----------------

def cmd_bond(args):
    """bond          中美国债（akshare bond_zh_us_rate，EOD）
    bond global   全球国债收益率（新浪全球国债源，见 cmd_gbond）
    """
    if args and args[0] in ("global", "全球", "gbond"):
        return cmd_gbond(args[1:])
    b = ak.bond_zh_us_rate()
    last = b.iloc[-1]
    print(f"日期：{last['日期']}（EOD，滞后一个交易日）")
    print("  中国国债 10年  {:.4f}%   2年 {:.4f}%   30年 {:.4f}%".format(
        _f(last.get("中国国债收益率10年"), 4),
        _f(last.get("中国国债收益率2年"), 4),
        _f(last.get("中国国债收益率30年"), 4)))
    print("  美国国债 10年  {:.4f}%   2年 {:.4f}%   30年 {:.4f}%".format(
        _f(last.get("美国国债收益率10年"), 4),
        _f(last.get("美国国债收益率2年"), 4),
        _f(last.get("美国国债收益率30年"), 4)))


# ---------------- 全球国债收益率（新浪全球国债源） ----------------
#
# akshare 只有中/美（bond_zh_us_rate）与**美国各期限**（bond_gb_us_sina，symbol_map 仅列美国）；
# 日本/德国/英国等它**没有封装**。但底层是同一处新浪端点，实测 US/CN/JP/DE/GB/FR/IT 全通：
#   https://bond.finance.sina.com.cn/hq/gb/daily?symbol=JP10YT   （约 1000 条日线，含最新收盘）
# 所以这里直接打该端点，把日/德/英等国补齐。

_GBOND_LABEL = {"US": "美国", "CN": "中国", "JP": "日本", "DE": "德国",
                "GB": "英国", "FR": "法国", "IT": "意大利", "CA": "加拿大", "AU": "澳大利亚"}
_GBOND_DEFAULT = ["US10YT", "CN10YT", "JP10YT", "DE10YT", "GB10YT"]


def _gbond_fetch(symbol):
    r = requests.get(f"https://bond.finance.sina.com.cn/hq/gb/daily?symbol={symbol}",
                     headers={"User-Agent": "Mozilla/5.0",
                              "Referer": "https://stock.finance.sina.com.cn/"}, timeout=15)
    data = r.json()["result"]["data"]
    return [(x["d"], float(x["c"])) for x in data]


def _gbond_resolve(token):
    """'日本'/'jp' → JP10YT；'JP2YT'/'DE10YT' 之类的完整符号原样返回。"""
    t = token.strip()
    up = t.upper()
    # 完整符号：<两位国别><数字期限>YT|MT，如 US10YT / JP2YT / DE30YT
    if len(up) >= 5 and up[:2] in _GBOND_LABEL and up[-2:] in ("YT", "MT") and up[2:-2].isdigit():
        return up
    code = up if up in _GBOND_LABEL else None       # us / jp / de ...
    if code is None:
        for k, v in _GBOND_LABEL.items():            # 美国 / 日本 ...
            if v == t:
                code = k
                break
    if code is None:
        raise ValueError(f"认不出「{token}」，可用国别：{'/'.join(_GBOND_LABEL)}（默认 10 年），"
                         f"或直接给符号如 JP2YT/DE10YT")
    return code + "10YT"


def _gbond_name(sym):
    """JP10YT → 日本10Y；US2YT → 美国2Y；DE6MT → 德国6M"""
    cty, tenor, unit = _GBOND_LABEL.get(sym[:2], sym[:2]), sym[2:-2], sym[-2]
    return f"{cty}{tenor}{unit}"


def cmd_gbond(args=None):
    """全球国债收益率（新浪全球国债源，EOD，约 1000 条日线）。

    fetch.py gbond                # 默认：美/中/日/德/英 10 年
    fetch.py gbond 日本 德国       # 按国别（默认 10 年）
    fetch.py gbond JP2YT DE2YT    # 直接给符号：<国别><期限>YT|MT
    """
    tokens = list(args) if args else _GBOND_DEFAULT
    try:
        symbols = [_gbond_resolve(t) for t in tokens]
    except ValueError as e:
        print(e)
        sys.exit(1)
    print(f"{'名称':<11}{'符号':<9}{'最新日期':<13}{'收益率':>9}{'日变动':>9}{'5日变动':>10}{'样本起':>12}")
    for sym in symbols:
        try:
            rows = _gbond_fetch(sym)
            last_d, last_v = rows[-1]
            prev_v = rows[-2][1] if len(rows) >= 2 else last_v
            f5_v = rows[-6][1] if len(rows) >= 6 else rows[0][1]
            print(f"{_pad(_gbond_name(sym), 11)}{_pad(sym, 9)}{_pad(last_d, 13)}{last_v:>8.3f}%"
                  f"{(last_v - prev_v) * 100:>+8.1f}bp{(last_v - f5_v) * 100:>+9.1f}bp{rows[0][0]:>12}")
        except Exception as e:
            print(f"{_pad(_gbond_name(sym), 11)}{_pad(sym, 9)}FAILED  {type(e).__name__}")


# ---------------- 美股（新浪源） ----------------
#
# 为什么单独走新浪源：东财的美股接口（stock_us_spot_em / stock_us_hist /
# famous_spot_em）会打 63/69/72.push2*.eastmoney.com，本机代理**间歇性拦截**
# （ProxyError，时通时不通）。新浪源接口实测稳定（0.1–0.6s，连跑一致）。
# 局限：给的是**日线**（截至最近一个美股收盘），不是盘中/盘前实时价。

_US_INDEX = [
    (".INX", "标普500"),
    (".DJI", "道指"),
    (".IXIC", "纳指"),
    (".SOX", "费城半导体"),
]

_US_SEMIS = [
    ("AVGO", "博通"), ("NVDA", "英伟达"), ("TSM", "台积电"),
    ("AMD", "超威半导体"), ("ASML", "阿斯麦"), ("INTC", "英特尔"),
]


def _us_last(df):
    """取最后一行的 (日期, 收盘, 涨跌幅)，涨跌幅用最后两行算。"""
    last = df.iloc[-1]
    chg = "-"
    if len(df) >= 2:
        try:
            chg = f"{(float(last['close']) / float(df.iloc[-2]['close']) - 1) * 100:+.2f}%"
        except (TypeError, ValueError, ZeroDivisionError):
            pass
    return str(last["date"])[:10], float(last["close"]), chg


def cmd_us(args):
    """us indices | us semis | us stock <代码...>（新浪源，日线）"""
    sub = args[0] if args else "indices"
    rest = args[1:]
    if sub == "indices":
        print(f"{'指数':<10}{'代码':<8}{'日期':<12}{'收盘':>13}{'涨跌幅':>10}")
        for sym, nm in _US_INDEX:
            try:
                d, c, chg = _us_last(ak.index_us_stock_sina(symbol=sym))
                print(f"{nm:<10}{sym:<8}{d:<12}{c:>13.2f}{chg:>10}")
            except Exception as e:
                print(f"{nm:<10}{sym:<8}{'FAILED':<12}{type(e).__name__}")
    elif sub in ("semis", "stock"):
        pairs = [(s, s) for s in rest] if rest else _US_SEMIS
        print(f"{'名称':<12}{'代码':<8}{'日期':<12}{'收盘':>12}{'涨跌幅':>10}")
        for sym, nm in pairs:
            try:
                d, c, chg = _us_last(ak.stock_us_daily(symbol=sym))
                print(f"{nm:<12}{sym:<8}{d:<12}{c:>12.2f}{chg:>10}")
            except Exception as e:
                print(f"{nm:<12}{sym:<8}{'FAILED':<12}{type(e).__name__}")
    else:
        print("用法：fetch.py us [indices | semis | stock <代码...>]")
        sys.exit(1)


# ---------------- 融资融券（两融因子） ----------------
#
# 接口分工（akshare 1.18.94，2026-09-15 实测）：
#   macro_china_market_margin_sh/sz()   沪深**全历史**汇总（单位：元）
#   stock_margin_bse(date)              北交所单日（单位：万元）
#   stock_margin_account_info()         两融账户数 / 维持担保比例（单位：亿元、%）
#   stock_margin_detail_sse/szse(date)  个股明细（单位：元）
#   stock_margin_ratio_pa(symbol,date)  标的证券**融资/融券比例**（保证金参数，非余额）
#
# ⚠️ 三个单位陷阱：macro 是元、北交所是万元、account_info 是亿元——统一折算成**亿元**输出。
# ⚠️ `stock_margin_ratio_pa` 常被误当情绪因子：它给的是「这只票的融资保证金比例」，
#    用于筛选标的与杠杆档位，**不代表资金流入**；情绪因子看余额与买入额。

def _ymd(d):
    return str(d).replace("-", "")[:8]


def _margin_panel():
    """沪深两融汇总（亿元），按日期合并。"""
    sh = ak.macro_china_market_margin_sh()[["日期", "融资余额", "融券余额"]].copy()
    sz = ak.macro_china_market_margin_sz()[["日期", "融资余额", "融券余额"]].copy()
    sh.columns = ["日期", "沪融资", "沪融券"]
    sz.columns = ["日期", "深融资", "深融券"]
    m = pd.merge(sh, sz, on="日期", how="outer").sort_values("日期").reset_index(drop=True)
    for c in ("沪融资", "沪融券", "深融资", "深融券"):
        m[c] = pd.to_numeric(m[c], errors="coerce") / 1e8          # 元 → 亿元
    m["沪深融资"] = m["沪融资"] + m["深融资"]
    m["沪深合计"] = m["沪深融资"] + m["沪融券"] + m["深融券"]
    m["日期"] = m["日期"].astype(str)
    return m


def _margin_bse(date):
    """北交所两融（亿元）：接口给万元。"""
    df = ak.stock_margin_bse(date=_ymd(date))
    r = df.iloc[0]
    return float(r["融资余额"]) / 1e4, float(r["融券余额"]) / 1e4


def _delta(series, n):
    if len(series) <= n:
        return float("nan")
    return float(series.iloc[-1] - series.iloc[-1 - n])


def cmd_margin(args=None):
    """融资融券因子。

    fetch.py margin                 # 汇总：沪深北 融资/融券/两融余额 + 1/5/20 日变动 + 杠杆与参与度
    fetch.py margin hist [N]        # 近 N 日两融合计序列（默认 20）
    fetch.py margin top [日期] [N]  # 个股融资余额排行（拥挤度，默认前 15）
    fetch.py margin ratio [市场] [关键词]   # 标的证券融资/融券比例（沪市/深市/北交所）
    """
    args = list(args or [])
    sub = args[0] if args else "summary"

    # ---- 汇总 ----
    if sub in ("summary", "总量", ""):
        m = _margin_panel()
        last = m.iloc[-1]
        try:
            bse_rz, bse_rq = _margin_bse(last["日期"])
        except Exception:
            bse_rz = bse_rq = float("nan")
        rows = [("沪市", last["沪融资"], last["沪融券"]),
                ("深市", last["深融资"], last["深融券"]),
                ("北交所", bse_rz, bse_rq)]
        rz_t = sum(r for _, r, _ in rows if r == r)
        rq_t = sum(r for _, _, r in rows if r == r)
        print(f"■ 两融因子　{last['日期']}（EOD，交易所口径）")
        print(f"{'市场':<8}{'融资余额(亿)':>13}{'融券余额(亿)':>13}{'两融余额(亿)':>13}")
        for nm, rz, rq in rows:
            print(f"{nm:<8}{rz:>13.2f}{rq:>13.2f}{rz + rq:>13.2f}")
        print(f"{'合计':<8}{rz_t:>13.2f}{rq_t:>13.2f}{rz_t + rq_t:>13.2f}")
        d1, d5, d20 = _delta(m["沪深合计"], 1), _delta(m["沪深合计"], 5), _delta(m["沪深合计"], 20)
        print(f"\n沪深两融合计变动：日 {d1:+.2f} 亿｜5日 {d5:+.2f} 亿｜20日 {d20:+.2f} 亿"
              f"（20日 {(d20 / (m['沪深合计'].iloc[-21] or 1)) * 100:+.2f}%）")
        try:
            ai = ak.stock_margin_account_info()
            a_last, a_prev = ai.iloc[-1], ai.iloc[-2]
            pv = float(a_last["参与交易的投资者数量"])
            pp = float(a_prev["参与交易的投资者数量"])
            print(f"杠杆与参与度（{a_last['日期']}）：平均维持担保比例 {float(a_last['平均维持担保比例']):.1f}%"
                  f"（前值 {float(a_prev['平均维持担保比例']):.1f}%）｜"
                  f"参与交易投资者 {pv:,.0f}（{(pv / pp - 1) * 100:+.1f}%）｜"
                  f"有融资负债投资者 {float(a_last['有融资融券负债的投资者数量']):,.0f}")
            print("  读数：维持担保比例越高=杠杆越安全（<150% 需警惕）；参与投资者减少=交投降温。")
        except Exception as e:
            print(f"  账户/担保比例取数失败：{type(e).__name__}")
        print("  读数：融资余额升=杠杆资金加仓（顺周期确认）；连降 3 日以上=资金撤离，反弹缺增量。")
        return

    # ---- 历史序列 ----
    if sub in ("hist", "历史"):
        n = int(args[1]) if len(args) > 1 and args[1].isdigit() else 20
        m = _margin_panel().tail(n)
        m["日变动"] = m["沪深合计"].diff()
        print(f"{'日期':<13}{'沪(亿)':>11}{'深(亿)':>11}{'沪深合计(亿)':>15}{'日变动(亿)':>12}")
        for _, r in m.iterrows():
            d = r["日变动"]
            print(f"{r['日期']:<13}{r['沪融资'] + r['沪融券']:>11.1f}{r['深融资'] + r['深融券']:>11.1f}"
                  f"{r['沪深合计']:>15.1f}{'—' if d != d else f'{d:+.1f}':>12}")
        return

    # ---- 个股排行 ----
    if sub in ("top", "个股", "排行"):
        date = args[1] if len(args) > 1 and args[1].isdigit() else None
        n = int(args[2]) if len(args) > 2 and args[2].isdigit() else 15
        if date is None:
            date = _ymd(_margin_panel().iloc[-1]["日期"])
        frames = []
        for mk, fn in (("沪", ak.stock_margin_detail_sse), ("深", ak.stock_margin_detail_szse)):
            try:
                df = fn(date=date)[["证券代码", "证券简称", "融资余额", "融资买入额"]].copy()
                df["市场"] = mk
                frames.append(df)
            except Exception as e:
                print(f"  {mk}市明细失败：{type(e).__name__}")
        if not frames:
            print("未取到个股两融明细"); sys.exit(1)
        allm = pd.concat(frames, ignore_index=True)
        for c in ("融资余额", "融资买入额"):
            allm[c] = pd.to_numeric(allm[c], errors="coerce") / 1e8
        allm = allm.sort_values("融资余额", ascending=False).head(n)
        print(f"■ 个股融资余额排行　{date}（前 {n}，拥挤度观察）")
        print(f"{'代码':<9}{'名称':<12}{'市':<3}{'融资余额(亿)':>13}{'融资买入额(亿)':>15}")
        for _, r in allm.iterrows():
            print(f"{str(r['证券代码']):<9}{_pad(r['证券简称'], 12)}{str(r['市场']):<3}"
                  f"{r['融资余额']:>13.2f}{r['融资买入额']:>15.2f}")
        print("  读数：融资余额大且买入额占比高=拥挤（回调时被动减仓压力大）。")
        return

    # ---- 标的证券比例（用户常见的那张表） ----
    if sub in ("ratio", "比例"):
        mk = args[1] if len(args) > 1 and args[1] in ("沪市", "深市", "北交所") else "沪市"
        kw = args[2] if len(args) > 2 else None
        date = args[3] if len(args) > 3 and args[3].isdigit() else _ymd(_margin_panel().iloc[-1]["日期"])
        df = ak.stock_margin_ratio_pa(symbol=mk, date=date)
        print(f"■ {mk}标的证券融资/融券比例　{date}　共 {len(df)} 只")
        for col in ("融资比例", "融券比例"):
            vc = df[col].value_counts().sort_index()
            print(f"  {col}分布：" + "｜".join(f"{k}:{v}只" for k, v in vc.items()))
        if kw:
            hit = df[df["证券代码"].astype(str).str.contains(kw, na=False)
                     | df["证券简称"].astype(str).str.contains(kw, na=False)]
            print(hit.head(20).to_string(index=False) if len(hit) else f"  未匹配到「{kw}」")
        else:
            print("  提示：加关键词可查具体标的，如 `fetch margin ratio 沪市 中芯`")
        print("  ⚠️ 这是**保证金参数**（标的能不能两融、杠杆档位），不是资金流入——情绪因子看 `margin` 汇总。")
        return

    print(__doc__)
    sys.exit(1)


# ---------------- 入口 ----------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    args = sys.argv[2:]
    table = {
        "index": cmd_index,
        "indices": cmd_indices,
        "etf": cmd_etf,
        "bond": cmd_bond,
        "gbond": cmd_gbond,
        "margin": cmd_margin,
        "a50": cmd_a50,
        "us": cmd_us,
    }
    fn = table.get(cmd)
    if fn is None:
        print(f"未知命令：{cmd}\n{__doc__}")
        sys.exit(2)
    fn(args)


if __name__ == "__main__":
    main()
