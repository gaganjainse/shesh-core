"""Completion tests: real /proc process listing + IO edge-case honesty."""
import shesh_ebpf.server as srv


def test_list_processes_reads_real_proc():
    res = srv.list_processes()
    assert res["ok"] is True and res["count"] >= 1
    assert any(p["pid"] == 1 for p in res["processes"])  # init always exists
    for p in res["processes"]:
        assert set(p) == {"pid", "name", "state"}
        assert p["state"] in "RSDZTtXZKWxPIP"  # kernel state letters


def test_list_processes_limit_clamped():
    res = srv.list_processes(1)
    assert res["count"] == 1
    assert srv.list_processes(0)["count"] >= 1  # clamps to >=1


def test_get_process_io_missing_pid_is_honest():
    res = srv.get_process_io(4194304)  # beyond any live pid
    assert res["ok"] is False and "No /proc/4194304/io" in res["error"]


def test_get_system_metrics_real_load_keys():
    res = srv.get_system_metrics()
    assert len(res["load_avg"]) == 3
    assert "MemTotal" in res["meminfo"]
    assert res["ebpf_available"] is False  # Aya path not built — stated, not faked
