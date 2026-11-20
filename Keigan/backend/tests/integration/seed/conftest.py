"""Two real runs of scripts/generate_demo_data_sql.py, shared by the demo data SQL tests (each run seeds a throw-away SQLite database, about a minute)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_DIRECTORY = Path(__file__).resolve().parents[3]
GENERATOR_PATH = BACKEND_DIRECTORY / "scripts" / "generate_demo_data_sql.py"


@pytest.fixture(scope="session")
def generated_demo_data_runs(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """Output folders of two independent runs with different PYTHONHASHSEED values (set iteration order differs between them), started side by side."""
    output_directories = (tmp_path_factory.mktemp("demo_data_run_one"), tmp_path_factory.mktemp("demo_data_run_two"))
    base_environment = {key: value for key, value in os.environ.items() if key not in ("DATABASE_URL", "DATABASE_SCHEMA", "DATA_DIRECTORY")}
    processes = [
        subprocess.Popen(
            [sys.executable, str(GENERATOR_PATH), str(output_directory), "keigan"],
            cwd=BACKEND_DIRECTORY, env={**base_environment, "PYTHONHASHSEED": hash_seed}, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        for output_directory, hash_seed in zip(output_directories, ("1", "2"), strict=True)
    ]
    for process in processes:
        standard_output, standard_error = process.communicate(timeout=600)
        assert process.returncode == 0, f"The demo data generator failed.\nSTDOUT:\n{standard_output}\nSTDERR:\n{standard_error}"
    return output_directories


@pytest.fixture(scope="session")
def generated_demo_data_directory(generated_demo_data_runs: tuple[Path, Path]) -> Path:
    return generated_demo_data_runs[0]
