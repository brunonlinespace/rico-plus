#!/usr/bin/env python3
"""Dependency-free semantic checks over Ricopad's curated RTF corpus."""
from __future__ import annotations
import ast, base64, html, importlib.util, pathlib, re, sys
sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[1]
RTF = ROOT / 'rtf_codec.py'
SUPPORT = ROOT / 'rich_text_support.py'
CORPUS = pathlib.Path(__file__).resolve().parent / 'rtf-corpus'

def require(value, message):
    if not value:
        raise AssertionError(message)

spec = importlib.util.spec_from_file_location('ricopad_rich_support_fidelity', SUPPORT)
support = importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(support)
text = RTF.read_text(encoding='utf-8'); tree = ast.parse(text)
names = {
    '_balanced_rtf_group','_rtf_bounded_decimal','_rtf_top_level_child_groups','_rtf_font_table','_rtf_colour_table',
    '_rtf_style_delta','_rtf_style_table','_rtf_list_definitions',
    '_rtf_choose_automatic_foreground_sentinel','_rtf_signed_unicode','_new_rtf_state',
    '_safe_css_font_family','_rtf_twips_to_qt_px','_rtf_run_signature','_rtf_paragraph_signature','rtf_to_html',
    '_rtf_document_properties','_rtf_compatibility_warnings',
}
nodes = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
require({n.name for n in nodes} == names, 'RTF parser extraction incomplete')
ns = {
    'base64': base64, 'html': html, 're': re,
    'MAX_EMBEDDED_IMAGE_SIZE': 12*1024*1024, 'MAX_RTF_GROUP_DEPTH': 4096,
    'MAX_RTF_PARAGRAPHS': 250000, 'MAX_RTF_RUNS': 500000,
    'MAX_RTF_CAPTURE_CHARS': 16*1024, 'MAX_RTF_TABLE_CHARS': 2*1024*1024,
    'MAX_RTF_TABLE_ENTRIES': 4096, 'MAX_RTF_TABLE_ROWS': 1000,
    'MAX_RTF_TABLE_COLUMNS': 64, 'MAX_RTF_TABLE_CELLS': 20000,
    'MAX_RTF_CONTROL_NUMBER': 1000000000,
    'TWIPS_PER_QT_PIXEL': 15.0,
    'is_safe_link_target': support.is_safe_link_target,
}
exec(compile(ast.Module(body=nodes, type_ignores=[]), str(RTF), 'exec'), ns)
parse = ns['rtf_to_html']; props = ns['_rtf_document_properties']; warnings = ns['_rtf_compatibility_warnings']
files = {p.name: p.read_bytes() for p in sorted(CORPUS.glob('*.rtf'))}
require(len(files) >= 20, 'RTF corpus unexpectedly small')

plain = parse(files['plain.rtf']); require('Plain text only.' in plain, 'plain fixture failed')
legacy_html, legacy_model = parse(files['ricopad-heading-first-default.rtf'], return_model=True)
require(legacy_model['default_half_points'] == 28, f'heading-first legacy Ricopad guessed wrong default size: {legacy_model["default_half_points"]}')
legacy_list = [row for row in legacy_model['paragraphs'] if row.get('style', {}).get('list_type')][0]
legacy_text = ''.join(part for run in legacy_list['runs'] for part in run.get('text', ()))
require(legacy_text == 'Bullet body', f'legacy list marker separator leaked into body text: {legacy_text!r}')
paras = parse(files['paragraphs-lines.rtf']); require('<br>' in paras and paras.count('<p') >= 3, 'paragraph/manual-line fidelity failed')
cycle = parse(files['repeated-save-paragraphs.rtf']); require(cycle.count('<p') == 4, 'consecutive empty paragraphs were not retained by parser'); require('margin-left:32px' in cycle and 'margin-right:8px' in cycle and 'text-indent:12px' in cycle, 'LibreOffice lin/rin/fi indentation aliases were not retained')
spacing = parse(files['libreoffice-paragraph-spacing.rtf'])
for token in ('margin-top:16px','margin-bottom:24px','line-height:115%','line-height:20px'):
    require(token in spacing, f'LibreOffice-style paragraph spacing lost {token}')
fmt = parse(files['formatting.rtf']);
for token in ('font-weight:700', 'font-style:italic', 'text-decoration:underline', 'line-through', 'vertical-align:super', 'vertical-align:sub'):
    require(token in fmt, f'formatting fixture lost {token}')
