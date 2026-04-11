"""Tests for the stateful Python session runtime."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import duckdb
import pytest
from src.core.exceptions import SandboxError
from src.tools.python_session import (
    PythonSession,
    ephemeral_manager,
)


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    """A dataset directory containing one small Parquet file."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    con = duckdb.connect(":memory:")
    try:
        con.execute(
            "CREATE TABLE t AS SELECT * FROM (VALUES "
            "(1, 'North', 100.0), (2, 'South', 200.0), (3, 'East', 150.0)) "
            "AS v(id, region, revenue)"
        )
        con.table("t").write_parquet(str(data_dir / "gold.parquet"))
    finally:
        con.close()
    return data_dir


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    out = tmp_path / "output"
    out.mkdir()
    return out


@pytest.fixture
def session(dataset_dir: Path, output_dir: Path) -> Iterator[PythonSession]:
    session = PythonSession(
        session_id="test_session",
        dataset_directory=dataset_dir,
        output_directory=output_dir,
    )
    session.start()
    try:
        yield session
    finally:
        session.stop()


class TestBootstrap:
    def test_df_is_preloaded(self, session: PythonSession) -> None:
        result = session.execute("print(df.shape)")
        assert result.exit_code == 0
        assert "(3, 3)" in result.stdout

    def test_duckdb_connection_available(self, session: PythonSession) -> None:
        result = session.execute(
            "print(con.execute('SELECT COUNT(*) FROM dataset').fetchone()[0])"
        )
        assert result.exit_code == 0
        assert "3" in result.stdout

    def test_output_dir_exposed(self, session: PythonSession) -> None:
        result = session.execute("print(OUTPUT_DIR.name)")
        assert result.exit_code == 0
        assert "output" in result.stdout


class TestStatePersistence:
    def test_variable_defined_in_one_call_visible_in_next(
        self, session: PythonSession
    ) -> None:
        first = session.execute("x = 42")
        assert first.exit_code == 0

        second = session.execute("print(x * 2)")
        assert second.exit_code == 0
        assert "84" in second.stdout

    def test_dataframe_can_be_mutated_across_calls(
        self, session: PythonSession
    ) -> None:
        session.execute("subset = df[df.revenue > 100]")
        session.execute("subset = subset.sort_values('revenue', ascending=False)")
        result = session.execute("print(subset.iloc[0].region)")
        assert "South" in result.stdout

    def test_imports_persist(self, session: PythonSession) -> None:
        session.execute("import statistics")
        result = session.execute("print(statistics.mean([1, 2, 3, 4, 5]))")
        assert result.exit_code == 0
        assert "3" in result.stdout


class TestReprCapture:
    def test_bare_expression_returns_repr(self, session: PythonSession) -> None:
        result = session.execute("2 + 2")
        assert result.exit_code == 0
        assert result.repr == "4"

    def test_statement_does_not_return_repr(self, session: PythonSession) -> None:
        result = session.execute("y = 5")
        assert result.exit_code == 0
        assert result.repr is None


class TestErrorHandling:
    def test_runtime_error_keeps_session_alive(self, session: PythonSession) -> None:
        bad = session.execute("raise ValueError('boom')")
        assert bad.exit_code == 1
        assert "ValueError" in bad.stderr
        assert "boom" in bad.stderr

        # Session still works.
        ok = session.execute("print('still alive')")
        assert ok.exit_code == 0
        assert "still alive" in ok.stdout

    def test_syntax_error_keeps_session_alive(self, session: PythonSession) -> None:
        bad = session.execute("this is not valid python")
        assert bad.exit_code == 1
        assert "SyntaxError" in bad.stderr

        ok = session.execute("print(1 + 1)")
        assert ok.exit_code == 0


class TestFileTracking:
    def test_files_created_in_output_dir_are_reported(
        self, session: PythonSession
    ) -> None:
        result = session.execute(
            "(OUTPUT_DIR / 'report.txt').write_text('hello world')"
        )
        assert result.exit_code == 0
        assert any(f["name"] == "report.txt" for f in result.files_created)


class TestManager:
    def test_get_or_create_returns_same_session(
        self, dataset_dir: Path, output_dir: Path
    ) -> None:
        with ephemeral_manager() as manager:
            first = manager.get_or_create(
                session_id="stable",
                dataset_directory=dataset_dir,
                output_directory=output_dir,
            )
            first.execute("stored = 'hello'")

            second = manager.get_or_create(
                session_id="stable",
                dataset_directory=dataset_dir,
                output_directory=output_dir,
            )
            assert second is first
            result = second.execute("print(stored)")
            assert "hello" in result.stdout

    def test_drop_session_removes_it(self, dataset_dir: Path, output_dir: Path) -> None:
        with ephemeral_manager() as manager:
            session = manager.get_or_create(
                session_id="to_drop",
                dataset_directory=dataset_dir,
                output_directory=output_dir,
            )
            assert session.alive
            manager.drop("to_drop")
            assert not session.alive
            assert "to_drop" not in manager.list_sessions()

    def test_new_session_id_generated_when_omitted(
        self, dataset_dir: Path, output_dir: Path
    ) -> None:
        with ephemeral_manager() as manager:
            s1 = manager.get_or_create(
                session_id=None,
                dataset_directory=dataset_dir,
                output_directory=output_dir,
            )
            s2 = manager.get_or_create(
                session_id=None,
                dataset_directory=dataset_dir,
                output_directory=output_dir,
            )
            assert s1.session_id != s2.session_id


class TestTimeout:
    def test_infinite_loop_hits_timeout(
        self, dataset_dir: Path, output_dir: Path
    ) -> None:
        session = PythonSession(
            session_id="timeout_test",
            dataset_directory=dataset_dir,
            output_directory=output_dir,
        )
        session.start()
        try:
            result = session.execute("while True: pass", timeout_seconds=2)
            assert result.timed_out is True
            assert result.exit_code == -1
        finally:
            session.stop()

    def test_dead_session_raises_sandbox_error(
        self, dataset_dir: Path, output_dir: Path
    ) -> None:
        session = PythonSession(
            session_id="dead_test",
            dataset_directory=dataset_dir,
            output_directory=output_dir,
        )
        session.start()
        session.stop()
        with pytest.raises(SandboxError):
            session.execute("print('nope')")
