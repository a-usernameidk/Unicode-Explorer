"""
Theming.

Replaces the old `styles.py`, which hardcoded a single palette as module-level
constants at import time (so nothing could change colours at runtime).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Dict

from PySide6.QtGui import QColor


@dataclass(frozen=True)
class Theme:
    """A complete palette. Every colour is a hex string."""

    name: str = "Midnight"
    bg: str = "#16161e"
    surface: str = "#1f1f2b"
    border: str = "#2f2f3f"
    text: str = "#c8d0e0"
    muted: str = "#7f869c"
    accent: str = "#7aa2f7"

    @property
    def on_accent(self) -> str:
        """Readable text colour on top of the accent fill.

        Picked by luminance so a light accent doesn't end up with white text.
        """
        c = QColor(self.accent)
        luminance = (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255
        return "#10101a" if luminance > 0.55 else "#ffffff"

    @property
    def is_light(self) -> bool:
        c = QColor(self.bg)
        return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255 > 0.5

    def with_overrides(self, **kwargs) -> "Theme":
        data = asdict(self)
        data.update({k: v for k, v in kwargs.items() if v})
        return Theme(**data)

    @staticmethod
    def field_names() -> list:
        return [f.name for f in fields(Theme) if f.name != "name"]


PRESETS: Dict[str, Theme] = {
    t.name: t
    for t in (
        Theme(),  # Midnight (default)
        Theme(name="Nord", bg="#2e3440", surface="#3b4252", border="#434c5e",
              text="#d8dee9", muted="#7b88a1", accent="#88c0d0"),
        Theme(name="Dracula", bg="#282a36", surface="#343746", border="#44475a",
              text="#f8f8f2", muted="#6272a4", accent="#bd93f9"),
        Theme(name="Forest", bg="#121a17", surface="#1c2723", border="#2b3a34",
              text="#cfe3d8", muted="#7a9689", accent="#5fd08a"),
        Theme(name="Paper", bg="#fbfbfd", surface="#eeeef4", border="#d5d5e0",
              text="#1d1d24", muted="#6b6b7a", accent="#3b5bdb"),
        Theme(name="High Contrast", bg="#000000", surface="#121212", border="#4d4d4d",
              text="#ffffff", muted="#c9c9c9", accent="#ffd400"),
    )
}

DEFAULT_THEME = PRESETS["Midnight"]


def build_stylesheet(t: Theme) -> str:
    """Render a Qt stylesheet for the given palette."""
    hover = t.surface if not t.is_light else "#e2e2ec"
    return f"""
#Root {{
    background-color: {t.bg};
    border: 1px solid {t.border};
    border-radius: 12px;
}}
QLineEdit#SearchBar {{
    background-color: {t.surface};
    border: 1px solid {t.border};
    border-radius: 8px;
    padding: 10px 12px;
    font-size: 15px;
    color: {t.text};
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
}}
QLineEdit#SearchBar:focus {{ border: 1px solid {t.accent}; }}
QComboBox {{
    background-color: {t.surface};
    border: 1px solid {t.border};
    border-radius: 8px;
    padding: 6px 10px;
    color: {t.muted};
    min-width: 140px;
}}
QComboBox QAbstractItemView {{
    background-color: {t.surface};
    color: {t.text};
    selection-background-color: {t.accent};
    selection-color: {t.on_accent};
    border: 1px solid {t.border};
    outline: none;
}}
QToolButton#GearButton {{
    background-color: {t.surface};
    border: 1px solid {t.border};
    border-radius: 8px;
    color: {t.muted};
    font-size: 15px;
    padding: 6px 9px;
}}
QToolButton#GearButton:hover {{ color: {t.accent}; border-color: {t.accent}; }}
QListWidget {{ background-color: transparent; border: none; outline: none; }}
QListWidget::item {{ color: {t.text}; padding: 4px 6px; border-radius: 8px; }}
QListWidget::item:selected {{ background-color: {t.accent}; color: {t.on_accent}; }}
QScrollBar:vertical {{ background: transparent; width: 8px; margin: 0; }}
QScrollBar::handle:vertical {{
    background: {t.border}; border-radius: 4px; min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QLabel#Detail {{ color: {t.muted}; font-size: 12px; }}
QLabel#Hint {{ color: {t.muted}; font-size: 11px; }}

/* ---- settings dialog ---- */
QDialog {{ background-color: {t.bg}; }}
QDialog QLabel {{ color: {t.text}; }}
QDialog QLabel#Note {{ color: {t.muted}; font-size: 11px; }}
QDialog QLabel#Danger {{ color: #ff6b6b; font-size: 11px; }}
QTabWidget::pane {{ border: 1px solid {t.border}; border-radius: 8px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {t.muted};
    padding: 7px 16px; border: 1px solid transparent;
    border-top-left-radius: 8px; border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{
    color: {t.text}; background: {t.surface};
    border-color: {t.border}; border-bottom-color: {t.surface};
}}
QGroupBox {{
    color: {t.muted}; border: 1px solid {t.border};
    border-radius: 8px; margin-top: 12px; padding-top: 10px;
}}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 5px; }}
QPushButton {{
    background-color: {t.surface}; color: {t.text};
    border: 1px solid {t.border}; border-radius: 8px;
    padding: 7px 14px;
}}
QPushButton:hover {{ border-color: {t.accent}; color: {t.accent}; }}
QPushButton:disabled {{ color: {t.muted}; border-color: {t.border}; }}
QPushButton#Primary {{
    background-color: {t.accent}; color: {t.on_accent}; border: none;
}}
QPushButton#Danger {{ color: #ff6b6b; border-color: #5c2b2b; }}
QPushButton#Danger:hover {{ background-color: #3a1e1e; color: #ff8787; }}
QCheckBox {{ color: {t.text}; spacing: 8px; }}
QCheckBox::indicator {{
    width: 15px; height: 15px; border-radius: 4px;
    border: 1px solid {t.border}; background: {hover};
}}
QCheckBox::indicator:checked {{ background: {t.accent}; border-color: {t.accent}; }}
QPlainTextEdit {{
    background-color: {t.surface}; color: {t.muted};
    border: 1px solid {t.border}; border-radius: 8px;
    font-family: Menlo, Consolas, monospace; font-size: 11px;
}}
"""
