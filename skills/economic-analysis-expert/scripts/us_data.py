#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""美股数据（akshare · 新浪源）。

为什么用新浪源：东财接口（stock_us_spot_em / stock_us_hist / famous_spot_em）会打
`63/69/72.push2*.eastmoney.com`，本机代理**间歇性拦截**（ProxyError），不可靠；
新浪源接口实测稳定（0.1–0.6s，连跑一致），且**费半 .SOX 也能拿到**。

局限：给的是**日线（截至最近一个美股收盘）**，不是盘中/盘前实时价。
要看美股**盘前/实时**，用同目录的 `market_panel.sh us`（新浪 hq.sinajs.cn）。

用法（必须用 akshare-data 的 venv 跑，系统 python 没装 akshare）：
    SKILLS=/Users/xueancao/Projects/QoderProjects/agents-silky/skills
    PY=$SKILLS/akshare-data/.venv/bin/python
    $PY $SKILLS/economic-analysis-expert/scripts/us_data.py indices   # 标普/道指/纳指/费半
    $PY $SKILLS/economic-analysis-expert/scripts/us_data.py semis     # 半导体一篮子
    $PY $SKILLS/economic-analysis-expert/scripts/us_data.py stock AVGO NVDA
    $PY $SKILLS/economic-analysis-expert/scripts/us_data.py hist AVGO 15
"""
import os
import sys

os.environ.setdefault("TQDM_DISABLE", "1")

import warnings
warnings.filterwarnings("ignore")

import akshare as ak

INDEX_MAP = {
    ".INX": "标普500",
    ".DJI": "道指",
    ".IXIC": "纳指",
    ".SOX": "费城半导体",
}

SEMIS = [
    ("AVGO", "博通"), ("NVDA", "英伟达"), ("TSM", "台积电"),
    ("AMD", "超威半导体"), ("ASML", "阿斯麦"), ("INTC", "英特尔"),
]


def _pct(prev, cur):
    try:
        return f"{(float(cur) / float(prev) - 1) * 100:+.2f}%"
    except (TypeError, ValueError, ZeroDivisionError):
        return "-"


def _row_from(df):
    """返回 (日期, 收盘, 涨跌幅) —— 用最后两行算涨跌幅。"""
    last = df.iloc[-1]
    chg = "-"
    if len(df) >= 2:
        chg = _pct(df.iloc[-2]["close"], last["close"])
    return str(last["date"])[:10], float(last["close"]), chg


def cmd_indices(_args):
    print(f"{'指数':<10}{'代码':<8}{'日期':<12}{'收盘':>13}{'涨跌幅':>10}")
    for sym, nm in INDEX_MAP.items():
        try:
            d, c, chg = _row_from(ak.index_us_stock_sina(symbol=sym))
            print(f"{nm:<10}{sym:<8}{d:<12}{c:>13.2f}{chg:>10}")
        except Exception as e:
            print(f"{nm:<10}{sym:<8}{'FAILED':<12}{type(e).__name__}")


def _print_stock(sym, nm):
    try:
        d, c, chg = _row_from(ak.stock_us_daily(symbol=sym))
        print(f"{nm:<12}{sym:<8}{d:<12}{c:>12.2f}{chg:>10}")
    except Exception as e:
        print(f"{nm:<12}{sym:<8}{'FAILED':<12}{type(e).__name__}")


def cmd_semis(args):
    pairs = [(s, s) for s in args] if args else SEMIS
    print(f"{'名称':<12}{'代码':<8}{'日期':<12}{'收盘':>12}{'涨跌幅':>10}")
    for sym, nm in pairs:
        _print_stock(sym, nm)


def cmd_stock(args):
    if not args:
        print("用法：us_data.py stock <代码...>，如 AVGO NVDA TSM")
        sys.exit(1)
    cmd_semis(args)


def cmd_hist(args):
    if not args:
        print("用法：us_data.py hist <代码> [条数]，如 AVGO 15")
        sys.exit(1)
    sym = args[0]
    n = int(args[1]) if len(args) > 1 else 10
    df = ak.stock_us_daily(symbol=sym).tail(n).copy()
    df["date"] = df["date"].astype(str).str[:10]
    df["涨跌幅"] = (df["close"].pct_change() * 100).round(2)
    print(df.to_string(index=False))


def main():
    table = {
        "indices": cmd_indices,
        "semis": cmd_semis,
        "stock": cmd_stock,
        "hist": cmd_hist,
    }
    if len(sys.argv) < 2 or sys.argv[1] not in table:
        print(__doc__)
        sys.exit(0)
    table[sys.argv[1]](sys.argv[2:])


if __name__ == "__main__":
    main()
