#!/usr/bin/env bash
# 准备桌面 Electron 嵌入式运行时（macOS/Linux CI）。
# 嵌入式 Python 来源同 prepare-runtime.ps1 头部注释。

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUT_DIR="${OUT_DIR:-$REPO_ROOT/apps/desktop/runtime}"
SKIP_TORCH=0
SKIP_PIP=0
SKIP_WEB_BUILD=0
FORCE_PYTHON_REFRESH=0

usage() {
  cat <<'EOF'
用法: prepare-runtime.sh [--repo-root PATH] [--out-dir PATH] [--skip-torch] [--skip-pip] [--skip-web-build] [--force-python-refresh]
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-root) REPO_ROOT="$2"; shift 2 ;;
    --out-dir) OUT_DIR="$2"; shift 2 ;;
    --skip-torch) SKIP_TORCH=1; shift ;;
    --skip-pip) SKIP_PIP=1; shift ;;
    --skip-web-build) SKIP_WEB_BUILD=1; shift ;;
    --force-python-refresh) FORCE_PYTHON_REFRESH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1" >&2; usage; exit 1 ;;
  esac
done

step() { printf '\n==> %s\n' "$1"; }

detect_arch() {
  local uname_s uname_m
  uname_s="$(uname -s)"
  uname_m="$(uname -m)"
  case "$uname_s" in
    Darwin)
      if [[ "$uname_m" == "arm64" ]]; then
        echo "aarch64-apple-darwin"
      else
        echo "x86_64-apple-darwin"
      fi
      ;;
    Linux)
      if [[ "$uname_m" == "aarch64" ]]; then
        echo "aarch64-unknown-linux-gnu"
      else
        echo "x86_64-unknown-linux-gnu"
      fi
      ;;
    *)
      echo "不支持的平台: $uname_s" >&2
      exit 1
      ;;
  esac
}

python_exe() {
  local python_dir="$1"
  if [[ -x "$python_dir/bin/python3" ]]; then
    echo "$python_dir/bin/python3"
  elif [[ -x "$python_dir/python.exe" ]]; then
    echo "$python_dir/python.exe"
  else
    echo "解压后未找到 Python: $python_dir" >&2
    exit 1
  fi
}

mirror_copy() {
  local src="$1"
  local dst="$2"
  mkdir -p "$dst"
  rsync -a --delete \
    --exclude node_modules \
    --exclude dist \
    --exclude __pycache__ \
    --exclude .pytest_cache \
    --exclude runtime \
    "$src/" "$dst/"
}

VERSION_FILE="$SCRIPT_DIR/python-version.txt"
REQ_DESKTOP="$REPO_ROOT/requirements-desktop.txt"
API_BOOT_SRC="$SCRIPT_DIR/api_boot.py"
PYTHON_OUT="$OUT_DIR/python"
WEB_OUT="$OUT_DIR/web"
SRC_OUT="$OUT_DIR/src"

step "仓库根: $REPO_ROOT"
step "输出目录: $OUT_DIR"

[[ -f "$VERSION_FILE" ]] || { echo "缺少 $VERSION_FILE" >&2; exit 1; }
[[ -f "$REQ_DESKTOP" ]] || { echo "缺少 $REQ_DESKTOP" >&2; exit 1; }

python_tag="$(tr -d '[:space:]' < "$VERSION_FILE")"
if [[ ! "$python_tag" =~ ^cpython-[0-9.]+[+]([0-9]+)$ ]]; then
  echo "python-version.txt 格式无效: $python_tag" >&2
  exit 1
fi
release_tag="${BASH_REMATCH[1]}"
arch="$(detect_arch)"
asset_name="${python_tag}-${arch}-install_only.tar.gz"
download_url="https://github.com/astral-sh/python-build-standalone/releases/download/${release_tag}/${asset_name}"

py=""
if [[ "$FORCE_PYTHON_REFRESH" -eq 0 ]] && [[ -d "$PYTHON_OUT" ]]; then
  candidate_py="$(python_exe "$PYTHON_OUT" 2>/dev/null || true)"
  if [[ -n "$candidate_py" && -x "$candidate_py" ]]; then
    py="$candidate_py"
    step "复用已有嵌入式 Python: $py"
  fi
fi

if [[ -z "$py" ]]; then
  step "下载嵌入式 Python: $asset_name"
  mkdir -p "$PYTHON_OUT"
  tar_path="${TMPDIR:-/tmp}/$asset_name"
  if [[ ! -f "$tar_path" ]]; then
    curl -fsSL "$download_url" -o "$tar_path"
  fi

  step "解压到 $PYTHON_OUT"
  rm -rf "${PYTHON_OUT:?}/"*
  tar -xzf "$tar_path" -C "$PYTHON_OUT"

  nested_python="$PYTHON_OUT/python"
  if [[ -d "$nested_python" ]]; then
    shopt -s dotglob
    mv "$nested_python"/* "$PYTHON_OUT/"
    shopt -u dotglob
    rmdir "$nested_python"
  fi

  py="$(python_exe "$PYTHON_OUT")"

  step "ensurepip + 升级 pip"
  "$py" -m ensurepip --upgrade
  "$py" -m pip install --upgrade pip wheel setuptools
fi

if [[ "$SKIP_PIP" -eq 0 ]]; then
  step "pip install -r requirements-desktop.txt"
  "$py" -m pip install -r "$REQ_DESKTOP"

  if [[ "$SKIP_TORCH" -eq 0 ]]; then
    step "验证 torch / whisperx（macOS 使用 PyPI 默认索引）"
    if ! "$py" -c "import torch; import whisperx; print('torch', torch.__version__)"; then
      echo "torch/whisperx 导入失败，请检查 pip 日志" >&2
      exit 1
    fi
  else
    echo "SkipTorch: 跳过 torch/whisperx 验证"
  fi
else
  echo "SkipPip: 跳过 pip install"
fi

if [[ "$SKIP_WEB_BUILD" -eq 0 ]]; then
  step "构建前端 apps/web"
  (cd "$REPO_ROOT/apps/web" && npm ci && npm run build)
else
  echo "SkipWebBuild: 跳过 npm build"
fi

web_dist="$REPO_ROOT/apps/web/dist"
[[ -f "$web_dist/index.html" ]] || { echo "前端产物不存在: $web_dist/index.html" >&2; exit 1; }

step "拷贝 web/dist -> runtime/web"
rm -rf "$WEB_OUT"
cp -a "$web_dist" "$WEB_OUT"

step "拷贝 core/ 与 apps/ -> runtime/src/"
rm -rf "$SRC_OUT"
mkdir -p "$SRC_OUT"
mirror_copy "$REPO_ROOT/core" "$SRC_OUT/core"
mirror_copy "$REPO_ROOT/apps" "$SRC_OUT/apps"

step "拷贝 api_boot.py 并写入 requirements.lock"
cp "$API_BOOT_SRC" "$OUT_DIR/api_boot.py"
"$py" -m pip freeze > "$OUT_DIR/requirements.lock"

step "完成"
echo "  Python: $py"
echo "  Web:    $WEB_OUT/index.html"
echo "  Boot:   $OUT_DIR/api_boot.py"
