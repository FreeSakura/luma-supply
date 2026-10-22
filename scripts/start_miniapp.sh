#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
    echo '未找到项目 Python 环境，请先按 README 完成本地安装。' >&2
    exit 1
fi
exec .venv/bin/python -m scripts.start_miniapp "$@"
