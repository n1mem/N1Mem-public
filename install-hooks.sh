#!/bin/sh
# install-hooks.sh — 安装 N1Mem-public 的 git hooks（新 clone 后运行一次）
#
# 作用：把版本化的 scripts/pre-commit 复制到 .git/hooks/pre-commit，
#       使「文档治理闸门」在每次 git commit 前自动生效，防止再次误公开内部文档。
#
# 用法（在仓库根目录执行其一）：
#   bash install-hooks.sh
#   sh  install-hooks.sh
#
# 退出码：0=安装成功，非 0=失败。
set -e

ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
if [ -z "$ROOT" ]; then
  echo "错误：请在 N1Mem-public git 仓库内运行此脚本。" >&2
  exit 1
fi

SRC="$ROOT/scripts/pre-commit"
DEST="$ROOT/.git/hooks/pre-commit"

if [ ! -f "$SRC" ]; then
  echo "错误：未找到版本化钩子源 $SRC" >&2
  exit 1
fi

# 若已存在旧钩子，先备份（避免覆盖用户自定义内容）
if [ -f "$DEST" ] && [ ! -f "$DEST.bak" ]; then
  cp "$DEST" "$DEST.bak"
  echo "[install-hooks] 已备份旧钩子 -> $DEST.bak"
fi

cp "$SRC" "$DEST"
# Windows Git Bash 下 chmod 可能无效果，但无害；类 Unix 下确保可执行
chmod +x "$DEST" 2>/dev/null || true

echo "[install-hooks] ✔ 已安装 pre-commit 钩子 -> $DEST"

# 自检：在干净暂存区下运行钩子，应放行（exit 0）
if sh "$DEST" >/dev/null 2>&1; then
  echo "[install-hooks] ✔ 钩子自检通过（干净树放行）。"
else
  echo "[install-hooks] ⚠ 钩子自检出错，请检查 scripts/doc_gate.py 与 python 可用性。"
  exit 1
fi

echo "[install-hooks] 完成。今后 commit 会自动跑文档治理闸门。"
exit 0
