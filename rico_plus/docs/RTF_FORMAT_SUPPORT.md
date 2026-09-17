# RTF Format Support in Rico Plus 0.0.2

Rico Plus opens and saves `.rtf` only. Standards interoperability is the
persistence target.

## Supported core

- Unicode text and common RTF code-page escapes
- Font family/size and supported stylesheet inheritance
- Bold, italic, underline, strikethrough, superscript, and subscript
- Foreground and highlight colors, including automatic/unset states
- Paragraph alignment, indentation, margins, spacing, tabs, and manual breaks
- Standard bullet lists; imported standard decimal lists are retained
- Safe hyperlinks and embedded PNG/JPEG images
- Horizontal rules
- Bounded simple non-nested tables
- Page size, margins, and landscape properties

Rico Plus writes standard list tables and overrides so compatible applications
such as LibreOffice recognize semantic lists rather than visual marker text.

## Limits

The editor does not promise lossless rewriting of OLE/object payloads, drawing
objects, headers/footers, comments, footnotes/endnotes, tracked revisions,
nested tables, complex bidirectional controls, or producer-specific extensions.
Properties and pre-save warnings identify known unsupported constructs before a
dirty rewrite.

Files are bounded to 25 MiB for responsive editing. Tables are bounded to 1,000
rows, 64 columns, and 20,000 cells. Embedded images are validated and stored in
the RTF rather than followed from local file links during serialization.
