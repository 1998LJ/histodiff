from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from histodiff._git import main

_OID = "1" * 40
_MODE = "100644"


def protocol(old: Path, new: Path, path: str = "example.py") -> list[str]:
    return [path, str(old), _OID, _MODE, str(new), _OID, _MODE]


def test_external_diff_renders_git_labels_and_normalizes_status(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.write_text("before\n", encoding="utf-8")
    new.write_text("after\n", encoding="utf-8")
    monkeypatch.delenv("GIT_EXTERNAL_DIFF_TRUST_EXIT_CODE", raising=False)

    assert main(protocol(old, new)) == 0
    output = capsys.readouterr().out
    assert output.startswith("diff --histodiff a/example.py b/example.py\n")
    assert "--- a/example.py\n" in output
    assert "+++ b/example.py\n" in output
    assert "-before\n+after\n" in output

    monkeypatch.setenv("GIT_EXTERNAL_DIFF_TRUST_EXIT_CODE", "true")
    assert main(protocol(old, new)) == 1


def test_external_diff_handles_added_and_deleted_files(tmp_path: Path, capsys) -> None:
    present = tmp_path / "present"
    present.write_text("content\n", encoding="utf-8")

    added = ["new.txt", "/dev/null", ".", ".", str(present), _OID, _MODE]
    assert main(added) == 0
    output = capsys.readouterr().out
    assert "diff --histodiff /dev/null b/new.txt" in output
    assert "new file mode 100644" in output
    assert "--- /dev/null\n" in output
    assert "+++ b/new.txt\n" in output

    deleted = ["old.txt", str(present), _OID, _MODE, "/dev/null", ".", "."]
    assert main(deleted) == 0
    output = capsys.readouterr().out
    assert "diff --histodiff a/old.txt /dev/null" in output
    assert "deleted file mode 100644" in output
    assert "--- a/old.txt\n" in output
    assert "+++ /dev/null\n" in output


def test_external_diff_handles_renames_and_mode_changes(tmp_path: Path, capsys) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.write_text("same\n", encoding="utf-8")
    new.write_text("same\n", encoding="utf-8")
    args = [
        "old.py",
        str(old),
        _OID,
        _MODE,
        str(new),
        _OID,
        "100755",
        "new.py",
        "similarity index 100%",
    ]

    assert main(args) == 0
    output = capsys.readouterr().out
    assert "diff --histodiff a/old.py b/new.py" in output
    assert "old mode 100644" in output
    assert "new mode 100755" in output
    assert "similarity index 100%" in output
    assert "path from old.py" in output
    assert "path to new.py" in output


def test_external_diff_summarizes_binary_files(tmp_path: Path, capsys) -> None:
    old = tmp_path / "old"
    new = tmp_path / "new"
    old.write_bytes(b"old\0bytes")
    new.write_bytes(b"new\0bytes")

    assert main(protocol(old, new, "asset.bin")) == 0
    output = capsys.readouterr().out
    assert "Binary files a/asset.bin and b/asset.bin differ" in output
    assert "--- " not in output


def test_external_diff_reports_unmerged_and_bad_invocations(capsys) -> None:
    assert main(["conflicted.py"]) == 0
    assert capsys.readouterr().out == "Unmerged path: conflicted.py\n"

    assert main([]) == 2
    assert "usage: git-histodiff" in capsys.readouterr().err

    assert main(["--help"]) == 0
    assert "git config diff.external git-histodiff" in capsys.readouterr().out


def test_documented_git_workflow(tmp_path: Path) -> None:
    git = shutil.which("git")
    adapter = shutil.which("git-histodiff", path=str(Path(sys.executable).parent))
    assert git is not None, "Git is required for the integration test"
    assert adapter is not None, "install the project before running its tests"

    environment = os.environ.copy()
    environment.pop("GIT_EXTERNAL_DIFF", None)
    environment.pop("GIT_EXTERNAL_DIFF_TRUST_EXIT_CODE", None)
    environment["GIT_CONFIG_NOSYSTEM"] = "1"
    environment["GIT_CONFIG_GLOBAL"] = os.devnull

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [git, "-C", str(tmp_path), *args],
            check=False,
            capture_output=True,
            text=True,
            env=environment,
        )

    assert run("init", "-q").returncode == 0
    assert run("config", "user.name", "histodiff test").returncode == 0
    assert run("config", "user.email", "test@example.invalid").returncode == 0
    adapter_command = f'"{Path(adapter).as_posix()}"'
    assert run("config", "diff.external", adapter_command).returncode == 0

    source = tmp_path / "sample.py"
    source.write_text(
        "def first():\n"
        "    return 1\n\n"
        "def moved():\n"
        "    return 'kept'\n\n"
        "def last():\n"
        "    return 3\n",
        encoding="utf-8",
    )
    assert run("add", "sample.py").returncode == 0
    assert run("commit", "-qm", "initial").returncode == 0

    source.write_text(
        "def first():\n"
        "    return 2\n\n"
        "def last():\n"
        "    return 3\n\n"
        "def moved():\n"
        "    return 'kept'\n",
        encoding="utf-8",
    )

    working = run("diff", "--", "sample.py")
    assert working.returncode == 0
    assert "diff --histodiff a/sample.py b/sample.py" in working.stdout
    assert "-    return 1" in working.stdout
    assert "+    return 2" in working.stdout
    assert "-def moved():" in working.stdout
    assert "+def moved():" in working.stdout

    assert run("diff", "--exit-code", "--", "sample.py").returncode == 1

    assert run("add", "sample.py").returncode == 0
    staged = run("diff", "--cached")
    assert staged.returncode == 0
    assert "diff --histodiff a/sample.py b/sample.py" in staged.stdout

    assert run("commit", "-qm", "move and edit").returncode == 0
    committed = run("show", "--ext-diff", "--format=", "HEAD")
    assert committed.returncode == 0
    assert "diff --histodiff a/sample.py b/sample.py" in committed.stdout
