#!/usr/bin/env bash
# 一键打包桌面应用(当前平台)
#
# 环境前置(一次性安装):
#   - Node + npm(前端构建)
#   - Python + pip(后端,以及 PyInstaller)
#   - Rust 工具链(https://rustup.rs)+ Tauri CLI:
#       cargo install tauri-cli --version "^2.0"
#   - lark-cli 已装(用于飞书功能,会复制进安装包)
#
# 用法:
#   cd skill-tree
#   bash scripts/build-desktop.sh
#
# 产物: desktop/src-tauri/target/release/bundle/<msi|nsis|dmg|app>
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> 1/4 前端构建 (npm run build → frontend/dist)"
cd frontend && npm run build && cd ..

echo "==> 2/4 后端 PyInstaller 冻结 (→ backend/dist/skill-tree-backend/)"
cd backend
pip install -q pyinstaller
pyinstaller skill-tree-backend.spec --noconfirm
cd ..

echo "==> 3/4 放 lark-cli 到 resources (按当前平台)"
mkdir -p desktop/src-tauri/resources
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows*)
    LARK="$(which lark-cli 2>/dev/null || true)"
    [ -n "$LARK" ] && cp "$LARK" desktop/src-tauri/resources/lark-cli.exe \
      || echo "WARN: lark-cli 未找到,飞书功能打包后不可用(用户需另装)"
    ;;
  Darwin)
    LARK="$(which lark-cli 2>/dev/null || true)"
    [ -n "$LARK" ] && cp "$LARK" desktop/src-tauri/resources/lark-cli \
      || echo "WARN: lark-cli 未找到"
    ;;
  *) echo "WARN: 未识别平台 $(uname -s),跳过 lark-cli 复制" ;;
esac

echo "==> 4/4 Tauri 打包 (cargo tauri build)"
# 把后端 sidecar 产物放到 Tauri 能找到的位置(exe 同目录)
case "$(uname -s)" in
  MINGW*|MSYS*|CYGWIN*|Windows*)
    cp -r backend/dist/skill-tree-backend/* desktop/src-tauri/
    ;;
  *)
    cp -r backend/dist/skill-tree-backend desktop/src-tauri/skill-tree-backend-dist
    ;;
esac
cd desktop/src-tauri
cargo tauri build

echo ""
echo "==> 完成!安装包在:"
echo "    desktop/src-tauri/target/release/bundle/"
echo "    (Windows: .msi/.exe; macOS: .dmg/.app)"
