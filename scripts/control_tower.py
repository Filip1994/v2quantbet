"""Read-only, offline-first QuantBet service inventory and snapshot diff.

Only explicitly selected Railway metadata fields can enter a fixture. This module
never imports application code, connects to a database, or changes a deployment.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
SAFE_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
SAFE_REPO = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SAFE_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
MODULE = re.compile(r"(?:^|\s)python(?:3)?\s+-m\s+([A-Za-z_][A-Za-z0-9_.]*)")
DIFF_FIELDS = (
    "display_name",
    "category",
    "owner",
    "source_repo",
    "source_commit",
    "last_changed_at",
    "last_successful_deployment_at",
    "code_path",
    "entrypoint_module",
    "cron_schedule",
    "latest_deployment_status",
    "operational_state",
    "running_instances",
    "dependencies",
    "datastores_read",
    "datastores_write",
    "permission_scope",
    "ci_status",
    "data_freshness_at",
    "purpose",
    "documented_reason",
)


def _allow(value: Any, pattern: re.Pattern[str]) -> str | None:
    return value if isinstance(value, str) and pattern.fullmatch(value) else None


def _iso(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return (
        parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        if parsed.tzinfo
        else None
    )


def sanitize_railway_status(
    raw: dict[str, Any], project_id: str, observed_at: str
) -> list[dict[str, Any]]:
    """Select metadata only; never copy variables, start commands or deployment meta."""
    result: list[dict[str, Any]] = []
    project_name = _allow(raw.get("name"), SAFE_NAME) or project_id
    for environment_edge in raw.get("environments", {}).get("edges", []):
        environment = environment_edge.get("node") or {}
        environment_name = _allow(environment.get("name"), SAFE_NAME)
        environment_id = _allow(environment.get("id"), SAFE_NAME)
        if not environment_name or not environment_id:
            continue
        for service_edge in environment.get("serviceInstances", {}).get("edges", []):
            service = service_edge.get("node") or {}
            deployment = service.get("latestDeployment") or {}
            name = _allow(service.get("serviceName"), SAFE_NAME)
            service_id = _allow(service.get("serviceId"), SAFE_NAME)
            if not name or not service_id:
                continue
            source_repo = _allow((service.get("source") or {}).get("repo"), SAFE_REPO)
            commit = _allow((deployment.get("meta") or {}).get("commitHash"), SAFE_COMMIT)
            command = service.get("startCommand")
            module_match = MODULE.search(command) if isinstance(command, str) else None
            cron = service.get("cronSchedule")
            cron = (
                cron
                if isinstance(cron, str) and re.fullmatch(r"[0-9A-Za-z*/?, -]{1,100}", cron)
                else None
            )
            active = service.get("activeDeployments") or []
            running = sum(
                instance.get("status") == "RUNNING"
                for item in active
                for instance in (item.get("instances") or [])
            )
            result.append(
                {
                    "project": project_name,
                    "project_id": project_id,
                    "environment": environment_name,
                    "environment_id": environment_id,
                    "service_id": service_id,
                    "name": name,
                    "source_repo": source_repo,
                    "source_commit": commit,
                    "entrypoint_module": module_match.group(1) if module_match else None,
                    "cron_schedule": cron,
                    "latest_deployment_at": _iso(deployment.get("createdAt")),
                    "latest_deployment_status": _allow(deployment.get("status"), SAFE_NAME),
                    "latest_deployment_stopped": bool(deployment.get("deploymentStopped")),
                    "running_instances": running,
                }
            )
    return sorted(result, key=lambda row: (row["project_id"], row["service_id"]))


def _state(service: dict[str, Any]) -> str:
    if service.get("latest_deployment_status") in {"FAILED", "CRASHED"}:
        return "failed_or_crashed_latest_deployment"
    if service.get("cron_schedule"):
        return "scheduled_cron_current_run_unknown"
    if service.get("latest_deployment_status") == "SLEEPING":
        return "sleeping_deployment"
    if service.get("running_instances", 0) > 0:
        return "running_instance"
    if service.get("latest_deployment_stopped"):
        return "stopped_or_completed"
    return "no_running_instance"


def _category(name: str) -> str:
    lower = name.lower()
    if lower == "postgres":
        return "database"
    if "dashboard" in lower or lower in {
        "quantbet-quantlab",
        "quantbet-kellylab",
        "quantbet-research",
    }:
        return "dashboard"
    if "collector" in lower:
        return "collector"
    if "modeler" in lower:
        return "modeler"
    if "archive" in lower or "cold-storage" in lower:
        return "archive"
    if any(
        word in lower
        for word in ("query", "audit", "test", "diagnostic", "inspect", "find", "void")
    ):
        return "diagnostic_or_one_shot"
    if any(word in lower for word in ("engine", "worker", "baseball", "basketball")):
        return "worker"
    return "unknown"


def _service_id(service: dict[str, Any]) -> str:
    return (
        "railway:"
        + service["project_id"]
        + ":"
        + service["environment_id"]
        + ":"
        + service["service_id"]
    )


def build_registry(
    fixture: dict[str, Any], annotations: dict[str, Any], github: dict[str, Any] | None = None
) -> dict[str, Any]:
    if fixture.get("schema_version") != SCHEMA_VERSION or not _iso(fixture.get("observed_at")):
        raise ValueError("Expected a v1 fixture with a UTC observed_at timestamp")
    services = fixture.get("services")
    if not isinstance(services, list):
        raise TypeError("Fixture services must be a list")
    records = []
    seen = set()
    by_name = annotations.get("services", {})
    github_by_repo = {row.get("full_name"): row for row in (github or {}).get("repos", [])}
    for raw in services:
        # Strict allowlist even when an imported fixture has extra fields.
        name = _allow(raw.get("name"), SAFE_NAME)
        project_id = _allow(raw.get("project_id"), SAFE_NAME)
        environment_id = _allow(raw.get("environment_id"), SAFE_NAME)
        service_id = _allow(raw.get("service_id"), SAFE_NAME)
        if not all((name, project_id, environment_id, service_id)):
            raise ValueError("Invalid service identity")
        key = _service_id(raw)
        if key in seen:
            raise ValueError(f"Duplicate service identity: {key}")
        seen.add(key)
        note = by_name.get(name, {})
        if not isinstance(note, dict):
            raise TypeError(f"Invalid annotation: {name}")
        repo = _allow(raw.get("source_repo"), SAFE_REPO)
        commit = _allow(raw.get("source_commit"), SAFE_COMMIT)
        deployment_at = _iso(raw.get("latest_deployment_at"))
        category = note.get("category") or _category(name)
        repo_snapshot = github_by_repo.get(repo, {})
        matching_run = next(
            (
                run
                for run in repo_snapshot.get("workflow_runs", [])
                if run.get("head_sha") == commit
            ),
            None,
        )
        records.append(
            {
                "component_id": key,
                "display_name": name,
                "category": category,
                "owner": note.get("owner") or "unknown",
                "purpose": note.get("purpose") or "unknown",
                "documented_reason": note.get("documented_reason") or "reason unknown",
                "code_path": note.get("code_path") or "unknown",
                "source_repo": repo or "unknown",
                "source_commit": commit,
                "entrypoint_module": _allow(raw.get("entrypoint_module"), SAFE_NAME),
                "project": _allow(raw.get("project"), SAFE_NAME) or "unknown",
                "project_id": project_id,
                "environment": _allow(raw.get("environment"), SAFE_NAME) or "unknown",
                "environment_id": environment_id,
                "service_id": service_id,
                "first_seen_at": fixture["observed_at"],
                "created_at": None,
                "last_changed_at": deployment_at,
                "last_successful_deployment_at": deployment_at
                if raw.get("latest_deployment_status") == "SUCCESS"
                else None,
                "latest_deployment_status": _allow(raw.get("latest_deployment_status"), SAFE_NAME),
                "operational_state": _state(raw),
                "running_instances": max(0, int(raw.get("running_instances") or 0)),
                "cron_schedule": raw.get("cron_schedule")
                if isinstance(raw.get("cron_schedule"), str)
                else None,
                "dependencies": sorted(set(note.get("dependencies", []))),
                "datastores_read": sorted(set(note.get("datastores_read", []))),
                "datastores_write": sorted(set(note.get("datastores_write", []))),
                "provider_categories": sorted(set(note.get("provider_categories", []))),
                "consumers": sorted(set(note.get("consumers", []))),
                "permission_scope": note.get("permission_scope") or "unknown",
                "data_freshness_at": None,
                "observability": note.get("observability") or "unknown",
                "ci_status": (matching_run.get("conclusion") or matching_run.get("status"))
                if matching_run
                else None,
                "risk_classification": note.get("risk_classification") or "unknown",
                "api_cost_envelope": note.get("api_cost_envelope"),
                "deprecated": note.get("deprecated"),
                "mapping_status": "mapped"
                if note.get("purpose")
                and note.get("owner") not in (None, "unknown")
                and note.get("evidence_url")
                and (note.get("code_path") or category == "database")
                else "unmapped",
                "verification": note.get("verification") or ("inferred" if note else "unknown"),
                "evidence_url": note.get("evidence_url"),
                "evidence_observed_at": fixture["observed_at"],
            }
        )
    records.sort(key=lambda row: row["component_id"])
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": fixture["observed_at"],
        "source": fixture.get("source") or "unknown",
        "coverage": {
            "registered_services": len(records),
            "registry_rows": len(records),
            "mapped_services": sum(row["mapping_status"] == "mapped" for row in records),
            "git_source_refs": sum(row["source_repo"] != "unknown" for row in records),
            "entrypoint_modules": sum(bool(row["entrypoint_module"]) for row in records),
            "services_with_running_instance": sum(row["running_instances"] > 0 for row in records),
            "cron_definitions": sum(bool(row["cron_schedule"]) for row in records),
            "failed_latest_deployments": sum(
                row["latest_deployment_status"] in {"FAILED", "CRASHED"} for row in records
            ),
            "sleeping_latest_deployments": sum(
                row["latest_deployment_status"] == "SLEEPING" for row in records
            ),
        },
        "services": records,
        "extra_components": annotations.get("extra_components", []),
        "github_observed_at": (github or {}).get("observed_at"),
        "recent_pull_requests": sorted(
            (
                {
                    "repo": repo.get("full_name"),
                    "number": pr.get("number"),
                    "title": pr.get("title"),
                    "state": pr.get("state"),
                    "merged_at": pr.get("merged_at"),
                    "url": pr.get("url"),
                    "documented_reason": "reason unknown",
                }
                for repo in (github or {}).get("repos", [])
                for pr in repo.get("pull_requests", [])
            ),
            key=lambda item: (item["repo"] or "", item["number"] or 0),
        ),
        "change_history": sorted(
            (
                {
                    "repo": repo.get("full_name"),
                    "sha": commit.get("sha"),
                    "at": commit.get("at"),
                    "what": commit.get("title"),
                    "documented_reason": "reason unknown",
                    "url": commit.get("url"),
                }
                for repo in (github or {}).get("repos", [])
                for commit in repo.get("commits", [])
            ),
            key=lambda item: (item["repo"] or "", item["at"] or "", item["sha"] or ""),
        ),
    }


def render_inventory(registry: dict[str, Any], assessment: dict[str, Any]) -> str:
    coverage = registry["coverage"]
    lines = [
        "# QuantBet Control Tower V1",
        "",
        f"Snapshot: `{registry['observed_at']}`. Registered: **{coverage['registered_services']}**; detailed mapped: **{coverage['mapped_services']}**; Git source ref: **{coverage['git_source_refs']}**; recognized module entrypoint: **{coverage['entrypoint_modules']}**. Registry coverage is {coverage['registry_rows']}/{coverage['registered_services']}; functional mapping coverage is {coverage['mapped_services']}/{coverage['registered_services']}.",
        "",
        f"Runtime metadata at that instant: **{coverage['services_with_running_instance']}** services with a `RUNNING` instance, **{coverage['cron_definitions']}** cron definitions, **{coverage['failed_latest_deployments']}** latest `FAILED`/`CRASHED` deployments, **{coverage['sleeping_latest_deployments']}** latest `SLEEPING` deployments. These counts overlap and are not a health score.",
        "",
        "`SUCCESS` is the last deployment result, not uptime, job success or data freshness. `unknown` is preserved where evidence is missing. The historical [audit](../ARCHITECTURE_AUDIT_2026-10.md) gives context and direct links.",
        "",
        "## Service registry",
        "",
        "| Service / project | Purpose / owner | Code | State / cron / last deploy | Reads → writes | CI at commit | Risk | Evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for row in registry["services"]:
        code = row["source_repo"] + (
            " @ " + row["source_commit"][:8] if row["source_commit"] else ""
        )
        stores = ", ".join(row["datastores_read"]) or "unknown"
        writes = ", ".join(row["datastores_write"])
        if not writes and row["mapping_status"] == "mapped":
            writes = "none documented; DB grants unknown"
        stores += " → " + (writes or "unknown")
        evidence = f"[source]({row['evidence_url']})" if row["evidence_url"] else "unknown"
        state = row["operational_state"] + (
            f"; `{row['cron_schedule']}`" if row["cron_schedule"] else ""
        )
        state += "; " + (row["last_changed_at"] or "deploy time unknown")
        lines.append(
            f"| `{row['display_name']}`<br>`{row['project']}` / `{row['service_id']}` | {row['purpose']} / {row['owner']} | {code}; `{row['code_path']}` | {state} | {stores} | {row['ci_status'] or 'unknown'} | {row['risk_classification']} | {evidence}; {row['verification']} |"
        )
    lines += [
        "",
        "## Architecture scorecard",
        "",
        "The [audit rubric](../ARCHITECTURE_AUDIT_2026-10.md#ocena-arhitektonskih-oblasti) defines 1–10 bands. Missing runtime evidence remains `not assessed`.",
        "",
        "| Dimension | Score / 10 | Confidence | Evidence |",
        "| --- | ---: | --- | --- |",
    ]
    for item in assessment.get("dimensions", []):
        score = item.get("score") if item.get("score") is not None else "not assessed"
        lines.append(f"| {item['name']} | {score} | {item['confidence']} | {item['evidence']} |")
    lines += [
        "",
        "## Risk register",
        "",
        "| ID | Risk | Severity × likelihood | Evidence | Action |",
        "| --- | --- | ---: | --- | --- |",
    ]
    for risk in assessment.get("risks", []):
        lines.append(
            f"| {risk['id']} | {risk['title']} | {risk['severity']} × {risk['likelihood']} | {risk['evidence']} | {risk['action']} |"
        )
    lines += [
        "",
        "## Recent code history (metadata only)",
        "",
        "Commit title describes what was submitted. It is not evidence of motive. `reason unknown` remains until a PR or decision document explicitly explains why.",
        "",
        "| Repo | When (UTC) | What | Why |",
        "| --- | --- | --- | --- |",
    ]
    for item in registry.get("change_history", []):
        title = (item["what"] or "unknown").replace("|", "\\|")
        lines.append(
            f"| {item['repo']} | {item['at'] or 'unknown'} | [{item['sha'][:8]}]({item['url']}) {title} | {item['documented_reason']} |"
        )
    if not registry.get("change_history"):
        lines.append("| unknown | unknown | GitHub fixture unavailable | reason unknown |")
    lines += [
        "",
        "## Recent pull requests",
        "",
        "PR titles are metadata, not a verified explanation of intent. Open the linked discussion for rationale.",
        "",
        "| Repo | PR | State | Documented reason in this snapshot |",
        "| --- | --- | --- | --- |",
    ]
    for item in registry.get("recent_pull_requests", []):
        title = (item["title"] or "unknown").replace("|", "\\|")
        lines.append(
            f"| {item['repo']} | [#{item['number']} {title}]({item['url']}) | {item['state']} | {item['documented_reason']} |"
        )
    if not registry.get("recent_pull_requests"):
        lines.append("| unknown | unknown | unknown | reason unknown |")
    lines += ["", "## Additional components", ""]
    for component in registry.get("extra_components", []):
        lines.append(
            f"- **{component['name']}** — {component['purpose']} ([source]({component['evidence_url']})); runtime status: {component['runtime_status']}."
        )
    return "\n".join(lines) + "\n"


def render_graph(registry: dict[str, Any]) -> str:
    rows = registry["services"]
    by_project_name = {(row["project_id"], row["display_name"]): row for row in rows}
    lines = [
        "flowchart LR",
        "  %% Solid arrows read or consume; dotted arrows document application writes.",
        "  AF[API-Football]",
        "  AB[API-Sports Baseball]",
        "  AK[API-Sports Basketball]",
    ]
    ids = {row["component_id"]: f"S{index}" for index, row in enumerate(rows)}
    projects = sorted({(row["project_id"], row["project"]) for row in rows})
    for project_index, (project_id, project_name) in enumerate(projects):
        lines.append(
            f'  subgraph P{project_index}["Railway {project_name} / production environment"]'
        )
        for row in rows:
            if row["project_id"] == project_id:
                label = row["display_name"].replace('"', "")
                lines.append(f'    {ids[row["component_id"]]}["{label}"]')
        lines.append("  end")
    extra = registry.get("extra_components", [])
    if extra:
        lines.append(
            '  subgraph M["Code modules / independent repository; runtime status separate"]'
        )
        for index, component in enumerate(extra):
            label = component["name"].replace('"', "")
            lines.append(f'    M{index}["{label}"]')
        lines.append("  end")
    lines += [
        "  classDef production fill:#ffd8c2,stroke:#a34b00",
        "  classDef research fill:#dcecff,stroke:#2e63a0",
        "  classDef datastore fill:#e3d8ff,stroke:#6545a0",
    ]
    for row in rows:
        cls = (
            "datastore"
            if row["category"] == "database"
            else "production"
            if row["category"] in {"production_worker", "baseball_worker", "basketball_v2_worker"}
            else "research"
        )
        lines.append(f"  class {ids[row['component_id']]} {cls}")
    edges = set()
    for row in rows:
        target = ids[row["component_id"]]
        for dep in row["dependencies"]:
            scoped = by_project_name.get((row["project_id"], dep))
            if scoped:
                source = ids[scoped["component_id"]]
                if dep == "Postgres":
                    if row["datastores_read"] and row["datastores_read"] != ["unknown"]:
                        edges.add(f"  {source} -->|read documented| {target}")
                    if row["datastores_write"] and row["datastores_write"] != ["unknown"]:
                        edges.add(f"  {target} -.->|write documented, DB grants unknown| {source}")
                else:
                    edges.add(f"  {source} --> {target}")
            elif dep == "API-Football":
                edges.add(f"  AF --> {target}")
            elif dep == "API-Sports Baseball":
                edges.add(f"  AB --> {target}")
            elif dep == "API-Sports Basketball":
                edges.add(f"  AK --> {target}")
    collector = next(
        (row for row in rows if row["display_name"] == "quantbet-quantlab-collector"), None
    )
    if collector:
        for index, component in enumerate(extra):
            if component["name"] in {"GoalLab", "CornerLab", "CardLab", "H2HLab"}:
                edges.add(
                    f"  {ids[collector['component_id']]} -.->|documented shared module| M{index}"
                )
    lines.extend(sorted(edges))
    return "\n".join(lines) + "\n"


def diff_registries(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    old = {row["component_id"]: row for row in before["services"]}
    new = {row["component_id"]: row for row in after["services"]}
    changes = []
    for key in sorted(old.keys() & new.keys()):
        fields = {
            field: {"before": old[key].get(field), "after": new[key].get(field)}
            for field in DIFF_FIELDS
            if old[key].get(field) != new[key].get(field)
        }
        if fields:
            changes.append(
                {
                    "component_id": key,
                    "name": new[key]["display_name"],
                    "fields": fields,
                    "documented_reason": "reason unknown",
                }
            )
    return {
        "schema_version": SCHEMA_VERSION,
        "before_observed_at": before["observed_at"],
        "after_observed_at": after["observed_at"],
        "added": sorted(new.keys() - old.keys()),
        "retired_from_registry": sorted(old.keys() - new.keys()),
        "changes": changes,
        "failure_counts": {
            "before": sum(
                row.get("latest_deployment_status") in {"FAILED", "CRASHED"} for row in old.values()
            ),
            "after": sum(
                row.get("latest_deployment_status") in {"FAILED", "CRASHED"} for row in new.values()
            ),
        },
        "ci_failure_counts": {
            "before": sum(row.get("ci_status") == "failure" for row in old.values()),
            "after": sum(row.get("ci_status") == "failure" for row in new.values()),
        },
        "note": "Retired from registry means absent in the later snapshot, not confirmed deleted. Missing CI/freshness/permission evidence is unknown.",
    }


def render_diff(diff: dict[str, Any]) -> str:
    lines = [
        "# Control Tower snapshot diff",
        "",
        f"Before `{diff['before_observed_at']}` → after `{diff['after_observed_at']}`.",
        "",
        f"Added: {len(diff['added'])}; absent later: {len(diff['retired_from_registry'])}; changed: {len(diff['changes'])}. Latest FAILED/CRASHED deployment count: {diff['failure_counts']['before']} → {diff['failure_counts']['after']}. CI failures in supplied metadata: {diff['ci_failure_counts']['before']} → {diff['ci_failure_counts']['after']} (unknown if CI metadata was not supplied).",
        "",
        diff["note"],
        "",
    ]
    for heading, key in (
        ("Added", "added"),
        ("Absent later (verify before declaring retired)", "retired_from_registry"),
    ):
        lines += [f"## {heading}", ""]
        lines += [f"- `{value}`" for value in diff[key]] or ["- None observed"]
        lines.append("")
    lines += ["## Changed", ""]
    for change in diff["changes"]:
        lines.append(f"### {change['name']}")
        lines.append("")
        for field, values in change["fields"].items():
            lines.append(f"- `{field}`: `{values['before']}` → `{values['after']}`")
        lines.append(f"- Documented reason: {change['documented_reason']}")
        lines.append("")
    if not diff["changes"]:
        lines.append("No changed fields in the available evidence.\n")
    return "\n".join(lines)


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_bytes(
        (json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    )


def capture_github(repos: list[str]) -> dict[str, Any]:
    """Fetch bounded public metadata; omit bodies, emails, secrets and API errors."""
    token = os.getenv("GITHUB_TOKEN")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "quantbet-control-tower-v1"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    def fetch(url: str) -> Any:
        request = Request(url, headers=headers)
        with urlopen(request, timeout=15) as response:
            payload = response.read(2_000_001)
        if len(payload) > 2_000_000:
            raise ValueError("GitHub response exceeded bounded size")
        return json.loads(payload)

    snapshots = []
    for repo in repos:
        root = f"https://api.github.com/repos/{repo}"
        item: dict[str, Any] = {
            "full_name": repo,
            "commits": [],
            "pull_requests": [],
            "workflow_runs": [],
            "status": "ok",
        }
        try:
            for commit in fetch(root + "/commits?per_page=5"):
                data = commit.get("commit") or {}
                title = (data.get("message") or "").splitlines()[0][:180]
                item["commits"].append(
                    {
                        "sha": commit.get("sha"),
                        "at": _iso((data.get("committer") or {}).get("date")),
                        "title": title,
                        "url": commit.get("html_url"),
                    }
                )
            for pr in fetch(root + "/pulls?state=all&per_page=5"):
                item["pull_requests"].append(
                    {
                        "number": pr.get("number"),
                        "title": (pr.get("title") or "")[:180],
                        "state": pr.get("state"),
                        "merged_at": _iso(pr.get("merged_at")),
                        "merge_commit_sha": pr.get("merge_commit_sha"),
                        "url": pr.get("html_url"),
                    }
                )
            runs = fetch(root + "/actions/runs?per_page=5")
            for run in runs.get("workflow_runs", []):
                item["workflow_runs"].append(
                    {
                        "head_sha": run.get("head_sha"),
                        "status": run.get("status"),
                        "conclusion": run.get("conclusion"),
                        "created_at": _iso(run.get("created_at")),
                        "url": run.get("html_url"),
                    }
                )
        except (HTTPError, URLError, TimeoutError, ValueError) as error:
            item["status"] = "unavailable:" + type(error).__name__
        snapshots.append(item)
    return {
        "schema_version": SCHEMA_VERSION,
        "observed_at": datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z"),
        "repos": snapshots,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_subparsers(dest="command", required=True)
    capture = command.add_parser(
        "capture-railway", help="Explicit, bounded read-only Railway metadata capture"
    )
    capture.add_argument(
        "--project", action="append", required=True, help="Railway project ID (repeat, max 8)"
    )
    capture.add_argument("--environment", default="production")
    capture.add_argument("--out", type=Path, required=True)
    capture.add_argument("--at", help="Override UTC observation timestamp for reproducible tests")
    github_capture = command.add_parser(
        "capture-github", help="Bounded read-only commit, PR and CI metadata capture"
    )
    github_capture.add_argument(
        "--repo", action="append", required=True, help="owner/repo (repeat, max 8)"
    )
    github_capture.add_argument("--out", type=Path, required=True)
    build = command.add_parser(
        "build", help="Generate deterministic registry, report and dependency graph"
    )
    build.add_argument("--fixture", type=Path, required=True)
    build.add_argument(
        "--annotations", type=Path, default=Path("docs/control-tower/annotations.json")
    )
    build.add_argument(
        "--assessment", type=Path, default=Path("docs/control-tower/assessment.json")
    )
    build.add_argument(
        "--github-fixture", type=Path, help="Optional sanitized commit, PR and CI snapshot"
    )
    build.add_argument("--out", type=Path, required=True)
    diff = command.add_parser("diff", help="Compare two generated registry JSON snapshots")
    diff.add_argument("--before", type=Path, required=True)
    diff.add_argument("--after", type=Path, required=True)
    diff.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "capture-railway":
        if len(args.project) > 8 or any(not _allow(value, SAFE_NAME) for value in args.project):
            parser.error("Provide 1–8 explicit project IDs")
        at = args.at or datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
        if not _iso(at):
            parser.error("--at must be an ISO timestamp with timezone")
        services = []
        for project_id in args.project:
            result = subprocess.run(
                ["railway", "status", "-p", project_id, "-e", args.environment, "--json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
            )
            services += sanitize_railway_status(json.loads(result.stdout), project_id, at)
        data = {
            "schema_version": SCHEMA_VERSION,
            "observed_at": at,
            "source": "Railway CLI status --json; selected metadata only",
            "services": sorted(services, key=lambda row: (row["project_id"], row["service_id"])),
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        _write_json(args.out, data)
    elif args.command == "capture-github":
        if len(args.repo) > 8 or any(not _allow(value, SAFE_REPO) for value in args.repo):
            parser.error("Provide 1–8 owner/repo values")
        args.out.parent.mkdir(parents=True, exist_ok=True)
        _write_json(args.out, capture_github(args.repo))
    elif args.command == "build":
        registry = build_registry(
            _load(args.fixture),
            _load(args.annotations),
            _load(args.github_fixture) if args.github_fixture else None,
        )
        assessment = _load(args.assessment)
        args.out.mkdir(parents=True, exist_ok=True)
        _write_json(args.out / "inventory.v1.json", registry)
        (args.out / "CONTROL_TOWER.md").write_bytes(
            render_inventory(registry, assessment).encode("utf-8")
        )
        (args.out / "architecture.mmd").write_bytes(render_graph(registry).encode("utf-8"))
    else:
        result = diff_registries(_load(args.before), _load(args.after))
        args.out.mkdir(parents=True, exist_ok=True)
        _write_json(args.out / "snapshot_diff.v1.json", result)
        (args.out / "SNAPSHOT_DIFF.md").write_bytes(render_diff(result).encode("utf-8"))


if __name__ == "__main__":
    main()
