#!/usr/bin/env python3
import argparse
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _find_python(repo_root: Path) -> str:
    candidates = []
    if os.name == "nt":
        candidates.append(repo_root / "python" / "python.exe")
        candidates.append(repo_root / "myenv" / "Scripts" / "python.exe")
    else:
        candidates.append(repo_root / ".venv" / "bin" / "python")
        candidates.append(repo_root / "myenv" / "bin" / "python")

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)

    return sys.executable


def _build_server_args(repo_root: Path, port: int) -> list[str]:
    server_path = repo_root / "app" / "backend" / "server.py"
    static_dir = repo_root / "app" / "frontend"
    data_dir = repo_root / "data"
    models_config = repo_root / "app" / "backend" / "models.json"
    library_dir = repo_root / "Survival Guides"

    return [
        str(server_path),
        "--port",
        str(port),
        "--static-dir",
        str(static_dir),
        "--data-dir",
        str(data_dir),
        "--models-config",
        str(models_config),
        "--library-dir",
        str(library_dir),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description="LLM in a Box launcher")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()

    repo_root = _repo_root()
    python_exe = _find_python(repo_root)

    port = args.port
    if port is None:
        try:
            port = _pick_free_port()
        except OSError:
            port = 8000

    server_args = [python_exe, *_build_server_args(repo_root, port)]

    url = f"http://127.0.0.1:{port}"
    print("LLM-in-a-Box launcher")
    print(f"Server URL: {url}")

    proc = subprocess.Popen(server_args, cwd=str(repo_root))

    if not args.no_browser:
        ready = False
        for _ in range(40):
            if proc.poll() is not None:
                break
            try:
                urllib.request.urlopen(f"{url}/api/session", timeout=1)
                ready = True
                break
            except (urllib.error.URLError, ValueError):
                time.sleep(0.25)

        if not ready:
            time.sleep(0.5)
        webbrowser.open(url, new=2)

    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    return proc.returncode or 0


if __name__ == "__main__":
    raise SystemExit(main())
