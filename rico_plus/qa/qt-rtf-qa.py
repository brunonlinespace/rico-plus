#!/usr/bin/env python3
"""Qt-backed RTF round-trip regression suite for build hosts with PyQt6."""
from __future__ import annotations
import os, pathlib, sys, tempfile
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
QA_STATE = tempfile.TemporaryDirectory(prefix='ricopad-qt-rtf-qa-')
os.environ['XDG_CONFIG_HOME'] = QA_STATE.name
sys.dont_write_bytecode = True
PACKAGE = pathlib.Path(__file__).resolve().parents[1]
PROJECT = PACKAGE.parent
CORPUS = pathlib.Path(__file__).resolve().parent / 'rtf-corpus'
sys.path.insert(0, str(PROJECT))
from PyQt6.QtCore import QBuffer, QByteArray, QEvent, QIODevice, QMimeData, Qt, QUrl
from PyQt6.QtGui import QBrush, QColor, QFont, QImage, QKeyEvent, QTextBlockFormat, QTextCharFormat, QTextCursor, QTextDocument, QTextFormat, QTextImageFormat, QTextListFormat
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox
from rico_plus.rtf_codec import document_to_rtf, decode_rtf, _rtf_clear_automatic_foreground, populate_qtextdocument_from_rtf_model, RTF_TABLE_AUTOFIT_PROPERTY, RTF_AUTOMATIC_CONTRAST_PROPERTY

app = QApplication.instance() or QApplication(['rico-plus-qt-rtf-qa'])
from rico_plus.widgets import rtf_editor as rtf_editor_module
from rico_plus.widgets.rtf_editor import OPEN_WINDOWS, RICOPAD_INLINE_RICH_MIME, RtfEditorWindow, RichTextEdit
rtf_editor_module.SMOKE_TEST_MODE = True
rtf_editor_module.platform_config_locations = lambda: (QA_STATE.name, ())

def require(value, message):
    if not value:
        raise AssertionError(message)

def reopen(payload: bytes) -> QTextDocument:
    decoded = decode_rtf(payload)
    doc = QTextDocument()
    if not populate_qtextdocument_from_rtf_model(doc, decoded.model):
        doc.setHtml(decoded.html)
        if decoded.automatic_foreground:
            _rtf_clear_automatic_foreground(doc, decoded.automatic_foreground)
    return doc

def block_snapshot(doc: QTextDocument):
    rows=[]; block=doc.begin()
    while block.isValid():
        fmt=block.blockFormat()
        rows.append((block.text(), round(fmt.leftMargin(),4), round(fmt.rightMargin(),4), round(fmt.textIndent(),4), round(fmt.topMargin(),4), round(fmt.bottomMargin(),4)))
        block=block.next()
    return rows

# Release-critical invariant: plain/unset formatting must not become black.
doc = QTextDocument(); doc.setDefaultFont(QFont('Sans Serif', 11)); doc.setPlainText('Plain\nSecond')
payload = document_to_rtf(doc)
require(b'\\cf' not in payload, 'plain document acquired explicit foreground colour')
require(b'\\highlight' not in payload, 'plain document acquired explicit highlight')
require(reopen(payload).toPlainText() == 'Plain\nSecond', 'plain paragraph round trip failed')

# Heading-first RtfEditorWindow documents must preserve the document baseline rather
# than promoting Heading 1's 24 pt run to the default after reopen.
doc = QTextDocument(); base = QFont('Adwaita Mono', 14); doc.setDefaultFont(base); c = QTextCursor(doc)
heading = QTextCharFormat(); heading.setFontFamily('Adwaita Mono'); heading.setFontPointSize(24); heading.setFontWeight(QFont.Weight.Bold); c.insertText('Heading', heading); c.insertBlock(); body = QTextCharFormat(); body.setFontFamily('Adwaita Mono'); body.setFontPointSize(14); c.insertText('Body', body)
payload = document_to_rtf(doc); require(br'\f0\fs28\viewkind4' in payload, 'root document font-size baseline was not serialized')
reopened = reopen(payload); require(abs(reopened.defaultFont().pointSizeF()-14.0)<0.01, f'heading-first reopen changed default to {reopened.defaultFont().pointSizeF()} pt')

# Explicit black remains distinguishable from Automatic/NoBrush.
doc = QTextDocument(); doc.setPlainText('Black Automatic')
c = QTextCursor(doc); c.setPosition(0); c.setPosition(5, QTextCursor.MoveMode.KeepAnchor)
f = QTextCharFormat(); f.setForeground(QColor(Qt.GlobalColor.black)); c.mergeCharFormat(f)
payload = document_to_rtf(doc)
require(b'\\cf1' in payload and b'\\red0\\green0\\blue0;' in payload, 'explicit black foreground lost')

