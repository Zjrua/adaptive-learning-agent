# skill-tree-backend.spec — PyInstaller 配置,冻结后端为 sidecar(目录模式)
#
# 用法:
#   cd skill-tree/backend
#   pip install pyinstaller
#   pyinstaller skill-tree-backend.spec --noconfirm
#
# 产物: dist/skill-tree-backend/skill-tree-backend.exe(+ 依赖目录)
#       Tauri 会把这个目录带进安装包,启动时 spawn 其中的 .exe
#
# ⚠ 本文件未经实跑验证(本会话环境无 PyInstaller)。
#   首次打包若报 ModuleNotFoundError,把缺的模块加进 hiddenimports 重打。
#   seed 目录(datas 里 '../data/users/default')解包后的实际路径需在
#   entry.py / main.py 用 sys._MEIPASS 或 Path(__file__).parent 探测,见注释。

from PyInstaller.utils.hooks import collect_all

# uvicorn / fastapi / pydantic 常有隐藏 import,显式收集
datas, binaries, hiddenimports = [], [], []
for pkg in ('uvicorn', 'fastapi', 'pydantic'):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# 带上 seed 数据(首次启动复制到用户主目录);解包后落在 _internal/seed/
datas += [('../data/users/default', 'seed')]

# 本项目自己的模块(Python 标准库外的本地 import,PyInstaller 静态分析常漏)
hiddenimports += [
    'main', 'entry', 'ai', 'larkpub', 'layout', 'progress', 'chat_store',
    'agent', 'agent.loop', 'agent.prompts', 'agent.tools',
    'agent.tool_runtime', 'agent.protocol', 'agent.session',
    'rag', 'rag.indexer', 'rag.retriever', 'rag.paper_fetch', 'rag.store',
]

a = Analysis(
    ['entry.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
)
pyz = PYZ(a.pure, a.zipped_data)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='skill-tree-backend',
    console=True,        # sidecar 需 stdout 打印 READY:<port>;勿关
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.zipfiles, a.datas, name='skill-tree-backend')
