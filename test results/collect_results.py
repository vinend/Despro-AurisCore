"""Consolidate AurisCore test outputs and create a SHA-256 artifact manifest."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree


RESULTS_DIR = Path(__file__).resolve().parent


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def relative(path: Path) -> str:
    return path.relative_to(RESULTS_DIR).as_posix()


def collect_junit() -> dict:
    path = RESULTS_DIR / "ai-pytest-junit.xml"
    root = ElementTree.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    if suite is None:
        raise ValueError("JUnit XML contains no testsuite")

    cases = []
    for case in suite.findall("testcase"):
        status = "passed"
        details = None
        for tag in ("failure", "error", "skipped"):
            child = case.find(tag)
            if child is not None:
                status = tag
                details = child.get("message") or (child.text or "").strip()
                break
        cases.append(
            {
                "classname": case.get("classname"),
                "name": case.get("name"),
                "duration_seconds": float(case.get("time", "0")),
                "status": status,
                "details": details,
            }
        )

    return {
        "source": relative(path),
        "name": suite.get("name"),
        "tests": int(suite.get("tests", "0")),
        "failures": int(suite.get("failures", "0")),
        "errors": int(suite.get("errors", "0")),
        "skipped": int(suite.get("skipped", "0")),
        "duration_seconds": float(suite.get("time", "0")),
        "test_cases": cases,
    }


def collect_model_artifacts() -> list[dict]:
    names = {
        "baseline_metrics.json": "svm_development",
        "cnn_metrics.json": "cnn_development",
        "final_holdout_metrics.json": "locked_holdout",
        "holdout_lock.json": "holdout_identity",
    }
    artifacts = []
    for path in sorted((RESULTS_DIR / "raw" / "pytest-temp").rglob("*.json")):
        artifact_type = names.get(path.name)
        if artifact_type is None:
            continue
        artifacts.append(
            {
                "artifact_type": artifact_type,
                "source": relative(path),
                "data": read_json(path),
            }
        )
    return artifacts


def collect_audit() -> dict:
    path = RESULTS_DIR / "logs" / "web-npm-audit.json"
    audit = read_json(path)
    return {
        "source": relative(path),
        "metadata": audit.get("metadata", {}),
        "vulnerabilities": audit.get("vulnerabilities", {}),
    }


def write_consolidated() -> None:
    suite = read_json(RESULTS_DIR / "summary.json")
    mock = read_json(RESULTS_DIR / "runtime-mock-device.json")
    web = read_json(RESULTS_DIR / "runtime-web-http.json")
    junit = collect_junit()
    result = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall_passed": bool(
            suite["overall_passed"]
            and mock["passed"]
            and web["passed"]
            and junit["failures"] == 0
            and junit["errors"] == 0
        ),
        "scope": {
            "git_commit": suite["git_commit"],
            "git_branch": suite["git_branch"],
            "real_external_wav_count": suite["real_external_wav_count"],
            "clinical_performance_evaluated": False,
            "model_metrics_kind": "synthetic smoke-test metrics only",
        },
        "automated_gates": suite,
        "python_tests": junit,
        "runtime_checks": {
            "mock_device": mock,
            "web_http": web,
        },
        "model_artifacts": collect_model_artifacts(),
        "dependency_audit": collect_audit(),
        "environment": read_json(RESULTS_DIR / "metadata" / "environment.json"),
        "limitations": [
            "No real external WAV dataset was present, so no clinical model-performance claim can be made.",
            "SVM and CNN metrics were produced from small, separable synthetic fixtures and only verify pipeline behavior.",
            "The dependency audit is informational and reports known production dependency advisories.",
        ],
    }
    (RESULTS_DIR / "consolidated-metrics.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )


def write_manifest() -> None:
    manifest_path = RESULTS_DIR / "artifact-manifest.json"
    files = []
    for path in sorted(RESULTS_DIR.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files.append(
            {
                "path": relative(path),
                "bytes": path.stat().st_size,
                "sha256": digest,
            }
        )
    manifest = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "algorithm": "SHA-256",
        "file_count_excluding_manifest": len(files),
        "total_bytes_excluding_manifest": sum(item["bytes"] for item in files),
        "files": files,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    write_consolidated()
    write_manifest()
