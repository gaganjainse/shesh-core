from shesh_ebpf.server import (
    get_network_stats,
    get_process_io,
    get_system_metrics,
    list_ebpf_programs,
)


def test_system_metrics():
    res = get_system_metrics()
    assert "load_avg" in res
    assert "meminfo" in res

def test_network():
    res = get_network_stats()
    assert "net_dev" in res

def test_io():
    res = get_process_io(1)
    assert "ok" in res

def test_list():
    res = list_ebpf_programs()
    assert "programs" in res
    assert len(res["programs"]) >= 3
