"""entry.py — PyInstaller sidecar 入口。

打包后由 Tauri shell 启动:
  skill-tree-backend.exe --port 52317 --data-dir ~/.skill-tree/data

读 port/data-dir,设 env(main.py 据此定 DATA_ROOT),起 uvicorn。
"""
from __future__ import annotations
import argparse
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data-dir", default=None, help="覆盖 DATA_ROOT")
    parser.add_argument("--resume-dir", default=None)
    parser.add_argument("--projects-dir", default=None)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()

    if args.data_dir:
        os.environ["DATA_ROOT"] = args.data_dir
    if args.resume_dir:
        os.environ["RESUME_DIR"] = args.resume_dir
    if args.projects_dir:
        os.environ["PROJECTS_DIR"] = args.projects_dir

    import uvicorn
    # READY 信号:Tauri shell 读 stdout 等这行再让 webview 请求
    print(f"READY:{args.port}", flush=True)
    uvicorn.run("main:app", host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