# Clear highlight must serialize as absence of highlight, never black.
doc = QTextDocument(); doc.setPlainText('Clear me')
c = QTextCursor(doc); c.select(QTextCursor.SelectionType.Document)
f = QTextCharFormat(); f.setBackground(QColor(Qt.GlobalColor.yellow)); c.mergeCharFormat(f)
f2 = QTextCharFormat(); f2.setBackground(QBrush(Qt.BrushStyle.NoBrush)); c.mergeCharFormat(f2)
payload = document_to_rtf(doc)
require(b'\\highlight' not in payload, 'cleared highlight reappeared during serialization')

# A light highlight may use a temporary dark display foreground for readability,
# but a run tagged as Automatic must still serialize without an explicit \cf.
doc = QTextDocument(); doc.setPlainText('Automatic contrast')
c = QTextCursor(doc); c.select(QTextCursor.SelectionType.Document)
f = QTextCharFormat(); f.setBackground(QColor(Qt.GlobalColor.yellow)); f.setForeground(QColor(Qt.GlobalColor.black)); f.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY, True); c.mergeCharFormat(f)
payload = document_to_rtf(doc); require(b'\\highlight' in payload and b'\\cf' not in payload, 'automatic highlight contrast leaked an explicit foreground into RTF')
doc = QTextDocument(); doc.setPlainText('Explicit contrast')
c = QTextCursor(doc); c.select(QTextCursor.SelectionType.Document)
f = QTextCharFormat(); f.setBackground(QColor(Qt.GlobalColor.yellow)); f.setForeground(QColor(Qt.GlobalColor.red)); f.setProperty(RTF_AUTOMATIC_CONTRAST_PROPERTY, False); c.mergeCharFormat(f)
payload = document_to_rtf(doc); require(b'\\highlight' in payload and b'\\cf' in payload, 'explicit foreground was lost beside highlight')

# Manual line versus paragraph structure.
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('First'); c.insertText('\u2028'); c.insertText('Second'); c.insertBlock(); c.insertBlock(); c.insertText('Fourth')
payload = document_to_rtf(doc); decoded = decode_rtf(payload)
require('<br>' in decoded.html and decoded.html.count('<p') >= 3, 'manual line/blank paragraph structure lost')

# Simple table survives through the supported RTF subset.
doc = QTextDocument(); c = QTextCursor(doc); table = c.insertTable(2,2)
for row, values in enumerate((('A1','B1'),('A2','B2'))):
    for col, value in enumerate(values): table.cellAt(row,col).firstCursorPosition().insertText(value)
payload = document_to_rtf(doc); require(b'\\trowd' in payload and payload.count(b'\\row') >= 2, 'table serialization missing')
round_doc = reopen(payload); require('A1' in round_doc.toPlainText() and 'B2' in round_doc.toPlainText(), 'table round trip lost cell text')

# Horizontal-rule block maps to the conservative RTF paragraph-border subset.
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Before'); c.insertBlock(); bf = QTextBlockFormat(); bf.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth, 100); c.setBlockFormat(bf); c.insertBlock(); c.insertText('After')
payload = document_to_rtf(doc); require(b'\\brdrb' in payload, 'horizontal-rule serialization missing'); require('<hr>' in decode_rtf(payload).html, 'horizontal-rule import missing')

# Embedded images are serialized into the RTF itself, never as local file links.
doc = QTextDocument(); image = QImage(2, 2, QImage.Format.Format_ARGB32); image.fill(QColor(Qt.GlobalColor.red)); image_url = QUrl('ricopad-qa-image')
doc.addResource(QTextDocument.ResourceType.ImageResource, image_url, image); c = QTextCursor(doc); c.insertImage(image_url.toString())
payload = document_to_rtf(doc); decoded = decode_rtf(payload); require(b'\\pict\\pngblip' in payload and 'data:image/png;base64,' in decoded.html, 'embedded image round trip failed')

