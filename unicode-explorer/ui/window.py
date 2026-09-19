"""Launcher-style Unicode picker window."""

from __future__ import annotations

from typing import List, Optional

from PySide6.QtCore import (
    QEvent, QPoint, QRect, QSize, Qt, QThread, QTimer, Signal,
)
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QStyle, QStyledItemDelegate, QToolButton, QVBoxLayout,
    QWidget,
)

from core.clipboard import ClipboardEngine
from core.index import Character, UnicodeIndex, shared_index
from core.settings import MAX_RECENTS, AppSettings
from ui.settings_dialog import SettingsDialog
from core.theme import Theme, build_stylesheet

_ROLE_CHAR = Qt.ItemDataRole.UserRole + 1


class IndexLoader(QThread):
    """Builds the 143k-character index off the UI thread so the window opens
    instantly instead of freezing on first show."""

    ready = Signal(object)

    def run(self) -> None:
        self.ready.emit(shared_index())


class CharDelegate(QStyledItemDelegate):
    """Draws each row as: big glyph | name | codepoint."""

    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme
        self.glyph_font = QFont()
        self.glyph_font.setPointSize(19)
        self.name_font = QFont()
        self.name_font.setPointSize(10)
        self.code_font = QFont()
        self.code_font.setPointSize(9)

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 40)

    def paint(self, painter: QPainter, option, index) -> None:
        char: Optional[Character] = index.data(_ROLE_CHAR)
        if char is None:
            super().paint(painter, option, index)
            return

        painter.save()
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect: QRect = option.rect.adjusted(4, 2, -4, -2)

        if selected:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setBrush(QColor(self.theme.accent))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(rect, 8, 8)

        text_colour = QColor(
            self.theme.on_accent if selected else self.theme.text)
        muted_colour = QColor(
            self.theme.on_accent if selected else self.theme.muted)

        # Combining marks and format chars render as nothing on their own, so
        # pair them with a dotted circle to make them visible.
        glyph = char.char if char.is_printable else "\u25CC" + char.char

        painter.setFont(self.glyph_font)
        painter.setPen(text_colour)
        glyph_rect = QRect(rect.left() + 10, rect.top(), 44, rect.height())
        painter.drawText(glyph_rect, int(Qt.AlignmentFlag.AlignCenter), glyph)

        painter.setFont(self.code_font)
        fm = QFontMetrics(self.code_font)
        code_w = fm.horizontalAdvance("U+10FFFF") + 14
        code_rect = QRect(rect.right() - code_w, rect.top(), code_w, rect.height())
        painter.setPen(muted_colour)
        painter.drawText(
            code_rect,
            int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
            char.code,
        )

        painter.setFont(self.name_font)
        painter.setPen(text_colour)
        name_rect = QRect(
            rect.left() + 62, rect.top(),
            rect.width() - 62 - code_w - 8, rect.height(),
        )
        elided = QFontMetrics(self.name_font).elidedText(
            char.name.title(), Qt.TextElideMode.ElideRight, name_rect.width()
        )
        painter.drawText(
            name_rect,
            int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
            elided,
        )
        painter.restore()


