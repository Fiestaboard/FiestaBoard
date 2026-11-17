"""Read-only Linux proc/cgroup collector; no process is started at import time."""

from pathlib import Path
import os


def _text(path):
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None


def _kb_fields(path):
    result = {}
    for line in (_text(path) or "").splitlines():
        name, _, raw = line.partition(":")
        parts = raw.split()
        try:
            result[name] = int(parts[0]) * 1024 if len(parts) == 2 and parts[1] == "kB" else int(parts[0])
        except (ValueError, IndexError):
            continue
    return result


def collect_snapshot(proc_root, cgroup_root, data_dir, pids):
    proc_root, cgroup_root, data_dir = Path(proc_root), Path(cgroup_root), Path(data_dir)
    processes = []
    unavailable = []
    for role, pid in pids.items():
        root = proc_root / str(pid)
        status = _kb_fields(root / "status")
        smaps = _kb_fields(root / "smaps_rollup")
        stat_text = _text(root / "stat")
        start = None
        try:
            start = int(stat_text.rsplit(")", 1)[1].split()[19])
        except (AttributeError, IndexError, ValueError):
            unavailable.append(f"{role}:process_identity")
        fd_count, socket_count = None, None
        try:
            fds = list((root / "fd").iterdir())
            fd_count, socket_count = len(fds), 0
            for fd in fds:
                try:
                    socket_count += os.readlink(fd).startswith("socket:[")
                except OSError:
                    continue
        except OSError:
            unavailable.append(f"{role}:fd/socket")
        processes.append({"role": role, "pid": pid, "start_time_ticks": start, "rss_bytes": status.get("VmRSS"),
                          "rss_anon_bytes": status.get("RssAnon"), "rss_file_bytes": status.get("RssFile"),
                          "virtual_bytes": status.get("VmSize"), "threads": status.get("Threads"),
                          "pss_bytes": smaps.get("Pss"), "private_clean_bytes": smaps.get("Private_Clean"),
                          "private_dirty_bytes": smaps.get("Private_Dirty"), "fd_count": fd_count, "socket_count": socket_count})
    cgroup = {}
    for name in ("memory.current", "memory.max", "memory.peak", "pids.current", "pids.max"):
        raw = _text(cgroup_root / name)
        value = raw.strip() if raw is not None else None
        cgroup[name] = int(value) if value and value.isdigit() else value
    for name in ("memory.events", "cpu.stat", "io.stat", "memory.pressure", "cpu.pressure", "io.pressure"):
        cgroup[name] = _text(cgroup_root / name)
    store_bytes, files = 0, 0
    try:
        for directory, dirs, names in os.walk(data_dir, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)):
            if any((Path(directory) / name).is_symlink() for name in dirs + names):
                raise OSError("Store contains symlinks; footprint unresolved")
            for name in names:
                store_bytes += (Path(directory) / name).stat().st_size
                files += 1
        statvfs = os.statvfs(data_dir)
        free_bytes = statvfs.f_bavail * statvfs.f_frsize
    except OSError:
        store_bytes, files, free_bytes = None, None, None
        unavailable.append("data_store")
    return {"processes": processes, "cgroup": cgroup, "data_store_bytes": store_bytes, "data_store_files": files,
            "data_filesystem_available_bytes": free_bytes,
            "host_loadavg": _text(proc_root / "loadavg"), "host_meminfo": _text(proc_root / "meminfo"),
            "python_heap": {"available": False, "reason": "Published process has no heap instrumentation"},
            "queues": {"available": False, "reason": "Published process has no internal queue instrumentation"},
            "node_ui_server": {"expected": False, "reason": "Published nginx serves static client"},
            "unavailable": unavailable}
