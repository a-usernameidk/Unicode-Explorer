"""
Unicode Explorer — a keyboard-driven picker for all 143,000 named Unicode
characters, living in the system tray.

Run with:  python main.py
"""

from __future__ import annotations

import os
import sys

# Make the project importable no matter what directory it is launched from.
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from PySide6.QtCore import QObject, QSharedMemory, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon

from core.settings import AppSettings
from ui.window import UnicodeExplorerWindow


class HotkeyManager(QObject):
    """Registers the global hotkey and can rebind it while running.

    The `keyboard` library fires callbacks on its own thread, so the callback
    only emits a signal; touching widgets from that thread would crash.
    """

    triggered = Signal()
    statusChanged = Signal(str)   # "" means registered successfully

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self._handle = None
        self._backend = None
        self.status = ""
        try:
            import keyboard
            self._backend = keyboard
        except ImportError:
            self.status = "keyboard package not installed \u2014 use the tray icon"

    @property
    def available(self) -> bool:
        return self._backend is not None

    def rebind(self, combo: str) -> str:
        """Bind `combo`, releasing any previous binding. Returns a status string."""
        if self._backend is None:
            self.statusChanged.emit(self.status)
            return self.status

        if self._handle is not None:
            try:
                self._backend.remove_hotkey(self._handle)
            except (KeyError, ValueError):
                pass  # already gone
            self._handle = None

        try:
            # `suppress=True` is deliberately not used: it swallowed the
            # keystroke globally and broke the shortcut in every other app.
            self._handle = self._backend.add_hotkey(combo, self.triggered.emit)
            self.status = ""
        except Exception as exc:  # permissions, no X server, bad combo
            self.status = f"could not register {combo} ({exc}) \u2014 use the tray icon"

        self.statusChanged.emit(self.status)
        return self.status

    def release(self) -> None:
        if self._backend is not None and self._handle is not None:
            try:
                self._backend.remove_hotkey(self._handle)
            except (KeyError, ValueError):
                pass
            self._handle = None


def build_tray_icon(accent: str = "#7aa2f7", bg: str = "#16161e") -> QIcon:
    """Draw a glyph icon instead of borrowing the 'information' icon."""
    pixmap = QPixmap(64, 64)
    pixmap.fill(QColor(bg))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    painter.setPen(QColor(accent))
    font = QFont()
    font.setPointSize(34)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), int(Qt.AlignmentFlag.AlignCenter), "U+")
    painter.end()
    return QIcon(pixmap)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Unicode Explorer")
    app.setQuitOnLastWindowClosed(False)

    # Refuse to start twice; duplicate tray icons and double hotkeys are a mess.
    guard = QSharedMemory("UnicodeExplorer-SingleInstance", app)
    if not guard.create(1):
        QMessageBox.information(
            None, "Unicode Explorer", "Unicode Explorer is already running."
        )
        return 0

    settings = AppSettings(app)
    theme = settings.theme

    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("[!] No system tray on this desktop; showing the window directly.")

    window = UnicodeExplorerWindow(settings)

    hotkeys = HotkeyManager(app)
    hotkeys.triggered.connect(window.reveal)

    tray = QSystemTrayIcon(build_tray_icon(theme.accent, theme.bg), app)
    menu = QMenu()
    menu.addAction("Open Explorer").triggered.connect(window.reveal)
    menu.addAction("Settings\u2026").triggered.connect(window.open_settings)
    menu.addSeparator()
    menu.addAction("Quit").triggered.connect(app.quit)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: window.reveal()
        if reason == QSystemTrayIcon.ActivationReason.Trigger
        else None
    )
    tray.show()

    def refresh_status(problem: str) -> None:
        if problem:
            tray.setToolTip(f"Unicode Explorer \u2014 {problem}")
            print(f"[!] {problem}")
        else:
            tray.setToolTip(f"Unicode Explorer \u2014 press {settings.hotkey}")
            print(f"[*] Listening for {settings.hotkey}")

    hotkeys.statusChanged.connect(refresh_status)

    # Rebind live whenever the hotkey is changed in Settings.
    settings.hotkeyChanged.connect(hotkeys.rebind)
    # Keep the tray icon in step with the chosen palette.
    settings.themeChanged.connect(
        lambda t: tray.setIcon(build_tray_icon(t.accent, t.bg))
    )

    problem = hotkeys.rebind(settings.hotkey)
    if problem:
        window.reveal()  # nothing else would open it, so show it once

    app.aboutToQuit.connect(hotkeys.release)
    app.aboutToQuit.connect(settings.sync)

    print("[*] Unicode Explorer running in the system tray.")
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
