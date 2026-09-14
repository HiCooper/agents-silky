#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A股指数 / ETF / 中美债收益率 / 美股（日线） 行情获取脚本（基于 akshare）。

用法：
    fetch.py index   <代码或名称>   单个指数实时行情
    fetch.py indices              核心指数一览
    fetch.py etf     <关键词或代码> ETF 实时行情（按名称模糊搜索）
    fetch.py bond                 中美国债收益率（最新，EOD 滞后一个交易日）
    fetch.py us                  美股指数（标普/道指/纳指/费半，新浪源，日线）
    fetch.py us semis            美股半导体一篮子（日线）
    fetch.py us stock AVGO NVDA  指定美股个股（日线）

示例：
    fetch.py index 000688        # 科创50（数字代码自动补 sh/sz 前缀）
    fetch.py index 科创50
    fetch.py etf 半导体
    fetch.py etf 512480
    fetch.py bond
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


# ---------------- 格式化工具 ----------------

def _f(v, nd=3):
    try:
        return round(float(v), nd)
    except (TypeError, ValueError):
        return v


def _pct(v):
    try:
        return f"{float(v):+.2f}%"
    except (TypeError, ValueError):
        return str(v)


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

def cmd_bond(_args):
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
        "us": cmd_us,
    }
    fn = table.get(cmd)
    if fn is None:
        print(f"未知命令：{cmd}\n{__doc__}")
        sys.exit(2)
    fn(args)


if __name__ == "__main__":
    main()
