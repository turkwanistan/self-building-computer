from __future__ import annotations

import ast
import json
from pathlib import Path


EXPECTED_SCHEMA = "195c410b85d40f4cfe65ef7eb8baa0463a32e93882fd9d39c0045e6518cd2913"


def test_evolution_python_sources_parse():
    for path in [Path("host/evolutionctl.py"), Path("host/verify-evolution-mcp.py")]:
        ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_noop_candidate_manifest_is_authority_neutral():
    payload = json.loads(Path("candidate/release.json").read_text(encoding="utf-8"))
    assert payload["cycle_id"] == "noop-lifecycle-001"
    assert payload["kind"] == "NOOP_LIFECYCLE_DRILL"
    assert payload["authority_delta"] == "NONE"
    assert payload["expected_tool_count"] == 51
    assert payload["expected_tool_schema_sha256"] == EXPECTED_SCHEMA


def test_candidate_service_confinement_is_root_controlled_and_loopback_only():
    text = Path("host/bootstrap-evolution.sh").read_text(encoding="utf-8")
    for required in [
        "User=mcp",
        "NoNewPrivileges=true",
        "ProtectSystem=strict",
        "ProtectHome=true",
        "PrivateDevices=true",
        "CapabilityBoundingSet=",
        "RestrictAddressFamilies=AF_INET AF_INET6",
        "IPAddressDeny=any",
        "IPAddressAllow=localhost",
        "InaccessiblePaths=/etc/mcp-agent /var/lib/mcp-evolution /run /var/run",
    ]:
        assert required in text
    assert "127.0.0.1:8790" in Path("docs/BLUE_GREEN_LIFECYCLE.md").read_text(encoding="utf-8")


def test_staging_allowlist_does_not_execute_candidate_host_artifacts():
    text = Path("host/evolutionctl.py").read_text(encoding="utf-8")
    assert 'source_files(PROJECT, "mcp_frontend")' in text
    assert 'PROJECT / "pyproject.toml"' in text
    assert 'PROJECT / "candidate/release.json"' in text
    assert "deploy/install.sh" not in text
    assert "sudoers" not in text


def test_root_state_and_event_log_are_outside_project_tree():
    text = Path("host/evolutionctl.py").read_text(encoding="utf-8")
    assert 'Path("/var/lib/mcp-evolution")' in text
    assert 'Path("/etc/mcp-evolution")' in text
    assert 'Path("/opt/mcp/releases")' in text
    assert 'Path("/opt/mcp/guardrails/releases")' in text
    assert '"event_hash"' in text
    assert '"prev_hash"' in text


def test_emergency_generation_zero_fallback_is_preserved():
    control = Path("host/evolutionctl.py").read_text(encoding="utf-8")
    assert '"emergency_fallback_service": "mcp-agent.service"' in control
    assert 'systemctl("enable", "--now", "mcp-agent.service", check=False)' in control
