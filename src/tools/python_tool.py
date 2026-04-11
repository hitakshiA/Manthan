"""Docker-sandboxed Python execution tool (SPEC §4.3).

Starts an ephemeral container from ``manthan-sandbox:latest`` with the
dataset's Parquet files mounted read-only at ``/data`` and a writable
``/output`` scratch dir. Resource limits, network isolation, and a hard
timeout are enforced by the Docker API.

Per SPEC:
- 2 GB memory limit, 2 CPUs, network disabled, 60s default timeout
- stdout, stderr, and any files written to /output are returned
- Container is always removed after execution (force-kill on timeout)
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from io import BytesIO
from pathlib import Path
from time import perf_counter
from typing import Any

from pydantic import BaseModel, Field

from src.core.config import Settings, get_settings
from src.core.exceptions import SandboxError
from src.core.logger import get_logger

_logger = get_logger()

_PRELUDE_RELATIVE_PATH = Path("src/sandbox/prelude.py")

_PYTHON_ENTRYPOINT = (
    "import runpy; "
    "globs = runpy.run_path('/sandbox/prelude.py'); "
    "globals().update({k: v for k, v in globs.items() if not k.startswith('_')}); "
    "exec(open('/sandbox/user_code.py').read(), globals())"
)


class SandboxFile(BaseModel):
    """A file produced by the sandbox in ``/output``."""

    name: str
    path: str
    size: int = Field(ge=0)


class SandboxResult(BaseModel):
    """Structured result returned by :func:`run_python`."""

    stdout: str
    stderr: str
    files_created: list[SandboxFile] = Field(default_factory=list)
    execution_time_ms: float = Field(ge=0.0)
    exit_code: int
    timed_out: bool = False


def run_python(
    *,
    code: str,
    dataset_directory: Path,
    output_directory: Path,
    timeout_seconds: int | None = None,
    settings: Settings | None = None,
) -> SandboxResult:
    """Execute ``code`` inside the Manthan sandbox container.

    Args:
        code: User / agent Python source.
        dataset_directory: Local directory containing the dataset's
            Parquet files (typically
            ``{data_directory}/{dataset_id}/data/``).
        output_directory: Local directory to collect files created in
            ``/output`` inside the container.
        timeout_seconds: Optional execution timeout. Defaults to
            :attr:`Settings.sandbox_timeout_seconds`.
        settings: Optional override settings.

    Returns:
        A :class:`SandboxResult` with stdout, stderr, created files, and
        execution metadata.

    Raises:
        SandboxError: If the Docker daemon is unavailable, the image is
            missing, or the container fails to start.
    """
    try:
        import docker
        from docker.errors import APIError, ContainerError, ImageNotFound
    except ImportError as exc:  # pragma: no cover
        raise SandboxError(f"docker library not installed: {exc}") from exc

    resolved = settings or get_settings()
    timeout = timeout_seconds or resolved.sandbox_timeout_seconds

    try:
        client = docker.from_env()
        client.ping()
    except Exception as exc:
        raise SandboxError(f"Docker daemon unreachable: {exc}") from exc

    output_directory.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as staging:
        staging_path = Path(staging)
        (staging_path / "user_code.py").write_text(code)

        host_config_kwargs: dict[str, Any] = {
            "image": resolved.sandbox_image,
            "command": ["python", "-c", _PYTHON_ENTRYPOINT],
            "volumes": {
                str(dataset_directory.resolve()): {
                    "bind": "/data",
                    "mode": "ro",
                },
                str(output_directory.resolve()): {
                    "bind": "/output",
                    "mode": "rw",
                },
            },
            "mem_limit": resolved.sandbox_memory_limit,
            "nano_cpus": int(resolved.sandbox_cpu_limit * 1e9),
            "network_disabled": resolved.sandbox_network_disabled,
            "detach": True,
            "stdout": True,
            "stderr": True,
            "remove": False,
        }

        try:
            container = client.containers.run(**host_config_kwargs)
        except ImageNotFound as exc:
            raise SandboxError(
                f"Sandbox image {resolved.sandbox_image!r} not found; "
                "build it with `docker build -t manthan-sandbox:latest "
                "src/sandbox/`"
            ) from exc
        except (ContainerError, APIError) as exc:
            raise SandboxError(f"Failed to start sandbox container: {exc}") from exc

        # Copy user_code.py and prelude.py into the running container's
        # /sandbox directory so they override whatever was baked into the
        # image (keeps the image itself tiny).
        try:
            _put_file_in_container(
                container, staging_path / "user_code.py", "/sandbox/user_code.py"
            )
            prelude_path = _resolve_prelude_path()
            _put_file_in_container(container, prelude_path, "/sandbox/prelude.py")
        except Exception as exc:
            with _suppress_exceptions():
                container.remove(force=True)
            raise SandboxError(f"Failed to inject sandbox files: {exc}") from exc

        started = perf_counter()
        timed_out = False
        try:
            wait_result = container.wait(timeout=timeout)
            exit_code = int(wait_result.get("StatusCode", -1))
        except Exception:
            timed_out = True
            exit_code = -1
            with _suppress_exceptions():
                container.kill()

        elapsed_ms = (perf_counter() - started) * 1000.0
        stdout = _safe_logs(container, stdout=True, stderr=False)
        stderr = _safe_logs(container, stdout=False, stderr=True)
        with _suppress_exceptions():
            container.remove(force=True)

    files_created = _collect_outputs(output_directory)
    _logger.info(
        "sandbox.run",
        exit_code=exit_code,
        timed_out=timed_out,
        elapsed_ms=elapsed_ms,
        files=len(files_created),
    )

    return SandboxResult(
        stdout=stdout,
        stderr=stderr,
        files_created=files_created,
        execution_time_ms=round(elapsed_ms, 3),
        exit_code=exit_code,
        timed_out=timed_out,
    )


def _put_file_in_container(
    container: Any,
    source: Path,
    destination: str,
) -> None:
    """Use docker's put_archive API to copy ``source`` to ``destination``."""
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        info = tarfile.TarInfo(name=Path(destination).name)
        data = source.read_bytes()
        info.size = len(data)
        archive.addfile(info, BytesIO(data))
    buffer.seek(0)
    parent = str(Path(destination).parent)
    ok = container.put_archive(parent, buffer.getvalue())
    if not ok:
        raise SandboxError(f"Failed to put {source.name} into {destination} in sandbox")