# Standards-based bullet creation plus externally authored decimal lists retain list semantics.  The output
# must carry the RTF list tables/overrides recognised by Word/LibreOffice, not
# only a visual marker destination.
doc = QTextDocument(); doc.setDefaultFont(QFont('Sans Serif',14)); c = QTextCursor(doc); c.insertText('Bullet one'); lf = QTextListFormat(); lf.setStyle(QTextListFormat.Style.ListDisc); c.createList(lf); c.insertBlock(); c.insertText('Bullet two'); payload = document_to_rtf(doc); require(br'\listtable' in payload and br'\listoverridetable' in payload and br'\levelnfc23' in payload and br'\ilvl0' in payload and br'\ls1' in payload and '<ul>' in decode_rtf(payload).html, 'standard bullet list round trip failed'); require(br"{\leveltext \'01\u8226 ?;}" in payload, 'bullet leveltext SDATA escape is malformed'); bullet_reopen=reopen(payload); require(bullet_reopen.toPlainText().splitlines()[:2]==['Bullet one','Bullet two'], f'bullet list gained body whitespace: {bullet_reopen.toPlainText()!r}'); b=bullet_reopen.begin(); require(b.textList() is not None and abs(b.blockFormat().leftMargin())<0.01 and abs(b.blockFormat().textIndent())<0.01, 'reopened list double-applied RTF and QTextList indentation')
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Number one'); lf = QTextListFormat(); lf.setStyle(QTextListFormat.Style.ListDecimal); c.createList(lf); c.insertBlock(); c.insertText('Number two'); payload = document_to_rtf(doc); require(br'\listtable' in payload and br'\listoverridetable' in payload and br'\levelnfc0' in payload and br'\ilvl0' in payload and br'\ls1' in payload and '<ol>' in decode_rtf(payload).html, 'external decimal-list round trip failed'); require(br"{\leveltext \'02\'00.;}" in payload and br"{\levelnumbers \'01;}" in payload, 'external decimal-list leveltext/levelnumbers SDATA escapes are malformed')

# A list marker is paragraph metadata, not an instruction to trim the first
# character of every sibling formatting group.  Preserve deliberate spaces at
# normal/bold/italic run boundaries and stop marker state at the paragraph.
doc = QTextDocument(); doc.setDefaultFont(QFont('Sans Serif', 12)); c = QTextCursor(doc)
normal = QTextCharFormat(); normal.setFontPointSize(12)
bold = QTextCharFormat(normal); bold.setFontWeight(QFont.Weight.Bold)
italic = QTextCharFormat(normal); italic.setFontItalic(True)
c.insertText('Item', normal); lf = QTextListFormat(); lf.setStyle(QTextListFormat.Style.ListDisc); lf.setIndent(1); c.createList(lf); c.insertText(' bold', bold); c.insertText(' tail', italic)
c.insertBlock(); c.insertText('Second', normal); c.insertText(' bold', bold)
c.insertBlock(); plain_block = QTextBlockFormat(c.blockFormat()); plain_block.setObjectIndex(-1); plain_block.setIndent(0); plain_block.setLeftMargin(0.0); plain_block.setTextIndent(0.0); c.setBlockFormat(plain_block); c.insertText('After', normal); c.insertText(' bold', bold); c.insertText(' tail', italic)
expected_mixed = 'Item bold tail\nSecond bold\nAfter bold tail'
require(doc.toPlainText() == expected_mixed, f'mixed-run list QA setup changed: {doc.toPlainText()!r}')
first_payload = document_to_rtf(doc); first_reopen = reopen(first_payload); second_payload = document_to_rtf(first_reopen); second_reopen = reopen(second_payload)
require(first_reopen.toPlainText() == second_reopen.toPlainText() == expected_mixed, f'list formatting-boundary spaces changed across RTF cycles: {(first_reopen.toPlainText(), second_reopen.toPlainText())!r}')
first_block = second_reopen.begin(); second_block = first_block.next(); third_block = second_block.next()
require(first_block.textList() is not None and second_block.textList() is not None and third_block.textList() is None, 'list marker state leaked into the following normal paragraph')

# Qt's generic block indent is not an RTF field.  The serializer must
# materialise it as a left margin for compatibility with programmatic/legacy
# documents even though the fixed UI writes RTF-native margins directly.
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Legacy indent'); bf = c.blockFormat(); bf.setIndent(2); c.setBlockFormat(bf)
payload = document_to_rtf(doc); require(br'\li1200' in payload, 'QTextBlockFormat indent was not materialised into RTF left geometry'); legacy_indent_reopen = reopen(payload); require(abs(legacy_indent_reopen.begin().blockFormat().leftMargin() - 80.0) < 0.01, 'materialised block indent did not survive reopen')

