from __future__ import annotations

import math
from typing import Any

ALLOWED_FAMILIES = {"PULSE", "SWEEP", "VOLLEY"}


def _finite(v: Any) -> float:
    x = float(v)
    if not math.isfinite(x):
        raise ValueError("non-finite numeric value")
    return x


def evaluate_telemetry_profile(candidate: dict[str, Any], telemetry: dict[str, Any]) -> dict[str, Any]:
    checks = [
        "source_lineage", "duration", "beat_count", "bar_count", "section_count",
        "section_pattern", "largest_transition", "strongest_bars", "integrity",
    ]
    failures: list[str] = []
    source = telemetry.get("source") or {}
    bars = telemetry.get("bars") or []
    beats = telemetry.get("beats") or []
    sections = telemetry.get("sections") or []
    expected_sha = source.get("sha256")
    expected_duration = _finite(source.get("duration_seconds"))
    if candidate.get("source_sha256") != expected_sha:
        failures.append("source_lineage")
    if abs(_finite(candidate.get("duration_seconds")) - expected_duration) > 1e-6:
        failures.append("duration")
    if candidate.get("beat_count") != len(beats): failures.append("beat_count")
    if candidate.get("bar_count") != len(bars): failures.append("bar_count")
    if candidate.get("section_count") != len(sections): failures.append("section_count")
    pattern = "-".join(str(s.get("label", "")) for s in sections)
    if candidate.get("section_pattern") != pattern: failures.append("section_pattern")
    transitions = [
        {"section_index": int(s.get("index", i)), "time": round(_finite(s.get("start")), 6),
         "label": str(s.get("label", "")), "novelty": round(_finite(s.get("novelty", 0)), 6)}
        for i, s in enumerate(sections)
    ]
    expected_transition = max(transitions, key=lambda x: (x["novelty"], -x["section_index"])) if transitions else None
    if candidate.get("largest_transition") != expected_transition: failures.append("largest_transition")
    strongest = sorted(
        [{"index": int(b.get("index", i)), "start": round(_finite(b.get("start")), 6),
          "average_energy": round(_finite(b.get("average_energy", 0)), 6)} for i, b in enumerate(bars)],
        key=lambda x: (-x["average_energy"], x["index"]),
    )[:3]
    if candidate.get("strongest_bars") != strongest: failures.append("strongest_bars")
    integrity = candidate.get("integrity") or {}
    if integrity != {"ordered_beats": True, "ordered_bars": True, "ordered_sections": True, "bar_references_valid": True}:
        failures.append("integrity")
    return {
        "ok": not failures,
        "critical_failures": failures,
        "checks_run": checks,
        "observed": {"beat_count": len(beats), "bar_count": len(bars), "section_count": len(sections),
                     "largest_transition": expected_transition, "strongest_bars": strongest},
    }


def evaluate_songboss_audit(candidate: dict[str, Any], plan: dict[str, Any], telemetry_profile: dict[str, Any]) -> dict[str, Any]:
    checks = [
        "source_lineage", "duration_lineage", "attack_count", "observed_evidence_coverage",
        "observed_family_grammar", "observed_timing", "observed_safety", "candidate_consistency",
    ]
    failures: list[str] = []
    meta = plan.get("metadata") or {}
    attacks = plan.get("attacks") or []
    validation = plan.get("validation") or {}
    source_sha = meta.get("source_sha256")
    duration = _finite(meta.get("duration"))
    if telemetry_profile.get("source_sha256") != source_sha or candidate.get("source_sha256") != source_sha:
        failures.append("source_lineage")
    if abs(_finite(telemetry_profile.get("duration_seconds")) - duration) > 0.05 or abs(_finite(candidate.get("duration_seconds")) - duration) > 1e-6:
        failures.append("duration_lineage")
    if candidate.get("attack_count") != len(attacks): failures.append("attack_count")
    evidence_ok = 0
    families = {x: 0 for x in sorted(ALLOWED_FAMILIES)}
    unsupported: list[str] = []
    timing_violations = 0
    for attack in attacks:
        ev = attack.get("source_evidence")
        if isinstance(ev, dict) and ev and all(0 <= _finite(v) <= 1 for v in ev.values()): evidence_ok += 1
        fam = str(attack.get("family", ""))
        if fam in families: families[fam] += 1
        else: unsupported.append(fam or "<missing>")
        tele = _finite(attack.get("telegraph_start")); start = _finite(attack.get("active_start")); end = _finite(attack.get("active_end"))
        if not (0 <= tele <= start < end <= duration + 1e-6): timing_violations += 1
    observed_coverage = 1.0 if not attacks else evidence_ok / len(attacks)
    # CHECK:observed_evidence_coverage
    if observed_coverage < 1.0:
        failures.append("observed_evidence_coverage")
    if unsupported: failures.append("observed_family_grammar")
    if timing_violations: failures.append("observed_timing")
    safety_ok = bool(validation.get("reachability_pass")) and bool(validation.get("pattern_invariants_pass")) and int(validation.get("witness_collision_count", 0)) == 0
    if not safety_ok: failures.append("observed_safety")
    candidate_consistent = (
        candidate.get("family_counts") == families
        and candidate.get("unsupported_families") == sorted(set(unsupported))
        and candidate.get("timing_violations") == timing_violations
        and abs(_finite(candidate.get("causality_evidence_coverage")) - observed_coverage) <= 1e-6
        and candidate.get("verdict") == ("PASS" if not failures else "FAIL")
    )
    if not candidate_consistent: failures.append("candidate_consistency")
    return {
        "ok": not failures,
        "critical_failures": failures,
        "checks_run": checks,
        "observed": {"attack_count": len(attacks), "evidence_coverage": round(observed_coverage, 6),
                     "family_counts": families, "unsupported_families": sorted(set(unsupported)),
                     "timing_violations": timing_violations, "safety_ok": safety_ok},
    }
