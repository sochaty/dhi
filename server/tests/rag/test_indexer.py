"""Unit tests for rag/indexer.py.

Uses tmp_path (pytest built-in) to create real directory trees — no mocks,
no network, no Chroma.  pathspec is available in the test environment (it's
in requirements.txt), so .gitignore filtering is tested end-to-end.
"""

from pathlib import Path

from rag.indexer import count_source_files, iter_source_files

# ── helpers ────────────────────────────────────────────────────────────────────


def _write(root: Path, rel: str, content: str = "# placeholder\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    return p


# ── basic discovery ────────────────────────────────────────────────────────────


class TestIterSourceFiles:
    def test_discovers_python_files(self, tmp_path):
        _write(tmp_path, "a.py")
        _write(tmp_path, "b.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        basenames = {Path(p).name for p in result}
        assert "a.py" in basenames
        assert "b.py" in basenames

    def test_discovers_multiple_languages(self, tmp_path):
        _write(tmp_path, "main.go", "package main\nfunc main() {}\n")
        _write(tmp_path, "lib.rs", "fn main() {}\n")
        _write(tmp_path, "app.ts", "export const x = 1;\n")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        basenames = {Path(p).name for p in result}
        assert "main.go" in basenames
        assert "lib.rs" in basenames
        assert "app.ts" in basenames

    def test_ignores_non_source_files(self, tmp_path):
        _write(tmp_path, "README.md")
        _write(tmp_path, "styles.css")
        _write(tmp_path, "Dockerfile")
        _write(tmp_path, "app.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        basenames = {Path(p).name for p in result}
        assert "README.md" not in basenames
        assert "styles.css" not in basenames
        assert "Dockerfile" not in basenames
        assert "app.py" in basenames

    def test_recurses_into_subdirectories(self, tmp_path):
        _write(tmp_path, "src/core/utils.py")
        _write(tmp_path, "src/core/models.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        basenames = {Path(p).name for p in result}
        assert "utils.py" in basenames
        assert "models.py" in basenames

    def test_empty_directory_returns_nothing(self, tmp_path):
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        assert result == []

    def test_returns_absolute_paths(self, tmp_path):
        _write(tmp_path, "foo.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        for p in result:
            assert Path(p).is_absolute()

    def test_all_paths_are_files_that_exist(self, tmp_path):
        _write(tmp_path, "a.py")
        _write(tmp_path, "b.ts")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        for p in result:
            assert Path(p).is_file(), f"{p} is not a file"


# ── skip-dir pruning ───────────────────────────────────────────────────────────


class TestSkipDirs:
    def test_skips_node_modules(self, tmp_path):
        _write(tmp_path, "node_modules/lodash/index.js")
        _write(tmp_path, "src/index.js")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        paths = [Path(p).parts for p in result]
        assert not any("node_modules" in parts for parts in paths)

    def test_skips_dot_git(self, tmp_path):
        _write(tmp_path, ".git/COMMIT_EDITMSG")
        _write(tmp_path, "app.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        paths = [Path(p).parts for p in result]
        assert not any(".git" in parts for parts in paths)

    def test_skips_pycache(self, tmp_path):
        _write(tmp_path, "__pycache__/app.cpython-311.pyc")
        _write(tmp_path, "app.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        paths = [Path(p).parts for p in result]
        assert not any("__pycache__" in parts for parts in paths)

    def test_skips_venv(self, tmp_path):
        _write(tmp_path, ".venv/lib/site-packages/pip/__init__.py")
        _write(tmp_path, "main.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        paths = [Path(p).parts for p in result]
        assert not any(".venv" in parts for parts in paths)

    def test_skips_hidden_directories(self, tmp_path):
        _write(tmp_path, ".hidden/secret.py")
        _write(tmp_path, "visible.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        paths = [Path(p).parts for p in result]
        assert not any(any(p.startswith(".") for p in parts) for parts in paths)

    def test_skips_dist(self, tmp_path):
        _write(tmp_path, "dist/bundle.js")
        _write(tmp_path, "src/index.js")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        paths = [Path(p).parts for p in result]
        assert not any("dist" in parts for parts in paths)


# ── .gitignore filtering ───────────────────────────────────────────────────────


class TestGitignoreFiltering:
    def test_gitignore_excludes_pattern(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.log\n")
        _write(tmp_path, "error.log")
        _write(tmp_path, "app.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=True))
        basenames = {Path(p).name for p in result}
        assert "error.log" not in basenames
        assert "app.py" in basenames

    def test_gitignore_excludes_directory(self, tmp_path):
        (tmp_path / ".gitignore").write_text("generated/\n")
        _write(tmp_path, "generated/models.py")
        _write(tmp_path, "src/core.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=True))
        paths = [Path(p).parts for p in result]
        assert not any("generated" in parts for parts in paths)

    def test_no_gitignore_includes_all_source(self, tmp_path):
        _write(tmp_path, "a.py")
        _write(tmp_path, "b.ts")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=True))
        assert len(result) == 2

    def test_respect_gitignore_false_ignores_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.py\n")
        _write(tmp_path, "app.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=False))
        basenames = {Path(p).name for p in result}
        assert "app.py" in basenames

    def test_gitignore_wildcard_excludes_multiple(self, tmp_path):
        (tmp_path / ".gitignore").write_text("secret_*.py\n")
        _write(tmp_path, "secret_key.py")
        _write(tmp_path, "secret_config.py")
        _write(tmp_path, "public.py")
        result = list(iter_source_files(str(tmp_path), respect_gitignore=True))
        basenames = {Path(p).name for p in result}
        assert "secret_key.py" not in basenames
        assert "secret_config.py" not in basenames
        assert "public.py" in basenames


# ── count_source_files ─────────────────────────────────────────────────────────


class TestCountSourceFiles:
    def test_count_matches_iter_length(self, tmp_path):
        _write(tmp_path, "a.py")
        _write(tmp_path, "b.ts")
        _write(tmp_path, "README.md")
        n = count_source_files(str(tmp_path), respect_gitignore=False)
        assert n == 2

    def test_empty_dir_returns_zero(self, tmp_path):
        assert count_source_files(str(tmp_path)) == 0
