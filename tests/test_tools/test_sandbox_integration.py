"""Integration test for the Docker-backed Python sandbox.

Marked slow and skipped automatically when Docker is unavailable or the
``manthan-sandbox`` image has not been built.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest
from src.tools.python_tool import run_python


def _docker_and_image_ready() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        client.images.get("manthan-sandbox:latest")
        return True
    except Exception:
        return False


pytestmark = pytest.mark.slow


@pytest.mark.skipif(
    not _docker_and_image_ready(),
    reason="Docker or manthan-sandbox image unavailable",
)
def test_run_python_returns_stdout(tmp_path: Path) -> None:
    # Create a tiny Parquet dataset for the sandbox to read.
    dataset_dir = tmp_path / "data"
    output_dir = tmp_path / "output"
    dataset_dir.mkdir()
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            "CREATE TABLE t AS SELECT * FROM (VALUES "
            "(1, 'North', 100.0), (2, 'South', 200.0)) AS v(id, region, revenue)"
        )
        con.table("t").write_parquet(str(dataset_dir / "t.parquet"))
    finally:
        con.close()

    code = (
        "import duckdb, pandas\n"
        "print(df.shape)\n"
        "print(df['revenue'].sum())\n"
        "(OUTPUT_DIR / 'summary.txt').write_text(str(df['revenue'].sum()))\n"
    )

    result = run_python(
        code=code,
        dataset_directory=dataset_dir,
        output_directory=output_dir,
        timeout_seconds=30,
    )
    assert result.exit_code == 0, f"stderr: {result.stderr}"
    assert "300.0" in result.stdout
    assert any(f.name == "summary.txt" for f in result.files_created)
