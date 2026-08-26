#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
from typing import Any

VERSION = "gen11-intent-authority-routing-r1"
SCHEMA_VERSION = 1

INTENTS = (
    "architecture_design",
    "implementation_change",
    "debugging_diagnosis",
    "evaluation_benchmarking",
    "lifecycle_recovery",
    "security_containment",
    "historical_replay",
)

COMPILER_KIND = {
    "architecture_design": "explanation_architecture",
    "implementation_change": "code_change_planning",
    "debugging_diagnosis": "debugging",
    "evaluation_benchmarking": "evaluation",
    "lifecycle_recovery": "lifecycle_recovery",
    "security_containment": "lifecycle_recovery",
    "historical_replay": "explanation_architecture",
}

AUTHORITY_BY_INTENT = {
    "architecture_design": {"architecture_source"},
    "implementation_change": {"source_implementation", "validation_regression"},
    "debugging_diagnosis": {"source_implementation", "failure_lineage"},
    "evaluation_benchmarking": {"benchmark_evaluator", "validation_regression"},
    "lifecycle_recovery": {"lifecycle_state", "recovery_lkg", "security_containment"},
    "security_containment": {"security_containment"},
    "historical_replay": {"historical_version_scope", "causal_history"},
}
ALWAYS_AUTHORITIES = {"guest_security_boundary", "operational_identity"}
ALL_AUTHORITIES = ALWAYS_AUTHORITIES | set().union(*AUTHORITY_BY_INTENT.values())
SAFETY_CRITICAL_AUTHORITIES = {
    "guest_security_boundary", "operational_identity", "lifecycle_state", "recovery_lkg", "security_containment"
}


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha(value: Any) -> str:
    data = value if isinstance(value, bytes) else canonical(value)
    return hashlib.sha256(data).hexdigest()


def normalize_text(text: str) -> str:
    return " ".join(str(text).strip().split())


def _mask_quoted(text: str) -> str:
    # Quoted strings are data unless the surrounding action frame says otherwise.
    return re.sub(r"(['\"])(?:\\.|(?!\1).)*\1", " <quoted-literal> ", text)


def _operative_text(text: str) -> str:
    t = _mask_quoted(normalize_text(text)).lower()
    # Explicit vocabulary/example tails are negative controls, not requested actions.
    for marker in ("irrelevant vocabulary sample only:", "vocabulary sample only:", "literal vocabulary only:"):
        if marker in t:
            t = t.split(marker, 1)[0]
    return t


def _negated_intents(text: str) -> tuple[set[str], list[dict[str, Any]]]:
    t = _mask_quoted(normalize_text(text)).lower()
    blocked: set[str] = set()
    features: list[dict[str, Any]] = []
    spans = []
    for m in re.finditer(r"\b(?:do not|don't|without|no)\b\s+([^.;]+)", t):
        spans.append(m.group(0))
    if "not root-cause debugging" in t or "not root cause debugging" in t:
        spans.append("not root-cause debugging")
    if "not root-cause" in t and "debug" in t:
        spans.append("not root-cause debugging")
    if "not root-cause debugging" in t or "not root cause debugging" in t:
        blocked.add("debugging_diagnosis")
    for span in spans:
        local: set[str] = set()
        if re.search(r"\b(restart|reboot|roll ?back|rollback|promot|recover|restore|lifecycle|accepted state|recovery state)\w*\b", span):
            local.add("lifecycle_recovery")
        if re.search(r"\b(containment|live policy|host access|host control|private network|security action)\b", span):
            local.add("security_containment")
        if re.search(r"\b(implement|edit|modify|patch|refactor|source|code|touch source)\w*\b", span):
            local.add("implementation_change")
        if re.search(r"\b(debug|diagnos|investigat|root[- ]cause|trace failure)\w*\b", span):
            local.add("debugging_diagnosis")
        if re.search(r"\b(evaluat|score|rerun|benchmark evaluation|run benchmark)\w*\b", span):
            local.add("evaluation_benchmarking")
        if re.search(r"\b(design|architect|propos|specif|diagram)\w*\b", span):
            local.add("architecture_design")
        if "runtime changes" in span or "live state" in span or "current state" in span:
            local.update({"lifecycle_recovery", "security_containment"})
        blocked.update(local)
        for intent in sorted(local):
            features.append({"intent": intent, "feature": "explicit_negation", "evidence": span[:220]})
    return blocked, features


