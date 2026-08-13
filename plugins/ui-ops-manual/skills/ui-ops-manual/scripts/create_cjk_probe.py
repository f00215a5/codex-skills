#!/usr/bin/env python3
"""Create a minimal DOCX whose live Traditional Chinese text can be rendered."""

from __future__ import annotations

import argparse
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile


PROBE_TEXT = "繁體中文 glyph probe：險別管理／臺灣／龜麵／儲存／取消／欄位說明"


def non_empty(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise argparse.ArgumentTypeError("font name must not be empty")
    return normalized


def output_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def document_xml(font_name: str) -> str:
    font = escape(font_name, {'"': "&quot;"})
    text = escape(PROBE_TEXT)
    return f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p>
      <w:r>
        <w:rPr>
          <w:rFonts w:ascii="{font}" w:hAnsi="{font}" w:eastAsia="{font}"/>
          <w:lang w:val="zh-TW" w:eastAsia="zh-TW"/>
          <w:sz w:val="28"/>
          <w:szCs w:val="28"/>
        </w:rPr>
        <w:t>{text}</w:t>
      </w:r>
    </w:p>
    <w:sectPr>
      <w:pgSz w:w="12240" w:h="15840"/>
      <w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/>
    </w:sectPr>
  </w:body>
</w:document>
'''


CONTENT_TYPES = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
'''

PACKAGE_RELS = '''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
'''


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a temporary DOCX for Traditional Chinese glyph rendering verification."
    )
    parser.add_argument(
        "--font-name",
        required=True,
        type=non_empty,
        help="Confirmed CJK font name assigned to the probe's eastAsia run property.",
    )
    parser.add_argument("--output", required=True, type=output_path, help="Path for the probe DOCX.")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    output: Path = arguments.output
    output.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as document:
        document.writestr("[Content_Types].xml", CONTENT_TYPES)
        document.writestr("_rels/.rels", PACKAGE_RELS)
        document.writestr("word/document.xml", document_xml(arguments.font_name))
    print(f"CJK_PROBE_DOCX={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
