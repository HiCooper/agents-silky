#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
quote.py —— 新浪行情通用报价器（A50 / 美股夜盘 / 任意标的）

为什么需要它：`market_panel.sh` 是**固定面板**（不含 A50，也不支持任意美股代码），
而看隔夜/夜盘时经常要临时抓「A50 + 美股延长时段价 + 指定美股个股」。
本脚本把这些封装成命令，避免每次现写脚本。**纯标准库，无需 venv，系统 python3 即可。**

用法：
    quote.py                      # 默认 = night：A50 + 美股期货 + 商品 + 汇率 + 美股指
    quote.py night                # 同上
    quote.py us AVGO NVDA MU      # 任意美股：收盘 + 盘中/延长时段价
    quote.py us --basket optical  # 预设篮子：semi / optical / memory / software / mega
    quote.py cn 512480 588000     # A股 ETF/指数（自动补 sh/sz 前缀）
    quote.py hk 00981 00700       # 港股
    quote.py raw hf_CL gb_mu      # 逃生口：直接给新浪符号，打印原始字段
    quote.py --json night         # JSON 输出，便于下游处理

字段序（2026-09-15 实测；新浪改版时先跑 `raw` 核对）：
    gb_*  : [0]名称 [1]现价 [2]涨跌幅% [3]时间 [4]涨跌额 [5]今开 [6]高 [7]低
            [8]52周高 [9]52周低 [10]量 [12]市值 [13]PE
            [21]延长时段价 [22]延长时段涨跌幅% [23]延长时段涨跌额 [24]延长时段时刻
            [25]收盘时刻 [26]昨收       ← 指数与个股同为 26，指数的 [21..24] 为空/0
    hf_*  : [0]现价 [2]买 [3]卖 [4]高 [5]低 [6]时间 [7]昨结 [8]今开 [12]日期 [13]名称
    DINIW / USDCNY : [0]时间 [1]/[8]现价 [6]高 [7]低（**不给涨跌幅**，昨收语义未验证）
    sh/sz : [0]名称 [1]今开 [2]昨收 [3]现价 [4]高 [5]低 [8]量 [9]额 [30]日期 [31]时间
    rt_hk : [1]名称 [2]昨收 [3]今开 [4]高 [5]低 [6]现价 [7]涨跌额 [8]涨跌幅% [11]成交额 [17]时间

