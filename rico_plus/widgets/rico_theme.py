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
    if theme == "dark":
        palette = QPalette()
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
        # exp10: approved softer neutral light treatment.  The previous
        # near-white palette made the whole shell visually harsher than the
        # System-theme reference.  Keep the Rico brick accent, but align the
        # principal surfaces with that reference: window #D4D4D4, editable
        # base #F4F4F4 and buttons #E4E4E4.
        palette = app.style().standardPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#D4D4D4"))
        palette.setColor(QPalette.ColorRole.WindowText, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#F4F4F4"))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#E4E4E4"))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor("#F4F4F4"))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Button, QColor("#E4E4E4"))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor("#2A2A2A"))
        palette.setColor(QPalette.ColorRole.Light, QColor("#F4F4F4"))
        palette.setColor(QPalette.ColorRole.Midlight, QColor("#D0D0D0"))
        palette.setColor(QPalette.ColorRole.Mid, QColor("#B2B2B2"))
        palette.setColor(QPalette.ColorRole.Dark, QColor("#767676"))
        palette.setColor(QPalette.ColorRole.Shadow, QColor("#545454"))
        palette.setColor(QPalette.ColorRole.Highlight, QColor("#B24A3B"))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor("#767676"))
    app.setPalette(palette)


def effective_scheme(theme: str) -> str:
    if theme in {"light", "dark"}:
        return theme
    color = QApplication.instance().palette().color(QPalette.ColorRole.Base)
    return "light" if color.lightness() >= 140 else "dark"