# The real Indent/Outdent command writes normal paragraphs as RTF geometry and
# list paragraphs as semantic QTextList levels, without changing unselected
# siblings.  Both forms must survive two save/reopen cycles.
indent_window = RtfEditorWindow(); editor = indent_window.visual_editor; editor.clear(); editor.setPlainText('Normal paragraph'); editor.setTextCursor(QTextCursor(editor.document().begin())); indent_window.change_indent(1)
indent_step = float(editor.document().indentWidth()); normal_block = editor.document().begin(); require(normal_block.blockFormat().indent() == 0 and abs(normal_block.blockFormat().leftMargin() - indent_step) < 0.01, 'Indent did not create serializable paragraph geometry')
normal_payload = document_to_rtf(editor.document()); normal_reopen = reopen(normal_payload); normal_second = reopen(document_to_rtf(normal_reopen)); require(abs(normal_reopen.begin().blockFormat().leftMargin() - indent_step) < 0.01 and block_snapshot(normal_reopen) == block_snapshot(normal_second), 'normal paragraph indent drifted across RTF cycles')

editor.clear(); c = editor.textCursor(); c.insertText('Parent one'); lf = QTextListFormat(); lf.setStyle(QTextListFormat.Style.ListDisc); lf.setIndent(1); c.createList(lf); c.insertBlock(); c.insertText('Nested target'); c.insertBlock(); c.insertText('Parent two')
middle = editor.document().findBlockByNumber(1); editor.setTextCursor(QTextCursor(middle)); indent_window.change_indent(1)
list_blocks = [editor.document().findBlockByNumber(i) for i in range(3)]
levels = [block.textList().format().indent() if block.textList() is not None else 0 for block in list_blocks]
list_ids = [block.textList().objectIndex() if block.textList() is not None else -1 for block in list_blocks]
require(levels == [1, 2, 1] and list_ids[0] == list_ids[2] != list_ids[1], f'paragraph-local list indent changed siblings or missed semantic nesting: {(levels, list_ids)!r}')
list_payload = document_to_rtf(editor.document()); require(br'\ilvl1' in list_payload, 'nested list level was not serialized')
list_reopen = reopen(list_payload); list_second_payload = document_to_rtf(list_reopen); list_second = reopen(list_second_payload)
for cycle_payload in (list_payload, list_second_payload):
    nested_line = next(line for line in cycle_payload.splitlines() if b'Nested target' in line)
    require(br'\li1080\fi-360' in nested_line, f'nested list geometry drifted across RTF cycles: {nested_line!r}')
for candidate in (list_reopen, list_second):
    reopened_levels = [candidate.findBlockByNumber(i).textList().format().indent() for i in range(3)]
    require(reopened_levels == [1, 2, 1], f'list levels changed across RTF cycles: {reopened_levels!r}')
    reopened_ids = [candidate.findBlockByNumber(i).textList().objectIndex() for i in range(3)]
    require(reopened_ids[0] == reopened_ids[2] != reopened_ids[1], f'nested list split its resumed parent list: {reopened_ids!r}')
editor.setTextCursor(QTextCursor(editor.document().findBlockByNumber(1))); indent_window.change_indent(-1)
outdented = [editor.document().findBlockByNumber(i) for i in range(3)]; outdent_ids = [block.textList().objectIndex() for block in outdented]
require([block.textList().format().indent() for block in outdented] == [1, 1, 1] and len(set(outdent_ids)) == 1, 'Outdent did not rejoin the adjacent parent list')
group_cursor = QTextCursor(editor.document()); group_cursor.setPosition(outdented[1].position()); group_cursor.setPosition(outdented[2].position() + outdented[2].length() - 1, QTextCursor.MoveMode.KeepAnchor); editor.setTextCursor(group_cursor); indent_window.change_indent(1)
grouped = [editor.document().findBlockByNumber(i) for i in range(3)]; grouped_ids = [block.textList().objectIndex() for block in grouped]
require([block.textList().format().indent() for block in grouped] == [1, 2, 2] and grouped_ids[1] == grouped_ids[2] != grouped_ids[0], 'multi-paragraph list indent did not keep selected items together')

# RtfEditorWindow-internal single-paragraph rich clipboard data must paste inline, not
# acquire the outer <p> block wrapper generated by Qt's HTML clipboard format.
editor = RichTextEdit(); editor.setPlainText('Before after'); c = editor.textCursor(); c.setPosition(len('Before ')); editor.setTextCursor(c)
mime = QMimeData(); mime.setText('THIS'); mime.setHtml('<p><span style="font-weight:700">THIS</span></p>'); mime.setData(RICOPAD_INLINE_RICH_MIME, QByteArray(b'1')); editor.insertFromMimeData(mime)
require(editor.toPlainText() == 'Before THISafter', f'inline rich paste created a paragraph boundary: {editor.toPlainText()!r}')
c = editor.textCursor(); c.setPosition(len('Before ')); c.setPosition(len('Before THIS'), QTextCursor.MoveMode.KeepAnchor); require(int(c.charFormat().fontWeight()) >= int(QFont.Weight.Bold), 'inline rich paste lost character formatting')

