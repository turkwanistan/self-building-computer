from __future__ import annotations

THRESHOLD = 10
REDUNDANT_THRESHOLD = 20
REQUIRE_EVIDENCE = True
ALLOW_STALE = False
TRUST_SOURCE = "observed"
FAIL_CLOSED = True
NEGATIVE_CONTROL_ENABLED = True
NEGATIVE_CONTROL_EXPECTED = False
WEIGHTS = {"threshold": 3, "threshold_redundant": 3, "evidence": 3, "freshness": 3, "negative_control": 3}
PASS_SCORE = 9


def evaluate(candidate):
    observed = candidate.get("observed")
    declared = candidate.get("declared", observed)
    value = observed if TRUST_SOURCE == "observed" else declared
    checks = {}
    checks["threshold"] = value <= THRESHOLD  # CHECK_THRESHOLD_SENTINEL
    checks["threshold_redundant"] = value <= REDUNDANT_THRESHOLD  # CHECK_REDUNDANT_THRESHOLD_SENTINEL
    checks["evidence"] = (not REQUIRE_EVIDENCE) or ("evidence" in candidate)  # CHECK_EVIDENCE_SENTINEL
    checks["freshness"] = (candidate.get("evidence_state") == "fresh") or ALLOW_STALE  # CHECK_FRESHNESS_SENTINEL
    checks["negative_control"] = (not NEGATIVE_CONTROL_ENABLED) or (candidate.get("negative_control", False) == NEGATIVE_CONTROL_EXPECTED)  # CHECK_NEGATIVE_CONTROL_SENTINEL
    critical_failures = sorted(k for k, ok in checks.items() if not ok)
    score = sum(WEIGHTS[k] for k, ok in checks.items() if ok)
    score_pass = score >= PASS_SCORE
    ok = (not critical_failures and score_pass) if FAIL_CLOSED else score_pass
    return {"ok": ok, "checks": checks, "checks_run": sorted(checks), "critical_failures": critical_failures,
            "score": score, "score_pass": score_pass, "selected_value": value}
