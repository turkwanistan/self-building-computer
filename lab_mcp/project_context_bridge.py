#!/opt/optiplex-lab/venv/bin/python
from __future__ import annotations
import json, pathlib, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from project_onboarding import compose_platform_context


def compose(task: str, project_packet_path: str):
    return compose_platform_context(task, project_packet_path)


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: project_context_bridge.py TASK PROJECT_CONTEXT_JSON", file=sys.stderr); return 2
    try: out = compose(sys.argv[1], sys.argv[2])
    except Exception as exc:
        print(json.dumps({"ok": False, "fail_closed": True, "error": str(exc)}, sort_keys=True)); return 2
    print(json.dumps({"ok": True, **out}, indent=2, sort_keys=True)); return 0


if __name__ == "__main__": raise SystemExit(main())
