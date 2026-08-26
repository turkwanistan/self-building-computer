#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import secrets
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import Any

VERSION = "gen8-experiment-capsule-r1"
SCHEMA_VERSION = 1
SERVICE_WRAPPER_VERSION = "gen8-capsule-service-wrapper-r2"
CAPSULE_ROOT = pathlib.Path(os.environ.get("OPTIPLEX_CAPSULE_ROOT", "/var/tmp/optiplex-lab-capsules"))
OVERLAY_TARGETS = [
    pathlib.Path("/opt/optiplex-lab"),
    pathlib.Path("/etc/optiplex-lab"),
    pathlib.Path("/etc/systemd/system"),
    pathlib.Path("/var/lib/optiplex-lab"),
    pathlib.Path("/root"),
]
PROTECTED_FILES = [
    pathlib.Path("/etc/optiplex-lab/build.json"),
    pathlib.Path("/opt/optiplex-lab/server.py"),
    pathlib.Path("/var/lib/optiplex-lab/recovery/server.last-known-good.py"),
    pathlib.Path("/var/lib/optiplex-lab/capabilities/registry.json"),
    pathlib.Path("/var/lib/optiplex-lab/memory/registry.json"),
    pathlib.Path("/var/lib/optiplex-lab/regressions/registry.json"),
    pathlib.Path("/var/lib/optiplex-lab/traces/events.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/capabilities/provenance.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/memory/provenance.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/regressions/provenance.jsonl"),
    pathlib.Path("/var/lib/optiplex-lab/recovery/launcher-events.jsonl"),
]
PROTECTED_TREES = [
    pathlib.Path("/etc/systemd/system"),
    pathlib.Path("/var/lib/optiplex-lab/workflows"),
    pathlib.Path("/var/lib/optiplex-lab/workflow-graphs"),
]
AUDIT_APPEND_FILES = {
    "/var/lib/optiplex-lab/traces/events.jsonl",
    "/var/lib/optiplex-lab/capabilities/provenance.jsonl",
    "/var/lib/optiplex-lab/memory/provenance.jsonl",
    "/var/lib/optiplex-lab/regressions/provenance.jsonl",
    "/var/lib/optiplex-lab/recovery/launcher-events.jsonl",
}


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_path(path: pathlib.Path) -> str | None:
    try:
        return sha_bytes(path.read_bytes()) if path.is_file() else None
    except OSError:
        return None


