"""MCP server — eBPF telemetry with Aya (Rust) read-only stub (Python /proc fallback)."""

from __future__ import annotations

import pathlib
import time

from shesh_audit.mcp_guard import GuardedMCP as FastMCP

mcp = FastMCP("shesh-ebpf")

def _read_proc(path: str) -> str:
    try:
        return pathlib.Path(path).read_text()
    except (OSError, UnicodeError):
        return ""

@mcp.tool()
def get_system_metrics() -> dict:
    """Get system metrics via /proc — Aya eBPF would provide richer, here read-only /proc fallback."""
    load = _read_proc("/proc/loadavg").split()[:3]
    meminfo = {}
    for line in _read_proc("/proc/meminfo").splitlines()[:10]:
        if ":" in line:
            k, v = line.split(":", 1)
            meminfo[k.strip()] = v.strip()
    uptime = _read_proc("/proc/uptime").split()[0] if _read_proc("/proc/uptime") else "0"
    return {
        "load_avg": load,
        "meminfo": meminfo,
        "uptime_seconds": uptime,
        "timestamp": time.time(),
        "source": "procfs (Aya eBPF stub — future Rust Aya would use BPF_MAP_TYPE_HASH for execve/openat)",
        "ebpf_available": False,
        "note": "Read-only, no kprobes modifying, behind Guard",
    }

@mcp.tool()
def get_network_stats() -> dict:
    net_dev = _read_proc("/proc/net/dev").splitlines()[:20]
    tcp = _read_proc("/proc/net/snmp").splitlines()[:20]
    return {
        "net_dev": net_dev,
        "tcp_snmp": tcp,
        "source": "procfs",
        "ebpf_future": "Aya would trace tcp_retransmit_skb via kprobe",
    }

@mcp.tool()
def get_process_io(pid: int = 1) -> dict:
    io_text = _read_proc(f"/proc/{pid}/io")
    if not io_text:
        return {"ok": False, "error": f"No /proc/{pid}/io", "stub": True}
    data = {}
    for line in io_text.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            data[k.strip()] = v.strip()
    return {"ok": True, "pid": pid, "io": data, "source": "procfs"}

@mcp.tool()
def list_processes(limit: int = 50) -> dict:
    """List live processes from /proc (pid, name, state) — real procfs data.

    Aya eBPF would stream execve events; this is the honest read snapshot:
    every row existed at call time, nothing synthesized. Skips processes
    that vanish mid-scan (their /proc entries are inherently racy).
    """
    limit = max(1, min(int(limit), 1000))
    procs = []
    for entry in sorted(pathlib.Path("/proc").iterdir()):
        if len(procs) >= limit:
            break
        if not entry.name.isdigit():
            continue
        stat = _read_proc(str(entry / "stat"))
        if not stat:
            continue  # process exited between iterdir and read — expected race
        # comm may contain spaces/parens; state follows the final ')'
        rparen = stat.rfind(")")
        if rparen == -1:
            continue  # malformed stat — skip rather than guess
        comm = stat[stat.find("(") + 1:rparen]
        fields = stat[rparen + 1:].split()
        if not fields:
            continue
        procs.append({"pid": int(entry.name), "name": comm, "state": fields[0]})
    return {"ok": True, "count": len(procs), "processes": procs, "source": "procfs"}


@mcp.tool()
def list_ebpf_programs() -> dict:
    return {
        "programs": [
            {"name": "execve-tracer", "type": "kprobe", "status": "planned",
             "desc": "Trace execve via Aya BPF_PROG_TYPE_KPROBE"},
            {"name": "openat-tracer", "type": "kprobe", "status": "planned",
             "desc": "Trace openat for file access via Aya"},
            {"name": "tcp-retransmit", "type": "kprobe", "status": "planned",
             "desc": "Trace tcp_retransmit_skb via Aya"},
        ],
        "rust_crate": "ebpf-rs",
        "note": "Read-only, no modifications, behind Guard allow/confirm/deny",
    }

def main() -> None:
    mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
