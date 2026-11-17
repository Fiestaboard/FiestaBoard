"""Read-only fixture verification bridge; no network or auth at import time."""

import argparse
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


def main(argv=None):
    """Delegate source checks through Node's genuine, already-authenticated GETs."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-harness-dir", required=True)
    parser.add_argument("--max-frame-bytes", type=int, default=4 * 1024 * 1024)
    args = parser.parse_args(argv)
    sys.dont_write_bytecode = True

    def read_frame():
        raw = sys.stdin.buffer.readline(args.max_frame_bytes + 1)
        if not raw or not raw.endswith(b"\n") or len(raw) > args.max_frame_bytes:
            raise ValueError("Missing or oversized IPC frame")
        frame = json.loads(raw)
        if not isinstance(frame, dict):
            raise ValueError("IPC frame must be an object")
        return frame

    def emit(frame):
        raw = json.dumps(frame, separators=(",", ":"))
        if len(raw.encode()) + 1 > args.max_frame_bytes:
            raise ValueError("Oversized IPC frame")
        print(raw, flush=True)

    try:
        directory = Path(args.api_harness_dir).resolve(strict=True)
        if not directory.is_dir() or not all((directory / name).is_file() for name in ("runtime_common.py", "runtime_seed.py")):
            raise ValueError("Explicit API harness modules are required")
        sys.path.insert(0, str(directory))
        from runtime_common import HttpResult, JsonClient
        from runtime_seed import verify_manifest

        initial = read_frame()
        origin, manifest = initial["origin"], initial["manifest"]
        parsed = urlsplit(origin)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            raise ValueError("Explicit same-origin target required")
        origin = origin.rstrip("/")
        sequence = 0

        def exchange(method, url, payload, headers, timeout):
            nonlocal sequence
            if method != "GET" or payload is not None or not url.startswith(origin + "/api/"):
                raise ValueError("Read-only verifier permits GET only")
            path = url[len(origin):]
            if urlsplit(path).netloc or urlsplit(path).fragment:
                raise ValueError("Relative same-origin path required")
            sequence += 1
            emit({"type": "request", "id": sequence, "method": "GET", "path": path})
            response = read_frame()
            if response.get("type") != "response" or response.get("id") != sequence or response.get("status") != 200:
                raise ValueError("Protected Node read failed")
            return HttpResult(200, response["body"])

        # Credentials are intentionally absent. This constructor is network-free
        # and every request uses the supplied stdio transport; never call login
        # or verify_semantics, which would create sessions or change app state.
        client = JsonClient(origin, {}, transport=exchange)
        verification = verify_manifest(client, manifest)
        emit({"type": "result", "verification": verification})
        return 0
    except Exception as exc:
        # No repr/message: third-party exceptions can include response content.
        emit({"type": "error", "error_type": type(exc).__name__})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
