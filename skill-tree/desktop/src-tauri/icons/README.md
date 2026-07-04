# 图标

Tauri 打包需要图标文件(见 tauri.conf.json 的 bundle.icon):
- Windows: `icon.ico`(含多尺寸 256/128/64/32/16)
- macOS: `icon.icns`
- 通用 PNG: `32x32.png`, `128x128.png`, `128x128@2x.png`

首次打包前需放好图标。可用任意 256x256 图(项目 logo / 一棵树)用
`tauri icon path/to/source.png` 自动生成全套(Tauri CLI 自带该命令)。

本目录未预置图标(二进制文件不入库),首次 `cargo tauri build` 前需补全。
临时占位:随便放一个 .ico 即可跑通流程,后续替换正式 logo。
