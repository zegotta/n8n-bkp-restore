from __future__ import annotations

import re
import tomllib
from pathlib import Path

from n8n_backup_restore import __version__


SEMVER_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")


def test_package_version_is_semver() -> None:
    assert SEMVER_PATTERN.match(__version__), f"Versão inválida para SemVer: {__version__}"


def test_pyproject_version_matches_package_version() -> None:
    pyproject_path = Path(__file__).resolve().parents[1] / "pyproject.toml"
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project_version = pyproject["project"]["version"]
    assert project_version == __version__


def test_changelog_has_current_version_section() -> None:
    changelog_path = Path(__file__).resolve().parents[1] / "CHANGELOG.md"
    changelog = changelog_path.read_text(encoding="utf-8")
    assert f"## [{__version__}] -" in changelog
