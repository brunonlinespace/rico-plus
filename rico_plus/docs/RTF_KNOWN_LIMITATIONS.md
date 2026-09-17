# Rico Plus RTF Known Limitations

- Final AppImage promotion requires live target-desktop GUI testing.
- Printing and PDF export require target printer/paint-device validation.
- Clipboard interoperability should be tested against each target desktop.
- Complex multilevel numbering may be normalized to supported list styles.
- OLE objects, shapes, comments, footnotes, headers/footers, tracked revisions,
  nested tables, and other advanced constructs can be lossy after a real edit;
  Rico Plus warns before rewriting recognized unsupported content.
