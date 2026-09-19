"""
Project packaging.

Produces a clean, distributable archive of the source tree. Deliberately has
no Qt import, so it can be run headless from `tools/` or called from the UI.

The old `tools/build_release.py` had two real problems:

  * Its ignore check looked for "\\venv\\" / "/venv/" as a *substring*, so a
    top-level `venv/` directory (no trailing separator match at the root) and
    any path oddity could slip through.
  * It wrote the archive into the project directory it was walking, so a
    rebuild could pick up the previous archive mid-walk.

This version walks with an explicit prune list, writes to a separate `dist/`
directory, and refuses to include itself.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, List, Optional, Tuple

# Directories pruned entirely. This is the list that keeps `venv/` out.
IGNORE_DIRS = frozenset({
    "venv", ".venv", "env", ".env", "virtualenv",
    "__pycache__", ".git", ".hg", ".svn",
    ".vscode", ".idea", ".vs",
    "dist", "build", "node_modules",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox",
    "site-packages", "Scripts", "bin-cache",
})

IGNORE_EXTS = frozenset({
    ".pyc", ".pyo", ".pyd", ".zip", ".tar", ".gz", ".log",
    ".spec", ".egg-info", ".db", ".sqlite", ".sqlite3",
})

IGNORE_FILES = frozenset({
    ".DS_Store", "Thumbs.db", "desktop.ini", ".coverage", "unicode_data.db",
})

GITIGNORE = """\
# Python
__pycache__/
*.py[cod]
*.egg-info/

# Virtual environments
venv/
.venv/
env/

# Build output
dist/
build/
*.zip

# Editors / OS
.vscode/
.idea/
.DS_Store
Thumbs.db
"""


@dataclass
class PackageResult:
    archive_path: str
    file_count: int
    size_bytes: int
    included: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)

    @property
    def size_human(self) -> str:
        size = float(self.size_bytes)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024 or unit == "GB":
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"


def _should_skip_file(name: str) -> bool:
    if name in IGNORE_FILES:
        return True
    ext = os.path.splitext(name)[1].lower()
    return ext in IGNORE_EXTS


def collect_files(root: str) -> Tuple[List[str], List[str]]:
    """Return (included, skipped) paths relative to `root`."""
    included: List[str] = []
    skipped: List[str] = []
    root = os.path.abspath(root)

    for dirpath, dirnames, filenames in os.walk(root):
        # Prune in place so os.walk never descends into ignored trees. This is
        # what actually keeps venv/ (and its thousands of files) out.
        pruned = [d for d in dirnames if d in IGNORE_DIRS or d.startswith(".")]
        for d in pruned:
            skipped.append(os.path.relpath(os.path.join(dirpath, d), root) + os.sep)
        dirnames[:] = [d for d in dirnames
                       if d not in IGNORE_DIRS and not d.startswith(".")]
        dirnames.sort()

        for name in sorted(filenames):
            rel = os.path.relpath(os.path.join(dirpath, name), root)
            if _should_skip_file(name):
                skipped.append(rel)
            else:
                included.append(rel)
    return included, skipped


def build_package(
    root: str,
    version: str = "",
    package_name: str = "unicode-explorer",
    output_dir: str = "",
    add_gitignore: bool = True,
    progress: Optional[Callable[[str], None]] = None,
) -> PackageResult:
    """Zip the project into `dist/`, excluding local environments and caches."""
    root = os.path.abspath(root)
    output_dir = os.path.abspath(output_dir or os.path.join(root, "dist"))
    os.makedirs(output_dir, exist_ok=True)

    stamp = version or datetime.now().strftime("%Y.%m.%d")
    archive_path = os.path.join(output_dir, f"{package_name}-{stamp}.zip")

    included, skipped = collect_files(root)

    def log(msg: str) -> None:
        if progress:
            progress(msg)

    log(f"Packaging {len(included)} files from {root}")
    if skipped:
        log(f"Excluding {len(skipped)} local/build artefacts (venv, caches, archives)")

    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for rel in included:
            # Nest under a folder so unzipping doesn't scatter files everywhere.
            z.write(os.path.join(root, rel), os.path.join(package_name, rel))
        if add_gitignore and ".gitignore" not in included:
            z.writestr(os.path.join(package_name, ".gitignore"), GITIGNORE)
            included.append(".gitignore (generated)")
            log("Added a generated .gitignore")

    size = os.path.getsize(archive_path)
    log(f"Wrote {os.path.basename(archive_path)}")
    return PackageResult(archive_path, len(included), size, included, skipped)
