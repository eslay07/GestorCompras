from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QTextCharFormat, QTextListFormat, QTextTableFormat
from PySide6.QtWidgets import (
    QColorDialog,
    QComboBox,
    QFontComboBox,
    QHBoxLayout,
    QInputDialog,
    QPlainTextEdit,
    QPushButton,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class RichTemplateEditor(QWidget):
    """Visual email editor with an explicit HTML source view."""

    def __init__(self, source: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self.original = source
        self.dirty = False
        self.syncing = False
        layout = QVBoxLayout(self)
        bar = QHBoxLayout()
        self.visual = QTextEdit()
        self.visual.setAcceptRichText(True)
        self.visual.setHtml(source)
        self.source = QPlainTextEdit(source)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.visual, "Editor visual")
        self.tabs.addTab(self.source, "Código HTML")
        font = QFontComboBox()
        font.currentFontChanged.connect(self.visual.setCurrentFont)
        bar.addWidget(font)
        size = QComboBox()
        size.addItems(["8", "10", "11", "12", "14", "16", "18", "24", "36"])
        size.setCurrentText("11")
        size.currentTextChanged.connect(lambda value: self.visual.setFontPointSize(float(value)))
        bar.addWidget(size)
        for label, callback in [
            ("Negrita", lambda: self.visual.setFontWeight(QFont.Normal if self.visual.fontWeight() >= QFont.Bold else QFont.Bold)),
            ("Cursiva", lambda: self.visual.setFontItalic(not self.visual.fontItalic())),
            ("Subrayado", lambda: self.visual.setFontUnderline(not self.visual.fontUnderline())),
            ("Color", self.color),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            bar.addWidget(button)
        layout.addLayout(bar)
        extra = QHBoxLayout()
        for label, callback in [
            ("Izquierda", lambda: self.visual.setAlignment(Qt.AlignLeft)),
            ("Centro", lambda: self.visual.setAlignment(Qt.AlignHCenter)),
            ("Derecha", lambda: self.visual.setAlignment(Qt.AlignRight)),
            ("Viñetas", lambda: self.visual.textCursor().createList(QTextListFormat.ListDisc)),
            ("Numeración", lambda: self.visual.textCursor().createList(QTextListFormat.ListDecimal)),
            ("Tabla", self.table), ("Enlace", self.link),
            ("Deshacer", self.visual.undo), ("Rehacer", self.visual.redo),
        ]:
            button = QPushButton(label)
            button.clicked.connect(callback)
            extra.addWidget(button)
        layout.addLayout(extra)
        layout.addWidget(self.tabs)
        self.previous_tab = 0
        self.visual.textChanged.connect(self.changed)
        self.source.textChanged.connect(self.changed)
        self.tabs.currentChanged.connect(self.switch)

    def changed(self):
        if not self.syncing:
            self.dirty = True

    def switch(self, index):
        self.syncing = True
        if index == 1:
            self.source.setPlainText(self.visual.toHtml() if self.dirty else self.original)
        else:
            self.visual.setHtml(self.source.toPlainText())
        self.syncing = False
        self.previous_tab = index

    def toPlainText(self):
        # Compatibility with TemplateDialog's HTML persistence contract.
        if not self.dirty:
            return self.original
        return self.source.toPlainText() if self.tabs.currentIndex() == 1 else self.visual.toHtml()

    def color(self):
        color = QColorDialog.getColor(self.visual.textColor(), self)
        if color.isValid():
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            self.visual.mergeCurrentCharFormat(fmt)

    def table(self):
        rows, ok = QInputDialog.getInt(self, "Tabla", "Filas", 2, 1, 50)
        if not ok:
            return
        cols, ok = QInputDialog.getInt(self, "Tabla", "Columnas", 3, 1, 12)
        if ok:
            fmt = QTextTableFormat()
            fmt.setBorder(1)
            fmt.setCellPadding(5)
            self.visual.textCursor().insertTable(rows, cols, fmt)

    def link(self):
        url, ok = QInputDialog.getText(self, "Enlace", "Dirección https:// o mailto:")
        if ok and url.startswith(("https://", "http://", "mailto:")):
            cursor = self.visual.textCursor()
            label = cursor.selectedText() or url
            cursor.insertHtml(f'<a href="{html.escape(url, quote=True)}">{html.escape(label)}</a>')