# Repeated Return on a clean explicitly-spaced document is a live widget/input
# invariant.  Do not emulate it by calling the protected keyPressEvent() method
# directly on a hidden offscreen QTextEdit: that synthetic path can diverge from
# normal Qt event delivery and reject a release even when the portable runtime
# is correct.  Build-time RTF QA instead verifies the underlying invariant that
# unbounded trailing empty paragraphs are representable and survive a codec
# round trip.  Real Return behaviour remains covered by live Portable/AppImage QA.
editor = RichTextEdit(); editor.clear(); c = editor.textCursor(); bf = c.blockFormat(); bf.setLineHeight(115.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value); c.setBlockFormat(bf)
for _ in range(12):
    c.insertBlock()
editor.setTextCursor(c)
require(editor.document().blockCount() == 13 and editor.textCursor().blockNumber() == 12, 'clean document did not retain repeated trailing empty paragraphs')
require(editor.toPlainText() == '\n' * 12, f'repeated Return on a clean document paragraph structure changed: {editor.toPlainText()!r}')
empty_payload = document_to_rtf(editor.document()); empty_reopen = reopen(empty_payload)
require(empty_reopen.blockCount() == 13 and empty_reopen.toPlainText() == '\n' * 12, 'trailing empty paragraphs did not survive RTF round trip')

# Enter must retain proportional spacing without replacing the new block format
# or detaching the continuation block from its QTextList.
editor = RichTextEdit(); editor.setPlainText('Item one'); c = editor.textCursor(); c.movePosition(QTextCursor.MoveOperation.End); bf = c.blockFormat(); bf.setLineHeight(200.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value); c.setBlockFormat(bf); lf = QTextListFormat(); lf.setStyle(QTextListFormat.Style.ListDisc); c.createList(lf); editor.setTextCursor(c)
editor.keyPressEvent(QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier))
require(editor.document().blockCount() == 2, 'Enter did not create the next list paragraph'); next_block = editor.textCursor().block(); require(next_block.textList() is not None, 'Enter detached the next paragraph from its list'); require(round(next_block.blockFormat().lineHeight()) == 200, 'Enter lost explicit line spacing')

# LibreOffice-style Unicode list markers must consume their fallback bytes
# inside the listtext destination, never from the first character of body text.
# Imported table cell padding/alignment and the absence of trgaph are likewise
# part of the supported dirty-rewrite fidelity contract.
foreign_lists = (CORPUS / 'libreoffice-lists-table-padding.rtf').read_bytes()
foreign_lists_doc = reopen(foreign_lists)
foreign_text = foreign_lists_doc.toPlainText()
require('9 font definitions' in foreign_text and 'LibreOffice palette' in foreign_text, 'LibreOffice list import ate body characters')
foreign_lists_out = document_to_rtf(foreign_lists_doc)
require(br'\listtable' in foreign_lists_out and br'\listoverridetable' in foreign_lists_out and br'\levelnfc23' in foreign_lists_out and b'9 font definitions' in foreign_lists_out, 'LibreOffice bullet dirty rewrite lost standard list semantics or first character')
for token in (br'\clpadfl3\clpadl28', br'\clpadft3\clpadt28', br'\clpadfb3\clpadb28', br'\clpadfr3\clpadr28', br'\clvertalc', br'\cellx7610', br'\cellx8256'):
    require(token in foreign_lists_out, f'LibreOffice table cell geometry/padding lost {token!r}')
require(br'\trgaph108' not in foreign_lists_out, 'LibreOffice table acquired synthetic 108-twip row gap')