def atomic_json(path: pathlib.Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile("w", dir=str(path.parent), delete=False, encoding="utf-8") as fh:
        fh.write(payload)
        tmp = pathlib.Path(fh.name)
    tmp.replace(path)


def tree_manifest(root: pathlib.Path) -> dict[str, Any]:
    items=[]
    if root.is_dir():
        for p in sorted(root.rglob("*"), key=lambda x:str(x)):
            rel=str(p.relative_to(root))
            try:
                if p.is_symlink(): items.append({"path":rel,"type":"symlink","target":os.readlink(p)})
                elif p.is_file(): items.append({"path":rel,"type":"file","bytes":p.stat().st_size,"sha256":sha_path(p)})
                elif p.is_dir(): items.append({"path":rel,"type":"dir"})
            except OSError as exc: items.append({"path":rel,"type":"error","error":type(exc).__name__})
    return {"path":str(root),"exists":root.exists(),"items":items,"digest":sha_bytes(canonical(items))}


def protected_manifest() -> dict[str, Any]:
    files=[]
    for p in PROTECTED_FILES:
        files.append({"path":str(p),"exists":p.exists(),"bytes":p.stat().st_size if p.is_file() else None,"sha256":sha_path(p)})
    trees=[tree_manifest(p) for p in PROTECTED_TREES]
    result={"version":"gen8-protected-state-manifest-r1","files":files,"trees":trees}
    result["digest"]=sha_bytes(canonical(result))
    return result


def compare_manifests(before: dict[str, Any], after: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    forbidden=[]; allowed_audit=[]
    bf={x["path"]:x for x in before.get("files",[])}; af={x["path"]:x for x in after.get("files",[])}
    for path in sorted(set(bf)|set(af)):
        b=bf.get(path); a=af.get(path)
        if b==a: continue
        if path in AUDIT_APPEND_FILES and b and a and b.get("exists") and a.get("exists") and isinstance(b.get("bytes"),int) and isinstance(a.get("bytes"),int) and a["bytes"]>=b["bytes"]:
            try:
                with pathlib.Path(path).open("rb") as fh: prefix=fh.read(b["bytes"])
                if sha_bytes(prefix)==b.get("sha256"):
                    allowed_audit.append({"path":path,"kind":"append_only_outer_audit","bytes_appended":a["bytes"]-b["bytes"],"before_sha256":b.get("sha256"),"after_sha256":a.get("sha256")})
                    continue
            except OSError:
                pass
        forbidden.append({"path":path,"kind":"file","before":b,"after":a})
    bt={x["path"]:x for x in before.get("trees",[])}; at={x["path"]:x for x in after.get("trees",[])}
    for path in sorted(set(bt)|set(at)):
        b=bt.get(path); a=at.get(path)
        if (b or {}).get("digest")!=(a or {}).get("digest"): forbidden.append({"path":path,"kind":"tree","before_digest":(b or {}).get("digest"),"after_digest":(a or {}).get("digest")})
    return forbidden, allowed_audit


def service_wrapper_text(state_file: pathlib.Path, job_dir: pathlib.Path) -> str:
    return f'''#!/bin/bash
set -euo pipefail
state={str(state_file)!r}
jobdir={str(job_dir)!r}
mkdir -p "$jobdir"
cmd=${{1:-}}
shift || true
getpid() {{ cat "$state" 2>/dev/null || echo 50001; }}
incpid() {{ p=$(getpid); echo $((p+1)) > "$state"; }}
simulate_restart() {{
  live=/opt/optiplex-lab/server.py
  lkg=/var/lib/optiplex-lab/recovery/server.last-known-good.py
  build=/etc/optiplex-lab/build.json
  if [[ -f "$live" && -f "$lkg" ]] && ! cmp -s "$live" "$lkg"; then
    bad=$(sha256sum "$live" | awk '{{print $1}}')
    cp -a "$lkg" "$live"
    restored=$(sha256sum "$live" | awk '{{print $1}}')
    /opt/optiplex-lab/venv/bin/python - "$build" "$bad" "$restored" <<'PY'
import datetime,json,pathlib,sys
p=pathlib.Path(sys.argv[1]); bad=sys.argv[2]; restored=sys.argv[3]
try:b=json.loads(p.read_text()) if p.exists() else {{}}
except Exception:b={{}}
b['recovery_state']='AUTO_ROLLED_BACK'; b['recovered_at']=datetime.datetime.now(datetime.timezone.utc).isoformat(); b['source_sha256']=restored
p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(b,indent=2)+'\\n')
log=pathlib.Path('/var/lib/optiplex-lab/recovery/launcher-events.jsonl'); log.parent.mkdir(parents=True,exist_ok=True)
with log.open('a') as f:f.write(json.dumps({{'timestamp':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event':'auto_rollback','bad_sha256':bad,'restored_sha256':restored}},separators=(',',':'))+'\\n')
PY
  fi
  incpid
}}
case "$cmd" in
  show)
    unit="${1:-}"
    if printf '%s\\n' "$@" | grep -q MainPID; then getpid; exit 0; fi
    if [[ -f "$jobdir/$unit" ]]; then cat "$jobdir/$unit"; exit 0; fi
    if printf '%s\\n' "$@" | grep -q ActiveState; then echo 'ActiveState=active'; echo 'ExecMainStatus=0'; exit 0; fi
    echo 'ActiveState=active'; exit 0;;
  cat)
    cat /etc/systemd/system/optiplex-lab-mcp.service 2>/dev/null || true; exit 0;;
  restart)
    if [[ "${1:-}" == "optiplex-lab-mcp.service" || "${1:-}" == "optiplex-lab-mcp" ]]; then simulate_restart; fi
    exit 0;;
  start)
    unit="${1:-}"
    if [[ "$unit" == "optiplex-lab-mcp.service" || "$unit" == "optiplex-lab-mcp" ]]; then exit 0; fi
    up="/etc/systemd/system/$unit"
    if [[ -f "$up" ]]; then
      exec_line=$(sed -n 's/^ExecStart=//p' "$up" | head -1)
      if [[ -n "$exec_line" ]]; then /bin/bash -c "$exec_line"; fi
    fi
    exit 0;;
  daemon-reload|stop|enable|disable|status)
    exit 0;;
  is-active) echo active; exit 0;;
  is-enabled) echo enabled; exit 0;;
  *)
    echo "capsule systemctl: unsupported command $cmd" >&2; exit 1;;
esac
'''


def systemd_run_wrapper_text(service_wrapper: pathlib.Path, job_dir: pathlib.Path) -> str:
    return f'''#!/bin/bash
set -euo pipefail
args=("$@")
jobdir={str(job_dir)!r}
mkdir -p "$jobdir"
unit=""
for a in "${{args[@]}}"; do case "$a" in --unit=*) unit="${{a#--unit=}}";; esac; done
# Lifecycle self-update schedules a delayed systemctl restart. Simulate it now.
for ((i=0;i<${{#args[@]}};i++)); do
  if [[ "${{args[$i]}}" == */systemctl || "${{args[$i]}}" == systemctl ]]; then
    {str(service_wrapper)!r} restart optiplex-lab-mcp.service
    exit 0
  fi
done
# For non-service transient work, execute the command after common systemd-run options.
cmd=()
seen=0
for a in "${{args[@]}}"; do
  if [[ $seen -eq 0 ]]; then
    case "$a" in
      --quiet|--collect|--wait|--pipe) continue;;
      --unit=*|--property=*|--on-active=*) continue;;
      --) seen=1; continue;;
      -*) continue;;
      *) seen=1; cmd+=("$a");;
    esac
  else cmd+=("$a"); fi
done
if [[ ${{#cmd[@]}} -eq 0 ]]; then exit 0; fi
set +e
"${{cmd[@]}}"
rc=$?
set -e
if [[ -n "$unit" ]]; then printf 'ActiveState=inactive\nExecMainStatus=%s\n' "$rc" > "$jobdir/$unit"; fi
exit 0
'''


def write_wrappers(run_dir: pathlib.Path) -> dict[str, Any]:
    bindir=run_dir/"bin"; bindir.mkdir(parents=True,exist_ok=True)
    state=run_dir/"service.pid"; state.write_text("50001\n")
    job_dir=run_dir/"service-jobs"; job_dir.mkdir(parents=True,exist_ok=True)
    systemctl=bindir/"systemctl"; systemctl.write_text(service_wrapper_text(state,job_dir)); systemctl.chmod(0o755)
    systemdrun=bindir/"systemd-run"; systemdrun.write_text(systemd_run_wrapper_text(systemctl,job_dir)); systemdrun.chmod(0o755)
    resolv=run_dir/"resolv.conf"
    try: resolv.write_text(pathlib.Path('/etc/resolv.conf').read_text())
    except OSError: resolv.write_text('nameserver 1.1.1.1\n')
    return {"systemctl":str(systemctl),"systemd_run":str(systemdrun),"service_state":str(state),"resolv_conf":str(resolv),
            "wrapper_sha256":sha_bytes(SERVICE_WRAPPER_VERSION.encode()),
            "wrapper_instance_sha256":sha_bytes(systemctl.read_bytes()+b"\0"+systemdrun.read_bytes())}


def shell_quote(s: str) -> str:
    import shlex
    return shlex.quote(s)


def namespace_script(run_dir: pathlib.Path, command: str, empty_paths: list[pathlib.Path], captures: list[pathlib.Path], wrappers: dict[str, Any]) -> str:
    export=run_dir/"export"
    lines=["#!/bin/bash","set -euo pipefail","mount --make-rprivate /"]
    for idx,target in enumerate(OVERLAY_TARGETS):
        lower=run_dir/f"lower-{idx}"; upper=run_dir/f"upper-{idx}"; work=run_dir/f"work-{idx}"
        lower.mkdir(parents=True,exist_ok=True); upper.mkdir(parents=True,exist_ok=True); work.mkdir(parents=True,exist_ok=True)
        lines += [
            f"mount --bind {shell_quote(str(target))} {shell_quote(str(lower))}",
            f"mount -o remount,bind,ro {shell_quote(str(lower))}",
            f"mount -t overlay overlay -o lowerdir={shell_quote(str(lower))},upperdir={shell_quote(str(upper))},workdir={shell_quote(str(work))} {shell_quote(str(target))}",
        ]
    lines += [
        "mount -t tmpfs -o mode=1777,nosuid,nodev tmpfs /tmp",
        "mount -t tmpfs -o mode=755,nosuid,nodev tmpfs /run",
        "mkdir -p /run/systemd/resolve",
        "touch /run/systemd/resolve/stub-resolv.conf",
        f"mount --bind {shell_quote(wrappers['resolv_conf'])} /run/systemd/resolve/stub-resolv.conf",
    ]
    # Bind service wrappers over real entrypoints in this mount namespace, including absolute callers.
    # The network namespace is intentionally inherited, so public internet remains available while /run
    # no longer exposes the accepted guest service-manager/control sockets.
    lines += [
        f"mount --bind {shell_quote(wrappers['systemctl'])} /usr/bin/systemctl",
        f"mount --bind {shell_quote(wrappers['systemd_run'])} /usr/bin/systemd-run",
    ]
    for p in empty_paths:
        lines += [f"mkdir -p {shell_quote(str(p))}",f"mount -t tmpfs -o nosuid,nodev tmpfs {shell_quote(str(p))}"]
    lines += [
        f"export PATH={shell_quote(str(run_dir/'bin'))}:$PATH",
        "export OPTIPLEX_EXPERIMENT_CAPSULE=1",
        f"export OPTIPLEX_CAPSULE_RUN_ID={shell_quote(run_dir.name)}",
        f"export OPTIPLEX_CAPSULE_RUN_DIR={shell_quote(str(run_dir))}",
        f"export OPTIPLEX_CAPSULE_EXPORT={shell_quote(str(export))}",
        f"mkdir -p {shell_quote(str(export/'captures'))}",
        "set +e",
        f"/bin/bash -lc {shell_quote(command)} > {shell_quote(str(export/'stdout.log'))} 2> {shell_quote(str(export/'stderr.log'))}",
        "rc=$?",
        "set -e",
    ]
    for p in captures:
        rel=str(p).lstrip("/")
        dst=export/"captures"/rel
        lines += [f"if [[ -e {shell_quote(str(p))} ]]; then mkdir -p {shell_quote(str(dst.parent))}; cp -a {shell_quote(str(p))} {shell_quote(str(dst))}; fi"]
    lines += [
        f"/opt/optiplex-lab/venv/bin/python - <<'PY'\nimport json,pathlib,os\np=pathlib.Path({str(export/'child-result.json')!r}); p.write_text(json.dumps({{'exit_code':int(os.environ.get('CAPSULE_CHILD_RC','0'))}},indent=2)+'\\n')\nPY",
        "exit $rc",
    ]
    # Replace child-result helper with shell-authored value; keep script deterministic aside from run path.
    lines[-2]=f"printf '{{\"exit_code\":%s}}\\n' \"$rc\" > {shell_quote(str(export/'child-result.json'))}"
    return "\n".join(lines)+"\n"


def mutation_inventory(run_dir: pathlib.Path) -> dict[str, Any]:
    records=[]
    for idx,target in enumerate(OVERLAY_TARGETS):
        upper=run_dir/f"upper-{idx}"
        if not upper.exists(): continue
        for p in sorted(upper.rglob("*"),key=lambda x:str(x)):
            rel=str(p.relative_to(upper))
            try:
                if p.is_symlink(): records.append({"target_root":str(target),"path":rel,"type":"symlink","target":os.readlink(p)})
                elif p.is_file(): records.append({"target_root":str(target),"path":rel,"type":"file","bytes":p.stat().st_size,"sha256":sha_path(p)})
                elif p.is_dir(): records.append({"target_root":str(target),"path":rel,"type":"dir"})
                else: records.append({"target_root":str(target),"path":rel,"type":"special"})
            except OSError as exc: records.append({"target_root":str(target),"path":rel,"type":"error","error":type(exc).__name__})
    return {"records":records,"digest":sha_bytes(canonical(records))}


def capture_manifest(run_dir: pathlib.Path) -> list[dict[str, Any]]:
    root=run_dir/"export/captures"; out=[]
    if root.exists():
        for p in sorted(root.rglob("*"),key=lambda x:str(x)):
            if p.is_file(): out.append({"path":"/"+str(p.relative_to(root)),"export_path":str(p),"bytes":p.stat().st_size,"sha256":sha_path(p)})
    return out


def run_capsule(command: str, *, empty_paths: list[str] | None=None, captures: list[str] | None=None, label: str="experiment") -> dict[str, Any]:
    if os.environ.get("OPTIPLEX_EXPERIMENT_CAPSULE") == "1":
        raise RuntimeError("NESTED_CAPSULE_SAME_BOUNDARY_REFUSED: an active Capsule already owns this mutable state boundary")
    empty=[pathlib.Path(x) for x in (empty_paths or [])]; caps=[pathlib.Path(x) for x in (captures or [])]
    for p in [*empty,*caps]:
        if not p.is_absolute(): raise ValueError(f"capsule path must be absolute: {p}")
    for p in empty:
        if not any(p==root or root in p.parents for root in OVERLAY_TARGETS): raise ValueError(f"empty path must live under an overlaid target: {p}")
    CAPSULE_ROOT.mkdir(parents=True,exist_ok=True)
    run_id=f"cap8_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{secrets.token_hex(4)}"
    run_dir=CAPSULE_ROOT/run_id; run_dir.mkdir(mode=0o700)
    (run_dir/"export").mkdir()
    wrappers=write_wrappers(run_dir)
    before=protected_manifest(); atomic_json(run_dir/"protected-before.json",before)
    source_inputs=[]
    for p in OVERLAY_TARGETS:
        source_inputs.append({"path":str(p),"tree_digest":tree_manifest(p)["digest"] if p.is_dir() else sha_path(p)})
    recipe_core={"version":VERSION,"schema_version":SCHEMA_VERSION,"label":label,"command":command,"overlay_targets":[str(x) for x in OVERLAY_TARGETS],"empty_paths":[str(x) for x in empty],"captures":[str(x) for x in caps],"source_inputs":source_inputs,"wrapper_sha256":wrappers["wrapper_sha256"],"isolation":{"mount_namespace":True,"pid_namespace":True,"overlayfs":True,"private_tmp":True,"private_run":True,"service_manager_virtualized":True}}
    recipe_digest=sha_bytes(canonical(recipe_core)); manifest={**recipe_core,"run_id":run_id,"created_at":utc(),"recipe_digest":recipe_digest,"protected_before_digest":before["digest"],"wrapper_instance_sha256":wrappers["wrapper_instance_sha256"]}
    atomic_json(run_dir/"manifest.json",manifest)
    script=run_dir/"namespace-run.sh"; script.write_text(namespace_script(run_dir,command,empty,caps,wrappers)); script.chmod(0o700)
    started=time.monotonic()
    proc=subprocess.run(["unshare","--mount","--pid","--fork","--mount-proc",str(script)],capture_output=True,text=True,timeout=3600,check=False)
    duration=round((time.monotonic()-started)*1000,3)
    after=protected_manifest(); atomic_json(run_dir/"protected-after.json",after)
    forbidden, allowed_audit=compare_manifests(before,after); inv=mutation_inventory(run_dir); atomic_json(run_dir/"capsule-mutations.json",inv)
    exported=capture_manifest(run_dir)
    stdout_path=run_dir/"export/stdout.log"; stderr_path=run_dir/"export/stderr.log"
    result={
        "version":VERSION,"run_id":run_id,"label":label,"ok":proc.returncode==0 and not forbidden,"child_exit_code":proc.returncode,"duration_ms":duration,
        "recipe_digest":recipe_digest,"protected_before_digest":before["digest"],"protected_after_digest":after["digest"],"forbidden_accepted_state_mutations":forbidden,"allowed_outer_audit_appends":allowed_audit,
        "accepted_state_unchanged":not forbidden,"capsule_mutation_digest":inv["digest"],"capsule_mutation_records":len(inv["records"]),"captured_artifacts":exported,
        "stdout":{"path":str(stdout_path),"bytes":stdout_path.stat().st_size if stdout_path.exists() else 0,"sha256":sha_path(stdout_path)},
        "stderr":{"path":str(stderr_path),"bytes":stderr_path.stat().st_size if stderr_path.exists() else 0,"sha256":sha_path(stderr_path)},
        "namespace_stdout":proc.stdout[-4000:],"namespace_stderr":proc.stderr[-4000:],"run_dir":str(run_dir),"manifest":str(run_dir/"manifest.json"),
    }
    result["result_digest"]=sha_bytes(canonical(result)); atomic_json(run_dir/"result.json",result)
    return result


def cleanup(run_id: str) -> dict[str, Any]:
    p=(CAPSULE_ROOT/run_id).resolve(); root=CAPSULE_ROOT.resolve()
    if p.parent!=root or not p.name.startswith("cap8_"): raise ValueError("invalid capsule run id")
    existed=p.exists(); shutil.rmtree(p,ignore_errors=False) if existed else None
    return {"run_id":run_id,"removed":existed}


def selftest() -> dict[str, Any]:
    checks=[]
    def check(name:str,ok:bool,detail:Any=None): checks.append({"name":name,"ok":bool(ok),"detail":detail})
    build=pathlib.Path('/etc/optiplex-lab/build.json'); forge=pathlib.Path('/var/lib/optiplex-lab/capabilities/registry.json')
    b0=sha_path(build); f0=sha_path(forge)
    cmd="""set -e
printf '\nCAPSULE_SENTINEL\n' >> /etc/optiplex-lab/build.json
printf '\nCAPSULE_FORGE_SENTINEL\n' >> /var/lib/optiplex-lab/capabilities/registry.json
systemctl show optiplex-lab-mcp.service -p MainPID --value >/tmp/pid.before
systemctl restart optiplex-lab-mcp.service
systemctl show optiplex-lab-mcp.service -p MainPID --value >/tmp/pid.after
test \"$(cat /tmp/pid.before)\" != \"$(cat /tmp/pid.after)\"
test ! -S /run/systemd/private
"""
    r=run_capsule(cmd,label="capsule-selftest-cow-service")
    check("child_mutates_capsule_only",r["child_exit_code"]==0 and r["capsule_mutation_records"]>0,r)
    check("outer_build_unchanged",sha_path(build)==b0,{"before":b0,"after":sha_path(build)})
    check("outer_forge_unchanged",sha_path(forge)==f0,{"before":f0,"after":sha_path(forge)})
    check("protected_manifest_unchanged",r["accepted_state_unchanged"],r["forbidden_accepted_state_mutations"])
    # Empty namespace proof: lower populated Forge must disappear inside declared empty path.
    r2=run_capsule("set -e; test ! -e /var/lib/optiplex-lab/capabilities/registry.json; mkdir -p /var/lib/optiplex-lab/capabilities; echo '{}' > /var/lib/optiplex-lab/capabilities/registry.json",empty_paths=["/var/lib/optiplex-lab/capabilities"],label="capsule-selftest-empty-state")
    check("declared_empty_state_isolated",r2["child_exit_code"]==0 and r2["accepted_state_unchanged"],r2)
    return {"version":VERSION,"passed":sum(1 for x in checks if x["ok"]),"total":len(checks),"checks":checks,"runs":[r["run_id"],r2["run_id"]]}


def main() -> None:
    ap=argparse.ArgumentParser(description="Gen8 reproducible experiment capsule")
    ap.add_argument("--selftest",action="store_true")
    sub=ap.add_subparsers(dest="cmd")
    p=sub.add_parser("run"); p.add_argument("--command",required=True); p.add_argument("--label",default="experiment"); p.add_argument("--empty-path",action="append",default=[]); p.add_argument("--capture",action="append",default=[]); p.add_argument("--out")
    p=sub.add_parser("cleanup"); p.add_argument("run_id")
    p=sub.add_parser("protected-manifest"); p.add_argument("--out")
    args=ap.parse_args()
    if args.selftest:
        out=selftest(); print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if out["passed"]==out["total"] else 1)
    if args.cmd=="run":
        out=run_capsule(args.command,empty_paths=args.empty_path,captures=args.capture,label=args.label)
        if args.out: atomic_json(pathlib.Path(args.out),out)
        print(json.dumps(out,indent=2,sort_keys=True)); raise SystemExit(0 if out["ok"] else 1)
    if args.cmd=="cleanup": print(json.dumps(cleanup(args.run_id),indent=2,sort_keys=True)); return
    if args.cmd=="protected-manifest":
        out=protected_manifest()
        if args.out: atomic_json(pathlib.Path(args.out),out)
        print(json.dumps(out,indent=2,sort_keys=True)); return
    ap.error("command required")

if __name__=="__main__": main()
