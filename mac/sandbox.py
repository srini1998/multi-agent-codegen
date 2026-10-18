"""Execute generated Python in a fixed, offline, resource-bounded local container.

No host directory, Docker socket, credential, or project tree is mounted. The code is
sent on stdin. Failure to provision this sandbox is an infrastructure error, never a
reason to fall back to executing generated code on the host.
"""
from __future__ import annotations

import os
import selectors
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from pathlib import Path

IMAGE = "python@sha256:f3fa41d74a768c2fce8016b98c191ae8c1bacd8f1152870a3f9f87d350920b7c"
PROFILE = "local-container-v1"
OUTPUT_LIMIT = 64 * 1024
SOURCE_LIMIT = 256 * 1024

@dataclass
class ExecResult:
    ok: bool
    output: str
    timed_out: bool = False
    category: str = "candidate"
    profile: str = PROFILE
    image: str = IMAGE


def _docker() -> list[str] | None:
    executable = shutil.which("docker")
    if not executable:
        return None
    # Only known local sockets; never inherit a remote Docker context or URL.
    for socket in (Path.home() / ".colima/breakroom/docker.sock", Path("/var/run/docker.sock")):
        if socket.exists():
            return [executable, "--host", "unix://" + str(socket)]
    return None


def run_python(source: str, timeout: float = 15.0) -> ExecResult:
    if not isinstance(source, str) or len(source.encode()) > SOURCE_LIMIT or not 0 < timeout <= 60:
        return ExecResult(False, "Unsupported source size or timeout", category="invalid_input")
    docker = _docker()
    if docker is None:
        return ExecResult(False, "Local container sandbox unavailable; no host fallback", category="infrastructure")
    name = "mac-proof-" + uuid.uuid4().hex
    cmd = docker + ["run", "--rm", "--pull=never", "--name", name,
                    "--label", "workbench=mac-proof", "--network", "none",
                    "--read-only", "--user", "65534:65534", "--workdir", "/tmp",
                    "--tmpfs", "/tmp:rw,nosuid,nodev,size=67108864,mode=1777",
                    "--memory", "256m", "--memory-swap", "256m", "--cpus", "1",
                    "--pids-limit", "32", "--cap-drop", "ALL",
                    "--security-opt", "no-new-privileges", "--ulimit", "nofile=64:64",
                    "--ulimit", "cpu=10:10", "--ulimit", "fsize=10000000:10000000",
                    "--env", "PYTHONHASHSEED=0", "--env", "HOME=/tmp",
                    "--entrypoint", "python", "-i", IMAGE, "-I", "-"]
    proc = None
    selector = selectors.DefaultSelector()
    output = bytearray()
    timed_out = False
    limited = False
    safe_env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(Path.home())}
    try:
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, env=safe_env)
        encoded=source.encode()
        offset=0
        os.set_blocking(proc.stdin.fileno(),False)
        os.set_blocking(proc.stdout.fileno(),False)
        selector.register(proc.stdin,selectors.EVENT_WRITE,"input")
        selector.register(proc.stdout, selectors.EVENT_READ,"output")
        deadline = time.monotonic() + timeout
        while selector.get_map():
            if time.monotonic() >= deadline:
                timed_out = True
                break
            for key, _ in selector.select(min(.1, max(0, deadline - time.monotonic()))):
                if key.data=="input":
                    try:
                        offset+=os.write(proc.stdin.fileno(),encoded[offset:offset+4096])
                    except BrokenPipeError:
                        offset=len(encoded)
                    if offset>=len(encoded):
                        selector.unregister(proc.stdin)
                        proc.stdin.close()
                    continue
                chunk = os.read(key.fileobj.fileno(), 4096)
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                remaining = OUTPUT_LIMIT - len(output)
                output.extend(chunk[:remaining])
                if len(chunk) > remaining:
                    limited = True
                    break
            if limited:
                break
        if timed_out or limited:
            proc.stdout.close()
            subprocess.run(docker + ["rm", "-f", name], env=safe_env, capture_output=True, timeout=10)
            if proc.poll() is None:
                proc.terminate()
        code = proc.wait(timeout=5)
        text = output.decode(errors="replace")
        if timed_out:
            return ExecResult(False, text[-3000:] + f"\nwall deadline exceeded: {timeout}s", True)
        if limited:
            return ExecResult(False, text[-3000:] + "\noutput exceeded 64 KiB", category="output_limit")
        if code in (125, 126, 127):
            return ExecResult(False, text[-3000:], category="infrastructure")
        return ExecResult(code == 0, text[-3000:])
    except (OSError, subprocess.SubprocessError) as error:
        return ExecResult(False, "Sandbox infrastructure error: " + type(error).__name__, category="infrastructure")
    finally:
        selector.close()
        # Cleanup is restricted to the unpredictable name allocated by this call.
        try:
            subprocess.run(docker + ["rm", "-f", name], env=safe_env, capture_output=True, timeout=10)
        except (OSError, subprocess.SubprocessError):
            pass
        if proc is not None and proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)
