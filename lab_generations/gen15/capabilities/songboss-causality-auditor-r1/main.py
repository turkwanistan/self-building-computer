#!/usr/bin/env python3
import json, math, re, sys
ALLOWED=('PULSE','SWEEP','VOLLEY')
def fail(msg): raise ValueError(msg)
def finite(v,name):
    try:x=float(v)
    except Exception: fail(f"{name} must be numeric")
    if not math.isfinite(x): fail(f"{name} must be finite")
    return x

def audit(plan,profile=None):
    if not isinstance(plan,dict): fail('plan must be object')
    meta=plan.get('metadata') or {}; sha=str(meta.get('source_sha256',''))
    if not re.fullmatch(r'[0-9a-f]{64}',sha): fail('plan source sha256 invalid')
    duration=finite(meta.get('duration'),'plan duration')
    if duration<=0: fail('plan duration must be positive')
    lineage=None
    if profile is not None:
        if not isinstance(profile,dict): fail('telemetry_profile must be object')
        psha=str(profile.get('source_sha256',''))
        pdur=finite(profile.get('duration_seconds'),'profile duration_seconds')
        if psha!=sha or abs(pdur-duration)>0.05: fail('evaluator lineage mismatch')
        lineage=True
    attacks=plan.get('attacks'); segments=plan.get('segments'); setpieces=plan.get('set_pieces'); validation=plan.get('validation')
    if not isinstance(attacks,list) or not isinstance(segments,list) or not isinstance(setpieces,list) or not isinstance(validation,dict): fail('plan missing attacks/segments/set_pieces/validation')
    families={x:0 for x in ALLOWED}; unsupported=[]; timing=0; evidence_ok=0; findings=[]
    seen=set()
    for i,a in enumerate(attacks):
        if not isinstance(a,dict): fail('attack must be object')
        aid=str(a.get('id',f'#{i}'))
        if aid in seen: fail('duplicate attack id')
        seen.add(aid)
        fam=str(a.get('family',''))
        if fam in families: families[fam]+=1
        else: unsupported.append(fam or '<missing>')
        tele=finite(a.get('telegraph_start'),'telegraph_start'); start=finite(a.get('active_start'),'active_start'); end=finite(a.get('active_end'),'active_end')
        if not (0<=tele<=start<end<=duration+1e-6): timing+=1
        ev=a.get('source_evidence')
        if isinstance(ev,dict) and ev:
            valid=True
            for k,v in ev.items():
                x=finite(v,f'source_evidence.{k}')
                if not 0<=x<=1: valid=False
            if valid: evidence_ok+=1
        else: findings.append(f'attack {aid} lacks source evidence')
    if unsupported: findings.append('unsupported attack families: '+','.join(sorted(set(unsupported))))
    if timing: findings.append(f'{timing} attack timing violations')
    safety={'reachability_pass':bool(validation.get('reachability_pass')),'pattern_invariants_pass':bool(validation.get('pattern_invariants_pass')),'witness_collision_count':int(validation.get('witness_collision_count',0))}
    if not safety['reachability_pass']: findings.append('reachability failed')
    if not safety['pattern_invariants_pass']: findings.append('pattern invariants failed')
    if safety['witness_collision_count']!=0: findings.append('witness collisions present')
    for s in setpieces:
        bt=finite(s.get('boundary_time'),'set_piece.boundary_time'); st=finite(s.get('strength',0),'set_piece.strength')
        if not (0<=bt<=duration and 0<=st<=1): findings.append('invalid set-piece bounds')
    coverage=1.0 if not attacks else evidence_ok/len(attacks)
    if coverage<1: findings.append(f'causality evidence coverage {coverage:.3f}')
    return {'schema_version':'gen15.songboss-audit.v1','verdict':'PASS' if not findings else 'FAIL','source_sha256':sha,'duration_seconds':round(duration,6),'attack_count':len(attacks),'attack_rate_per_minute':round((len(attacks)*60/duration),6),'family_counts':families,'causality_evidence_coverage':round(coverage,6),'timing_violations':timing,'unsupported_families':sorted(set(unsupported)),'lineage_match':lineage,'safety':safety,'findings':findings}
try:
    x=json.load(sys.stdin)
    if not isinstance(x,dict) or set(x)-{'plan','telemetry_profile'} or 'plan' not in x: fail('invalid input keys')
    print(json.dumps(audit(x['plan'],x.get('telemetry_profile')),sort_keys=True,separators=(',',':')))
except Exception as e:
    print(str(e),file=sys.stderr); raise SystemExit(2)
