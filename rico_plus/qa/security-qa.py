#!/usr/bin/env python3
"""Dependency-free hostile-input/security regressions for Rico Plus."""
from __future__ import annotations
import ast, base64, html, importlib.util, pathlib, re, sys
sys.dont_write_bytecode=True
ROOT=pathlib.Path(__file__).resolve().parents[1]
SOURCE=ROOT/'widgets'/'rtf_editor.py'; RTF=ROOT/'rtf_codec.py'; SUPPORT=ROOT/'rich_text_support.py'

def check(value,message):
    if not value: raise AssertionError(message)

spec=importlib.util.spec_from_file_location('ricopad_rich_support_qa',SUPPORT); support=importlib.util.module_from_spec(spec); assert spec.loader; spec.loader.exec_module(support)
png=(b"\x89PNG\r\n\x1a\n"+b"\x00\x00\x00\x0dIHDR"+(1).to_bytes(4,'big')+(1).to_bytes(4,'big')+b"\x08\x06\x00\x00\x00")
safe_png='data:image/png;base64,'+base64.b64encode(png).decode('ascii')
malicious='<script>x</script><p onclick="x" style="background:url(file:///etc/passwd)">ok</p><img src="file:///etc/passwd"><img src="https://example.invalid/a.png"><a href="javascript:x">bad</a><a href="https://example.com/help">web</a><a href="#x">frag</a>'+f'<img src="{safe_png}">'
clean=support.sanitise_qt_html(malicious)
check('<script' not in clean.lower(),'script survived'); check('onclick' not in clean.lower(),'event survived'); check('url(' not in clean.lower(),'CSS URL survived'); check('file:///etc/passwd' not in clean,'file URL survived'); check('example.invalid' not in clean,'remote image survived'); check('javascript:' not in clean.lower(),'unsafe link survived'); check('href="https://example.com/help"' in clean,'safe HTTPS removed'); check('href="#x"' in clean,'safe fragment removed'); check(safe_png in clean,'safe embedded PNG removed')
huge=(b"\x89PNG\r\n\x1a\n"+b"\x00\x00\x00\x0dIHDR"+(100000).to_bytes(4,'big')+(100000).to_bytes(4,'big')+b"\x08\x06\x00\x00\x00")
huge_uri='data:image/png;base64,'+base64.b64encode(huge).decode('ascii'); check('src=' not in support.sanitise_qt_html(f'<img src="{huge_uri}">'),'oversized raster survived')

