"""Persistent application settings."""

from __future__ import annotations

from typing import List

from PySide6.QtCore import QObject, QSettings, Signal

from core.theme import DEFAULT_THEME, PRESETS, Theme

ORG = "UnicodeExplorer"
APP = "UnicodeExplorer"

DEFAULT_HOTKEY = "ctrl+alt+u"
MAX_RECENTS = 40


class AppSettings(QObject):
    """Typed accessors over QSettings, plus signals so the UI can react.

    Previously the window poked QSettings directly with stringly-typed keys and
    nothing else could observe a change.
    """

    themeChanged = Signal(object)      # Theme
    hotkeyChanged = Signal(str)
    developerModeChanged = Signal(bool)

    def __init__(self, parent: QObject = None) -> None:
        super().__init__(parent)
        self._s = QSettings(ORG, APP)

    # ------------------------------------------------------------- hotkey

    @property
    def hotkey(self) -> str:
        return str(self._s.value("hotkey", DEFAULT_HOTKEY))

    @hotkey.setter
    def hotkey(self, value: str) -> None:
        value = (value or DEFAULT_HOTKEY).strip().lower()
        if value != self.hotkey:
            self._s.setValue("hotkey", value)
            self.hotkeyChanged.emit(value)

    # -------------------------------------------------------------- theme

    @property
    def theme(self) -> Theme:
        name = str(self._s.value("theme/name", DEFAULT_THEME.name))
        base = PRESETS.get(name, DEFAULT_THEME)
        if name != "Custom":
            return base
        # Custom palettes are stored field by field, falling back to Midnight
        # for anything that was never set.
        overrides = {
            f: self._s.value(f"theme/custom/{f}", "")
            for f in Theme.field_names()
        }
        return DEFAULT_THEME.with_overrides(name="Custom", **overrides)

    def set_theme(self, theme: Theme) -> None:
        self._s.setValue("theme/name", theme.name)
        if theme.name == "Custom":
            for f in Theme.field_names():
                self._s.setValue(f"theme/custom/{f}", getattr(theme, f))
        self.themeChanged.emit(theme)

    # ------------------------------------------------------- developer mode

    @property
    def developer_mode(self) -> bool:
        return str(self._s.value("developer_mode", "false")).lower() == "true"

    @developer_mode.setter
    def developer_mode(self, value: bool) -> None:
        self._s.setValue("developer_mode", "true" if value else "false")
        self.developerModeChanged.emit(bool(value))

    # ---------------------------------------------------------- behaviour

    @property
    def hide_after_copy(self) -> bool:
        return str(self._s.value("hide_after_copy", "true")).lower() == "true"

    @hide_after_copy.setter
    def hide_after_copy(self, value: bool) -> None:
        self._s.setValue("hide_after_copy", "true" if value else "false")

    # ------------------------------------------------ favourites & recents

    def _int_list(self, key: str) -> List[int]:
        raw = self._s.value(key, []) or []
        if isinstance(raw, str):          # QSettings collapses 1-item lists
            raw = [raw]
        out = []
        for item in raw:
            try:
                out.append(int(item))
            except (TypeError, ValueError):
                continue
        return out

    @property
    def favourites(self) -> List[int]:
        return self._int_list("favourites")

    @favourites.setter
    def favourites(self, value: List[int]) -> None:
        self._s.setValue("favourites", [str(v) for v in value])

    @property
    def recents(self) -> List[int]:
        return self._int_list("recents")

    @recents.setter
    def recents(self, value: List[int]) -> None:
        self._s.setValue("recents", [str(v) for v in value[:MAX_RECENTS]])

    # ----------------------------------------------------------- lifecycle

    def sync(self) -> None:
        self._s.sync()

    def clear_all(self) -> None:
        """Wipe every stored preference. Used by the uninstaller."""
        self._s.clear()
        self._s.sync()

    def storage_location(self) -> str:
        return self._s.fileName()