def _add(features: list[dict[str, Any]], candidates: set[str], intent: str, feature: str, evidence: str) -> None:
    candidates.add(intent)
    features.append({"intent": intent, "feature": feature, "evidence": evidence[:220]})


def _detect_actions(text: str) -> tuple[set[str], set[str], list[dict[str, Any]], dict[str, Any]]:
    t = _operative_text(text)
    blocked, neg_features = _negated_intents(text)
    candidates: set[str] = set()
    features: list[dict[str, Any]] = list(neg_features)

    # Architecture/design requires an actual design/explanation action, not a design noun.
    for pattern, label in (
        (r"(?:^|[.;:]|\bthen\b)\s*(design|architect|propose|specify)\b|\b(design|architect|propose|specify)\s+(?:an?|the|this|how|and\s+implement)\b", "design_action"),
        (r"\b(diagram)\b", "diagram_action"),
    ):
        m = re.search(pattern, t)
        if m and "architecture_design" not in blocked:
            _add(features, candidates, "architecture_design", label, m.group(0))
            break

    # Implementation is source/code mutation. A bare 'fix' is accepted when code-ish context exists;
    # an ambiguous live safety 'fix' is handled conservatively below.
    impl = re.search(r"\b(implement|patch|refactor|edit|modify|update|add support|change the code|change source|code change|source change)\b|\bchange\b[^.;]{0,60}(?:\.py\b|/opt/|source|code)", t)
    fix = re.search(r"\bfix\b", t)
    codeish = bool(re.search(r"(?:/[^ ]+|\b\w+\.py\b|\b(code|source|module|parser|function|class|unit tests?|tests?)\b)", t))
    if "implementation_change" not in blocked and (impl or (fix and codeish)):
        m = impl or fix
        _add(features, candidates, "implementation_change", "source_mutation_action", m.group(0) if m else "source change")

    dbg = re.search(r"\b(debug|diagnose|investigate)\b|\b(identify|find) (?:the )?root cause\b|\bwhy\b[^.;]{0,100}\b(fail|failed|failure)\b", t)
    if dbg and "debugging_diagnosis" not in blocked:
        _add(features, candidates, "debugging_diagnosis", "diagnosis_action", dbg.group(0))

    ev = re.search(
        r"\b(evaluate|score)\b|\brun\b[^.;]{0,80}\bbenchmark(?:_gen\d+)?\b|\bbenchmark\s+(?:it|this|the routing|the implementation)\b|\bacceptance scoring\b",
        t,
    )
    if ev and "evaluation_benchmarking" not in blocked:
        _add(features, candidates, "evaluation_benchmarking", "evaluation_action", ev.group(0))

    life = re.search(r"\b(restart|reboot|promote)\b|\broll ?back\b|\brecover to\b|\brestore (?:last-known-good|last known good|lkg)\b|\bactivate it\b|\baccept[- ]current\b", t)
    if life and "lifecycle_recovery" not in blocked:
        _add(features, candidates, "lifecycle_recovery", "live_lifecycle_action", life.group(0))

    security_target = bool(re.search(r"\b(containment|security|host control sockets?|host sockets?|private[- ]network|private network|host access|authority boundary)\b", t))
    sec = re.search(r"\b(audit|inspect|verify|block|revoke|contain|isolate|harden)\b", t) if security_target else None
    if sec and "security_containment" not in blocked:
        _add(features, candidates, "security_containment", "live_security_action", sec.group(0))

    hist = re.search(r"\b(reconstruct|replay)\b|\bversion[- ]pinned\b|\bas of\b[^.;]{0,80}\b(accepted|snapshot|generation|gen\d+)\b|\bhistorical (?:evidence view|behavior|lineage|version)\b", t)
    if hist:
        _add(features, candidates, "historical_replay", "historical_scope_action", hist.group(0))

    # Explanation is architectural only when it is the terminal request, not a subordinate phrase
    # attached to debug/evaluate/history.
    explain = re.match(r"^(explain|describe|show how)\b", t)
    if explain and "architecture_design" not in blocked and not (candidates & {"implementation_change", "debugging_diagnosis", "evaluation_benchmarking", "lifecycle_recovery", "security_containment", "historical_replay"}):
        _add(features, candidates, "architecture_design", "architecture_explanation_action", explain.group(0))

    ambiguity = {
        "ambiguous": False,
        "safety_relevant": False,
        "conservative_route": False,
        "conflicts": [],
    }
    safety_nouns = {x for x in ("recovery" if "recovery" in t else None, "security" if "security" in t else None) if x}
    ambiguous_fix = bool(fix and "live" in t and "as needed" in t and safety_nouns and not codeish and not life)
    if ambiguous_fix:
        ambiguity.update({
            "ambiguous": True,
            "safety_relevant": True,
            "conservative_route": True,
            "conflicts": ["text does not distinguish source repair from live lifecycle/security remediation"],
        })
        if "implementation_change" not in blocked:
            _add(features, candidates, "implementation_change", "conservative_ambiguous_fix", "fix ... live ... as needed")
        if "recovery" in safety_nouns and "lifecycle_recovery" not in blocked:
            _add(features, candidates, "lifecycle_recovery", "conservative_live_recovery", "live recovery issue")
        if "security" in safety_nouns and "security_containment" not in blocked:
            _add(features, candidates, "security_containment", "conservative_live_security", "live security issue")

    # If explicit design and implementation coexist, both are real. Incidental design vocabulary
    # was never admitted because design requires an action verb.
    return candidates, blocked, features, ambiguity


