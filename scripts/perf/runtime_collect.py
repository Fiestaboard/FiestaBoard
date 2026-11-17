"""Read-only Linux proc/cgroup collector; no process is started at import time."""

import argparse
import json
import math
import os
import sys
import time
from pathlib import Path

from runtime_common import JsonlWriter, ProtocolError


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Collect actual hub Linux resources against an explicit shared-clock anchor"
    )
    parser.add_argument("--anchor", type=Path, required=True)
    parser.add_argument("--proc-root", type=Path, default=Path("/proc"))
    parser.add_argument("--cgroup-root", type=Path, default=Path("/sys/fs/cgroup"))
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--api-pid", type=int, required=True)
    parser.add_argument("--nginx-pid", type=int)
    parser.add_argument("--supervisor-pid", type=int)
    parser.add_argument("--duration", type=float, default=7200)
    parser.add_argument("--interval", type=float, default=5)
    args = parser.parse_args(argv)
    writer = None
    try:
        anchor = json.loads(args.anchor.read_text())
        boot_id = (args.proc_root / "sys/kernel/random/boot_id").read_text().strip()
        namespace = os.readlink(args.proc_root / "self/ns/pid")
        command = (args.proc_root / str(args.api_pid) / "cmdline").read_text().replace("\0", " ")
        validate_collector_anchor(anchor, boot_id=boot_id, pid_namespace=namespace, api_cmdline=command)
        if (
            args.duration <= 0
            or args.interval <= 0
            or not all(math.isfinite(n) for n in (args.duration, args.interval))
        ):
            raise ProtocolError("Collector duration/interval must be positive and finite")
        pids = {
            role: pid
            for role, pid in (("api", args.api_pid), ("nginx", args.nginx_pid), ("supervisor", args.supervisor_pid))
            if pid is not None
        }
        snapshot = collect_snapshot(args.proc_root, args.cgroup_root, args.data_dir, pids)
        api = next(p for p in snapshot["processes"] if p["role"] == "api")
        if api["start_time_ticks"] is None or api["rss_bytes"] is None:
            raise ProtocolError("Selected API PID has no readable identity/RSS")
        args.out_dir.mkdir(parents=True, exist_ok=True)
        ready = {
            **anchor,
            "api_pid": args.api_pid,
            "api_start_time_ticks": api["start_time_ticks"],
            "api_cmdline": command,
            "collector_pid": os.getpid(),
            "pid_namespace": namespace,
            "boot_id": boot_id,
        }
        with (args.out_dir / "collector-ready.json").open("x") as output:
            output.write(json.dumps(ready, indent=2) + "\n")
        writer = JsonlWriter(args.out_dir / "resources.jsonl", anchor["run_id"])
        start, index = anchor["start_monotonic"], 0
        if time.monotonic() > start:
            raise ProtocolError("Collector started after its measurement anchor")
        while index * args.interval <= args.duration:
            deadline = start + index * args.interval
            wait = deadline - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            elapsed = time.monotonic() - start
            if elapsed - index * args.interval >= args.interval:
                writer.write(
                    "gap",
                    reason="Collector missed interval",
                    scheduled_elapsed_s=index * args.interval,
                    monotonic_elapsed_s=elapsed,
                    boot_id=boot_id,
                    pid_namespace=namespace,
                )
                index = math.ceil(elapsed / args.interval)
                continue
            snapshot = collect_snapshot(args.proc_root, args.cgroup_root, args.data_dir, pids)
            writer.write("resource", monotonic_elapsed_s=elapsed, boot_id=boot_id, pid_namespace=namespace, **snapshot)
            index += 1
        return 0
    except (OSError, ValueError, KeyError, ProtocolError) as exc:
        if writer is not None:
            writer.write("interrupted", error=f"Collector stopped: {type(exc).__name__}")
        print(f"Collector refused: {type(exc).__name__}", file=sys.stderr)
        return 2
    finally:
        if writer is not None:
            writer.close()


def validate_collector_anchor(anchor, *, boot_id, pid_namespace, api_cmdline):
    if anchor.get("schema_version") != 1 or not anchor.get("run_id"):
        raise ProtocolError("Collector requires a named measurement anchor")
    if not boot_id or anchor.get("boot_id") != boot_id:
        raise ProtocolError("Collector and workload use different Linux monotonic clock domains")
    if not pid_namespace or anchor.get("pid_namespace") != pid_namespace:
        raise ProtocolError("Collector is not in the reserved published hub PID namespace")
    if "uvicorn" not in api_cmdline or "src.api_server:app" not in api_cmdline:
        raise ProtocolError("Selected API PID is not the published uvicorn API")
    start = anchor.get("start_monotonic")
    if not isinstance(start, (int, float)) or not math.isfinite(start) or start < 0:
        raise ProtocolError("Collector anchor needs a finite monotonic start")


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
        processes.append(
            {
                "role": role,
                "pid": pid,
                "start_time_ticks": start,
                "rss_bytes": status.get("VmRSS"),
                "rss_anon_bytes": status.get("RssAnon"),
                "rss_file_bytes": status.get("RssFile"),
                "virtual_bytes": status.get("VmSize"),
                "threads": status.get("Threads"),
                "pss_bytes": smaps.get("Pss"),
                "private_clean_bytes": smaps.get("Private_Clean"),
                "private_dirty_bytes": smaps.get("Private_Dirty"),
                "fd_count": fd_count,
                "socket_count": socket_count,
            }
        )
    cgroup = {}
    for name in ("memory.current", "memory.max", "memory.peak", "pids.current", "pids.max"):
        raw = _text(cgroup_root / name)
        value = raw.strip() if raw is not None else None
        cgroup[name] = int(value) if value and value.isdigit() else value
    for name in ("memory.events", "cpu.stat", "io.stat", "memory.pressure", "cpu.pressure", "io.pressure"):
        cgroup[name] = _text(cgroup_root / name)
    store_bytes, files = 0, 0
    try:
        for directory, dirs, names in os.walk(
            data_dir, followlinks=False, onerror=lambda error: (_ for _ in ()).throw(error)
        ):
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
    return {
        "processes": processes,
        "cgroup": cgroup,
        "data_store_bytes": store_bytes,
        "data_store_files": files,
        "data_filesystem_available_bytes": free_bytes,
        "host_loadavg": _text(proc_root / "loadavg"),
        "host_meminfo": _text(proc_root / "meminfo"),
        "python_heap": {"available": False, "reason": "Published process has no heap instrumentation"},
        "queues": {"available": False, "reason": "Published process has no internal queue instrumentation"},
        "node_ui_server": {"expected": False, "reason": "Published nginx serves static client"},
        "unavailable": unavailable,
    }


if __name__ == "__main__":
    raise SystemExit(main())
