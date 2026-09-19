"""Settings dialog: hotkey, appearance, and advanced tools."""

from __future__ import annotations

import os
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox, QColorDialog, QComboBox, QDialog, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from core import __version__
from core.packager import build_package
from core.settings import DEFAULT_HOTKEY, AppSettings
from core.uninstall import uninstall
from core.theme import PRESETS, Theme, build_stylesheet

# Qt key -> the name the `keyboard` library expects.
_SPECIAL_KEYS = {
    Qt.Key.Key_Space: "space", Qt.Key.Key_Tab: "tab",
    Qt.Key.Key_Return: "enter", Qt.Key.Key_Enter: "enter",
    Qt.Key.Key_Backspace: "backspace", Qt.Key.Key_Delete: "delete",
    Qt.Key.Key_Insert: "insert", Qt.Key.Key_Home: "home", Qt.Key.Key_End: "end",
    Qt.Key.Key_PageUp: "page up", Qt.Key.Key_PageDown: "page down",
    Qt.Key.Key_Up: "up", Qt.Key.Key_Down: "down",
    Qt.Key.Key_Left: "left", Qt.Key.Key_Right: "right",
    Qt.Key.Key_Escape: "esc", Qt.Key.Key_Print: "print screen",
}

_MODIFIER_KEYS = {
    Qt.Key.Key_Control, Qt.Key.Key_Alt, Qt.Key.Key_Shift, Qt.Key.Key_Meta,
    Qt.Key.Key_AltGr, Qt.Key.Key_CapsLock,
}


class HotkeyEdit(QLineEdit):
    """Click, then press a combination. Records it rather than typing text."""

    captured = Signal(str)

    def __init__(self, initial: str = "", parent=None) -> None:
        super().__init__(parent)
        self.setReadOnly(True)
        self.setObjectName("SearchBar")
        self.setPlaceholderText("Click here, then press a combination…")
        self._value = initial
        self.setText(self._pretty(initial))

    def value(self) -> str:
        return self._value

    @staticmethod
    def _pretty(combo: str) -> str:
        if not combo:
            return ""
        names = {"ctrl": "Ctrl", "alt": "Alt", "shift": "Shift",
                 "windows": "Win", "cmd": "Cmd"}
        return " + ".join(names.get(p, p.title()) for p in combo.split("+"))

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in _MODIFIER_KEYS:
            return  # wait for a real key

        mods = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("cmd" if sys.platform == "darwin" else "windows")

        if key in _SPECIAL_KEYS:
            base = _SPECIAL_KEYS[key]
        elif Qt.Key.Key_F1 <= key <= Qt.Key.Key_F24:
            base = f"f{key - Qt.Key.Key_F1 + 1}"
        elif Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            base = chr(key).lower()
        elif Qt.Key.Key_0 <= key <= Qt.Key.Key_9:
            base = chr(key)
        else:
            text = event.text().strip()
            if not text or not text.isprintable():
                return
            base = text.lower()

        if not parts:
            # A bare key as a *global* hotkey would hijack that key everywhere.
            self.setText("Needs at least one modifier (Ctrl / Alt / Shift)")
            return

        parts.append(base)
        self._value = "+".join(parts)
        self.setText(self._pretty(self._value))
        self.captured.emit(self._value)


