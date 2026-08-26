from __future__ import annotations

from pathlib import Path

from lab_mcp import server


def test_shell_executes():
    result = server.shell("printf lab-ok", cwd="/tmp")
    assert result["exit_code"] == 0
    assert result["stdout"] == "lab-ok"


def test_guest_file_round_trip(tmp_path: Path):
    target = tmp_path / "nested" / "file.txt"
    server.write_file(str(target), "hello")
    assert server.read_file(str(target)) == "hello"


def test_lab_firewall_allows_only_return_traffic_before_host_drop():
    text = Path("host/bootstrap-lab.sh").read_text()
    established = "iptables -A MCP_LAB_INPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT"
    drop = "iptables -A MCP_LAB_INPUT -j DROP"
    assert established in text
    assert text.index(established) < text.index(drop)
