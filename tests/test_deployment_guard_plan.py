"""Offline import-coverage check for the proposed Railway watch paths.

This checks the review document, not live Railway configuration or Git's exact glob engine.
"""

from __future__ import annotations

import ast
import fnmatch
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/control-tower/DEPLOYMENT_GUARD_PROPOSAL.md"
SOURCE = ROOT / "src/h2h"
ENTRYPOINTS = {
    "quantbet-engine": "h2h.entrypoint",
    "quantbet-dashboard": "h2h.dashboard_entrypoint",
    "quantbet-research": "h2h.research_dashboard_entrypoint",
    "quantbet-quantlab": "h2h.quantlab_dashboard_entrypoint",
    "quantbet-quantlab-collector": "h2h.quantlab.collector_entrypoint",
    "quantbet-quantlab-modeler": "h2h.quantlab.modeler_entrypoint",
    "quantbet-kellylab": "h2h.kellylab_dashboard_entrypoint",
    "quantbet-archive-lifecycle": "h2h.archive.lifecycle_entrypoint",
    "quantbet-find-26a813a9b6": "h2h.archive.entrypoint",
}


def _patterns() -> dict[str, tuple[str, ...]]:
    text = PLAN.read_text(encoding="utf-8")
    groups = {}
    for key in ("P", "M", "R"):
        match = re.search(rf"^{key} = (.+)$", text, re.MULTILINE)
        assert match is not None
        groups[key] = tuple(part.strip() for part in match.group(1).split("|"))
    result = {}
    for name in ENTRYPOINTS:
        rows = [line for line in text.splitlines() if line.startswith(f"| `{name}` (")]
        assert len(rows) == 1, name
        cell = rows[0].split(" | ")[1]
        patterns = list(re.findall(r"`([^`]+)`", cell))
        for key, values in groups.items():
            if re.search(rf"\b{key}\b", cell):
                patterns.extend(values)
        result[name] = tuple(patterns)
    return result


def _reachable_python_paths(entrypoint: str) -> set[str]:
    files = {
        ".".join(path.with_suffix("").relative_to(SOURCE.parent).parts): path
        for path in SOURCE.rglob("*.py")
    }
    seen: set[str] = set()
    pending = [entrypoint]
    while pending:
        module = pending.pop()
        if module in seen or module not in files:
            continue
        seen.add(module)
        tree = ast.parse(files[module].read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                pending.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                base = node.module or ""
                if node.level:
                    base = ".".join(
                        module.split(".")[: -node.level] + ([base] if base else [])
                    )
                pending.append(base)
                pending.extend(f"{base}.{alias.name}" for alias in node.names)
    paths = {
        files[module].relative_to(ROOT).as_posix()
        for module in seen
    }
    for module in seen:
        parts = module.split(".")
        for length in range(1, len(parts)):
            package_init = ".".join(parts[:length]) + ".__init__"
            if package_init in files:
                paths.add(files[package_init].relative_to(ROOT).as_posix())
    return paths


def test_proposed_watch_paths_cover_current_import_graph() -> None:
    for name, entrypoint in ENTRYPOINTS.items():
        patterns = _patterns()[name]
        missing = sorted(
            path
            for path in _reachable_python_paths(entrypoint)
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)
        )
        assert not missing, f"{name} misses Python runtime imports: {missing}"


def test_proposed_watch_paths_skip_documentation_and_tests() -> None:
    for name, patterns in _patterns().items():
        for path in (
            "docs/control-tower/RUNBOOK.md",
            "tests/test_control_tower.py",
            "scripts/control_tower.py",
            ".github/workflows/ci.yml",
        ):
            assert not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), (
                name,
                path,
            )


def test_migration_and_build_inputs_reach_required_services() -> None:
    patterns_by_service = _patterns()
    migration_services = {
        "quantbet-engine",
        "quantbet-research",
        "quantbet-quantlab",
        "quantbet-quantlab-collector",
        "quantbet-quantlab-modeler",
        "quantbet-kellylab",
        "quantbet-archive-lifecycle",
    }
    for name in migration_services:
        patterns = patterns_by_service[name]
        for path in ("migrations/067_example.sql", "src/h2h/persistence/migrations.py"):
            assert any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), (
                name,
                path,
            )
    archive = patterns_by_service["quantbet-archive-lifecycle"]
    assert "Dockerfile" in archive
    assert "railway.kellylab.json" in patterns_by_service["quantbet-kellylab"]