# RtfEditorWindow-created auto-fit tables stay auto-fit across save/reopen instead of
# expanding to percentage-constrained full-width tables.
doc = QTextDocument(); c=QTextCursor(doc); from PyQt6.QtGui import QTextTableFormat
tf=QTextTableFormat(); tf.setProperty(RTF_TABLE_AUTOFIT_PROPERTY,True); table=c.insertTable(2,2,tf); table.cellAt(0,0).firstCursorPosition().insertText('A'); table.cellAt(0,1).firstCursorPosition().insertText('B')
payload=document_to_rtf(doc); require(br'\trautofit1' in payload,'auto-fit table marker missing'); require(br'\cellx2700\cellx5400' in payload,'RtfEditorWindow-created auto-fit table retained page-width default geometry'); require(br'\trgaph108' not in payload,'auto-fit table acquired synthetic 108-twip gap'); auto_doc=reopen(payload); auto_table=QTextCursor(auto_doc.begin()).currentTable()
if auto_table is None:
    probe=auto_doc.begin()
    while probe.isValid() and auto_table is None:
        auto_table=QTextCursor(probe).currentTable(); probe=probe.next()
require(auto_table is not None and bool(auto_table.format().property(RTF_TABLE_AUTOFIT_PROPERTY)), 'auto-fit table metadata lost on reopen')
require(len(auto_table.format().columnWidthConstraints())==0, 'auto-fit table reopened with forced full-width percentage constraints')

# Safe hyperlink survives the field representation.
doc = QTextDocument(); c = QTextCursor(doc); f = QTextCharFormat(); f.setAnchor(True); f.setAnchorHref('https://example.com/'); f.setFontUnderline(True); c.insertText('Example', f); payload = document_to_rtf(doc); decoded = decode_rtf(payload); require(b'HYPERLINK' in payload and 'href="https://example.com/"' in decoded.html, 'hyperlink round trip failed')

# Basic Unicode, emphasis and paragraph alignment round-trip.
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Café Δειά 日 '); f = QTextCharFormat(); f.setFontWeight(QFont.Weight.Bold); c.insertText('Bold', f); c.insertBlock(); bf = QTextBlockFormat(); bf.setAlignment(Qt.AlignmentFlag.AlignHCenter); c.setBlockFormat(bf); c.insertText('Centered')
payload = document_to_rtf(doc); reopened = reopen(payload); require('Café Δειά 日 Bold' in reopened.toPlainText() and 'Centered' in reopened.toPlainText(), 'Unicode/text round trip failed')
require(b'\\qc' in payload and b'\\b' in payload, 'supported formatting serialization failed')


# Paragraph geometry must round-trip using Qt layout pixels <-> RTF twips, and
# line spacing must respect QTextBlockFormat.LineHeightTypes instead of treating
# every line-height value as a percentage.
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Spacing')
bf = c.blockFormat(); bf.setLeftMargin(16); bf.setRightMargin(8); bf.setTextIndent(4); bf.setTopMargin(16); bf.setBottomMargin(24); bf.setLineHeight(115.0, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value); c.setBlockFormat(bf)
payload = document_to_rtf(doc)
for token in (br'\li240', br'\ri120', br'\fi60', br'\sb240', br'\sa360', br'\sl276', br'\slmult1'):
    require(token in payload, f'paragraph geometry lost {token!r}')

doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Exact'); bf = c.blockFormat(); bf.setLineHeight(20.0, QTextBlockFormat.LineHeightTypes.FixedHeight.value); c.setBlockFormat(bf); payload = document_to_rtf(doc); require(br'\sl-300' in payload and br'\slmult0' in payload, 'fixed/exact line spacing serialized incorrectly')
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Minimum'); bf = c.blockFormat(); bf.setLineHeight(20.0, QTextBlockFormat.LineHeightTypes.MinimumHeight.value); c.setBlockFormat(bf); payload = document_to_rtf(doc); require(br'\sl300' in payload and br'\slmult0' in payload, 'minimum line spacing serialized incorrectly')

# Historical 0.5/0.6 ruler inheritance could leave two adjacent empty ruler
# blocks.  Canonical output must repair that sequence to one border paragraph.
doc = QTextDocument(); c = QTextCursor(doc); rf = QTextBlockFormat(); rf.setProperty(QTextFormat.Property.BlockTrailingHorizontalRulerWidth, 100); c.setBlockFormat(rf); c.insertBlock(rf); c.insertBlock(QTextBlockFormat()); c.insertText('After'); payload = document_to_rtf(doc); require(payload.count(br'\brdrb') == 1, 'adjacent inherited ruler blocks were not canonicalized')

