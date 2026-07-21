#!/usr/bin/env bash
# 从 apps/desktop/icon.png 生成 macOS .icns（sips + iconutil）。
# 非 macOS 或缺少工具时跳过，electron-builder 将回退使用 icon.png。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
ICON_PNG="$REPO_ROOT/apps/desktop/icon.png"
BUILD_DIR="$REPO_ROOT/apps/desktop/build"
ICONSET_DIR="$BUILD_DIR/icon.iconset"
ICNS_OUT="$BUILD_DIR/icon.icns"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "export-icns: 非 macOS，跳过（electron-builder 将使用 icon.png）"
  exit 0
fi

if [[ ! -f "$ICON_PNG" ]]; then
  echo "缺少图标源文件: $ICON_PNG" >&2
  exit 1
fi

if ! command -v sips >/dev/null 2>&1 || ! command -v iconutil >/dev/null 2>&1; then
  echo "export-icns: sips/iconutil 不可用，跳过" >&2
  exit 0
fi

mkdir -p "$ICONSET_DIR"

for size in 16 32 128 256 512; do
  sips -z "$size" "$size" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}.png" >/dev/null
  double=$((size * 2))
  sips -z "$double" "$double" "$ICON_PNG" --out "$ICONSET_DIR/icon_${size}x${size}@2x.png" >/dev/null
done

iconutil -c icns "$ICONSET_DIR" -o "$ICNS_OUT"
rm -rf "$ICONSET_DIR"

echo "export-icns: 已生成 $ICNS_OUT"
