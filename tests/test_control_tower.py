"""Contract tests for the read-only architecture inventory."""

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.control_tower import (
    FOOTBALL_PROJECT_ID,
    FOOTBALL_PROJECT_NAME,
    build_registry,
    capture_github,
    diff_registries,
    render_graph,
    render_inventory,
    sanitize_railway_status,
)


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "docs/control-tower/fixtures/football-2026-10-10-0950.json"
EARLIER = ROOT / "docs/control-tower/fixtures/football-2026-10-10.json"
ANNOTATIONS = ROOT / "docs/control-tower/annotations.json"
ASSESSMENT = ROOT / "docs/control-tower/assessment.json"
GITHUB = ROOT / "docs/control-tower/fixtures/football-github-2026-10-10.json"
GENERATED = ROOT / "docs/control-tower/generated/football-2026-10-10"


def _load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def test_live_fixture_registers_all_definitions_without_claiming_full_mapping():
    result = build_registry(_load(FIXTURE), _load(ANNOTATIONS))
    assert result["coverage"]["registered_services"] == 18
    assert result["coverage"]["registry_rows"] == 18
    assert result["coverage"]["git_source_refs"] == 15
    assert result["coverage"]["entrypoint_modules"] == 8
    assert result["coverage"]["mapped_services"] == 8
    assert result["coverage"]["services_with_running_instance"] == 8
    assert result["coverage"]["cron_definitions"] == 4
    assert result["coverage"]["failed_latest_deployments"] == 1
    assert {row["project"] for row in result["services"]} == {FOOTBALL_PROJECT_NAME}
    assert any(row["mapping_status"] == "unmapped" for row in result["services"])
    assert all(row["created_at"] is None for row in result["services"])


def test_railway_capture_is_allowlisted_and_discards_secret_bearing_fields():
    raw = {
        "name": FOOTBALL_PROJECT_NAME,
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
    selected = sanitize_railway_status(raw, FOOTBALL_PROJECT_ID, "2026-10-10T00:00:00Z")
    encoded = json.dumps(selected)
    assert len(selected) == 1
    assert selected[0]["entrypoint_module"] == "safe.worker"
    assert selected[0]["running_instances"] == 1
    assert "secret" not in encoded
    assert "private@example.com" not in encoded
    assert "DATABASE_URL" not in encoded


def test_wrong_project_identity_is_rejected_before_capture_or_build(tmp_path):
    fixture = _load(FIXTURE)
    fixture["services"][0]["project_id"] = "unexpected-project"
    with pytest.raises(ValueError, match="outside the football allowlist"):
        build_registry(fixture, _load(ANNOTATIONS))
    with pytest.raises(ValueError, match="football allowlist"):
        sanitize_railway_status(
            {"name": "unexpected-project"}, FOOTBALL_PROJECT_ID, fixture["observed_at"]
        )
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/control_tower.py"),
            "capture-railway",
            "--project",
            "unexpected-project",
            "--out",
            str(tmp_path / "capture.json"),
        ],
        capture_output=True,
        check=False,
        cwd=ROOT,
    )
    assert result.returncode != 0
    assert not (tmp_path / "capture.json").exists()


def test_github_and_snapshot_diff_reject_out_of_scope_inputs():
    with pytest.raises(ValueError, match="football repository"):
        capture_github(["unexpected/other"])
    fixture = _load(FIXTURE)
    github = _load(GITHUB)
    github["repos"].append({"full_name": "unexpected/other"})
    with pytest.raises(ValueError, match="outside the football allowlist"):
        build_registry(fixture, _load(ANNOTATIONS), github)
    before = build_registry(fixture, _load(ANNOTATIONS))
    after = deepcopy(before)
    after["services"][0]["project_id"] = "unexpected-project"
    with pytest.raises(ValueError, match="out-of-scope"):
        diff_registries(before, after)
    annotations = _load(ANNOTATIONS)
    annotations["extra_components"].append({"name": "unexpected-component"})
    with pytest.raises(ValueError, match="outside the football allowlist"):
        build_registry(fixture, annotations)
    assessment = _load(ASSESSMENT)
    assessment["project"] = "unexpected-project"
    with pytest.raises(ValueError, match="football allowlist"):
        render_inventory(before, assessment)


