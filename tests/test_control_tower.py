"""Contract tests for the read-only architecture inventory."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

from scripts.control_tower import (
    build_registry,
    diff_registries,
    render_graph,
    sanitize_railway_status,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/control-tower/fixtures/railway-2026-10-10-0950.json"
EARLIER = ROOT / "docs/control-tower/fixtures/railway-2026-10-10.json"
ANNOTATIONS = ROOT / "docs/control-tower/annotations.json"
ASSESSMENT = ROOT / "docs/control-tower/assessment.json"
GITHUB = ROOT / "docs/control-tower/fixtures/github-2026-10-10.json"
GENERATED = ROOT / "docs/control-tower/generated/2026-10-10"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_live_fixture_registers_all_definitions_without_claiming_full_mapping():
    result = build_registry(_load(FIXTURE), _load(ANNOTATIONS))
    assert result["coverage"]["registered_services"] == 48
    assert result["coverage"]["registry_rows"] == 48
    assert result["coverage"]["git_source_refs"] == 31
    assert result["coverage"]["entrypoint_modules"] == 19
    assert result["coverage"]["mapped_services"] == 20
    assert result["coverage"]["services_with_running_instance"] == 12
    assert result["coverage"]["cron_definitions"] == 14
    assert result["coverage"]["failed_latest_deployments"] == 2
    assert any(row["mapping_status"] == "unmapped" for row in result["services"])
    assert all(row["created_at"] is None for row in result["services"])


def test_railway_capture_is_allowlisted_and_discards_secret_bearing_fields():
    raw = {
        "name": "project",
        "environments": {
            "edges": [
                {
                    "node": {
                        "name": "production",
                        "id": "env1",
                        "serviceInstances": {
                            "edges": [
                                {
                                    "node": {
                                        "serviceName": "worker",
                                        "serviceId": "service1",
                                        "source": {"repo": "owner/repo"},
                                        "startCommand": "PASSWORD=secret python -m safe.worker --token secret",
                                        "variables": {"DATABASE_URL": "postgres://secret"},
                                        "latestDeployment": {
                                            "createdAt": "2026-10-10T00:00:00Z",
                                            "status": "SUCCESS",
                                            "deploymentStopped": False,
                                            "meta": {
                                                "commitHash": "a" * 40,
                                                "commitAuthor": "private@example.com",
                                                "commitMessage": "secret",
                                            },
                                        },
                                        "activeDeployments": [
                                            {"instances": [{"status": "RUNNING"}]}
                                        ],
                                    }
                                }
                            ]
                        },
                    }
                }
            ]
        },
    }
    selected = sanitize_railway_status(raw, "project1", "2026-10-10T00:00:00Z")
    encoded = json.dumps(selected)
    assert len(selected) == 1
    assert selected[0]["entrypoint_module"] == "safe.worker"
    assert selected[0]["running_instances"] == 1
    assert "secret" not in encoded
    assert "private@example.com" not in encoded
    assert "DATABASE_URL" not in encoded


def test_graph_uses_database_in_same_project():
    fixture = _load(FIXTURE)
    registry = build_registry(fixture, _load(ANNOTATIONS))
    graph = render_graph(registry)
    rows = registry["services"]
    ids = {row["component_id"]: f"S{index}" for index, row in enumerate(rows)}
    for worker_name, project in (
        ("quantbet-engine", "sincere-balance"),
        ("basketball-v2-worker", "believable-contentment"),
    ):
        worker = next(row for row in rows if row["display_name"] == worker_name)
        database = next(
            row for row in rows if row["display_name"] == "Postgres" and row["project"] == project
        )
        assert (
            f"{ids[database['component_id']]} -->|read documented| {ids[worker['component_id']]}"
            in graph
        )


def test_snapshot_diff_reports_observation_separately_from_reason():
    source = _load(FIXTURE)
    annotations = _load(ANNOTATIONS)
    before = build_registry(source, annotations)
    later = deepcopy(source)
    later["observed_at"] = "2026-10-11T00:00:00Z"
    changed = next(row for row in later["services"] if row["name"] == "quantbet-engine")
    changed["latest_deployment_status"] = "FAILED"
    changed["source_commit"] = "b" * 40
    changed["latest_deployment_at"] = "2026-10-11T00:00:00Z"
    after = build_registry(later, annotations)
    diff = diff_registries(before, after)
    engine = next(row for row in diff["changes"] if row["name"] == "quantbet-engine")
    assert "source_commit" in engine["fields"]
    assert "last_changed_at" in engine["fields"]
    assert engine["documented_reason"] == "reason unknown"
    assert diff["failure_counts"] == {"before": 2, "after": 3}


def test_offline_cli_regeneration_is_byte_for_byte_deterministic(tmp_path):
    outputs = []
    for index in range(2):
        folder = tmp_path / str(index)
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/control_tower.py"),
                "build",
                "--fixture",
                str(FIXTURE),
                "--annotations",
                str(ANNOTATIONS),
                "--assessment",
                str(ASSESSMENT),
                "--github-fixture",
                str(GITHUB),
                "--out",
                str(folder),
            ],
            check=True,
            cwd=ROOT,
        )
        outputs.append({file.name: file.read_bytes() for file in folder.iterdir()})
    assert outputs[0] == outputs[1]
    assert set(outputs[0]) == {"inventory.v1.json", "CONTROL_TOWER.md", "architecture.mmd"}
    assert outputs[0] == {file.name: file.read_bytes() for file in GENERATED.iterdir()}


def test_diff_identifies_absent_service_without_claiming_deletion():
    source = _load(FIXTURE)
    before = build_registry(source, _load(ANNOTATIONS))
    later = deepcopy(source)
    later["observed_at"] = "2026-10-11T00:00:00Z"
    later["services"] = [row for row in later["services"] if row["name"] != "quantbet-void-1636701"]
    after = build_registry(later, _load(ANNOTATIONS))
    diff = diff_registries(before, after)
    assert len(diff["retired_from_registry"]) == 1
    assert "not confirmed deleted" in diff["note"]


def test_two_observed_snapshots_detect_runtime_status_drift():
    annotations = _load(ANNOTATIONS)
    earlier = build_registry(_load(EARLIER), annotations)
    later = build_registry(_load(FIXTURE), annotations)
    diff = diff_registries(earlier, later)
    assert diff["added"] == diff["retired_from_registry"] == []
    assert diff["failure_counts"] == {"before": 1, "after": 2}
    assert {item["name"] for item in diff["changes"]} == {
        "quantbet-baseball-cold-storage",
        "quantbet-quantlab-collector",
    }


def test_diff_catches_owner_dependency_permission_ci_and_freshness_drift():
    before = build_registry(_load(FIXTURE), _load(ANNOTATIONS))
    after = deepcopy(before)
    after["observed_at"] = "2026-10-11T00:00:00Z"
    engine = next(row for row in after["services"] if row["display_name"] == "quantbet-engine")
    engine["owner"] = "unexpected-owner"
    engine["dependencies"] = ["Postgres"]
    engine["permission_scope"] = "unexpected-write"
    engine["ci_status"] = "failure"
    engine["data_freshness_at"] = "2026-10-01T00:00:00Z"
    diff = diff_registries(before, after)
    change = next(row for row in diff["changes"] if row["name"] == "quantbet-engine")
    assert {"owner", "dependencies", "permission_scope", "ci_status", "data_freshness_at"} <= set(
        change["fields"]
    )
    assert diff["ci_failure_counts"]["after"] == diff["ci_failure_counts"]["before"] + 1
    assert change["documented_reason"] == "reason unknown"