# Multi-cycle idempotence: indentation and consecutive empty paragraphs must not
# erode after save -> reopen -> save -> reopen.
doc = QTextDocument(); c = QTextCursor(doc); c.insertText('Indented')
bf = c.blockFormat(); bf.setLeftMargin(32); bf.setRightMargin(8); bf.setTextIndent(12); bf.setTopMargin(6); bf.setBottomMargin(10); c.setBlockFormat(bf)
# Three block insertions are required to create *two* empty paragraphs between
# two text paragraphs: the final inserted block is the one that receives the
# following text.  0.6.8 originally used only two insertBlock() calls here, so
# the QA fixture created one empty paragraph but incorrectly asserted two.  The
# application code was not at fault; keep this regression precise so a release
# build cannot be rejected by a malformed test fixture again.
c.insertBlock(); c.insertBlock(); c.insertBlock(); c.insertText('After blanks')
first_payload = document_to_rtf(doc); first_reopen = reopen(first_payload); second_payload = document_to_rtf(first_reopen); second_reopen = reopen(second_payload); third_payload = document_to_rtf(second_reopen); third_reopen = reopen(third_payload)
expected_blocks = ['Indented', '', '', 'After blanks']
first_blocks = [row[0] for row in block_snapshot(first_reopen)]
require(first_blocks == expected_blocks, f'paragraph-cycle QA fixture/import mismatch: expected {expected_blocks!r}, got {first_blocks!r}')
require(block_snapshot(first_reopen) == block_snapshot(second_reopen) == block_snapshot(third_reopen), 'paragraph/indent geometry drifted across repeated RTF cycles')
third_blocks = [row[0] for row in block_snapshot(third_reopen)]
require(third_blocks == expected_blocks, f'consecutive empty paragraphs changed across repeated RTF cycles: expected {expected_blocks!r}, got {third_blocks!r}')
require(br'\li480' in second_payload and br'\fi180' in second_payload, 'indent controls were lost after reopen/resave')


# LibreOffice dirty-rewrite fidelity: resolve stylesheet inheritance before the
# QTextDocument is built and retain imported table cell boundaries instead of
# normalising every table to equal-width columns.
foreign_payload = (CORPUS / 'libreoffice-styles-table.rtf').read_bytes()
foreign_doc = reopen(foreign_payload)
require(foreign_doc.defaultFont().family() == 'Liberation Serif', f'LibreOffice default font style lost: {foreign_doc.defaultFont().family()!r}')
require(abs(foreign_doc.defaultFont().pointSizeF() - 12.0) < 0.01, f'LibreOffice default size style lost: {foreign_doc.defaultFont().pointSizeF()}')
foreign_out = document_to_rtf(foreign_doc)
require(b'Liberation Serif;' in foreign_out and b'Liberation Mono;' in foreign_out and b'Liberation Sans;' in foreign_out, 'LibreOffice inherited font families were flattened during canonical rewrite')
require(br'\cellx7610\cellx8256\cellx9744' in foreign_out, 'LibreOffice table column geometry was normalised during canonical rewrite')
require(br'\fs24' in foreign_out and br'\fs28' in foreign_out, 'LibreOffice inherited body/heading sizes were flattened during canonical rewrite')

# Original JPEG bytes must survive a supported RTF cycle rather than being
# decoded and silently converted to PNG.
image = QImage(3, 2, QImage.Format.Format_RGB32); image.fill(QColor('#a34b2a'))
array = QByteArray(); buffer = QBuffer(array); require(buffer.open(QIODevice.OpenModeFlag.WriteOnly), 'jpeg QA buffer failed'); require(image.save(buffer, 'JPEG', 87), 'jpeg plugin unavailable for RTF QA'); buffer.close(); jpeg = bytes(array)
name = 'data:image/jpeg;base64,' + __import__('base64').b64encode(jpeg).decode('ascii')
doc = QTextDocument(); doc.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image); c = QTextCursor(doc); image_format = QTextImageFormat(); image_format.setName(name); image_format.setWidth(3); image_format.setHeight(2); c.insertImage(image_format)
payload = document_to_rtf(doc); require(br'\jpegblip' in payload and jpeg.hex().encode('ascii') in payload.replace(b'\n', b''), 'JPEG was re-encoded or converted on first RTF save')
reopened = reopen(payload); payload2 = document_to_rtf(reopened); require(br'\jpegblip' in payload2 and jpeg.hex().encode('ascii') in payload2.replace(b'\n', b''), 'JPEG payload changed after reopen/resave')

