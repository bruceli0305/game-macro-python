# rotation_editor/storage.py
from __future__ import annotations

from pathlib import Path

from core.io.json_store import atomic_write_json, ensure_dir, read_json
from rotation_editor.core.models import RotationsFile


def rotations_path(profile_dir: Path) -> Path:
    """
    给定 Profile 目录，返回该 Profile 下的 rotation.json 路径。
    不强依赖 ProfileContext，外面只要传入目录即可。
    """
    return profile_dir / "rotation.json"


def load_or_create_rotations(profile_dir: Path) -> RotationsFile:
    """
    从 profile_dir/rotation.json 读取 RotationsFile，
    不存在则创建默认文件并写盘。
    """
    p = rotations_path(profile_dir)
    ensure_dir(profile_dir)

    existed = p.exists()
    data = read_json(p, default={})
    rotations = RotationsFile.from_dict(data)

    if not existed:
        save_rotations(profile_dir, rotations, backup=False)

    return rotations


def save_rotations(profile_dir: Path, rotations: RotationsFile, *, backup: bool = False) -> None:
    """
    将 RotationsFile 写回 profile_dir/rotation.json。
    """
    p = rotations_path(profile_dir)
    ensure_dir(profile_dir)
    atomic_write_json(p, rotations.to_dict(), backup=backup)