class UnicodeExplorerWindow(QWidget):
    def __init__(self, settings: Optional[AppSettings] = None) -> None:
        super().__init__()
        self.setWindowTitle("Unicode Explorer")
        self.resize(660, 480)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)

        self.settings = settings or AppSettings(self)
        self.index: Optional[UnicodeIndex] = None
        self.clipboard_engine = ClipboardEngine()
        self._drag_offset: Optional[QPoint] = None
        self._dialog: Optional[SettingsDialog] = None

        self.favourites: List[int] = self.settings.favourites
        self.recents: List[int] = self.settings.recents

        self._setup_ui()
        self.apply_theme(self.settings.theme)
        self.settings.themeChanged.connect(self.apply_theme)

        # Debounce keystrokes so a fast typist doesn't queue up searches.
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(60)
        self._debounce.timeout.connect(self.run_search)

        self._loader = IndexLoader(self)
        self._loader.ready.connect(self._on_index_ready)
        self._loader.start()

    # ------------------------------------------------------------------ ui

    def _setup_ui(self) -> None:
        root = QWidget(self)
        root.setObjectName("Root")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(root)

        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(8)
        self.search_bar = QLineEdit(self)
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText(
            "Search 143,000 characters — name, U+2713, or paste a glyph"
        )
        self.search_bar.textChanged.connect(lambda _: self._debounce.start())
        self.search_bar.installEventFilter(self)
        top.addWidget(self.search_bar, 1)

        self.block_filter = QComboBox(self)
        self.block_filter.addItem("All blocks", "")
        self.block_filter.currentIndexChanged.connect(self.run_search)
        top.addWidget(self.block_filter)

        self.gear_button = QToolButton(self)
        self.gear_button.setObjectName("GearButton")
        self.gear_button.setText("\u2699")
        self.gear_button.setToolTip("Settings")
        self.gear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.gear_button.clicked.connect(self.open_settings)
        top.addWidget(self.gear_button)
        layout.addLayout(top)

        self.list_widget = QListWidget(self)
        self.list_widget.setItemDelegate(
            CharDelegate(self.settings.theme, self))
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        self.list_widget.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.list_widget.itemActivated.connect(self.copy_item)
        self.list_widget.itemClicked.connect(self.copy_item)
        self.list_widget.currentItemChanged.connect(
            lambda cur, _prev: self._update_detail(cur)
        )
        layout.addWidget(self.list_widget, 1)

        self.detail_label = QLabel("", self)
        self.detail_label.setObjectName("Detail")
        self.detail_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self.detail_label)

        self.hint_label = QLabel(
            "↑↓ navigate   ·   Enter copy   ·   Ctrl+Enter copy escape   ·   "
            "Ctrl+D favourite   ·   Esc hide",
            self,
        )
        self.hint_label.setObjectName("Hint")
        layout.addWidget(self.hint_label)

    # --------------------------------------------------------------- theme

    def apply_theme(self, theme: Theme) -> None:
        """Restyle live. The delegate paints manually, so it needs the palette
        handed to it directly -- a stylesheet alone won't reach it."""
        self.setStyleSheet(build_stylesheet(theme))
        delegate = self.list_widget.itemDelegate()
        if isinstance(delegate, CharDelegate):
            delegate.theme = theme
        self.list_widget.viewport().update()

    def open_settings(self) -> None:
        if self._dialog is None:
            self._dialog = SettingsDialog(self.settings, self)
        self._dialog.show()
        self._dialog.raise_()
        self._dialog.activateWindow()

    # ------------------------------------------------------------- loading

    def _on_index_ready(self, index: UnicodeIndex) -> None:
        self.index = index
        self.block_filter.blockSignals(True)
        for block in index.blocks:
            self.block_filter.addItem(block, block)
        self.block_filter.blockSignals(False)
        self.run_search()

    # -------------------------------------------------------------- search

    def run_search(self) -> None:
        if self.index is None:
            self.detail_label.setText("Building Unicode index…")
            return

        query = self.search_bar.text()
        block = self.block_filter.currentData() or None

        if not query.strip() and not block:
            results = self._starter_set()
        else:
            results = self.index.search(query, limit=300, block=block)

        self.list_widget.clear()
        for char in results:
            item = QListWidgetItem()
            item.setData(_ROLE_CHAR, char)
            if char.cp in self.favourites:
                item.setData(Qt.ItemDataRole.ToolTipRole, "Favourite")
            self.list_widget.addItem(item)

        if self.list_widget.count():
            self.list_widget.setCurrentRow(0)
        else:
            self.detail_label.setText(f"No characters match “{query.strip()}”.")

    def _starter_set(self) -> List[Character]:
        """With no query, show favourites, then recents, then common symbols."""
        assert self.index is not None
        out: List[Character] = []
        seen = set()
        for cp in self.favourites + self.recents:
            char = self.index.get(cp)
            if char and cp not in seen:
                out.append(char)
                seen.add(cp)
        for char in self.index.search("", limit=300):
            if char.cp not in seen:
                out.append(char)
        return out[:300]

    def _update_detail(self, item: Optional[QListWidgetItem]) -> None:
        char: Optional[Character] = item.data(_ROLE_CHAR) if item else None
        if char is None:
            self.detail_label.setText("")
            return
        star = "★ " if char.cp in self.favourites else ""
        self.detail_label.setText(
            f"{star}{char.code}   ·   {char.block}   ·   {char.category_label}"
            f"   ·   {char.python_escape}   ·   {char.html_entity}"
            f"   ·   UTF-8 {char.utf8_bytes}"
        )

    # --------------------------------------------------------------- copy

    def _current_char(self) -> Optional[Character]:
        item = self.list_widget.currentItem()
        return item.data(_ROLE_CHAR) if item else None

    def copy_item(self, item: Optional[QListWidgetItem] = None) -> None:
        char = item.data(_ROLE_CHAR) if item else self._current_char()
        if char is None:
            return
        self.clipboard_engine.copy(char.char, char.name)
        self._remember(char.cp)
        if self.settings.hide_after_copy:
            self.hide()

    def copy_variant(self, kind: str) -> None:
        char = self._current_char()
        if char is None:
            return
        payload = char.python_escape if kind == "escape" else char.html_entity
        self.clipboard_engine.copy(payload, char.name)
        self._remember(char.cp)
        if self.settings.hide_after_copy:
            self.hide()

    def _remember(self, cp: int) -> None:
        if cp in self.recents:
            self.recents.remove(cp)
        self.recents.insert(0, cp)
        del self.recents[MAX_RECENTS:]
        self.settings.recents = self.recents

    def toggle_favourite(self) -> None:
        char = self._current_char()
        if char is None:
            return
        if char.cp in self.favourites:
            self.favourites.remove(char.cp)
        else:
            self.favourites.insert(0, char.cp)
        self.settings.favourites = self.favourites
        self._update_detail(self.list_widget.currentItem())

    # ------------------------------------------------------------ behaviour

    def eventFilter(self, obj, event) -> bool:
        """Let ↑/↓/PgUp/PgDn drive the list while focus stays in the search bar."""
        if obj is self.search_bar and event.type() == QEvent.Type.KeyPress:
            if event.key() in (
                Qt.Key.Key_Up, Qt.Key.Key_Down,
                Qt.Key.Key_PageUp, Qt.Key.Key_PageDown,
            ):
                self.list_widget.keyPressEvent(event)
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        if key == Qt.Key.Key_Escape:
            self.hide()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if ctrl and shift:
                self.copy_variant("html")
            elif ctrl:
                self.copy_variant("escape")
            else:
                self.copy_item()
        elif ctrl and key == Qt.Key.Key_D:
            self.toggle_favourite()
        else:
            super().keyPressEvent(event)

    # Frameless windows have no title bar, so make the whole surface draggable.
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = (
                event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:
        if self._drag_offset is not None:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_offset = None

    def center_on_cursor(self) -> None:
        """Open near the mouse, clamped to the screen the cursor is actually on."""
        from PySide6.QtGui import QCursor, QGuiApplication

        pos = QCursor.pos()
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()

        x = pos.x() - self.width() // 2
        y = pos.y() - self.height() // 3
        x = max(area.left(), min(x, area.right() - self.width()))
        y = max(area.top(), min(y, area.bottom() - self.height()))
        self.move(x, y)

    def reveal(self) -> None:
        self.center_on_cursor()
        self.search_bar.clear()
        self.search_bar.setFocus()
        self.run_search()
        self.show()
        self.raise_()
        self.activateWindow()
