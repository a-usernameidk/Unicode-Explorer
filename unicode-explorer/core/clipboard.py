"""
Clipboard output.

The old implementation used raw pywin32 and was broken in ways that silently
corrupted pastes:

  * CF_UNICODETEXT was handed UTF-16LE bytes with no NUL terminator.
  * "HTML Format" was set without the mandatory CF_HTML byte-offset header, so
    any app that prefers HTML (Word, Outlook, browsers) pasted garbage.
  * CF_TEXT was set to the *Python escape* of the character, so plain-text
    targets pasted "\\u2713" instead of the glyph.
  * The clipboard was opened before the try block, so any failure leaked the
    clipboard lock and froze copy/paste system-wide.

Qt's QClipboard handles all of that correctly on Windows, macOS and Linux, so
pywin32 is no longer a dependency.
"""

from __future__ import annotations

from html import escape as _html_escape

from PySide6.QtCore import QMimeData
from PySide6.QtGui import QGuiApplication


class ClipboardEngine:
    """Copies a character to the clipboard in several formats at once."""

    @staticmethod
    def copy(text: str, name: str = "") -> bool:
        """Copy `text` as plain text, plus an HTML flavour carrying the name."""
        clipboard = QGuiApplication.clipboard()
        if clipboard is None:
            return False

        mime = QMimeData()
        mime.setText(text)
        title = f' title="{_html_escape(name, quote=True)}"' if name else ""
        mime.setHtml(f"<span{title}>{_html_escape(text)}</span>")
        clipboard.setMimeData(mime)
        return True

    # Backwards-compatible alias: the old window called `inject_unicode`.
    @classmethod
    def inject_unicode(cls, character: str, name: str = "") -> bool:
        return cls.copy(character, name)