# Exercise the first-save path through Save As, then open and resave the exact
# blank file.  Keep dialogs non-blocking so any unexpected error becomes a
# deterministic assertion instead of hanging the release gate.
messages = []
old_save_dialog = QFileDialog.getSaveFileName
old_critical, old_warning, old_information, old_question = QMessageBox.critical, QMessageBox.warning, QMessageBox.information, QMessageBox.question
virgin_windows = []
try:
    with tempfile.TemporaryDirectory(prefix='ricopad-virgin-save-') as temp_dir:
        requested_path = pathlib.Path(temp_dir) / 'virgin-document'
        saved_path = pathlib.Path(str(requested_path) + '.rtf')
        invalid_path = pathlib.Path(temp_dir) / 'invalid-empty.rtf'
        invalid_path.write_bytes(b'')
        QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(requested_path), 'Rich Text Format (*.rtf)')
        QMessageBox.critical = lambda *args, **kwargs: messages.append(('critical', args[1:])) or QMessageBox.StandardButton.Cancel
        QMessageBox.warning = lambda *args, **kwargs: messages.append(('warning', args[1:])) or QMessageBox.StandardButton.Cancel
        QMessageBox.information = lambda *args, **kwargs: messages.append(('information', args[1:])) or QMessageBox.StandardButton.Cancel
        virgin = RtfEditorWindow(); virgin_windows.append(virgin)
        require(virgin.visual_editor.toPlainText() == '' and virgin.file_path is None, 'virgin-file QA did not start blank and untitled')
        require(not virgin.visual_editor.document().isModified() and virgin.content_saved and not virgin.windowTitle().startswith('*'), 'untouched startup was incorrectly marked modified')
        app.processEvents()
        require(not virgin.visual_editor.document().isModified() and virgin.content_saved, 'untouched startup became modified after event processing')
        questions = []
        QMessageBox.question = lambda *args, **kwargs: questions.append(args[2]) or QMessageBox.StandardButton.Cancel
        require(virgin.check_save_changes() and not questions, 'untouched startup invoked the save-changes question')
        cursor = virgin.visual_editor.textCursor(); cursor.insertText('User edit'); virgin.visual_editor.setTextCursor(cursor)
        require(virgin.visual_editor.document().isModified() and not virgin.content_saved and virgin.windowTitle().startswith('*'), 'first genuine user edit did not mark the document modified')
        require(not virgin.check_save_changes() and questions == ['Do you want to save changes?'], 'modified document did not invoke the normal save-changes question')
        QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Discard
        require(virgin.new_file(), 'File -> New failed after discarding the lifecycle probe edit')
        require(virgin.visual_editor.toPlainText() == '' and not virgin.visual_editor.document().isModified() and virgin.content_saved and not virgin.windowTitle().startswith('*'), 'File -> New did not restore a clean Untitled document')
        failed_open = RtfEditorWindow(str(invalid_path)); virgin_windows.append(failed_open)
        require(messages and messages[-1][0] == 'warning' and 'does not begin with an RTF header' in str(messages[-1][1]), 'invalid startup RTF did not report its import error')
        messages.clear()
        questions.clear()
        QMessageBox.question = lambda *args, **kwargs: questions.append(args[2]) or QMessageBox.StandardButton.Cancel
        require(failed_open.file_path is None and failed_open.visual_editor.toPlainText() == '' and not failed_open.visual_editor.document().isModified() and failed_open.content_saved, 'failed startup import did not leave a clean unbound Untitled document')
        require(failed_open.check_save_changes() and not questions, 'failed startup import left a spurious save prompt')
        require(virgin.save_as_file(), f'virgin Save As failed: {messages!r}')
        require(saved_path.is_file() and saved_path.read_bytes().startswith(b'{\\rtf1'), 'virgin Save As did not create a recognizable RTF file')
        reader = RtfEditorWindow(); virgin_windows.append(reader)
        require(reader.load_file(str(saved_path), check_changes=False, show_error=True), f'virgin saved file would not reopen: {messages!r}')
        require(reader.visual_editor.toPlainText() == '' and reader.save_file(check_external_change=False), f'virgin reopen/resave changed or failed: {messages!r}')
        require(reopen(saved_path.read_bytes()).toPlainText() == '', 'virgin reopen/resave payload is not an empty RTF document')
        require(not messages, f'virgin save/reopen displayed an unexpected dialog: {messages!r}')
finally:
    QFileDialog.getSaveFileName = old_save_dialog
    QMessageBox.critical, QMessageBox.warning, QMessageBox.information = old_critical, old_warning, old_information
    QMessageBox.question = old_question
    for window in virgin_windows + [indent_window]:
        if window in OPEN_WINDOWS:
            window._skip_close_save_prompt = True; window.close()
    app.processEvents(); QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete); app.processEvents()

print('PASS: Qt-backed RTF save/round-trip QA (document-default stability, list spaces/levels, virgin first-save, auto-fit tables, NoBrush, paragraph cycles, LibreOffice fidelity, images)')
