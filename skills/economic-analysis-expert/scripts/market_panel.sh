#!/usr/bin/env bash
# 跨市场实时行情面板（数据源：新浪 hq.sinajs.cn）
#
# 用法:
#   market_panel.sh all        # 全部（默认）
#   market_panel.sh ashare     # A股指数 / ETF
#   market_panel.sh us         # 美股指数 + 半导体个股 + 费半
#   market_panel.sh hk         # 港股
#   market_panel.sh asia       # 韩国 KOSPI / KOSDAQ
#   market_panel.sh futures    # 美股期货 ES / NQ
#   market_panel.sh commodity  # 油 / 金 / 银
#   market_panel.sh fx         # 美元指数 / 人民币
#
# 说明:
#   - 新浪返回 GBK，这里用 iconv 转 UTF-8，避免乱码。
#   - 美股实时 akshare 拉不到（代理挡 72.push2），所以走新浪接口。
#   - 拿不到的：10Y 美债实时(gb_$tnx)、日经、韩国个股 —— 用 WebSearch。
set -uo pipefail

REF="https://finance.sina.com.cn"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"

# 2.83 指数字段: 名称,最新价,涨跌额,涨跌幅,成交量,成交额
ASHARE="s_sh000001,s_sz399001,s_sz399006,s_sh000688,s_sh000300,sh512480,sh588000,sz159813"
# gb_ 美股: 名称,最新价,涨跌幅,时间,涨跌额,今开,高,低,52周高,52周低,...
US="gb_dji,gb_ixic,gb_inx,gb_avgo,gb_nvda,gb_tsm,gb_amd,gb_asml,gb_intc,gb_\$sox"
HK="hkHSI,hkHSTECH"
ASIA="b_KOSPI,b_KOSDAQ"
FUTURES="hf_ES,hf_NQ"
COMMODITY="hf_CL,hf_GC,hf_SI"
FX="DINIW,USDCNY"

fetch_group() {
  local syms="$1" title="$2"
  printf '\n=== %s ===\n' "$title"
  curl -s -H "Referer: $REF" -H "User-Agent: $UA" \
    "https://hq.sinajs.cn/list=$syms" \
    | iconv -f gbk -t utf-8 2>/dev/null || echo "(抓取失败)"
}

case "${1:-all}" in
  ashare)    fetch_group "$ASHARE"    "A股指数 / ETF";;
  us)        fetch_group "$US"        "美股指数 / 半导体 / 费半";;
  hk)        fetch_group "$HK"        "港股";;
  asia)      fetch_group "$ASIA"      "韩国 KOSPI / KOSDAQ";;
  futures)   fetch_group "$FUTURES"   "美股期货 ES / NQ";;
  commodity) fetch_group "$COMMODITY" "商品：油 / 金 / 银";;
  fx)        fetch_group "$FX"        "汇率：美元指数 / 人民币";;
  all)
    fetch_group "$ASHARE"    "A股指数 / ETF"
    fetch_group "$US"        "美股指数 / 半导体 / 费半"
    fetch_group "$HK"        "港股"
    fetch_group "$ASIA"      "韩国 KOSPI / KOSDAQ"
    fetch_group "$FUTURES"   "美股期货 ES / NQ"
    fetch_group "$COMMODITY" "商品：油 / 金 / 银"
    fetch_group "$FX"        "汇率：美元指数 / 人民币"
    ;;
  *) echo "未知分组：$1"; sed -n '3,16p' "$0"; exit 2;;
esac