def _collect_outputs(output_directory: Path) -> list[SandboxFile]:
    files: list[SandboxFile] = []
    for entry in sorted(output_directory.glob("**/*")):
        if entry.is_file():
            files.append(
                SandboxFile(
                    name=entry.name,
                    path=str(entry.resolve()),
                    size=entry.stat().st_size,
                )
            )
    return files


def _safe_logs(container: Any, *, stdout: bool, stderr: bool) -> str:
    try:
        raw = container.logs(stdout=stdout, stderr=stderr)
    except Exception:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return str(raw)


def _resolve_prelude_path() -> Path:
    """Find ``prelude.py`` on the host filesystem."""
    candidate = Path(__file__).resolve().parent.parent / "sandbox" / "prelude.py"
    if candidate.exists():
        return candidate
    cwd_candidate = Path.cwd() / _PRELUDE_RELATIVE_PATH
    if cwd_candidate.exists():
        return cwd_candidate
    raise SandboxError(f"Sandbox prelude not found at {candidate}")


class _suppress_exceptions:  # noqa: N801 — tiny context manager, lowercase OK
    """Context manager that swallows any exception (cleanup helper)."""

    def __enter__(self) -> _suppress_exceptions:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> bool:
        return True


def ensure_sandbox_image(
    *,
    settings: Settings | None = None,
    sandbox_source_dir: Path | None = None,
) -> None:
    """Build the sandbox image if it is not already present locally."""
    try:
        import docker
        from docker.errors import APIError, BuildError, ImageNotFound
    except ImportError as exc:  # pragma: no cover
        raise SandboxError(f"docker library not installed: {exc}") from exc

    resolved = settings or get_settings()
    client = docker.from_env()
    try:
        client.images.get(resolved.sandbox_image)
        return  # already built
    except ImageNotFound:
        pass

    source = sandbox_source_dir or Path(__file__).resolve().parent.parent / "sandbox"
    if not source.exists():
        raise SandboxError(f"Sandbox source directory not found: {source}")

    _logger.info("sandbox.build", image=resolved.sandbox_image, context=str(source))
    try:
        client.images.build(
            path=str(source),
            tag=resolved.sandbox_image,
            rm=True,
            forcerm=True,
        )
    except (BuildError, APIError) as exc:
        raise SandboxError(f"Failed to build sandbox image: {exc}") from exc

    # Best-effort cleanup of any stranded build context
    shutil.rmtree(source / "__pycache__", ignore_errors=True)
