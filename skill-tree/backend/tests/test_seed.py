from __future__ import annotations
from pathlib import Path
import main


def test_seed_copies_when_data_dir_empty(tmp_path):
    """DATA_ROOT 为空时,从 seed 目录复制初始数据。"""
    seed = tmp_path / "seed"
    seed.mkdir()
    (seed / "agent.json").write_text('{"tree_id":"agent"}', encoding="utf-8")
    target = tmp_path / "data"
    main.seed_if_empty(target, seed)
    assert (target / "agent.json").exists()
    assert (target / "agent.json").read_text(encoding="utf-8") == '{"tree_id":"agent"}'


def test_seed_skips_when_data_already_present(tmp_path):
    """DATA_ROOT 已有数据时不覆盖(幂等)。"""
    seed = tmp_path / "seed"; seed.mkdir()
    (seed / "agent.json").write_text('{"seed":true}', encoding="utf-8")
    target = tmp_path / "data"; target.mkdir()
    (target / "existing.json").write_text('{"keep":true}', encoding="utf-8")
    main.seed_if_empty(target, seed)
    assert not (target / "agent.json").exists()   # 不覆盖、不补
    assert (target / "existing.json").read_text(encoding="utf-8") == '{"keep":true}'


def test_seed_no_seed_dir_is_noop(tmp_path):
    """seed 目录不存在时静默跳过(打包未含 seed 的 dev 场景)。"""
    target = tmp_path / "data"; target.mkdir()
    main.seed_if_empty(target, tmp_path / "nope")   # 不应抛错
    assert not list(target.iterdir())