class ColourButton(QPushButton):
    """A swatch that opens a colour picker."""

    picked = Signal(str)

    def __init__(self, colour: str, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour
        self.setFixedSize(58, 26)
        self.clicked.connect(self._choose)
        self._refresh()

    def colour(self) -> str:
        return self._colour

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self._refresh()

    def _refresh(self) -> None:
        self.setStyleSheet(
            f"background-color: {self._colour};"
            "border: 1px solid #555; border-radius: 6px;"
        )
        self.setToolTip(self._colour)

    def _choose(self) -> None:
        chosen = QColorDialog.getColor(QColor(self._colour), self, "Pick a colour")
        if chosen.isValid():
            self.set_colour(chosen.name())
            self.picked.emit(chosen.name())


class SettingsDialog(QDialog):
    """Preferences. `window` is the main window, used for live theme preview."""

    def __init__(self, settings: AppSettings, window: QWidget) -> None:
        super().__init__(window)
        self.settings = settings
        self.window_ref = window
        self.project_root = os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
        self._working_theme = settings.theme

        self.setWindowTitle("Unicode Explorer — Settings")
        self.setMinimumWidth(500)
        self.setStyleSheet(build_stylesheet(self._working_theme))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 14)
        tabs = QTabWidget(self)
        tabs.addTab(self._general_tab(), "General")
        tabs.addTab(self._appearance_tab(), "Appearance")
        tabs.addTab(self._advanced_tab(), "Advanced")
        layout.addWidget(tabs)

        buttons = QHBoxLayout()
        version = QLabel(f"v{__version__}", self)
        version.setObjectName("Note")
        buttons.addWidget(version)
        buttons.addStretch(1)
        reset = QPushButton("Reset to defaults", self)
        reset.clicked.connect(self._reset)
        buttons.addWidget(reset)
        close = QPushButton("Done", self)
        close.setObjectName("Primary")
        close.setDefault(True)
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    # ------------------------------------------------------------ general

    def _general_tab(self) -> QWidget:
        page = QWidget(self)
        form = QFormLayout(page)
        form.setContentsMargins(14, 16, 14, 14)
        form.setSpacing(10)

        self.hotkey_edit = HotkeyEdit(self.settings.hotkey, page)
        self.hotkey_edit.captured.connect(self._on_hotkey)
        form.addRow("Global hotkey", self.hotkey_edit)

        note = QLabel(
            "Registering a global hotkey needs Administrator on Windows and "
            "root on Linux. Without it the tray icon still works.", page
        )
        note.setObjectName("Note")
        note.setWordWrap(True)
        form.addRow("", note)

        self.hide_check = QCheckBox("Hide the window after copying", page)
        self.hide_check.setChecked(self.settings.hide_after_copy)
        self.hide_check.toggled.connect(
            lambda v: setattr(self.settings, "hide_after_copy", v)
        )
        form.addRow("", self.hide_check)
        return page

    def _on_hotkey(self, combo: str) -> None:
        self.settings.hotkey = combo

    # --------------------------------------------------------- appearance

    def _appearance_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(14, 16, 14, 14)

        row = QHBoxLayout()
        row.addWidget(QLabel("Preset", page))
        self.preset_combo = QComboBox(page)
        for name in PRESETS:
            self.preset_combo.addItem(name)
        self.preset_combo.addItem("Custom")
        current = self._working_theme.name
        self.preset_combo.setCurrentText(
            current if current in PRESETS or current == "Custom" else "Midnight"
        )
        self.preset_combo.currentTextChanged.connect(self._on_preset)
        row.addWidget(self.preset_combo, 1)
        outer.addLayout(row)

        group = QGroupBox("Colours", page)
        grid = QFormLayout(group)
        grid.setSpacing(8)
        self.colour_buttons = {}
        labels = {
            "bg": "Background", "surface": "Panels", "border": "Borders",
            "text": "Text", "muted": "Secondary text", "accent": "Accent",
        }
        for fieldname, label in labels.items():
            btn = ColourButton(getattr(self._working_theme, fieldname), group)
            btn.picked.connect(
                lambda colour, f=fieldname: self._on_colour(f, colour)
            )
            self.colour_buttons[fieldname] = btn
            grid.addRow(label, btn)
        outer.addWidget(group)

        hint = QLabel("Changes preview immediately in the main window.", page)
        hint.setObjectName("Note")
        outer.addWidget(hint)
        outer.addStretch(1)
        return page

    def _on_preset(self, name: str) -> None:
        if name in PRESETS:
            self._working_theme = PRESETS[name]
            for fieldname, btn in self.colour_buttons.items():
                btn.set_colour(getattr(self._working_theme, fieldname))
            self._apply_theme()

    def _on_colour(self, fieldname: str, colour: str) -> None:
        # Editing any swatch turns the palette into a custom one.
        self._working_theme = self._working_theme.with_overrides(
            name="Custom", **{fieldname: colour}
        )
        self.preset_combo.blockSignals(True)
        self.preset_combo.setCurrentText("Custom")
        self.preset_combo.blockSignals(False)
        self._apply_theme()

    def _apply_theme(self) -> None:
        self.settings.set_theme(self._working_theme)
        self.setStyleSheet(build_stylesheet(self._working_theme))

    # ----------------------------------------------------------- advanced

    def _advanced_tab(self) -> QWidget:
        page = QWidget(self)
        outer = QVBoxLayout(page)
        outer.setContentsMargins(14, 16, 14, 14)
        outer.setSpacing(10)

        self.dev_check = QCheckBox("Developer mode", page)
        self.dev_check.setChecked(self.settings.developer_mode)
        self.dev_check.toggled.connect(self._on_dev_mode)
        outer.addWidget(self.dev_check)

        dev_note = QLabel(
            "Exposes project maintenance tools. Not needed for everyday use.",
            page,
        )
        dev_note.setObjectName("Note")
        dev_note.setWordWrap(True)
        outer.addWidget(dev_note)

        self.dev_group = QGroupBox("Project tools", page)
        dev_layout = QVBoxLayout(self.dev_group)
        dev_layout.setSpacing(8)

        export_row = QHBoxLayout()
        self.export_btn = QPushButton("Export Package…", self.dev_group)
        self.export_btn.clicked.connect(self._export_package)
        export_row.addWidget(self.export_btn)
        self.open_dist_btn = QPushButton("Open output folder", self.dev_group)
        self.open_dist_btn.clicked.connect(self._open_dist)
        self.open_dist_btn.setEnabled(False)
        export_row.addWidget(self.open_dist_btn)
        export_row.addStretch(1)
        dev_layout.addLayout(export_row)

        export_note = QLabel(
            "Builds a clean archive of the source tree in dist/, excluding "
            "venv, __pycache__, .git and previous builds.", self.dev_group
        )
        export_note.setObjectName("Note")
        export_note.setWordWrap(True)
        dev_layout.addWidget(export_note)

        self.export_log = QPlainTextEdit(self.dev_group)
        self.export_log.setReadOnly(True)
        self.export_log.setFixedHeight(96)
        self.export_log.setPlaceholderText("Build output appears here.")
        dev_layout.addWidget(self.export_log)

        outer.addWidget(self.dev_group)
        self.dev_group.setVisible(self.settings.developer_mode)

        danger = QGroupBox("Remove Unicode Explorer", page)
        danger_layout = QVBoxLayout(danger)
        uninstall_btn = QPushButton("Uninstall…", danger)
        uninstall_btn.setObjectName("Danger")
        uninstall_btn.clicked.connect(self._uninstall)
        danger_layout.addWidget(uninstall_btn)
        danger_note = QLabel(
            "Clears saved settings, favourites and recents, then removes the "
            "virtual environment, caches and any auto-start entry.", danger
        )
        danger_note.setObjectName("Note")
        danger_note.setWordWrap(True)
        danger_layout.addWidget(danger_note)
        outer.addWidget(danger)

        outer.addStretch(1)
        return page

    def _on_dev_mode(self, enabled: bool) -> None:
        self.settings.developer_mode = enabled
        self.dev_group.setVisible(enabled)
        self.adjustSize()

    def _export_package(self) -> None:
        self.export_log.clear()
        self.export_btn.setEnabled(False)
        try:
            result = build_package(
                self.project_root,
                version=__version__,
                progress=self.export_log.appendPlainText,
            )
        except OSError as exc:
            self.export_log.appendPlainText(f"Failed: {exc}")
            self.export_btn.setEnabled(True)
            return

        self._last_archive = result.archive_path
        self.export_log.appendPlainText(
            f"Done — {result.file_count} files, {result.size_human}"
        )
        self.export_log.appendPlainText(result.archive_path)
        self.open_dist_btn.setEnabled(True)
        self.export_btn.setEnabled(True)

    def _open_dist(self) -> None:
        path = os.path.join(self.project_root, "dist")
        if not os.path.isdir(path):
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # noqa: S606
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            self.export_log.appendPlainText(f"Could not open folder: {exc}")

    def _uninstall(self) -> None:
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Uninstall Unicode Explorer")
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setText("Remove Unicode Explorer's local data?")
        confirm.setInformativeText(
            "This clears saved settings, favourites and recents, and deletes "
            "the virtual environment, caches and any auto-start entry.\n\n"
            "The project folder is not deleted — you can remove it yourself "
            "afterwards. This cannot be undone."
        )
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Cancel | QMessageBox.StandardButton.Yes
        )
        confirm.setDefaultButton(QMessageBox.StandardButton.Cancel)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return

        report = uninstall(self.project_root, remove_dist=True)
        self.settings.clear_all()

        lines = [report.freed_summary, ""]
        lines += [f"Removed: {p}" for p in report.removed[:12]]
        if len(report.removed) > 12:
            lines.append(f"…and {len(report.removed) - 12} more")
        lines += [f"Could not remove: {p}" for p in report.failed]
        lines += [""] + report.notes

        done = QMessageBox(self)
        done.setWindowTitle("Uninstall complete")
        done.setText("Unicode Explorer has been removed.")
        done.setDetailedText("\n".join(lines))
        done.setInformativeText("The application will now close.")
        done.exec()

        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    # -------------------------------------------------------------- reset

    def _reset(self) -> None:
        self.settings.hotkey = DEFAULT_HOTKEY
        self.hotkey_edit._value = DEFAULT_HOTKEY
        self.hotkey_edit.setText(HotkeyEdit._pretty(DEFAULT_HOTKEY))
        self.preset_combo.setCurrentText("Midnight")
        self._on_preset("Midnight")
