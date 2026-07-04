import os, tempfile
# 测试用临时 DATA_ROOT,避免污染本机 ~/.skill-tree(必须在 import main 前 set)
os.environ.setdefault("DATA_ROOT", tempfile.mkdtemp(prefix="st_test_"))
os.environ.setdefault("SEED_DIR", tempfile.mkdtemp(prefix="st_seed_"))
