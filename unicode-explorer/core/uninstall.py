"""
Uninstall / cleanup.

Qt-free so it can be exercised headlessly. Nothing here deletes the project
folder itself: a running process cannot reliably remove the directory it is
executing from, especially on Windows. The caller reports the folder path and
lets the user delete it.
"""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass, field
from typing import List

VENV_DIRS = ("venv", ".venv", "env")
CACHE_DIRS = ("__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache")


@dataclass
class UninstallReport:
    removed: List[str] = field(default_factory=list)
    failed: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)

    @property
    def freed_summary(self) -> str:
        if not self.removed and not self.failed:
            return "Nothing to remove."
        return f"{len(self.removed)} item(s) removed, {len(self.failed)} failed."


def _rm(path: str, report: UninstallReport) -> None:
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            shutil.rmtree(path)
        elif os.path.exists(path) or os.path.islink(path):
            os.remove(path)
        else:
            return
        report.removed.append(path)
    except OSError as exc:
        report.failed.append(f"{path} ({exc.strerror or exc})")


def startup_entries() -> List[str]:
    """Auto-start shortcuts a previous version may have created."""
    found: List[str] = []
    if sys.platform != "win32":
        return found
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return found
    startup = os.path.join(
        appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )
    if not os.path.isdir(startup):
        return found
    for name in os.listdir(startup):
        low = name.lower()
        if "unicode" in low and low.endswith((".lnk", ".vbs", ".bat", ".cmd")):
            found.append(os.path.join(startup, name))
    return found


def uninstall(
    project_root: str,
    remove_venv: bool = True,
    remove_caches: bool = True,
    remove_startup: bool = True,
    remove_dist: bool = False,
) -> UninstallReport:
    """Remove local artefacts. Settings are cleared separately by the caller."""
    report = UninstallReport()
    project_root = os.path.abspath(project_root)

    if remove_startup:
        for entry in startup_entries():
            _rm(entry, report)

    if remove_venv:
        for name in VENV_DIRS:
            candidate = os.path.join(project_root, name)
            if os.path.isdir(candidate):
                _rm(candidate, report)

    if remove_caches:
        for dirpath, dirnames, _ in os.walk(project_root, topdown=True):
            for name in list(dirnames):
                if name in CACHE_DIRS:
                    _rm(os.path.join(dirpath, name), report)
                    dirnames.remove(name)

    if remove_dist:
        _rm(os.path.join(project_root, "dist"), report)

    report.notes.append(
        f"The project folder itself was left in place: {project_root}"
    )
    report.notes.append("Delete it manually once the app has closed.")
    return report