def _primary(candidates: set[str]) -> tuple[str, list[str]]:
    rules: list[str] = []
    if not candidates:
        rules.append("no explicit mutation/diagnosis/evaluation/lifecycle/security/history action; conservative architecture explanation fallback")
        return "architecture_design", rules
    # Live safety effects dominate because selecting too little authority would be unsafe.
    for intent, rule in (
        ("lifecycle_recovery", "explicit/conservative live lifecycle effect outranks lower-authority actions"),
        ("security_containment", "explicit live containment effect outranks design/debug/source context"),
        ("implementation_change", "explicit source mutation is terminal action over motivating design/evaluation/failure vocabulary"),
        ("debugging_diagnosis", "explicit diagnosis outranks incidental benchmark/design/history vocabulary"),
        ("evaluation_benchmarking", "explicit evaluator/benchmark action outranks incidental failure vocabulary"),
        ("historical_replay", "version-pinned reconstruction is terminal action when no stronger current action exists"),
        ("architecture_design", "explicit design/explanation action selected"),
    ):
        if intent in candidates:
            rules.append(rule)
            return intent, rules
    raise AssertionError("unreachable intent precedence")


def _obligations(authority_classes: set[str]) -> list[dict[str, Any]]:
    specs = {
        "guest_security_boundary": ("authority_security", True),
        "operational_identity": ("operational_identity", True),
        "architecture_source": ("source_or_generation", False),
        "source_implementation": ("source", False),
        "validation_regression": ("validation_regression_evaluator", False),
        "failure_lineage": ("regression_or_causal_evidence", False),
        "benchmark_evaluator": ("benchmark_validation_or_evaluator", False),
        "lifecycle_state": ("build_state_recovery_or_service", True),
        "recovery_lkg": ("recovery_build_or_operational_identity", True),
        "security_containment": ("authority_security", True),
        "historical_version_scope": ("version_pinned_scope", False),
        "causal_history": ("causal_or_historical_source", False),
    }
    return [
        {"authority_class": a, "evidence_requirement": specs[a][0], "safety_critical": specs[a][1]}
        for a in sorted(authority_classes)
    ]


def route_task(text: str) -> dict[str, Any]:
    normalized = normalize_text(text)
    candidates, blocked, features, ambiguity = _detect_actions(normalized)
    primary, precedence = _primary(candidates)
    if primary not in candidates:
        candidates.add(primary)
    secondary = sorted(x for x in candidates if x != primary)
    authorities = set(ALWAYS_AUTHORITIES)
    for intent in candidates:
        authorities.update(AUTHORITY_BY_INTENT[intent])
    # A pure historical reconstruction must not acquire architecture authority solely from fallback prose.
    if primary == "historical_replay" and "architecture_design" not in candidates:
        authorities.discard("architecture_source")
    proof_core = {
        "schema_version": SCHEMA_VERSION,
        "router_version": VERSION,
        "task_text": normalized,
        "task_hash": hashlib.sha256(normalized.encode()).hexdigest(),
        "detected_primary_intent": primary,
        "secondary_intents": secondary,
        "detected_intents": sorted(candidates),
        "suppressed_by_explicit_negation": sorted(blocked),
        "decisive_evidence_features": sorted(features, key=lambda x: (x["intent"], x["feature"], x["evidence"])),
        "precedence_rules_applied": precedence,
        "required_authority_classes": sorted(authorities),
        "mandatory_evidence_obligations": _obligations(authorities),
        "evidence_explicitly_not_required": sorted(ALL_AUTHORITIES - authorities),
        "ambiguity_conflict_state": ambiguity,
        "compiler_task_kind": COMPILER_KIND[primary],
        "historical_scope": "task-requested-version-pinned" if "historical_replay" in candidates else None,
        "fail_closed": False,
    }
    proof = copy.deepcopy(proof_core)
    proof["routing_digest"] = sha(proof_core)
    return proof