`cn` 的**指数**代码走白名单（000688→sh000688 科创50、000001→sh000001 上证指数…），
因为 000xxx 在沪深两市撞车（sz000688 是国城矿业、sz000001 是平安银行）；其余按 5/6/9→sh、0/1/2/3→sz。
"""
import json
import sys
import urllib.request
from datetime import datetime

UA = {"User-Agent": "Mozilla/5.0", "Referer": "https://finance.sina.com.cn"}
BASE = "https://hq.sinajs.cn/list="

BASKETS = {
    "semi": ["AVGO", "NVDA", "TSM", "AMD", "ASML", "INTC", "MU", "LRCX", "AMAT", "KLAC", "ARM", "SMCI"],
    "optical": ["COHR", "GLW", "LITE", "CIEN", "AAOI", "MRVL", "ANET", "NOK"],  # 光通信/网络
    "memory": ["MU", "WDC", "SNDK", "STX"],
    "software": ["MSFT", "GOOGL", "META", "AMZN", "NOW", "ADBE", "CRM", "SNOW", "PLTR", "ORCL"],
    "mega": ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA"],
}

NIGHT = ["gb_dji", "gb_ixic", "gb_inx", "gb_$sox",
         "hf_CHA50CFD", "hf_ES", "hf_NQ",
         "hf_CL", "hf_GC", "hf_SI",
         "DINIW", "USDCNY"]

NIGHT_LABEL = {"gb_dji": "道指", "gb_ixic": "纳指", "gb_inx": "标普500", "gb_$sox": "费半SOX",
               "hf_CHA50CFD": "富时中国A50", "hf_ES": "标普期货", "hf_NQ": "纳指期货",
               "hf_CL": "WTI原油", "hf_GC": "COMEX黄金", "hf_SI": "COMEX白银",
               "DINIW": "美元指数", "USDCNY": "美元人民币"}


# ---------- 取数 ----------
def fetch(symbols):
    """一次请求拿多标的，返回 {symbol: [字段,...]}（GBK 解码）"""
    url = BASE + ",".join(symbols)
    raw = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=20).read().decode("gbk", "ignore")
    out = {}
    for line in raw.strip().split("\n"):
        if "hq_str_" not in line or "=" not in line:
            continue
        sym = line.split("hq_str_")[-1].split("=")[0]
        body = line.split('"')[1] if '"' in line else ""
        out[sym] = body.split(",") if body else []
    return out


def f(arr, i, default=""):
    return arr[i] if len(arr) > i else default


def num(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


# ---------- 符号规范化 ----------
# ⚠️ 指数代码在沪深两市会撞车：000001（sh=上证指数 / sz=平安银行）、000688（sh=科创50 / sz=国城矿业）。
#    所以指数**不猜**，走白名单；不在表里的 000xxx 一律当深市个股。
INDEX_MAP = {
    "000001": "sh000001", "000016": "sh000016", "000010": "sh000010", "000300": "sh000300",
    "000688": "sh000688", "000852": "sh000852", "000905": "sh000905",
    "399001": "sz399001", "399005": "sz399005", "399006": "sz399006",
    "399300": "sz399300", "399852": "sz399852", "399905": "sz399905",
}


def norm_cn(code):
    code = code.strip()
    if code[:2] in ("sh", "sz"):
        return code
    if code in INDEX_MAP:
        return INDEX_MAP[code]
    if code.startswith(("6", "5", "9")):
        return "sh" + code
    return "sz" + code


def norm_hk(code):
    code = code.strip()
    return code if code.startswith("rt_hk") else "rt_hk" + code.zfill(5)


def norm_us(code):
    code = code.strip()
    return code if code.startswith("gb_") else "gb_" + code.lower().replace(".", "$")


# ---------- 输出对齐（中日韩字符按 2 列计） ----------
def width(s):
    return sum(2 if ord(c) > 0x2E80 else 1 for c in s)


def pad(s, n):
    return s + " " * max(0, n - width(s))


def table(rows, header):
    if not rows:
        return ""
    cols = len(header)
    w = [max(width(str(r[i])) for r in [header] + rows) for i in range(cols)]
    line = lambda r: "  ".join(pad(str(r[i]), w[i]) for i in range(cols)).rstrip()
    out = [line(header), "  ".join("-" * x for x in w)]
    out += [line(r) for r in rows]
    return "\n".join(out)


def pct_str(cur, base):
    c, b = num(cur), num(base)
    if c is None or b in (None, 0):
        return "—"
    return f"{(c / b - 1) * 100:+.2f}%"


# ---------- 各市场的行构造 ----------
def row_us(sym, arr, label=None):
    if not arr:
        return None
    name = label or f(arr, 0)
    cur, chg, t = f(arr, 1), f(arr, 2), f(arr, 3)
    hi, lo, prev = f(arr, 6), f(arr, 7), f(arr, 26)
    ext, extchg, extt = f(arr, 21), f(arr, 22), f(arr, 24)
    ext_ok = num(ext, 0) not in (None, 0)          # 指数无延长时段，值为 0
    return {
        "symbol": sym, "name": name, "curr": num(cur), "chg_pct": num(chg), "time": t,
        "prev_close": num(prev), "high": num(hi), "low": num(lo),
        "ext_price": num(ext) if ext_ok else None,
        "ext_chg_pct": num(extchg) if ext_ok else None,
        "ext_time": extt if ext_ok else "",
        "basket": None,
    }


def row_hf(sym, arr, label=None):
    if len(arr) < 8:
        return None
    cur, hi, lo, t, prev = f(arr, 0), f(arr, 4), f(arr, 5), f(arr, 6), f(arr, 7)
    return {"symbol": sym, "name": label or f(arr, 13, sym), "curr": num(cur),
            "chg_pct": num(pct_str(cur, prev).rstrip("%")) if num(prev) else None,
            "time": t, "prev_close": num(prev), "high": num(hi), "low": num(lo)}


def row_fx(sym, arr, label=None):
    """DINIW / USDCNY：[0]时间　[1]/[8]现价　[6]高　[7]低

    ⚠️ **不输出涨跌幅**：该接口的「昨收」字段语义未经验证——USDCNY 用 [5] 反推会得到 +0.22%，
    而媒体口径是「在岸人民币较上周五夜盘收盘**跌 6 点**」（约 +0.01%）。宁可不给，也不给错。
    另注意 USDCNY 在境内闭市后不再更新（早盘 08:48 仍显示 02:52 的时点），盘前要看 09:15 中间价或离岸价。
    """
    if len(arr) < 9:
        return None
    return {"symbol": sym, "name": label or f(arr, 9, sym), "curr": num(f(arr, 8)),
            "time": f(arr, 0), "high": num(f(arr, 6)), "low": num(f(arr, 7)),
            "open_ref": num(f(arr, 1))}


def row_cn(sym, arr):
    if len(arr) < 10:
        return None
    cur, prev = f(arr, 3), f(arr, 2)
    return {"symbol": sym, "name": f(arr, 0), "curr": num(cur),
            "chg_pct": num(pct_str(cur, prev).rstrip("%")), "time": f(arr, 31),
            "prev_close": num(prev), "high": num(f(arr, 4)), "low": num(f(arr, 5)),
            "amount_yi": round(num(f(arr, 9), 0) / 1e8, 2)}


def row_hk(sym, arr):
    """rt_hk：[1]名称 [2]昨收 [3]今开 [4]高 [5]低 [6]现价 [7]涨跌额 [8]涨跌幅% [11]成交额 [17]时间"""
    if len(arr) < 9:
        return None
    return {"symbol": sym, "name": f(arr, 1), "curr": num(f(arr, 6)),
            "chg_pct": num(f(arr, 8)), "time": f(arr, 17) if len(arr) > 17 else "",
            "prev_close": num(f(arr, 2)), "high": num(f(arr, 4)), "low": num(f(arr, 5)),
            "amount_yi": round(num(f(arr, 11), 0) / 1e8, 2) if num(f(arr, 11)) else None}


# ---------- 渲染 ----------
def show_us(rows, title):
    out = []
    if title:
        out.append(title)
    out.append(table(
        [[r["name"], r["symbol"].replace("gb_", "").upper(),
          f'{r["curr"]:.2f}' if r["curr"] is not None else "—",
          f'{r["chg_pct"]:+.2f}%' if r["chg_pct"] is not None else "—",
          f'{r["ext_price"]:.2f}' if r["ext_price"] is not None else "—",
          f'{r["ext_chg_pct"]:+.2f}%' if r["ext_chg_pct"] is not None else "—",
          r["ext_time"] or "—",
          f'{r["prev_close"]:.2f}' if r["prev_close"] is not None else "—",
          r["time"]] for r in rows],
        ["名称", "代码", "收盘/现价", "涨跌幅", "延长时段", "延长幅", "延长时段刻", "昨收", "报价时间"]))
    return "\n".join(out)


def show_night(rows):
    out = [f"■ 夜盘/隔夜一屏　抓取时刻 {datetime.now():%Y-%m-%d %H:%M:%S}（价格时点见末列）", ""]
    idx = [r for r in rows if r["symbol"].startswith("gb_")]
    fut = [r for r in rows if r["symbol"].startswith("hf_")]
    fx = [r for r in rows if r["symbol"] in ("DINIW", "USDCNY")]
    if idx:
        out.append("【美股指数（收盘）】")
        out.append(show_us(idx, None)); out.append("")
    if fut:
        out.append("【期货 / 商品】")
        out.append(table([[r["name"], f'{r["curr"]:.2f}' if r["curr"] is not None else "—",
                           f'{r["chg_pct"]:+.2f}%' if r["chg_pct"] is not None else "—",
                           f'{r["high"]:.2f}' if r["high"] is not None else "—",
                           f'{r["low"]:.2f}' if r["low"] is not None else "—",
                           f'{r["prev_close"]:.2f}' if r["prev_close"] is not None else "—",
                           r["time"]] for r in fut],
                     ["名称", "现价", "涨跌幅", "高", "低", "昨结", "时间"]))
        out.append("")
    if fx:
        out.append("【汇率】（⚠️ 不给涨跌幅：新浪该接口「昨收」字段语义未验证；USDCNY 境内闭市后不再更新，其时间列可能滞后）")
        out.append(table([[r["name"], f'{r["curr"]:.4f}' if r["curr"] is not None else "—",
                           f'{r["high"]:.4f}' if r["high"] is not None else "—",
                           f'{r["low"]:.4f}' if r["low"] is not None else "—",
                           r["time"]] for r in fx],
                         ["名称", "现价", "高", "低", "时间"]))
    return "\n".join(out)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    flags = [a for a in argv if a.startswith("--")]
    as_json = "--json" in flags
    cmd = args[0] if args else "night"

    if cmd in ("night", "隔夜", "夜盘"):
        syms, kind = NIGHT, "night"
    elif cmd == "us":
        rest = args[1:]
        if rest and rest[0] in ("--basket",):
            rest = rest[1:]
        syms = []
        for a in rest:
            syms += BASKETS[a] if a in BASKETS else [a]
        if not syms:
            print("用法: quote.py us AVGO NVDA MU | quote.py us --basket optical\n"
                  f"可用篮子: {', '.join(BASKETS)}", file=sys.stderr)
            return 2
        syms, kind = [norm_us(s) for s in syms], "us"
    elif cmd == "cn":
        if len(args) < 2:
            print("用法: quote.py cn 512480 588000 000688", file=sys.stderr)
            return 2
        syms, kind = [norm_cn(s) for s in args[1:]], "cn"
    elif cmd == "hk":
        if len(args) < 2:
            print("用法: quote.py hk 00981 00700", file=sys.stderr)
            return 2
        syms, kind = [norm_hk(s) for s in args[1:]], "hk"
    elif cmd == "raw":
        if len(args) < 2:
            print("用法: quote.py raw hf_CL gb_mu", file=sys.stderr)
            return 2
        data = fetch(args[1:])
        for s in args[1:]:
            arr = data.get(s, [])
            print(f"--- {s} ({len(arr)} 字段) ---")
            for i, v in enumerate(arr):
                print(f"  [{i:>2}] {v}")
        return 0
    else:
        print(__doc__.split("用法：")[1].split("字段序")[0].strip(), file=sys.stderr)
        print(f"\n未知子命令: {cmd}", file=sys.stderr)
        return 2

    data = fetch(syms)
    rows = []
    for s in syms:
        arr = data.get(s, [])
        if not arr:
            print(f"⚠️ 无数据: {s}", file=sys.stderr)
            continue
        if kind == "night":
            r = (row_us(s, arr, NIGHT_LABEL.get(s)) if s.startswith("gb_")
                 else row_fx(s, arr, NIGHT_LABEL.get(s)) if s in ("DINIW", "USDCNY")
                 else row_hf(s, arr, NIGHT_LABEL.get(s)))
        elif kind == "us":
            r = row_us(s, arr)
        elif kind == "cn":
            r = row_cn(s, arr)
        else:
            r = row_hk(s, arr)
        if r:
            rows.append(r)

    if as_json:
        print(json.dumps(rows, ensure_ascii=False, indent=2, default=str))
    elif kind == "night":
        print(show_night(rows))
    elif kind == "us":
        print(show_us(rows, f"■ 美股　抓取时刻 {datetime.now():%Y-%m-%d %H:%M:%S}（「延长时段」= 盘前/盘后，时刻见该列）"))
    else:
        label = {"cn": "A股", "hk": "港股"}[kind]
        print(f"■ {label}　抓取时刻 {datetime.now():%Y-%m-%d %H:%M:%S}")
        print(table([[r["name"], r["symbol"].replace("rt_hk", "").replace("sh", "").replace("sz", ""),
                      f'{r["curr"]:.3f}' if r["curr"] is not None else "—",
                      f'{r["chg_pct"]:+.2f}%' if r["chg_pct"] is not None else "—",
                      f'{r["high"]:.3f}' if r["high"] is not None else "—",
                      f'{r["low"]:.3f}' if r["low"] is not None else "—",
                      f'{r["prev_close"]:.3f}' if r["prev_close"] is not None else "—",
                      f'{r["amount_yi"]:.2f}亿' if r.get("amount_yi") is not None else "—",
                      r["time"]] for r in rows],
                    ["名称", "代码", "现价", "涨跌幅", "高", "低", "昨收", "成交额", "时间"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
