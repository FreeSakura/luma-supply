#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
sh scripts/start_miniapp.sh "$@"
result=$?
printf '\n按回车关闭此窗口……'
read -r answer
exit "$result"