def _record_matches(authority_class: str, rec: dict[str, Any]) -> bool:
    kind = str(rec.get("kind") or "")
    eid = str(rec.get("evidence_id") or "")
    if authority_class == "guest_security_boundary": return kind == "authority_security" or eid.startswith("authority:guest-security")
    if authority_class == "operational_identity": return kind == "operational_identity" or eid == "operational:accepted-identity"
    if authority_class == "architecture_source": return kind in {"source", "generation", "authority_boundary"}
    if authority_class == "source_implementation": return kind == "source"
    if authority_class == "validation_regression": return kind in {"validation", "regression", "evaluator", "benchmark_artifact"}
    if authority_class == "failure_lineage": return kind in {"regression", "causal_evidence"}
    if authority_class == "benchmark_evaluator": return kind in {"validation", "evaluator", "benchmark_artifact"}
    if authority_class == "lifecycle_state": return kind in {"build_state", "recovery", "service"}
    if authority_class == "recovery_lkg": return kind in {"recovery", "build_state", "operational_identity"}
    if authority_class == "security_containment": return kind == "authority_security"
    if authority_class == "historical_version_scope": return False
    if authority_class == "causal_history": return kind in {"causal_evidence", "generation", "source", "evidence_artifact"}
    return False


def apply_route_to_packet(packet: dict[str, Any], route: dict[str, Any]) -> dict[str, Any]:
    """Bind a frozen routing proof to a Gen8 packet before Gen9 minimization.

    Existing evidence is upgraded to required/Tier-1 when it witnesses a routed obligation. Safety-critical
    route obligations missing from the compiler packet fail closed; noncritical misses remain explicit audit
    findings and may be satisfied by epoch-level historical scope or later bounded selection.
    """
    out = copy.deepcopy(packet)
    expected = route_task(str(out.get("task_text") or ""))
    if expected.get("routing_digest") != route.get("routing_digest"):
        out["fail_closed"] = True
        out.setdefault("uncertainties", []).append({"critical": True, "reason": "Gen11 routing proof/task mismatch"})
        out["intent_routing"] = copy.deepcopy(route)
        return out
    out["compiler_packet_digest_pre_route"] = out.get("packet_digest")
    out["task_kind"] = route["compiler_task_kind"]
    out.setdefault("normalized_task", {})["task_kind"] = route["compiler_task_kind"]
    out["normalized_task"]["gen11_primary_intent"] = route["detected_primary_intent"]
    out["normalized_task"]["gen11_secondary_intents"] = list(route["secondary_intents"])
    out["intent_routing"] = copy.deepcopy(route)

    records = [copy.deepcopy(r) for r in (out.get("selected_evidence_records") or [])]
    witnesses: dict[str, list[str]] = {}
    for authority_class in route.get("required_authority_classes") or []:
        matched = [r for r in records if _record_matches(str(authority_class), r)]
        if authority_class == "source_implementation":
            matched = [r for r in matched if bool(r.get("required")) or "Top deterministic task match" in str(r.get("selection_reason") or "")]
        elif authority_class in {"validation_regression", "failure_lineage", "benchmark_evaluator"}:
            matched = [r for r in matched if bool(r.get("required")) or int(r.get("priority_tier", 9)) <= 1]
        ids = sorted(str(r.get("evidence_id")) for r in matched)
        witnesses[str(authority_class)] = ids
        if not ids:
            continue
        # Route obligations are not allowed to be silently pruned by Gen9.
        for r in records:
            if str(r.get("evidence_id")) in ids and authority_class not in {"architecture_source", "historical_version_scope", "causal_history"}:
                r["required"] = True
                r["priority_tier"] = min(1, int(r.get("priority_tier", 9)))
                reason = str(r.get("selection_reason") or "")
                r["selection_reason"] = (reason + f" Gen11 route obligation: {authority_class}.").strip()
    out["selected_evidence_records"] = sorted(records, key=lambda r: (int(r.get("priority_tier", 9)), str(r.get("evidence_id"))))
    out["route_obligation_witnesses"] = witnesses

    historical = "historical_version_scope" in set(route.get("required_authority_classes") or [])
    missing_critical = []
    missing_noncritical = []
    for obligation in route.get("mandatory_evidence_obligations") or []:
        cls = str(obligation.get("authority_class"))
        if cls == "historical_version_scope" and historical:
            continue
        if witnesses.get(cls):
            continue
        if obligation.get("safety_critical"):
            missing_critical.append(cls)
        else:
            missing_noncritical.append(cls)
    if missing_critical:
        out["fail_closed"] = True
        out.setdefault("uncertainties", []).append({"critical": True, "reason": "missing Gen11 safety-critical routed authority witnesses", "authority_classes": missing_critical})
    out["route_unmet_noncritical_obligations"] = missing_noncritical
    if (route.get("ambiguity_conflict_state") or {}).get("conservative_route"):
        out.setdefault("uncertainties", []).append({"critical": False, "reason": "safety-relevant intent ambiguity conservatively routed with stronger authority", "routing_digest": route.get("routing_digest")})

    # Keep Gen8/Gen9 convenience indexes coherent after route upgrades.
    selected = out["selected_evidence_records"]
    out["memories"] = [r["evidence_id"] for r in selected if r.get("kind") == "procedural_memory"]
    out["causal_evidence"] = [r["evidence_id"] for r in selected if r.get("kind") == "causal_evidence"]
    out["regressions"] = [r["evidence_id"] for r in selected if r.get("kind") == "regression"]
    out["validations"] = [r["evidence_id"] for r in selected if r.get("kind") in {"validation", "evaluator", "benchmark_artifact"}]
    out["recovery_requirements"] = [r["evidence_id"] for r in selected if r.get("kind") in {"recovery", "build_state", "service"}]
    out["authority_security_requirements"] = [r["evidence_id"] for r in selected if int(r.get("priority_tier", 9)) == 0 and r.get("kind") in {"authority_security", "operational_identity", "contradiction_warning"}]
    material = {k: v for k, v in out.items() if k not in {"packet_digest", "gen11_routed_packet_digest"}}
    out["packet_digest"] = sha(material)
    out["gen11_routed_packet_digest"] = out["packet_digest"]
    return out