col = parse(files['colors-highlights.rtf']); require('background-color:#000000' in col and 'background-color:#ffff00' in col, 'highlight colours lost'); require('color:#000000' in col and 'color:#c80000' in col, 'foreground colours lost')
uni = parse(files['unicode.rtf']); require('Café' in uni and '日' in uni and 'Гор' in uni and 'Δειά' in uni, 'Unicode fixture lost text')
lists, lists_model = parse(files['lists.rtf'], return_model=True)
require('<ul>' in lists and lists.count('<li') >= 4 and '<ol>' in lists, 'standards-based list fixture failed')
list_paragraphs = [row for row in lists_model['paragraphs'] if row.get('style', {}).get('list_type')]
require([row['style'].get('list_type') for row in list_paragraphs] == ['unordered','unordered','ordered','ordered'], f'standard list types were not recovered: {list_paragraphs}')
require([row['style'].get('list_id') for row in list_paragraphs] == [1,1,2,2], f'standard list override ids were not retained: {list_paragraphs}')
boundary_html, boundary_model = parse(files['list-format-boundary-spaces.rtf'], return_model=True)
boundary_text = [
    ''.join(part for run in row.get('runs', ()) for part in run.get('text', ()))
    for row in boundary_model['paragraphs']
]
require(boundary_text[:4] == ['Item bold tail', '', ' Leading after empty item', 'After bold tail'], f'list marker state ate formatting-boundary spaces: {boundary_text!r}')
require(boundary_model['paragraphs'][0]['style'].get('list_type') == 'unordered' and not boundary_model['paragraphs'][3]['style'].get('list_type'), 'list marker state leaked into the following normal paragraph')
lo_standard_html, lo_standard_model = parse(files['libreoffice-standard-lists.rtf'], return_model=True)
lo_standard_paragraphs = [row for row in lo_standard_model['paragraphs'] if row.get('style', {}).get('list_type')]
require([row['style'].get('list_type') for row in lo_standard_paragraphs] == ['unordered','unordered','ordered','ordered'], f'LibreOffice standard list tables were not imported: {lo_standard_paragraphs}')
require('Libre bullet one' in lo_standard_html and 'Libre number two' in lo_standard_html and '<ul>' in lo_standard_html and '<ol>' in lo_standard_html, 'LibreOffice standard list content/structure failed')
link = parse(files['hyperlink.rtf']); require('href="https://example.com/"' in link and 'Example' in link, 'hyperlink fixture failed')
image = parse(files['image.rtf']); require('data:image/png;base64,' in image and '<img ' in image, 'embedded image fixture failed')
table = parse(files['table.rtf']); require(table.count('<tr>') == 2 and table.count('<td>') == 4 and 'A2' in table and 'B2' in table, 'table fixture failed')

lo_html, lo_model = parse(files['libreoffice-styles-table.rtf'], return_model=True)
require(lo_model['default_font_id'] == 3 and lo_model['default_half_points'] == 24, f'LibreOffice Normal/default style not resolved: {(lo_model["default_font_id"], lo_model["default_half_points"])}')
require(lo_model['fonts'].get(3) == 'Liberation Serif' and lo_model['fonts'].get(4) == 'Liberation Mono' and lo_model['fonts'].get(6) == 'Liberation Sans', f'LibreOffice nested fallback font groups lost: {lo_model["fonts"]}')
body_run = lo_model['paragraphs'][0]['runs'][0]['signature']
heading_run = lo_model['paragraphs'][1]['runs'][0]['signature']
require(body_run[4:6] == (3, 24), f'Body Text style inheritance lost font/size: {body_run}')
require(heading_run[4:6] == (6, 28) and heading_run[0] is True, f'Heading style inheritance lost: {heading_run}')
lo_rows = [row for row in lo_model['paragraphs'] if 'table_row' in row]
require(len(lo_rows) == 2 and lo_rows[0].get('cellx') == [7610,8256,9744], f'LibreOffice table cell geometry lost: {lo_rows[:1]}')
require(lo_rows[1]['table_row'][0]['runs'][0]['signature'][4] == 4, 'LibreOffice Source Text character style lost Liberation Mono')

lo_list_html, lo_list_model = parse(files['libreoffice-lists-table-padding.rtf'], return_model=True)
lo_list_paras = [row for row in lo_list_model['paragraphs'] if 'table_row' not in row]
require(lo_list_paras[1]['style'].get('list_type') == 'unordered', f'LibreOffice bullet marker not recognized: {lo_list_paras[1]["style"]}')
require(''.join(lo_list_paras[1]['runs'][0]['text']).lstrip().startswith('9 font definitions'), f'Unicode list fallback leaked into body and ate first character: {lo_list_paras[1]["runs"]}')
require(lo_list_paras[3]['style'].get('list_type') == 'ordered', f'LibreOffice numbered marker not recognized: {lo_list_paras[3]["style"]}')
lo_pad_rows = [row for row in lo_list_model['paragraphs'] if 'table_row' in row]
require(len(lo_pad_rows) == 1 and lo_pad_rows[0].get('cellx') == [7610,8256], f'LibreOffice padded table geometry lost: {lo_pad_rows}')
require('trgaph' not in lo_pad_rows[0], f'Absent LibreOffice trgaph was invented during parse: {lo_pad_rows[0]}')
first_meta = lo_pad_rows[0].get('cell_formats', [{}])[0]
require(first_meta == {'pad_left':28,'pad_right':28,'pad_top':28,'pad_bottom':28,'valign':'center'}, f'LibreOffice cell padding/alignment lost: {first_meta}')
rule = parse(files['horizontal-rule.rtf']); require('<hr>' in rule and 'Before' in rule and 'After' in rule, 'horizontal rule fixture failed')
page = props(files['page-properties.rtf']); require(page == {'paperw':12240,'paperh':15840,'margl':1440,'margr':1440,'margt':1080,'margb':1080}, f'page properties failed: {page}')
warn = warnings(files['unsupported-constructs.rtf']); require('Embedded OLE/object data' in warn and 'Headers or footers' in warn, 'unsupported-construct warnings failed')
print(f'PASS: RTF corpus semantic QA ({len(files)} fixtures)')
