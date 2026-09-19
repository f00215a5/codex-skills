#!/usr/bin/env python3
"""Programmatic structure QA for the generated manual DOCX (Python-only).

It checks the verifiable document contract — structure, numbering restarts,
tables, captions vs images, page setup, package integrity — and fails closed
when any check fails.

Usage:
    <venv-python> verify_docx.py --docx manual.docx [--manifest manual.json]

Exit code 0 == all structure checks passed. Visual review scope is reported in
the conversation, not added to the generated manual.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

from docx import Document
from docx.oxml.ns import qn

CAPTION_PATTERN = re.compile(r"紅框\s*(\d+)")
CHECKMARK = "PASS"
CROSS = "FAIL"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Structure QA for the manual DOCX.")
    parser.add_argument("--docx", required=True, type=Path)
    parser.add_argument("--manifest", type=Path, help="Optional manifest for caption/id cross-check.")
    return parser.parse_args()


class Reporter:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> None:
        status = CHECKMARK if condition else CROSS
        message = f"[{status}] {name}"
        if detail:
            message += f" — {detail}"
        print(message)
        if not condition:
            self.failures.append(name)


def headings_of(document: Document) -> list[tuple[str, str]]:
    """Return (style_name, text) of heading paragraphs in document order."""
    result = []
    for paragraph in document.paragraphs:
        style_name = paragraph.style.name if paragraph.style is not None else ""
        if style_name.startswith("Heading"):
            result.append((style_name, paragraph.text.strip()))
    return result


def numbered_paragraphs(document: Document) -> list[tuple[int, int]]:
    """Return (numId, ilvl) for every paragraph carrying w:numPr."""
    numbered = []
    for paragraph in document.paragraphs:
        num_pr = paragraph._p.find(qn("w:pPr") + "/" + qn("w:numPr"))
        if num_pr is None:
            continue
        num_id = num_pr.find(qn("w:numId"))
        ilvl = num_pr.find(qn("w:ilvl"))
        number = int(num_id.get(qn("w:val"))) if num_id is not None else -1
        level = int(ilvl.get(qn("w:val"))) if ilvl is not None else 0
        numbered.append((number, level))
    return numbered


def numbering_ids(document: Document) -> tuple[list[int], list[int], list[int], list[int]]:
    """Return abstract IDs, concrete IDs, nsids and startOverride values."""

    root = document.part.numbering_part.element
    abstract_ids: list[int] = []
    concrete_ids: list[int] = []
    nsids: list[int] = []
    overrides: list[int] = []
    for node in root.findall(qn("w:abstractNum")):
        raw_id = node.get(qn("w:abstractNumId"))
        if raw_id is not None:
            abstract_ids.append(int(raw_id))
        nsid = node.find(qn("w:nsid"))
        if nsid is not None and nsid.get(qn("w:val")) is not None:
            try:
                nsids.append(int(nsid.get(qn("w:val")), 16))
            except ValueError:
                pass
    for node in root.findall(qn("w:num")):
        raw_id = node.get(qn("w:numId"))
        if raw_id is not None:
            concrete_ids.append(int(raw_id))
        for override in node.findall(qn("w:lvlOverride")):
            start = override.find(qn("w:startOverride"))
            if start is not None and start.get(qn("w:val")) is not None:
                try:
                    overrides.append(int(start.get(qn("w:val"))))
                except ValueError:
                    pass
    return abstract_ids, concrete_ids, nsids, overrides


def operation_numbering_definitions(document: Document, num_ids: set[int]) -> list[str]:
    """Validate the concrete definitions actually used by operation steps."""

    root = document.part.numbering_part.element
    abstracts = {
        int(node.get(qn("w:abstractNumId"))): node
        for node in root.findall(qn("w:abstractNum"))
        if node.get(qn("w:abstractNumId")) is not None
    }
    concretes = {
        int(node.get(qn("w:numId"))): node
        for node in root.findall(qn("w:num"))
        if node.get(qn("w:numId")) is not None
    }
    failures: list[str] = []
    referenced_abstracts: set[int] = set()
    for num_id in sorted(num_ids):
        concrete = concretes.get(num_id)
        if concrete is None:
            failures.append(f"numId {num_id} has no concrete definition")
            continue
        abstract_ref = concrete.find(qn("w:abstractNumId"))
        raw_abstract_id = abstract_ref.get(qn("w:val")) if abstract_ref is not None else None
        try:
            abstract_id = int(raw_abstract_id) if raw_abstract_id is not None else -1
        except ValueError:
            abstract_id = -1
        if abstract_id not in abstracts:
            failures.append(f"numId {num_id} references missing abstractNumId {abstract_id}")
        else:
            referenced_abstracts.add(abstract_id)
            nsid = abstracts[abstract_id].find(qn("w:nsid"))
            if nsid is None or not nsid.get(qn("w:val")):
                failures.append(f"abstractNumId {abstract_id} is missing nsid")
        override_ok = False
        for override in concrete.findall(qn("w:lvlOverride")):
            if override.get(qn("w:ilvl")) != "0":
                continue
            start = override.find(qn("w:startOverride"))
            if start is not None and start.get(qn("w:val")) == "1":
                override_ok = True
                break
        if not override_ok:
            failures.append(f"numId {num_id} is missing level-0 startOverride=1")
    if len(referenced_abstracts) != len(num_ids):
        failures.append("operation sections do not have one distinct abstract numbering definition each")
    return failures


def drawing_targets(document: Document) -> list[tuple[int, str]]:
    """Return (paragraph_index, media target) for every embedded drawing."""
    items: list[tuple[int, str]] = []
    for index, paragraph in enumerate(document.paragraphs):
        for blip in paragraph._p.xpath(".//a:blip"):
            r_id = blip.get(qn("r:embed"))
            if r_id and r_id in document.part.related_parts:
                items.append((index, str(document.part.related_parts[r_id].partname)))
    return items


def inline_extent_failures(document: Document) -> list[str]:
    """Return final-package inline image extents outside the section container."""

    section = document.sections[0]
    content_width = int(section.page_width) - int(section.left_margin) - int(section.right_margin)
    content_height = int(section.page_height) - int(section.top_margin) - int(section.bottom_margin)
    failures: list[str] = []
    for index, extent in enumerate(document.element.body.iter(qn("wp:extent")), start=1):
        parent = extent.getparent()
        if parent is None or parent.tag != qn("wp:inline"):
            continue
        try:
            width = int(extent.get("cx"))
            height = int(extent.get("cy"))
        except (TypeError, ValueError):
            failures.append(f"inline image {index} has invalid extent")
            continue
        if width <= 0 or height <= 0:
            failures.append(f"inline image {index} has non-positive extent {width}x{height}")
            continue
        if width > content_width:
            failures.append(f"inline image {index} width {width} exceeds content width {content_width}")
        if height > content_height:
            failures.append(f"inline image {index} height {height} exceeds content height {content_height}")
    return failures


def exact_height_rows(document: Document) -> list[int]:
    """Return table-row indexes carrying an exact fixed height."""

    rows: list[int] = []
    for index, row in enumerate(document.element.body.iter(qn("w:tr")), start=1):
        tr_pr = row.find(qn("w:trPr"))
        height = tr_pr.find(qn("w:trHeight")) if tr_pr is not None else None
        if height is not None and height.get(qn("w:hRule")) == "exact":
            rows.append(index)
    return rows


def table_headers(table) -> list[str]:
    return [cell.text.strip() for cell in table.rows[0].cells]


def table_layout_properties(table) -> tuple[str | None, str | None, str | None, int | None, int | None]:
    """Return alignment, width/layout and declared/grid widths in twips."""

    tbl_pr = table._tbl.tblPr
    alignment = tbl_pr.find(qn("w:jc"))
    width = tbl_pr.find(qn("w:tblW"))
    layout = tbl_pr.find(qn("w:tblLayout"))
    try:
        width_value = int(width.get(qn("w:w"))) if width is not None else None
    except (TypeError, ValueError):
        width_value = None
    grid = table._tbl.tblGrid
    grid_width = 0
    grid_valid = True
    for column in grid:
        try:
            grid_width += int(column.get(qn("w:w")))
        except (TypeError, ValueError):
            grid_valid = False
            break
    if not grid_valid or grid_width <= 0:
        grid_width = None
    return (
        alignment.get(qn("w:val")) if alignment is not None else None,
        width.get(qn("w:type")) if width is not None else None,
        layout.get(qn("w:type")) if layout is not None else None,
        width_value,
        grid_width,
    )


def main() -> int:
    args = parse_args()
    docx_path = args.docx.expanduser().resolve()
    reporter = Reporter()

    try:
        document = Document(str(docx_path))
    except Exception as error:  # noqa: BLE001 — any open failure fails closed
        print(f"[FAIL] open docx — {error}")
        return 1

    # -- package integrity -------------------------------------------------- #
    try:
        with zipfile.ZipFile(docx_path) as archive:
            names = archive.namelist()
    except zipfile.BadZipFile as error:
        print(f"[FAIL] zip integrity — {error}")
        return 1
    reporter.check("docx contains document.xml", "word/document.xml" in names)
    media_files = [name for name in names if name.startswith("word/media/")]
    reporter.check("page writer exists", "word/numbering.xml" in names, f"media={len(media_files)}")

    # -- page setup (Letter, baseline margins) ------------------------------ #
    section = document.sections[0]
    reporter.check("paper size is Letter",
                   abs(section.page_width.inches - 8.5) < 0.01 and abs(section.page_height.inches - 11.0) < 0.01)
    reporter.check("margins match baseline",
                   abs(section.top_margin.inches - 0.67) < 0.01
                   and abs(section.bottom_margin.inches - 0.59) < 0.01
                   and abs(section.left_margin.inches - 0.65) < 0.01
                   and abs(section.right_margin.inches - 0.65) < 0.01)
    extent_failures = inline_extent_failures(document)
    reporter.check(
        "inline image extents fit section content container",
        not extent_failures,
        detail="; ".join(extent_failures),
    )
    exact_rows = exact_height_rows(document)
    if exact_rows:
        print(
            "[RISK] table rows use exact fixed heights; content clipping is not inferred — "
            f"rows={exact_rows}"
        )

    # -- heading order ------------------------------------------------------ #
    headings = headings_of(document)
    heading_texts = [text for _, text in headings]
    reporter.check("has title area content", any(paragraph.text.strip()
                                                 for paragraph in document.paragraphs[:5]))
    for required in ("修訂狀態", "使用提醒", "共通操作規則", "更新紀錄"):
        reporter.check(f"heading present: {required}", required in heading_texts)
    log_position = heading_texts.index("更新紀錄") if "更新紀錄" in heading_texts else -1
    reporter.check("更新紀錄 is the first heading",
                   log_position == 0)
    order = [text for text in heading_texts if text in ("更新紀錄", "修訂狀態", "使用提醒", "共通操作規則")]
    reporter.check("heading order 更新紀錄→修訂狀態→使用提醒→共通操作規則",
                   order == ["更新紀錄", "修訂狀態", "使用提醒", "共通操作規則"])

    # -- numbering definitions and independent step numbering ---------------- #
    abstract_ids, concrete_ids, nsids, overrides = numbering_ids(document)
    reporter.check("numbering abstract IDs are unique", len(abstract_ids) == len(set(abstract_ids)))
    reporter.check("numbering concrete IDs are unique", len(concrete_ids) == len(set(concrete_ids)))
    reporter.check("numbering concrete IDs are not the remove-numbering sentinel",
                   all(value >= 1 for value in concrete_ids))
    reporter.check("numbering custom abstract definitions have unique nsid",
                   len(nsids) == len(set(nsids)))
    # Built-in template lists may not have overrides.  The concrete lists used
    # by operation steps are checked against their own abstract definitions
    # below, so an unused template definition cannot create a false pass.

    numbered = numbered_paragraphs(document)
    reporter.check("operation steps carry numbering", len(numbered) >= 1, f"numbered paragraphs={len(numbered)}")
    # Every Heading-2 operation section must own exactly one numId so its step
    # list restarts at 1 instead of continuing from the previous section.
    blocks: list[list[int]] = []
    current: list[int] = []
    seen_section = False
    for paragraph in document.paragraphs:
        style = paragraph.style.name if paragraph.style else ""
        if style == "Heading 2":
            if current:
                blocks.append(current)
            current = []
            seen_section = True
            continue
        num_pr = paragraph._p.find(qn("w:pPr") + "/" + qn("w:numPr"))
        if seen_section and num_pr is not None and (num_id := num_pr.find(qn("w:numId"))) is not None:
            current.append(int(num_id.get(qn("w:val"))))
    if current:
        blocks.append(current)
    nonempty_blocks = [block for block in blocks if block]
    distinct_section_ids = [block[0] for block in nonempty_blocks if len(set(block)) == 1]
    reporter.check("every step list restarts within its section",
                   any(nonempty_blocks) and all(len(set(block)) == 1 for block in nonempty_blocks),
                   detail=f"step blocks={[len(b) for b in blocks]}")
    reporter.check("each operation section owns a distinct numbering definition",
                   len(distinct_section_ids) == len(set(distinct_section_ids)),
                   detail=f"numIds={distinct_section_ids}")
    numbering_definition_failures = operation_numbering_definitions(document, set(distinct_section_ids))
    reporter.check(
        "operation numbering definitions reference unique resettable abstract lists",
        not numbering_definition_failures,
        detail="; ".join(numbering_definition_failures),
    )

    # -- field tables ------------------------------------------------------- #
    tables = document.tables
    for index, table in enumerate(tables, start=1):
        alignment, width_type, layout, width_value, grid_width = table_layout_properties(table)
        width_units_valid = (
            (width_type == "pct" and (width_value is None or 0 <= width_value <= 5000))
            or (width_type == "dxa" and (width_value is None or 0 <= width_value <= 10368 + 20))
            or width_type == "auto"
            or width_type is None
        )
        # ``tblW`` percentage units and column-grid twips are independent;
        # never compare their numeric values as if they shared a unit.
        grid_units_valid = grid_width is None or 0 < grid_width <= 10368 + 20
        reporter.check(
            f"table {index} has explicit center alignment",
            alignment == "center",
            detail=f"alignment={alignment!r}",
        )
        reporter.check(
            f"table {index} uses flexible layout",
            layout in {"autofit", "fixed", None}
            and width_type in {"auto", "pct", "dxa", None}
            and width_units_valid
            and grid_units_valid,
            detail=f"width_type={width_type!r} layout={layout!r} width_twips={width_value!r} grid_twips={grid_width!r}",
        )
    field_tables = [
        t for t in tables
        if any("欄位" in header or "控制項" in header for header in table_headers(t))
    ]
    reporter.check("field tables present for operations", len(field_tables) >= 1, f"tables={len(field_tables)}")
    for table in field_tables:
        headers = table_headers(table)
        reporter.check("field table has 定義/必填 columns",
                       "定義" in headers and "必填" in headers, detail=f"headers={headers}")

    # -- update log --------------------------------------------------------- #
    if tables:
        first_table_headers = table_headers(tables[0])
        reporter.check("update log is the first table",
                       first_table_headers[:3] == ["版本", "日期", "更新內容"],
                       detail=f"headers={first_table_headers}")
        reporter.check("update log has data rows", len(tables[0].rows) >= 2)

    # -- captions vs images ------------------------------------------------- #
    # 紅框編號是每張圖獨立重編（同張圖內的控制項對照），所以不要求全域唯一。
    drawings = drawing_targets(document)
    reporter.check("images embedded", len(drawings) >= 1, f"drawings={len(drawings)}")
    missing_targets = [target for _, target in drawings if target.lstrip("/") not in names]
    reporter.check("every embedded image resolves inside the package",
                   not missing_targets, detail=f"missing={missing_targets}")

    drawings_paragraphs = {index for index, _ in drawings}
    captions: list[str] = []
    for index in range(len(document.paragraphs) - 1):
        if index in drawings_paragraphs:
            if match := CAPTION_PATTERN.match(document.paragraphs[index + 1].text.strip()):
                captions.append(match.group(1))
    reporter.check("image captions reference 紅框 numbers", len(captions) >= 1, f"captions={captions}")
    caption_follow = sum(
        1 for index, _ in drawings
        if index + 1 < len(document.paragraphs) and document.paragraphs[index + 1].text.strip()
    )
    reporter.check("every image drawing is followed by a caption line",
                   caption_follow == len(drawings),
                   f"captioned={caption_follow} drawings={len(drawings)}")

    # -- optional build-manifest cross-check -------------------------------- #
    if args.manifest:
        manifest = json_load(args.manifest.expanduser().resolve())
        expected: list[str] = []
        chapters = manifest.get("chapters")
        if chapters is None:
            chapters = [manifest.get("chapter") or {}]
        for chapter in chapters:
            entry = chapter.get("entry") or {}
            if entry.get("image"):
                if match := CAPTION_PATTERN.match(str(entry.get("caption", ""))):
                    expected.append(match.group(1))
            for section in chapter.get("sections", []):
                for step in section.get("steps", []):
                    if step.get("image"):
                        if match := CAPTION_PATTERN.match(str(step.get("caption", ""))):
                            expected.append(match.group(1))
        reporter.check("caption sequence matches build manifest order",
                       list(captions) == expected, detail=f"docx={captions} manifest={expected}")

    if reporter.failures:
        print(f"\nverify_docx.py: {len(reporter.failures)} check(s) failed "
              f"({', '.join(reporter.failures)})")
        return 1
    print("\nverify_docx.py: all structure checks passed. "
          "Visual fidelity after opening the file is not verified by this script.")
    return 0


def json_load(path: Path) -> dict[str, Any]:
    import json
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(payload, dict)
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