# Execute only the pure parser subset from rtf_codec.py; PyQt is not required for release QA.
text=RTF.read_text(encoding='utf-8'); tree=ast.parse(text)
names={'_balanced_rtf_group','_rtf_bounded_decimal','_rtf_top_level_child_groups','_rtf_font_table','_rtf_colour_table','_rtf_style_delta','_rtf_style_table','_rtf_list_definitions','_rtf_choose_automatic_foreground_sentinel','_rtf_signed_unicode','_new_rtf_state','_safe_css_font_family','_rtf_twips_to_qt_px','_rtf_run_signature','_rtf_paragraph_signature','rtf_to_html','_rtf_document_properties','_rtf_compatibility_warnings'}
nodes=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names]; check({n.name for n in nodes}==names,'pure RTF parser extraction incomplete')
ns={'base64':base64,'html':html,'re':re,'MAX_EMBEDDED_IMAGE_SIZE':12*1024*1024,'MAX_RTF_GROUP_DEPTH':4096,'MAX_RTF_PARAGRAPHS':250000,'MAX_RTF_RUNS':500000,'MAX_RTF_CAPTURE_CHARS':16*1024,'MAX_RTF_TABLE_CHARS':2*1024*1024,'MAX_RTF_TABLE_ENTRIES':4096,'MAX_RTF_TABLE_ROWS':1000,'MAX_RTF_TABLE_COLUMNS':64,'MAX_RTF_TABLE_CELLS':20000,'MAX_RTF_CONTROL_NUMBER':1000000000,'TWIPS_PER_QT_PIXEL':15.0,'is_safe_link_target':support.is_safe_link_target}
exec(compile(ast.Module(body=nodes,type_ignores=[]),str(RTF),'exec'),ns)
parse=ns['rtf_to_html']
check('Hello' in parse(r'{\rtf1\ansi\deff0{\fonttbl{\f0 Arial;}}\fs22 Hello\par}'),'basic RTF import')
# Automatic colour is not explicit black; highlight 0 is no highlight.
auto=parse(r'{\rtf1\ansi{\colortbl ;\red0\green0\blue0;}\cf0 Auto \cf1 Black\highlight0 NoHi \highlight1 BlackHi\par}')
check('Auto' in auto and 'BlackHi' in auto,'colour/highlight parse regression')
# paragraphs, blank paragraphs and manual line break must remain distinct.
structure=parse(r'{\rtf1\ansi First\line Second\par\par Fourth\par}')
check('First' in structure and 'Second' in structure and 'Fourth' in structure,'paragraph/line text lost'); check('<br>' in structure,'manual line break lost'); check(structure.count('<p')>=3,'blank paragraph collapsed')
# Unicode and fallback bytes.
check('é' in parse(r'{\rtf1\ansi\uc1 Caf\u233?\par}'),'Unicode escape lost')
# Long numeric controls cannot trigger Python giant-int conversion.
try: huge_num=parse('{\\rtf1\\ansi\\fs'+('9'*20000)+' Safe}')
except ValueError as exc: check('Exceeds the limit' not in str(exc),'pathological integer leaked')
else: check('Safe' in huge_num,'text after huge control lost')
# Depth and table limits.
try: parse('{\\rtf1 '+('{'*4100)+'x'+('}'*4100)+'}')
except ValueError as exc: check('nesting depth' in str(exc),'unexpected deep nesting failure')
else: raise AssertionError('RTF nesting bound missing')
table=parse(r'{\rtf1\ansi\trowd\trgaph108\cellx2000\cellx4000\pard\intbl A\cell\pard\intbl B\cell\row}')
check('<table' in table and 'A' in table and 'B' in table,'simple table import regression')
rule=parse(r'{\rtf1\ansi\pard\brdrb\brdrs\brdrw20\brsp20\par\pard After\par}'); check('<hr>' in rule and 'After' in rule,'horizontal rule regression')
double_rule=parse(r'{\rtf1\ansi\pard\brdrb\brdrs\brdrw20\brsp20\par\pard\brdrb\brdrs\brdrw20\brsp20\par\pard After\par}'); check(double_rule.count('<hr>')==1,'historical adjacent horizontal rules were not canonicalized')
spacing=parse(r'{\rtf1\ansi\pard\sb240\sa360\sl276\slmult1 X\par}'); check('margin-top:16px' in spacing and 'margin-bottom:24px' in spacing and 'line-height:115%' in spacing,'paragraph spacing bridge regression')
aliases=parse(r'{\rtf1\ansi\pard\lin480\rin120\fi180 X\par}'); check('margin-left:32px' in aliases and 'margin-right:8px' in aliases and 'text-indent:12px' in aliases,'lin/rin paragraph indent aliases lost')
try: parse(r'{\rtf1\ansi '+(r'\trowd\intbl X\cell\row'*1001)+'}')
except ValueError as exc: check('table rows' in str(exc),'unexpected oversized table failure')
else: raise AssertionError('table row bound missing')
unsafe=parse(r'{\rtf1\ansi{\field{\*\fldinst HYPERLINK "javascript:alert(1)"}{\fldrslt Click}}}'); check('javascript:' not in unsafe.lower(),'unsafe RTF hyperlink survived')
# Compatibility report and retained page geometry are pure parser features.
props=ns['_rtf_document_properties'](br'{\rtf1\paperw12240\paperh15840\margl1440\margr1440\landscape X}'); check(props.get('paperw')==12240 and props.get('landscape') is True,'page properties not retained')
warnings=ns['_rtf_compatibility_warnings'](br'{\rtf1{\object\objdata 00}{\header H}{\footnote F}}'); check('Embedded OLE/object data' in warnings and 'Headers or footers' in warnings and 'Footnotes/endnotes' in warnings,'compatibility warnings missing')
paragraph_warnings=ns['_rtf_compatibility_warnings'](br'{\rtf1\keepn\tx720 X}'); check('Paragraph pagination/widow controls' in paragraph_warnings and 'Custom paragraph tab stops/leaders' in paragraph_warnings,'paragraph compatibility warnings missing')

# Static high-risk primitive and no-external-image-save checks.
source_text=SOURCE.read_text(encoding='utf-8'); source_tree=ast.parse(source_text)
for tree_obj,label in ((source_tree,'main'),(tree,'rtf codec')):
    for node in ast.walk(tree_obj):
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in {'eval','exec'}: raise AssertionError(f'unsafe {node.func.id} in {label}')
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and isinstance(node.func.value,ast.Name) and node.func.value.id=='os' and node.func.attr=='system': raise AssertionError(f'os.system in {label}')
check('class SafeTextDocument(QTextDocument):' in source_text,'external resource guard missing')
check('read_bounded_bytes(' in source_text,'bounded file reader missing')
check('Qt.BrushStyle.NoBrush' in text,'NoBrush serializer regression guard missing')
image_func=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='_qt_image_payload'); image_src=ast.get_source_segment(text,image_func) or ''; check('isfile' not in image_src and 'local_path' not in image_src,'RTF serializer follows local image paths'); check('_rtf_data_image_parts(name)' in image_src,'embedded PNG/JPEG provenance preservation missing'); check('QImageReader(buffer)' in text and 'setAutoTransform(True)' in text,'embedded image display orientation support missing')
check(not (ROOT/'markdown_codec.py').exists() and not (ROOT/'source_editor.py').exists(),'retired mixed-format modules remain')
check('Cropped image geometry' in text,'RTF image-crop compatibility warning missing')
print('PASS: Rico Plus security/RTF hostile-input regressions')
