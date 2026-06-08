# tests/test_profile_repo_session.py
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.idgen.snowflake import SnowflakeGenerator
from core.domain.profile import Profile
from core.repos.profile_repo import ProfileRepository
from core.app.session import ProfileSession
from core.profiles import ProfileContext


@pytest.fixture
def tmp_profiles_root(tmp_path: Path) -> Path:
    root = tmp_path / "profiles"
    root.mkdir(parents=True, exist_ok=True)
    return root


@pytest.fixture
def idgen() -> SnowflakeGenerator:
    # worker_id 随便给个合法值
    return SnowflakeGenerator(worker_id=1)


def test_profile_repository_roundtrip(tmp_profiles_root: Path, idgen: SnowflakeGenerator) -> None:
    repo = ProfileRepository(tmp_profiles_root)

    name = "TestProfile"
    # 第一次 load_or_create 应创建新 profile 并写入磁盘
    prof1 = repo.load_or_create(name, idgen)
    path = repo.path_for(name)
    assert path.exists(), "profile.json 应该已写入磁盘"

    # 手动读一下 JSON 看结构
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data.get("meta", {}).get("profile_name") == "TestProfile"

    # 第二次 load_or_create 应加载已有 profile，不再重置 profile_id
    prof2 = repo.load_or_create(name, idgen)
    assert prof1.meta.profile_id == prof2.meta.profile_id
    assert prof2.meta.profile_name == "TestProfile"

    # Profile.from_dict / to_dict 自身的 roundtrip
    prof3 = Profile.from_dict(prof1.to_dict())
    assert prof3.meta.profile_id == prof1.meta.profile_id
    assert prof3.base.to_dict() == prof1.base.to_dict()


def make_profile_context(tmp_profiles_root: Path, idgen: SnowflakeGenerator, name: str) -> ProfileContext:
    repo = ProfileRepository(tmp_profiles_root)
    prof = repo.load_or_create(name, idgen)
    profile_dir = tmp_profiles_root / name
    profile_dir.mkdir(parents=True, exist_ok=True)
    return ProfileContext(
        profile_name=name,
        profile_dir=profile_dir,
        idgen=idgen,
        repo=repo,
        profile=prof,
    )


def test_profile_session_dirty_commit_reload(tmp_profiles_root: Path, idgen: SnowflakeGenerator) -> None:
    ctx = make_profile_context(tmp_profiles_root, idgen, "P1")
    session = ProfileSession(ctx)

    # 初始应无脏部分
    assert not session.is_dirty()
    assert session.dirty_parts() == set()

    # 修改 base 并标记 dirty
    session.profile.base.ui.theme = "flatly"
    session.mark_dirty("base")
    assert session.is_dirty()
    assert "base" in session.dirty_parts()

    # commit 后，dirty 应清除，profile.json 应更新
    session.commit(parts={"base"}, backup=False, touch_meta=True)
    assert not session.is_dirty()

    path = ctx.repo.path_for(ctx.profile_name)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["base"]["ui"]["theme"] == "flatly"

    # 修改 skills（比如追加一条空 skill），标记 dirty
    sfile = session.profile.skills
    old_len = len(sfile.skills)
    from core.models.skill import Skill
    sfile.skills.append(Skill(id="test-skill"))
    session.mark_dirty("skills")
    assert "skills" in session.dirty_parts()

    # reload_parts({"skills"}) 应丢弃刚刚追加的 skill
    session.reload_parts({"skills"})
    assert len(session.profile.skills.skills) == old_len
    assert "skills" not in session.dirty_parts()