#!/usr/bin/env bash
# 在缺 .venv 的机器上重建依赖环境（akshare）。.venv 不入库，换机器跑一次即可。
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 -m venv "$DIR/.venv"
"$DIR/.venv/bin/pip" install -U pip
"$DIR/.venv/bin/pip" install akshare
echo "OK: $DIR/.venv 就绪"
