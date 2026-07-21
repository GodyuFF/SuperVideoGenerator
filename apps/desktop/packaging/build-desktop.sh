#!/usr/bin/env bash
# Build unsigned SuperVideoGenerator desktop installer (platform-specific targets).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
DESKTOP_DIR="$REPO_ROOT/apps/desktop"
RUNTIME_PYTHON="$DESKTOP_DIR/runtime/python/bin/python3"
PREPARE_SCRIPT="$SCRIPT_DIR/prepare-runtime.sh"

SKIP_PREPARE=0
PACK_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --skip-prepare) SKIP_PREPARE=1 ;;
    --pack-only) PACK_ONLY=1 ;;
  esac
done

export CSC_IDENTITY_AUTO_DISCOVERY=false
export ELECTRON_MIRROR="${ELECTRON_MIRROR:-https://npmmirror.com/mirrors/electron/}"
export ELECTRON_BUILDER_BINARIES_MIRROR="${ELECTRON_BUILDER_BINARIES_MIRROR:-https://npmmirror.com/mirrors/electron-builder-binaries/}"

if [[ "$SKIP_PREPARE" -eq 0 ]]; then
  if [[ -x "$RUNTIME_PYTHON" ]]; then
    echo "==> Reusing existing runtime; refreshing web + source copy"
    bash "$PREPARE_SCRIPT" --skip-pip
  else
    echo "==> No runtime found; running full prepare-runtime"
    bash "$PREPARE_SCRIPT"
  fi
else
  echo "==> Skipping prepare-runtime (--skip-prepare)"
fi

if [[ ! -x "$RUNTIME_PYTHON" ]]; then
  echo "Runtime missing after prepare: $RUNTIME_PYTHON" >&2
  exit 1
fi

cd "$DESKTOP_DIR"
echo "==> npm ci (apps/desktop)"
if ! npm ci; then
  echo "npm ci failed; falling back to npm install"
  npm install
fi

if [[ "$PACK_ONLY" -eq 1 ]]; then
  echo "==> electron-builder --dir (unpackaged smoke)"
  npm run pack
else
  echo "==> electron-builder installer"
  npm run dist
fi

echo ""
echo "Done. Output: $DESKTOP_DIR/dist"