def selftest() -> dict[str, Any]:
    cases = [
        ("Design an architecture for the router; do not implement it.", "architecture_design"),
        ("Implement the parser in task_routing.py; do not restart anything.", "implementation_change"),
        ("Debug why the benchmark failed; do not rerun it.", "debugging_diagnosis"),
        ("Run and evaluate benchmark_gen10.py against its scoring criteria.", "evaluation_benchmarking"),
        ("Restart the service and recover to LKG if needed.", "lifecycle_recovery"),
        ("Audit containment and block an exposed host control socket.", "security_containment"),
        ("Reconstruct the version-pinned Gen7 historical evidence view.", "historical_replay"),
        ("Patch recovery code; do not restart, roll back, or change accepted state.", "implementation_change"),
    ]
    checks = []
    for i, (task, primary) in enumerate(cases):
        a = route_task(task); b = route_task(task)
        checks.append({"name": f"case_{i}_primary", "ok": a["detected_primary_intent"] == primary, "detail": a["detected_primary_intent"]})
        checks.append({"name": f"case_{i}_deterministic", "ok": a["routing_digest"] == b["routing_digest"], "detail": a["routing_digest"]})
    return {"version": VERSION, "passed": sum(1 for x in checks if x["ok"]), "total": len(checks), "checks": checks}


def main() -> None:
    ap = argparse.ArgumentParser(description="Gen11 deterministic task-intent and authority router")
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd")
    p = sub.add_parser("route"); p.add_argument("task")
    args = ap.parse_args()
    if args.selftest:
        out = selftest(); print(json.dumps(out, indent=2, sort_keys=True)); raise SystemExit(0 if out["passed"] == out["total"] else 1)
    if args.cmd != "route": ap.error("route command required")
    print(json.dumps(route_task(args.task), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
