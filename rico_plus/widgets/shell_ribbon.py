# Rico Plus
# Copyright (C) 2026 Bruno Machado
# SPDX-License-Identifier: GPL-3.0-or-later
"""Shell-owned Ribbon for Rico Plus.

Existing Ricopad presentation is authoritative. Rico Plus adds workspace-only
controls without reordering, renaming or restyling Ricopad's RTF controls.
"""
from __future__ import annotations

from PyQt6.QtCore import QEvent, QSize, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QComboBox, QFontComboBox, QFrame, QGridLayout, QHBoxLayout, QLabel,
    QScrollArea, QScroller, QSizePolicy, QTabWidget, QToolButton, QToolTip, QVBoxLayout,
    QWidget,
)

RIBBON_BUTTON_SIZE = 52
RIBBON_ICON_SIZE = 32
RIBBON_FONT_FAMILY_WIDTH = RIBBON_BUTTON_SIZE * 2


class RibbonScrollArea(QScrollArea):
    """Horizontally pannable Ribbon surface without swallowing taps.

    This is the same touch-arbitration contract used by canonical Ricopad:
    QScroller waits for Qt's platform drag threshold before taking the gesture,
    so a stationary touchscreen tap continues to activate the child control,
    while a finger drag pans the Ribbon horizontally.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        QScroller.grabGesture(
            self.viewport(), QScroller.ScrollerGestureType.TouchGesture
        )

    def pan_from_wheel_event(self, event) -> bool:
        """Translate a wheel event into horizontal Ribbon movement."""
        bar = self.horizontalScrollBar()
        if bar.maximum() <= bar.minimum():
            return False
        pixel_delta = event.pixelDelta()
        angle_delta = event.angleDelta()
        delta = pixel_delta.y() or pixel_delta.x()
        if not delta:
            delta = angle_delta.y() or angle_delta.x()
            if delta:
                notches = int(delta / 120)
                if notches == 0:
                    notches = 1 if delta > 0 else -1
                delta = notches * max(48, bar.singleStep() * 3)
        if not delta:
            return False
        bar.setValue(bar.value() - int(delta))
        event.accept()
        return True

    def wheelEvent(self, event) -> None:
        if self.pan_from_wheel_event(event):
            return
        super().wheelEvent(event)


class ShellRibbon(QWidget):
    """One persistent Plus-owned command surface using Ricopad's Ribbon grammar."""

    font_family_selected = pyqtSignal(object)
    font_size_selected = pyqtSignal(str)
    heading_selected = pyqtSignal(int)
    line_spacing_selected = pyqtSignal(int)
    collapsed_changed = pyqtSignal(bool)

    def __init__(self, actions: dict[str, QAction], parent=None) -> None:
        super().__init__(parent)
        self.actions = actions
        self._syncing_selectors = False
        self._collapsed = False
        self._expanded_minimum_height = 0
        self._expanded_maximum_height = 16777215
        self._instant_tooltip_widgets: list[QWidget] = []
        self._section_frames: list[QFrame] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._ribbon_pages: list[RibbonScrollArea] = []
        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("ricoPlusShellRibbon")
        self.tabs.setMinimumWidth(0)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.tabs.setDocumentMode(True)
        self.tabs.setMovable(False)
        self.tabs.setTabsClosable(False)
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(True)
        self.tabs.tabBar().installEventFilter(self)
        self.tabs.currentChanged.connect(self._sync_collapsed_page)
        layout.addWidget(self.tabs)

        self.font_combo = QFontComboBox(self)
        self.font_combo.setMaximumWidth(175)
        self.font_combo.setEditable(True)
        self.font_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        if self.font_combo.lineEdit() is not None:
            edit = self.font_combo.lineEdit()
            edit.setReadOnly(True)
            edit.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.font_combo.currentFontChanged.connect(self._emit_font_family)

        self.font_size_combo = QComboBox(self)
        self.font_size_combo.setEditable(True)
        self.font_size_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.font_size_combo.addItems(
            ["8", "9", "10", "11", "12", "14", "16", "18", "20", "24", "28", "32", "36", "48", "72"]
        )
        self.font_size_combo.currentTextChanged.connect(self._emit_font_size)

        self.heading_combo = QComboBox(self)
        for text, level in (("Normal", 0), ("Heading 1", 1), ("Heading 2", 2), ("Heading 3", 3), ("Heading 4", 4), ("Heading 5", 5), ("Heading 6", 6)):
            self.heading_combo.addItem(text, level)
        self.heading_combo.currentIndexChanged.connect(self._emit_heading)

        self.line_spacing_combo = QComboBox(self)
        for label, value in (("1", 100), ("1.15", 115), ("1.5", 150), ("2", 200)):
            self.line_spacing_combo.addItem(label, value)
        self.line_spacing_combo.currentIndexChanged.connect(self._emit_line_spacing)

        self._build_pages()
        QTimer.singleShot(0, self._sync_ribbon_page_heights)
        self.tabs.setCurrentIndex(next((i for i in range(self.tabs.count()) if self.tabs.tabText(i) == "Home"), 0))

    def _a(self, name: str) -> QAction:
        return self.actions[name]

    def _instant(self, widget: QWidget) -> QWidget:
        widget.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, True)
        widget.setProperty("ricopad_instant_tooltip", True)
        widget.installEventFilter(self)
        self._instant_tooltip_widgets.append(widget)
        return widget

    @staticmethod
    def _action_tooltip(action: QAction, label: str | None = None) -> str:
        clean = (label or action.text() or "").replace("&", "").replace("…", "").strip()
        shortcuts = []
        for sequence in action.shortcuts():
            rendered = sequence.toString(QKeySequence.SequenceFormat.NativeText).strip()
            if rendered and rendered not in shortcuts:
                shortcuts.append(rendered)
        return f"{clean} — {' / '.join(shortcuts)}" if shortcuts else clean

    def _page(self, label: str):
        # Rico's grouped two-row Ribbon needs a real horizontally scrollable
        # surface.  Do not substitute QToolBar overflow: custom group widgets
        # do not transfer correctly into its extension popup.
        scroll = RibbonScrollArea(self.tabs)
        scroll.setObjectName(f"ricoPlusRibbon{label}Page")
        scroll.setMinimumWidth(0)
        scroll.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget(scroll)
        body.setMinimumWidth(0)
        row = QHBoxLayout(body)
        row.setContentsMargins(6, 4, 6, 6)
        row.setSpacing(6)
        row.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        scroll.setWidget(body)
        scroll.horizontalScrollBar().rangeChanged.connect(
            lambda _minimum, _maximum, page=scroll: self._sync_ribbon_page_height(page)
        )
        self._ribbon_pages.append(scroll)
        self.tabs.addTab(scroll, label)
        return row

    def _sync_ribbon_page_height(self, scroll: RibbonScrollArea) -> None:
        """Reserve the scrollbar inside the Ribbon's own geometry.

        At narrow widths the horizontal bar must consume Ribbon height rather
        than being painted into the editor area below it.
        """
        body = scroll.widget()
        if body is None:
            return
        body.adjustSize()
        content_height = max(body.minimumSizeHint().height(), body.sizeHint().height())
        bar = scroll.horizontalScrollBar()
        bar_height = bar.sizeHint().height() if bar.maximum() > bar.minimum() else 0
        page_height = max(1, content_height + bar_height + (2 * scroll.frameWidth()))
        if scroll.minimumHeight() != page_height or scroll.maximumHeight() != page_height:
            scroll.setMinimumHeight(page_height)
            scroll.setMaximumHeight(page_height)
            scroll.updateGeometry()
            self.tabs.updateGeometry()
            self.updateGeometry()

    def _sync_ribbon_page_heights(self) -> None:
        if self._collapsed:
            return
        for scroll in tuple(self._ribbon_pages):
            self._sync_ribbon_page_height(scroll)

    def _group(self, layout, title: str):
        frame = QFrame(self.tabs)
        frame.setObjectName("ricoPlusRibbonSection")
        frame.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        frame.setStyleSheet(
            "QFrame#ricoPlusRibbonSection {background-color: palette(button); "
            "border: 1px solid palette(mid); border-radius: 6px;} "
            "QFrame#ricoPlusRibbonSection QLabel#ricoPlusRibbonSectionCaption "
            "{background: transparent; border: none; margin-bottom: 2px;}"
        )
        self._section_frames.append(frame)
        outer = QVBoxLayout(frame)
        outer.setContentsMargins(8, 5, 8, 6)
        outer.setSpacing(4)
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(3)
        outer.addLayout(grid)
        cap = QLabel(title, frame)
        cap.setObjectName("ricoPlusRibbonSectionCaption")
        cap.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        # Exact Ricopad caption treatment: deliberately smaller and italic.
        cap_font = cap.font()
        if cap_font.pointSizeF() > 0:
            cap_font.setPointSizeF(max(6.5, cap_font.pointSizeF() * 0.74))
        elif cap_font.pixelSize() > 0:
            cap_font.setPixelSize(max(8, int(round(cap_font.pixelSize() * 0.74))))
        cap_font.setItalic(True)
        cap.setFont(cap_font)
        outer.addWidget(cap)
        layout.addWidget(frame)
        return grid

    def _button(self, grid, name: str, row: int, col: int):
        action = self._a(name)
        button = QToolButton(self.tabs)
        label = action.text().replace("&", "").replace("…", "").strip()
        tooltip = self._action_tooltip(action, label)
        action.setToolTip(tooltip)
        button.setDefaultAction(action)
        button.setToolTip(tooltip)
        button.setAccessibleName(label)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIconSize(QSize(RIBBON_ICON_SIZE, RIBBON_ICON_SIZE))
        button.setFixedSize(RIBBON_BUTTON_SIZE, RIBBON_BUTTON_SIZE)
        button.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._instant(button)
        grid.addWidget(button, row, col, Qt.AlignmentFlag.AlignCenter)
        return button

    def _selector(self, grid, widget, row, col, tip, width, span=1):
        widget.setParent(self.tabs)
        widget.setToolTip(widget.toolTip() or tip)
        widget.setFixedSize(width, RIBBON_BUTTON_SIZE)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self._instant(widget)
        grid.addWidget(widget, row, col, 1, span, Qt.AlignmentFlag.AlignCenter)

    def _build_pages(self) -> None:
        p = self._page("File")
        g = self._group(p, "Create & Print")
        for n, r, c in (
            ("print_action", 0, 0),
            ("export_pdf_action", 0, 1),
            ("page_setup_action", 0, 2),
            ("new_action", 1, 0),
            ("new_folder_action", 1, 1),
            ("new_window_action", 1, 2),
        ):
            self._button(g, n, r, c)

        g = self._group(p, "This File")
        for n, r, c in (
            ("save_as_action", 0, 0),
            ("properties_action", 0, 1),
            ("delete_file_action", 0, 2),
            ("external_editor_action", 0, 3),
            ("save_action", 1, 0),
            ("rename_file_action", 1, 1),
            ("duplicate_action", 1, 2),
            ("open_document_folder_action", 1, 3),
        ):
            self._button(g, n, r, c)

        g = self._group(p, "This Session")
        for n, r, c in (
            ("manage_workspaces_action", 0, 0),
            ("save_dashboard_action", 0, 1),
            ("save_exit_action", 0, 2),
            ("dashboard_action", 1, 0),
            ("save_new_action", 1, 1),
            ("exit_action", 1, 2),
        ):
            self._button(g, n, r, c)
        p.addStretch(1)

        # Home remains Ricopad's authoritative RTF editing surface.
        p = self._page("Home")
        g = self._group(p, "Clipboard")
        for n, r, c in (("select_all_action", 0, 0), ("cut_action", 0, 1), ("delete_text_action", 0, 2), ("paste_plain_action", 0, 3), ("undo_action", 1, 0), ("redo_action", 1, 1), ("copy_action", 1, 2), ("paste_action", 1, 3)):
            self._button(g, n, r, c)
        g = self._group(p, "Font")
        self._selector(g, self.font_combo, 0, 0, "Font Face", RIBBON_FONT_FAMILY_WIDTH, 2)
        self._selector(g, self.font_size_combo, 0, 2, "Font Size", RIBBON_BUTTON_SIZE)
        self.heading_combo.setToolTip("Font Style — Normal Ctrl+Shift+0; Headings 1–6 Ctrl+Shift+1…6")
        self._selector(g, self.heading_combo, 0, 3, "Font Style", RIBBON_BUTTON_SIZE)
        for n, r, c in (("increase_font_size_action", 1, 0), ("decrease_font_size_action", 1, 1), ("font_dialog_action", 1, 2), ("text_colour_action", 1, 3)):
            self._button(g, n, r, c)
        g = self._group(p, "Formatting")
        for n, r, c in (("underline_action", 0, 0), ("strike_action", 0, 1), ("subscript_action", 0, 2), ("superscript_action", 0, 3), ("bold_action", 1, 0), ("italic_action", 1, 1), ("highlight_colour_action", 1, 2), ("bullet_action", 1, 3)):
            self._button(g, n, r, c)
        g = self._group(p, "Paragraph")
        for n, r, c in (("alignment_right_action", 0, 0), ("alignment_justify_action", 0, 1), ("indent_action", 0, 2), ("outdent_action", 0, 3), ("alignment_left_action", 1, 0), ("alignment_center_action", 1, 1), ("paragraph_action", 1, 2)):
            self._button(g, n, r, c)
        self.line_spacing_combo.setToolTip("Line Spacing — 1.0 Ctrl+1; 1.15 Ctrl+2; 1.5 Ctrl+3; 2.0 Ctrl+4")
        self._selector(g, self.line_spacing_combo, 1, 3, "Line Spacing", RIBBON_BUTTON_SIZE)
        g = self._group(p, "Advanced")
        for n, r, c in (("search_bar_action", 0, 0), ("replace_action", 0, 1), ("duplicate_line_action", 1, 0), ("delete_line_action", 1, 1)):
            self._button(g, n, r, c)
        p.addStretch(1)

        p = self._page("Insert")
        g = self._group(p, "Links & Images")
        for n, r, c in (("edit_link_action", 0, 0), ("remove_link_action", 0, 1), ("link_action", 1, 0), ("image_action", 1, 1)):
            self._button(g, n, r, c)
        g = self._group(p, "Tables")
        for n, r, c in (("table_delete_action", 0, 0), ("table_column_left_action", 0, 1), ("table_column_right_action", 0, 2), ("table_delete_column_action", 0, 3), ("table_action", 1, 0), ("table_row_above_action", 1, 1), ("table_row_below_action", 1, 2), ("table_delete_row_action", 1, 3)):
            self._button(g, n, r, c)
        g = self._group(p, "Classics")
        for n, r, c in (("date_action", 0, 0), ("time_action", 0, 1), ("clear_formatting_action", 0, 2), ("date_time_action", 1, 0), ("symbol_action", 1, 1), ("rule_action", 1, 2)):
            self._button(g, n, r, c)
        p.addStretch(1)

        p = self._page("Configure")
        g = self._group(p, "View Control")
        for n, r, c in (
            ("fullscreen_action", 0, 0),
            ("sidebar_action", 0, 1),
            ("status_bar_action", 0, 2),
            ("zoom_out_action", 1, 0),
            ("zoom_reset_action", 1, 1),
            ("zoom_in_action", 1, 2),
        ):
            self._button(g, n, r, c)

        g = self._group(p, "Editor Settings")
        for n, r, c in (
            ("file_header_action", 0, 0),
            ("tab_width_action", 0, 1),
            ("default_font_action", 0, 2),
            ("word_wrap_action", 1, 0),
            ("collapsed_mode_action", 1, 1),
            ("view_only_action", 1, 2),
        ):
            self._button(g, n, r, c)

        g = self._group(p, "Theme Settings")
        for n, r, c in (
            ("editor_canvas_theme_action", 0, 0),
            ("icon_classic_action", 0, 1),
            ("icon_new_action", 0, 2),
            ("theme_system_action", 1, 0),
            ("theme_light_action", 1, 1),
            ("theme_dark_action", 1, 2),
        ):
            self._button(g, n, r, c)

        g = self._group(p, "App Settings")
        for n, r, c in (
            ("grid_action", 0, 0),
            ("launch_last_file_action", 0, 1),
            ("drop_new_window_action", 0, 2),
            ("list_action", 1, 0),
            ("launch_dashboard_action", 1, 1),
            ("drop_active_action", 1, 2),
        ):
            self._button(g, n, r, c)
        p.addStretch(1)

        p = self._page("Help")
        g = self._group(p, "GitHub")
        self._button(g, "github_action", 0, 0)
        self._button(g, "issue_action", 1, 0)
        g = self._group(p, "Help")
        for n, r, c in (("docs_action", 0, 0), ("quick_start_action", 0, 1), ("shortcuts_action", 1, 0), ("about_action", 1, 1)):
            self._button(g, n, r, c)
        p.addStretch(1)
        QTimer.singleShot(0, self._sync_ribbon_page_heights)


    def refresh_theme(self) -> None:
        """Re-polish the persistent shell Ribbon after an application palette change.

        Rico Plus keeps this Ribbon alive while switching Dark/Light themes. Qt
        style-sheet palette references can retain their previous polish until a
        widget is recreated, so force the same existing widgets through a
        re-polish instead of rebuilding or rearranging the Ribbon.
        """
        for frame in tuple(self._section_frames):
            try:
                sheet = frame.styleSheet()
                frame.setStyleSheet("")
                frame.setStyleSheet(sheet)
            except RuntimeError:
                continue
        widgets = [self, self.tabs, *self.findChildren(QWidget)]
        seen: set[int] = set()
        for widget in widgets:
            ident = id(widget)
            if ident in seen:
                continue
            seen.add(ident)
            try:
                style = widget.style()
                style.unpolish(widget)
                style.polish(widget)
                widget.update()
            except RuntimeError:
                continue

    def _emit_font_family(self, font):
        if not self._syncing_selectors:
            self.font_family_selected.emit(font)

    def _emit_font_size(self, text):
        if not self._syncing_selectors:
            self.font_size_selected.emit(text)

    def _emit_heading(self, index):
        if not self._syncing_selectors and index >= 0:
            self.heading_selected.emit(int(self.heading_combo.itemData(index)))

    def _emit_line_spacing(self, index):
        if not self._syncing_selectors and index >= 0:
            self.line_spacing_selected.emit(int(self.line_spacing_combo.itemData(index)))

    def sync_from_engine(self, engine):
        self._syncing_selectors = True
        try:
            engine.update_formatting_state()
            if getattr(engine, "font_combo", None) is not None:
                self.font_combo.setCurrentFont(engine.font_combo.currentFont())
            if getattr(engine, "font_size_combo", None) is not None:
                self.font_size_combo.setCurrentText(engine.font_size_combo.currentText())
            if getattr(engine, "heading_combo", None) is not None:
                i = self.heading_combo.findData(engine.heading_combo.currentData())
                self.heading_combo.setCurrentIndex(i if i >= 0 else 0)
            if getattr(engine, "line_spacing_combo", None) is not None:
                i = self.line_spacing_combo.findData(engine.line_spacing_combo.currentData())
                self.line_spacing_combo.setCurrentIndex(i if i >= 0 else 0)
        finally:
            self._syncing_selectors = False

    def set_editor_enabled(self, enabled):
        for widget in (self.font_combo, self.font_size_combo, self.heading_combo, self.line_spacing_combo):
            widget.setEnabled(bool(enabled))

    def cycle_tab(self, step):
        if self.tabs.count():
            self.tabs.setCurrentIndex((self.tabs.currentIndex() + step) % self.tabs.count())

    def set_collapsed(self, collapsed, *, emit=True):
        collapsed = bool(collapsed)
        if collapsed == self._collapsed:
            return
        self._collapsed = collapsed
        current = self.tabs.currentWidget()
        if collapsed:
            if current is not None:
                current.setVisible(False)
            self._expanded_minimum_height = self.tabs.minimumHeight()
            self._expanded_maximum_height = self.tabs.maximumHeight()
            h = max(self.tabs.tabBar().height(), self.tabs.tabBar().sizeHint().height(), 1) + 2
            self.tabs.setMinimumHeight(h)
            self.tabs.setMaximumHeight(h)
        else:
            self.tabs.setMaximumHeight(self._expanded_maximum_height)
            self.tabs.setMinimumHeight(self._expanded_minimum_height)
            if current is not None:
                current.setVisible(True)
            QTimer.singleShot(0, self._sync_ribbon_page_heights)
        self.tabs.updateGeometry()
        if emit:
            self.collapsed_changed.emit(collapsed)

    def _sync_collapsed_page(self, _index=None):
        if self._collapsed and self.tabs.currentWidget() is not None:
            self.tabs.currentWidget().setVisible(False)

    def eventFilter(self, obj, event):
        if obj is self.tabs.tabBar():
            if event.type() == QEvent.Type.MouseButtonPress and self._collapsed and event.button() == Qt.MouseButton.LeftButton:
                i = self.tabs.tabBar().tabAt(event.position().toPoint())
                if i >= 0:
                    self.tabs.setCurrentIndex(i)
                    self.set_collapsed(False)
                    return True
            if event.type() == QEvent.Type.MouseButtonDblClick and not self._collapsed and event.button() == Qt.MouseButton.LeftButton and self.tabs.tabBar().tabAt(event.position().toPoint()) >= 0:
                self.set_collapsed(True)
                return True
            if event.type() == QEvent.Type.Wheel and event.angleDelta().y():
                self.cycle_tab(-1 if event.angleDelta().y() > 0 else 1)
                return True
        if bool(obj.property("ricopad_instant_tooltip")):
            if event.type() == QEvent.Type.Enter:
                if isinstance(obj, QToolButton) and isinstance(obj.defaultAction(), QAction):
                    action = obj.defaultAction()
                    tooltip = self._action_tooltip(action)
                    action.setToolTip(tooltip)
                    obj.setToolTip(tooltip)
                if obj.toolTip():
                    QToolTip.showText(obj.mapToGlobal(obj.rect().bottomLeft()), obj.toolTip(), obj, obj.rect(), 7000)
            elif event.type() == QEvent.Type.Leave:
                QToolTip.hideText()
            elif event.type() == QEvent.Type.Wheel:
                scroll = self.tabs.currentWidget()
                if isinstance(scroll, RibbonScrollArea) and scroll.pan_from_wheel_event(event):
                    return True
        return super().eventFilter(obj, event)
