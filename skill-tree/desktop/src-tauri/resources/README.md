# lark-cli 资源

打包时把当前平台的 lark-cli 二进制放这里(文件名按平台):
- Windows: `lark-cli.exe`
- macOS: `lark-cli`

Tauri 会把本目录的 `lark-cli*` 打进安装包(bundle.resources),运行时由
`src/main.rs` 解压到用户主目录 `~/.skill-tree/bin/`,供后端 larkpub.py 调用。

获取方式(打包脚本会自动做):
- 从本机 PATH 复制:`cp "$(which lark-cli)" lark-cli.exe`(Windows Git Bash)
- 或从 lark-cli release 下载对应平台版本(固定 v1.0.60)

本目录不预置二进制(不入库),由打包脚本 `scripts/build-desktop.sh` 填充。
