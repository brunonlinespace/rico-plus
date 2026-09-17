"""Rico Plus palette: Rico brick accent with neutral Plus-family surfaces."""
from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication


def apply_theme(app: QApplication, theme: str) -> None:
    """Apply Rico Plus's canonical System/Dark/Light application palette."""
    theme = theme if theme in {"system", "dark", "light"} else "system"
    app.setStyleSheet("")
    app.setPalette(app.style().standardPalette())
    if theme == "system":
        return
    palette = QPalette()
    if theme == "dark":
        palette.setColor(QPalette.ColorRole.Window, QColor("#202326"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#151719"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#202326"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#101214"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#292D31"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#B24A3B"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#8E969E"))
    else:
        palette.setColor(QPalette.ColorRole.Window, QColor("#F5F6F7"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#F1F3F4"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#202124"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#B24A3B"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    app.setPalette(palette)


def effective_scheme(theme: str) -> str:
    if theme in {"light", "dark"}:
        return theme
    color = QApplication.instance().palette().color(QPalette.ColorRole.Base)
    return "light" if color.lightness() >= 140 else "dark"