def test_graph_uses_database_in_same_project():
    fixture = _load(FIXTURE)
    registry = build_registry(fixture, _load(ANNOTATIONS))
    graph = render_graph(registry)
    rows = registry["services"]
    ids = {row["component_id"]: f"S{index}" for index, row in enumerate(rows)}
    worker = next(row for row in rows if row["display_name"] == "quantbet-engine")
    database = next(row for row in rows if row["display_name"] == "Postgres")
    assert (
        f"{ids[database['component_id']]} -->|read documented| {ids[worker['component_id']]}"
        in graph
    )
    assert "API-Sports" not in graph


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
    after = build_registry(later, annotations, previous=before)
    diff = diff_registries(before, after)
    engine = next(row for row in diff["changes"] if row["name"] == "quantbet-engine")
    later_engine = next(
        row for row in after["services"] if row["display_name"] == "quantbet-engine"
    )
    prior_engine = next(
        row for row in before["services"] if row["display_name"] == "quantbet-engine"
    )
    assert (
        later_engine["last_successful_deployment_at"]
        == prior_engine["last_successful_deployment_at"]
    )
    assert "source_commit" in engine["fields"]
    assert "last_changed_at" in engine["fields"]
    assert engine["documented_reason"] == "reason unknown"
    assert diff["failure_counts"] == {"before": 1, "after": 2}


def test_history_survives_new_snapshot_and_failed_deployment():
    annotations = _load(ANNOTATIONS)
    before = build_registry(_load(EARLIER), annotations)
    after = build_registry(_load(FIXTURE), annotations, previous=before)
    old = {row["component_id"]: row for row in before["services"]}
    assert all(
        row["first_seen_at"] == old[row["component_id"]]["first_seen_at"]
        for row in after["services"]
    )
    collector = next(
        row for row in after["services"] if row["display_name"] == "quantbet-quantlab-collector"
    )
    assert collector["latest_deployment_status"] == "SUCCESS"
    assert collector["running_instances"] == 0
    assert collector["last_successful_deployment_at"] == "2026-10-10T00:38:35Z"
    assert (
        "last observed SUCCESS deploy=2026-10-10T00:38:35Z (seen 2026-10-10T09:50:02Z)"
        in render_inventory(after, _load(ASSESSMENT))
    )


def test_cron_dimensions_are_separate_from_deployment_and_data_freshness():
    registry = build_registry(_load(FIXTURE), _load(ANNOTATIONS))
    cron = next(
        row for row in registry["services"] if row["display_name"] == "quantbet-quantlab-collector"
    )
    assert cron["cron_scheduled"] is True
    assert cron["cron_running_now"] is False
    assert cron["cron_last_successful_completion_at"] is None
    assert cron["data_freshness_at"] is None
    report = render_inventory(registry, _load(ASSESSMENT))
    assert "last successful completion=unknown" in report
    assert "data freshness=unknown" in report
    assert "generator does **not** calculate" in report


def test_verified_job_evidence_populates_completion_without_changing_deployment_status():
    base = build_registry(_load(FIXTURE), _load(ANNOTATIONS))
    cron = next(
        row for row in base["services"] if row["display_name"] == "quantbet-quantlab-collector"
    )
    evidence = {
        "services": {
            cron["component_id"]: {
                "last_successful_completion_at": "2026-10-10T08:02:00Z",
                "completion_evidence": "read-only job log review",
                "data_freshness_at": "2026-10-10T07:55:00Z",
                "data_freshness_evidence": "read-only watermark query",
            }
        }
    }
    result = build_registry(_load(FIXTURE), _load(ANNOTATIONS), operations=evidence)
    row = next(item for item in result["services"] if item["component_id"] == cron["component_id"])
    assert row["cron_last_successful_completion_at"] == "2026-10-10T08:02:00Z"
    assert row["data_freshness_at"] == "2026-10-10T07:55:00Z"
    assert row["latest_deployment_status"] == cron["latest_deployment_status"]


def test_job_timestamp_without_evidence_is_rejected():
    base = build_registry(_load(FIXTURE), _load(ANNOTATIONS))
    cron = next(
        row for row in base["services"] if row["display_name"] == "quantbet-quantlab-collector"
    )
    with pytest.raises(ValueError, match="requires valid time and evidence"):
        build_registry(
            _load(FIXTURE),
            _load(ANNOTATIONS),
            operations={
                "services": {
                    cron["component_id"]: {"last_successful_completion_at": "2026-10-10T08:02:00Z"}
                }
            },
        )


def test_offline_cli_regeneration_is_byte_for_byte_deterministic(tmp_path):
    earlier_registry = build_registry(_load(EARLIER), _load(ANNOTATIONS), _load(GITHUB))
    previous = tmp_path / "previous.json"
    previous.write_text(json.dumps(earlier_registry), encoding="utf-8")
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
                "--previous",
                str(previous),
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
    assert diff["failure_counts"] == {"before": 1, "after": 1}
    assert {item["name"] for item in diff["changes"]} == {"quantbet-quantlab-collector"}


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
