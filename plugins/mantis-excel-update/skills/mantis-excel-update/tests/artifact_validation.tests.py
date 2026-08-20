#!/usr/bin/env python3
"""Artifact-level contract tests for ``scripts/validate_artifact.py``."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import unittest
import warnings
import xml.etree.ElementTree as ET
import zipfile


TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
FIXTURES_DIR = TESTS_DIR / "fixtures"
CONTRACT_FIXTURE = FIXTURES_DIR / "synthetic-artifact-contract.json"
PREFLIGHT_FIXTURE = FIXTURES_DIR / "synthetic-preflight-snapshot.json"
CSV_FIXTURE = FIXTURES_DIR / "synthetic-mantis-issues-44.csv"
VALIDATOR = SKILL_DIR / "scripts" / "validate_artifact.py"
DEFAULT_TEMPLATE = SKILL_DIR / "assets" / "template.xlsx"

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
CONTENT_TYPES_NS = "http://schemas.openxmlformats.org/package/2006/content-types"

ET.register_namespace("", SPREADSHEET_NS)
ET.register_namespace("r", REL_NS)

FORMULAS = {
    "in_progress": ("B2", 'COUNTIF(Issues!$B$2:$B$45,"IN_PROGRESS")', 29),
    "pending_release": ("B3", 'COUNTIF(Issues!$B$2:$B$45,"PENDING_RELEASE")', 5),
    "resolved": ("B4", 'COUNTIF(Issues!$B$2:$B$45,"RESOLVED")', 10),
    "unknown": ("B5", "COUNTBLANK(Issues!$B$2:$B$45)", 0),
    "total": ("B6", "COUNTA(Issues!$A$2:$A$45)", 44),
}
MEBIBYTE = 1024 * 1024


def _qualified(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def _append_inline_cell(row: ET.Element, reference: str, value: str) -> None:
    cell = ET.SubElement(row, _qualified(SPREADSHEET_NS, "c"), {"r": reference, "t": "inlineStr"})
    inline_string = ET.SubElement(cell, _qualified(SPREADSHEET_NS, "is"))
    ET.SubElement(inline_string, _qualified(SPREADSHEET_NS, "t")).text = value


def _append_number_cell(row: ET.Element, reference: str, value: int) -> None:
    cell = ET.SubElement(row, _qualified(SPREADSHEET_NS, "c"), {"r": reference})
    ET.SubElement(cell, _qualified(SPREADSHEET_NS, "v")).text = str(value)


def _append_shared_string_cell(row: ET.Element, reference: str, index: int) -> None:
    cell = ET.SubElement(
        row,
        _qualified(SPREADSHEET_NS, "c"),
        {"r": reference, "t": "s"},
    )
    ET.SubElement(cell, _qualified(SPREADSHEET_NS, "v")).text = str(index)


def _shared_strings_xml(values: list[str]) -> bytes:
    root = ET.Element(
        _qualified(SPREADSHEET_NS, "sst"),
        {"count": str(len(values)), "uniqueCount": str(len(values))},
    )
    for value in values:
        item = ET.SubElement(root, _qualified(SPREADSHEET_NS, "si"))
        ET.SubElement(item, _qualified(SPREADSHEET_NS, "t")).text = value
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _sheet_root(
    *,
    active_cell: str,
    include_sheet_view: bool,
    tab_selected: bool = False,
) -> tuple[ET.Element, ET.Element]:
    root = ET.Element(_qualified(SPREADSHEET_NS, "worksheet"))
    if include_sheet_view:
        sheet_views = ET.SubElement(root, _qualified(SPREADSHEET_NS, "sheetViews"))
        sheet_view_attributes = {"workbookViewId": "0"}
        if tab_selected:
            sheet_view_attributes["tabSelected"] = "1"
        sheet_view = ET.SubElement(
            sheet_views,
            _qualified(SPREADSHEET_NS, "sheetView"),
            sheet_view_attributes,
        )
        ET.SubElement(
            sheet_view,
            _qualified(SPREADSHEET_NS, "selection"),
            {"activeCell": active_cell, "sqref": active_cell},
        )
    return root, ET.SubElement(root, _qualified(SPREADSHEET_NS, "sheetData"))


def _issues_sheet_xml(
    *,
    hidden_rows: set[int],
    hidden_columns: set[str],
    zero_width_columns: set[str],
    default_column_width: int | None,
    default_row_hidden: bool,
    populated_row_visible_override: str | None,
    shared_string_issue_ids: bool,
    shared_string_index_override: int | None,
    lose_leading_zero: bool,
    tab_selected: bool,
) -> bytes:
    root, sheet_data = _sheet_root(
        active_cell="A1",
        include_sheet_view=True,
        tab_selected=tab_selected,
    )
    if populated_row_visible_override not in {None, "hidden", "height"}:
        raise AssertionError(
            f"unsupported populated row visibility override: {populated_row_visible_override}",
        )
    sheet_format_attributes = {}
    if default_column_width is not None:
        sheet_format_attributes["defaultColWidth"] = str(default_column_width)
    if default_row_hidden:
        sheet_format_attributes["zeroHeight"] = "1"
    if sheet_format_attributes:
        sheet_format = ET.Element(
            _qualified(SPREADSHEET_NS, "sheetFormatPr"),
            sheet_format_attributes,
        )
        root.insert(list(root).index(sheet_data), sheet_format)
    if hidden_columns or zero_width_columns:
        columns = ET.Element(_qualified(SPREADSHEET_NS, "cols"))
        for column_number, column_name in enumerate(("A", "B", "C"), start=1):
            if column_name not in hidden_columns and column_name not in zero_width_columns:
                continue
            attributes = {"min": str(column_number), "max": str(column_number)}
            if column_name in hidden_columns:
                attributes["hidden"] = "1"
            if column_name in zero_width_columns:
                attributes.update({"width": "0", "customWidth": "1"})
            ET.SubElement(columns, _qualified(SPREADSHEET_NS, "col"), attributes)
        root.insert(list(root).index(sheet_data), columns)
    def visible_row_attributes(row_number: int) -> dict[str, str]:
        attributes = {"r": str(row_number)}
        if populated_row_visible_override == "hidden":
            attributes["hidden"] = "0"
        elif populated_row_visible_override == "height":
            attributes.update({"ht": "15", "customHeight": "1"})
        return attributes

    header = ET.SubElement(
        sheet_data,
        _qualified(SPREADSHEET_NS, "row"),
        visible_row_attributes(1),
    )
    for column, value in zip(("A", "B", "C"), ("Issue ID", "Status", "Summary")):
        _append_inline_cell(header, f"{column}1", value)

    with CSV_FIXTURE.open(newline="", encoding="utf-8") as csv_file:
        issues = list(csv.DictReader(csv_file))
    for excel_row, issue in enumerate(issues, start=2):
        attributes = visible_row_attributes(excel_row)
        if excel_row in hidden_rows:
            attributes["hidden"] = "1"
        row = ET.SubElement(sheet_data, _qualified(SPREADSHEET_NS, "row"), attributes)
        if shared_string_issue_ids:
            shared_string_index = excel_row - 2
            if excel_row == 2 and shared_string_index_override is not None:
                shared_string_index = shared_string_index_override
            _append_shared_string_cell(row, f"A{excel_row}", shared_string_index)
        elif lose_leading_zero and excel_row == 2:
            _append_number_cell(row, f"A{excel_row}", int(issue["Issue ID"]))
        else:
            _append_inline_cell(row, f"A{excel_row}", issue["Issue ID"])
        _append_inline_cell(row, f"B{excel_row}", issue["Status"])
        _append_inline_cell(row, f"C{excel_row}", issue["Summary"])
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _summary_sheet_xml(
    *,
    include_sheet_view: bool,
    formula_cache_overrides: dict[str, object],
    string_formula_caches: set[str],
    static_formula_cells: set[str],
    additional_formula_cells: dict[str, tuple[str, str, object]],
) -> bytes:
    root, sheet_data = _sheet_root(
        active_cell="B2",
        include_sheet_view=include_sheet_view,
        tab_selected=True,
    )
    header = ET.SubElement(sheet_data, _qualified(SPREADSHEET_NS, "row"), {"r": "1"})
    _append_inline_cell(header, "A1", "Statistic")
    _append_inline_cell(header, "B1", "Value")

    formula_entries = list(FORMULAS.items()) + list(additional_formula_cells.items())
    for excel_row, (statistic, (cell_ref, formula, expected)) in enumerate(formula_entries, start=2):
        row = ET.SubElement(sheet_data, _qualified(SPREADSHEET_NS, "row"), {"r": str(excel_row)})
        _append_inline_cell(row, f"A{excel_row}", statistic)
        cell_attributes = {"r": cell_ref}
        override = formula_cache_overrides.get(statistic, expected)
        if statistic in string_formula_caches:
            cell_attributes["t"] = "str"
        if override == "error":
            cell_attributes["t"] = "e"
        cell = ET.SubElement(row, _qualified(SPREADSHEET_NS, "c"), cell_attributes)
        if statistic not in static_formula_cells:
            ET.SubElement(cell, _qualified(SPREADSHEET_NS, "f")).text = formula
        if override != "blank":
            cached = ET.SubElement(cell, _qualified(SPREADSHEET_NS, "v"))
            cached.text = "#VALUE!" if override == "error" else str(override)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _workbook_xml(*, include_workbook_view: bool, include_internal_dtd: bool) -> bytes:
    root = ET.Element(_qualified(SPREADSHEET_NS, "workbook"))
    if include_workbook_view:
        book_views = ET.SubElement(root, _qualified(SPREADSHEET_NS, "bookViews"))
        ET.SubElement(
            book_views,
            _qualified(SPREADSHEET_NS, "workbookView"),
            {"activeTab": "1", "firstSheet": "0"},
        )
    sheets = ET.SubElement(root, _qualified(SPREADSHEET_NS, "sheets"))
    ET.SubElement(
        sheets,
        _qualified(SPREADSHEET_NS, "sheet"),
        {"name": "Issues", "sheetId": "1", _qualified(REL_NS, "id"): "rId1"},
    )
    ET.SubElement(
        sheets,
        _qualified(SPREADSHEET_NS, "sheet"),
        {"name": "Summary", "sheetId": "2", _qualified(REL_NS, "id"): "rId2"},
    )
    if include_internal_dtd:
        extensions = ET.SubElement(root, _qualified(SPREADSHEET_NS, "extLst"))
        extension = ET.SubElement(
            extensions,
            _qualified(SPREADSHEET_NS, "ext"),
            {"uri": "urn:synthetic:dtd-test"},
        )
        payload = ET.SubElement(extension, "{urn:synthetic:dtd-test}payload")
        payload.text = "DTD_ENTITY_REFERENCE_SENTINEL"

    workbook_xml = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if not include_internal_dtd:
        return workbook_xml
    declaration_end = workbook_xml.index(b"?>") + 2
    compact_doctype = b'''\n<!DOCTYPE workbook [
<!ENTITY level1 "ok">
<!ENTITY level2 "&level1;&level1;">
<!ENTITY level3 "&level2;&level2;">
<!ENTITY level4 "&level3;&level3;">
]>'''
    workbook_xml = workbook_xml[:declaration_end] + compact_doctype + workbook_xml[declaration_end:]
    return workbook_xml.replace(b"DTD_ENTITY_REFERENCE_SENTINEL", b"&level4;")


def _write_streaming_xml_part(
    workbook: zipfile.ZipFile,
    part_name: str,
    payload_bytes: int,
) -> None:
    chunk = b"x" * MEBIBYTE
    with workbook.open(part_name, "w", force_zip64=True) as xml_part:
        xml_part.write(b'<?xml version="1.0" encoding="UTF-8"?><oversized>')
        remaining = payload_bytes
        while remaining:
            size = min(remaining, len(chunk))
            xml_part.write(chunk[:size])
            remaining -= size
        xml_part.write(b"</oversized>")


def write_workbook(
    path: Path,
    *,
    hidden_rows: set[int] | None = None,
    hidden_columns: set[str] | None = None,
    zero_width_columns: set[str] | None = None,
    default_column_width: int | None = None,
    default_row_hidden: bool = False,
    populated_row_visible_override: str | None = None,
    issue_tab_selected: bool = False,
    include_workbook_view: bool = True,
    include_workbook_internal_dtd: bool = False,
    include_summary_sheet_view: bool = True,
    duplicate_workbook_part: bool = False,
    duplicate_issue_worksheet_part: bool = False,
    oversized_xml_payload_bytes: int | None = None,
    shared_string_issue_ids: bool = False,
    shared_string_index_override: int | None = None,
    formula_cache_overrides: dict[str, object] | None = None,
    string_formula_caches: set[str] | None = None,
    static_formula_cells: set[str] | None = None,
    additional_formula_cells: dict[str, tuple[str, str, object]] | None = None,
    lose_leading_zero: bool = False,
) -> None:
    hidden_rows = hidden_rows or set()
    hidden_columns = hidden_columns or set()
    zero_width_columns = zero_width_columns or set()
    formula_cache_overrides = formula_cache_overrides or {}
    string_formula_caches = string_formula_caches or set()
    static_formula_cells = static_formula_cells or set()
    additional_formula_cells = additional_formula_cells or {}
    shared_string_values: list[str] = []
    if shared_string_issue_ids:
        with CSV_FIXTURE.open(newline="", encoding="utf-8") as csv_file:
            shared_string_values = [issue["Issue ID"] for issue in csv.DictReader(csv_file)]
    workbook_xml = _workbook_xml(
        include_workbook_view=include_workbook_view,
        include_internal_dtd=include_workbook_internal_dtd,
    )
    issue_sheet_xml = _issues_sheet_xml(
        hidden_rows=hidden_rows,
        hidden_columns=hidden_columns,
        zero_width_columns=zero_width_columns,
        default_column_width=default_column_width,
        default_row_hidden=default_row_hidden,
        populated_row_visible_override=populated_row_visible_override,
        shared_string_issue_ids=shared_string_issue_ids,
        shared_string_index_override=shared_string_index_override,
        lose_leading_zero=lose_leading_zero,
        tab_selected=issue_tab_selected,
    )
    summary_sheet_xml = _summary_sheet_xml(
        include_sheet_view=include_summary_sheet_view,
        formula_cache_overrides=formula_cache_overrides,
        string_formula_caches=string_formula_caches,
        static_formula_cells=static_formula_cells,
        additional_formula_cells=additional_formula_cells,
    )
    shared_strings_content_type = ""
    shared_strings_relationship = ""
    shared_strings_xml = None
    if shared_string_issue_ids:
        shared_strings_content_type = f'''\n  <Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/>'''
        shared_strings_relationship = f'''\n  <Relationship Id="rId4" Type="{REL_NS}/sharedStrings" Target="sharedStrings.xml"/>'''
        shared_strings_xml = _shared_strings_xml(shared_string_values)
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CONTENT_TYPES_NS}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>{shared_strings_content_type}
</Types>'''.encode()
    package_relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{REL_NS}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''.encode()
    workbook_relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="{REL_NS}/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="{REL_NS}/styles" Target="styles.xml"/>{shared_strings_relationship}
</Relationships>'''.encode()
    styles = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="{SPREADSHEET_NS}">
  <fonts count="1"><font><name val="Calibri"/><sz val="11"/></font></fonts>
  <fills count="2">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/></cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
  <tableStyles count="0" defaultTableStyle="TableStyleMedium2" defaultPivotStyle="PivotStyleLight16"/>
</styleSheet>'''.encode()

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as workbook:
        workbook.writestr("[Content_Types].xml", content_types)
        workbook.writestr("_rels/.rels", package_relationships)
        workbook.writestr("xl/workbook.xml", workbook_xml)
        if duplicate_workbook_part:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                workbook.writestr("xl/workbook.xml", workbook_xml)
        workbook.writestr("xl/_rels/workbook.xml.rels", workbook_relationships)
        workbook.writestr("xl/styles.xml", styles)
        if shared_strings_xml is not None:
            workbook.writestr("xl/sharedStrings.xml", shared_strings_xml)
        workbook.writestr("xl/worksheets/sheet1.xml", issue_sheet_xml)
        if duplicate_issue_worksheet_part:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                workbook.writestr("xl/worksheets/sheet1.xml", issue_sheet_xml)
        workbook.writestr("xl/worksheets/sheet2.xml", summary_sheet_xml)
        if oversized_xml_payload_bytes is not None:
            _write_streaming_xml_part(
                workbook,
                "xl/oversized.xml",
                oversized_xml_payload_bytes,
            )


def _patch_zip_member_metadata(
    path: Path,
    member_name: str,
    *,
    encrypted: bool = False,
    compression_method: int | None = None,
) -> None:
    archive = bytearray(path.read_bytes())
    end_record = archive.rfind(b"PK\x05\x06")
    if end_record < 0:
        raise AssertionError("synthetic ZIP has no end-of-central-directory record")

    entry_count = struct.unpack_from("<H", archive, end_record + 10)[0]
    central_offset = struct.unpack_from("<I", archive, end_record + 16)[0]
    member_bytes = member_name.encode("utf-8")
    cursor = central_offset
    found = False

    for _ in range(entry_count):
        if archive[cursor : cursor + 4] != b"PK\x01\x02":
            raise AssertionError("synthetic ZIP has an invalid central-directory record")
        name_length, extra_length, comment_length = struct.unpack_from(
            "<HHH",
            archive,
            cursor + 28,
        )
        name_start = cursor + 46
        name_end = name_start + name_length
        if archive[name_start:name_end] == member_bytes:
            local_offset = struct.unpack_from("<I", archive, cursor + 42)[0]
            if archive[local_offset : local_offset + 4] != b"PK\x03\x04":
                raise AssertionError("synthetic ZIP has an invalid local-file header")
            if encrypted:
                central_flags = struct.unpack_from("<H", archive, cursor + 8)[0]
                local_flags = struct.unpack_from("<H", archive, local_offset + 6)[0]
                struct.pack_into("<H", archive, cursor + 8, central_flags | 0x0001)
                struct.pack_into("<H", archive, local_offset + 6, local_flags | 0x0001)
            if compression_method is not None:
                struct.pack_into("<H", archive, cursor + 10, compression_method)
                struct.pack_into("<H", archive, local_offset + 8, compression_method)
            found = True
            break
        cursor = name_end + extra_length + comment_length

    if not found:
        raise AssertionError(f"synthetic ZIP member not found: {member_name}")
    path.write_bytes(archive)


def write_fake_libreoffice(
    directory: Path,
    *,
    probe_exit: int = 0,
    convert_exit: int = 0,
    create_pdf: bool = True,
) -> Path:
    if os.name == "nt":
        executable = directory / "libreoffice.cmd"
        create_pdf_command = (
            'for %%F in ("%input%") do echo %%PDF-1.4 synthetic renderer output>"%outdir%\\%%~nF.pdf"'
            if create_pdf
            else "rem do not create a PDF"
        )
        executable.write_text(
            f'''@echo off
if "%~1"=="--version" (
  echo LibreOffice synthetic 1.0
  exit /b {probe_exit}
)
set "outdir="
set "input="
:next_argument
if "%~1"=="" goto convert
if "%~1"=="--outdir" (
  set "outdir=%~2"
  shift
  shift
  goto next_argument
)
if /I "%~x1"==".xlsx" set "input=%~1"
shift
goto next_argument
:convert
if not "{convert_exit}"=="0" exit /b {convert_exit}
{create_pdf_command}
exit /b 0
''',
            encoding="utf-8",
        )
        return executable

    executable = directory / "libreoffice"
    pdf_write = (
        'printf \'%s\\n\' \'%PDF-1.4 synthetic renderer output\' > "$outdir/${input_name%.xlsx}.pdf"'
        if create_pdf
        else ":"
    )
    executable.write_text(
        f'''#!/bin/sh
if [ "$1" = "--version" ]; then
  printf '%s\n' 'LibreOffice synthetic 1.0'
  exit {probe_exit}
fi
outdir=''
input=''
while [ "$#" -gt 0 ]; do
  case "$1" in
    --outdir)
      shift
      outdir=$1
      ;;
    *.xlsx)
      input=$1
      ;;
  esac
  shift
done
if [ {convert_exit} -ne 0 ]; then
  exit {convert_exit}
fi
input_name=${{input##*/}}
{pdf_write}
exit 0
''',
        encoding="utf-8",
    )
    executable.chmod(0o755)
    return executable


def renderer_environment(renderer_directory: Path) -> dict[str, str]:
    environment = dict(os.environ)
    environment["PATH"] = str(renderer_directory) + os.pathsep + environment.get("PATH", "")
    return environment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fixture_contract_payload() -> tuple[dict, dict]:
    contract = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    preflight = json.loads(PREFLIGHT_FIXTURE.read_text(encoding="utf-8"))
    for source in preflight["source_artifacts"]:
        source_path = (PREFLIGHT_FIXTURE.parent / source["path"]).resolve()
        source["path"] = str(source_path)
        source["sha256"] = sha256(source_path)
    contract["csv"]["path"] = str(CSV_FIXTURE)
    return contract, preflight


def write_fixture_contract(directory: Path) -> Path:
    contract, preflight = fixture_contract_payload()
    preflight_path = directory / "fixture-preflight-snapshot.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "fixture-artifact-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_runtime_contract(directory: Path, source_csv: Path, seed_workbook: Path) -> Path:
    contract = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    preflight_fixture = FIXTURES_DIR / contract["preflight_snapshot"]["path"]
    preflight = json.loads(preflight_fixture.read_text(encoding="utf-8"))

    snapshots_directory = directory / "snapshots" / "nested"
    snapshots_directory.mkdir(parents=True)
    preflight_path = snapshots_directory / "runtime-preflight-snapshot.json"
    preflight["source_artifacts"] = [
        {"path": f"../../{source_csv.name}", "sha256": sha256(source_csv)},
        {"path": f"../../{seed_workbook.name}", "sha256": sha256(seed_workbook)},
    ]
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contracts_directory = directory / "contracts"
    contracts_directory.mkdir()
    contract["csv"]["path"] = f"../{source_csv.name}"
    contract["preflight_snapshot"]["path"] = f"../snapshots/nested/{preflight_path.name}"
    contract_path = contracts_directory / "runtime-artifact-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_summary_sheet(directory: Path, summary_sheet: str) -> Path:
    contract, preflight = fixture_contract_payload()
    contract["mapping"]["summary"]["sheet"] = summary_sheet
    preflight_path = directory / "summary-sheet-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "summary-sheet-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_formula_sheet(
    directory: Path,
    *,
    formula_name: str,
    formula_sheet: str,
) -> Path:
    contract, preflight = fixture_contract_payload()
    preflight["formula_cells"][formula_name]["sheet"] = formula_sheet
    preflight_path = directory / "formula-sheet-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "formula-sheet-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_formula_text(
    directory: Path,
    *,
    formula_name: str,
    formula: str,
) -> Path:
    contract, preflight = fixture_contract_payload()
    preflight["formula_cells"][formula_name]["formula"] = formula
    preflight_path = directory / "formula-text-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "formula-text-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_expected_issue_ids(
    directory: Path,
    expected_issue_ids: list[str],
) -> Path:
    contract, preflight = fixture_contract_payload()
    preflight["expected_issue_ids"] = expected_issue_ids
    preflight_path = directory / "expected-issue-ids-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "expected-issue-ids-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_additional_formula(
    directory: Path,
    *,
    name: str,
    cell: str,
    formula: str,
    cached_value: object,
) -> Path:
    contract, preflight = fixture_contract_payload()
    preflight["formula_cells"][name] = {
        "sheet": "Summary",
        "cell": cell,
        "formula": formula,
        "cached_value": cached_value,
    }
    preflight_path = directory / "additional-formula-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "additional-formula-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def rewrite_zip_member(path: Path, member_name: str, replacement: bytes) -> None:
    replacement_path = path.with_suffix(".rewritten.xlsx")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        replacement_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as destination:
        for entry in source.infolist():
            destination.writestr(
                entry,
                replacement if entry.filename == member_name else source.read(entry.filename),
            )
    replacement_path.replace(path)


def add_zip_member(path: Path, member_name: str, content: bytes) -> None:
    replacement_path = path.with_suffix(".extended.xlsx")
    with zipfile.ZipFile(path, "r") as source, zipfile.ZipFile(
        replacement_path,
        "w",
        compression=zipfile.ZIP_DEFLATED,
    ) as destination:
        for entry in source.infolist():
            destination.writestr(entry, source.read(entry.filename))
        destination.writestr(member_name, content)
    replacement_path.replace(path)


def write_contract_with_preservation(
    directory: Path,
    source_workbook: Path,
    *,
    protected_sheets: list[str] | None = None,
    preserve_rule_comments: bool = False,
    forbidden_drawing_names: list[str] | None = None,
) -> Path:
    contract, preflight = fixture_contract_payload()
    preflight["source_artifacts"].append(
        {"path": str(source_workbook), "sha256": sha256(source_workbook)},
    )
    preflight["preservation"] = {
        "source_workbook": str(source_workbook),
        "protected_sheets": protected_sheets or [],
        "preserve_rule_comments": preserve_rule_comments,
        "forbidden_drawing_names": forbidden_drawing_names or [],
    }
    preflight_path = directory / "preservation-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")
    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "preservation-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


class ArtifactValidationCliTests(unittest.TestCase):
    maxDiff = None

    def assert_report_schema(self, report) -> None:
        self.assertEqual(
            ["schema_version", "outcome", "artifact", "layers"],
            list(report),
        )
        self.assertIsInstance(report["schema_version"], int)
        self.assertIsInstance(report["outcome"], str)
        self.assertIsInstance(report["artifact"], dict)
        self.assertIsInstance(report["layers"], dict)
        self.assertEqual(
            ["data_correctness", "visibility", "formula_cache", "rendering"],
            list(report["layers"]),
        )
        expected_layer_keys = ["heading", "status", "summary", "evidence", "reasons"]
        for layer_name, layer in report["layers"].items():
            self.assertEqual(expected_layer_keys, list(layer))
            self.assertIsInstance(layer["heading"], str)
            self.assertIsInstance(layer["status"], str)
            self.assertIsInstance(layer["summary"], dict)
            self.assertEqual(
                ["checks", "passed", "failed", "not_run"],
                list(layer["summary"]),
            )
            for count in layer["summary"].values():
                self.assertIs(type(count), int)
            self.assertIsInstance(layer["evidence"], list)
            for evidence in layer["evidence"]:
                self.assertIsInstance(evidence, dict)
            self.assertIsInstance(layer["reasons"], list)
            for reason in layer["reasons"]:
                self.assertIsInstance(reason, str)
            allowed_statuses = {"PASS", "FAIL", "NOT RUN"} if layer_name == "rendering" else {"PASS", "FAIL"}
            self.assertIn(layer["status"], allowed_statuses)

    def run_validator(
        self,
        artifact: Path,
        *,
        contract: Path = CONTRACT_FIXTURE,
        renderer: str = "none",
        env: dict[str, str] | None = None,
        timeout_seconds: float | None = None,
        visual_verdict: str | None = None,
    ):
        if contract == CONTRACT_FIXTURE:
            contract = write_fixture_contract(artifact.parent)
        command = [
            sys.executable,
            str(VALIDATOR),
            str(artifact),
            "--contract",
            str(contract),
            "--renderer",
            renderer,
        ]
        if visual_verdict is not None:
            command.extend(["--visual-verdict", visual_verdict])
        result = subprocess.run(
            command,
            cwd=SKILL_DIR,
            env=env,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
        self.assertTrue(
            result.stdout.strip(),
            f"validator emitted no JSON on stdout; exit={result.returncode}; stderr={result.stderr!r}",
        )
        try:
            report = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            self.fail(f"validator stdout is not JSON: {error}; stdout={result.stdout!r}")
        self.assert_report_schema(report)
        return result, report

    def assert_layer_failure(
        self,
        result,
        report,
        layer_name: str,
        expected_check: str | tuple[str, ...],
    ):
        layer = report["layers"][layer_name]
        expected_checks = (expected_check,) if isinstance(expected_check, str) else expected_check
        matching_failures = [
            evidence
            for evidence in layer["evidence"]
            if evidence.get("check") in expected_checks and evidence.get("status") == "FAIL"
        ]
        self.assertTrue(
            matching_failures,
            json.dumps(layer, ensure_ascii=False, indent=2),
        )
        self.assertEqual("FAIL", layer["status"])
        self.assertTrue(layer["reasons"])
        self.assertEqual("FAIL", report["outcome"])
        self.assertEqual(1, result.returncode, result.stderr)
        return matching_failures

    def test_default_template_has_expected_seed_sheets_and_rule_comments(self):
        with zipfile.ZipFile(DEFAULT_TEMPLATE) as workbook:
            workbook_root = ET.fromstring(workbook.read("xl/workbook.xml"))
            sheet_names = [
                sheet.get("name")
                for sheet in workbook_root.findall(
                    f"{{{SPREADSHEET_NS}}}sheets/{{{SPREADSHEET_NS}}}sheet",
                )
            ]
            rules = set()
            drawing_names = []
            for part_name in workbook.namelist():
                if part_name.startswith("xl/comments") or part_name.startswith(
                    "xl/threadedComments/",
                ):
                    root = ET.fromstring(workbook.read(part_name))
                    for element in root.iter():
                        if element.tag.rsplit("}", 1)[-1] not in {"comment", "threadedComment"}:
                            continue
                        payload = "".join(element.itertext()).strip()
                        if "MANTIS_RULE_V1" in payload:
                            rules.add((element.get("ref", ""), payload))
                if part_name.startswith("xl/drawings/") and part_name.endswith(".xml"):
                    root = ET.fromstring(workbook.read(part_name))
                    drawing_names.extend(
                        element.get("name")
                        for element in root.iter()
                        if element.get("name")
                    )

        self.assertEqual(["概要", "問題單清單", "過版調整"], sheet_names)
        self.assertEqual(20, len(rules))
        self.assertNotIn("Text Box 21", drawing_names)

    def test_valid_artifact_with_renderer_none_is_partial_and_has_stable_schema(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "validated-output.xlsx"
            write_workbook(artifact)

            result, report = self.run_validator(artifact)

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual(1, report["schema_version"])
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "NOT RUN"],
            [layer["status"] for layer in report["layers"].values()],
        )

    def test_valid_shared_string_issue_ids_remain_partial(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "shared-string-issue-ids.xlsx"
            write_workbook(artifact, shared_string_issue_ids=True)
            with zipfile.ZipFile(artifact) as workbook:
                names = set(workbook.namelist())
                content_types = workbook.read("[Content_Types].xml")
                relationships = workbook.read("xl/_rels/workbook.xml.rels")
                issue_sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            first_issue_id = issue_sheet.find(
                f".//{{{SPREADSHEET_NS}}}c[@r='A2']",
            )
            self.assertIn("xl/sharedStrings.xml", names)
            self.assertIn(b"sharedStrings.xml", content_types)
            self.assertIn(b"sharedStrings", relationships)
            self.assertIsNotNone(first_issue_id)
            self.assertEqual("s", first_issue_id.get("t"))

            result, report = self.run_validator(artifact)

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "NOT RUN"],
            [layer["status"] for layer in report["layers"].values()],
        )

    def test_negative_shared_string_index_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "negative-shared-string-index.xlsx"
            write_workbook(
                artifact,
                shared_string_issue_ids=True,
                shared_string_index_override=-1,
            )

            result, report = self.run_validator(artifact)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        self.assertNotIn("traceback", result.stderr.lower())
        failure_details = json.dumps(failures, ensure_ascii=False).lower()
        self.assertIn("shared string", failure_details)
        self.assertIn("-1", failure_details)
        self.assertIn("a2", failure_details)

    def test_shared_string_index_equal_to_table_length_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "past-end-shared-string-index.xlsx"
            write_workbook(
                artifact,
                shared_string_issue_ids=True,
                shared_string_index_override=44,
            )

            result, report = self.run_validator(artifact)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        self.assertNotIn("traceback", result.stderr.lower())
        failure_details = json.dumps(failures, ensure_ascii=False).lower()
        self.assertIn("shared string", failure_details)
        self.assertIn("44", failure_details)
        self.assertIn("a2", failure_details)

    def test_workbook_internal_dtd_and_entity_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "workbook-with-internal-dtd.xlsx"
            write_workbook(artifact, include_workbook_internal_dtd=True)

            started = time.monotonic()
            result, report = self.run_validator(artifact, timeout_seconds=5)
            elapsed = time.monotonic() - started

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        self.assertLess(elapsed, 5)
        rejection = json.dumps(
            {
                "failures": failures,
                "reasons": report["layers"]["data_correctness"]["reasons"],
            },
            ensure_ascii=False,
        ).lower()
        self.assertIn("dtd", rejection)
        self.assertIn("entity", rejection)
        self.assertRegex(rejection, r"not allowed|forbidden|prohibit|不允許|禁止")

    def test_duplicate_workbook_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "duplicate-workbook-part.xlsx"
            write_workbook(artifact, duplicate_workbook_part=True)

            result, report = self.run_validator(artifact)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        failure_details = json.dumps(failures, ensure_ascii=False).lower()
        self.assertIn("duplicate", failure_details)
        self.assertIn("xl/workbook.xml", failure_details)

    def test_duplicate_issue_worksheet_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "duplicate-worksheet-part.xlsx"
            write_workbook(artifact, duplicate_issue_worksheet_part=True)

            result, report = self.run_validator(artifact)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        failure_details = json.dumps(failures, ensure_ascii=False).lower()
        self.assertIn("duplicate", failure_details)
        self.assertIn("xl/worksheets/sheet1.xml", failure_details)

    def test_encrypted_required_workbook_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "encrypted-workbook-part.xlsx"
            write_workbook(artifact)
            _patch_zip_member_metadata(
                artifact,
                "xl/workbook.xml",
                encrypted=True,
            )
            with zipfile.ZipFile(artifact) as workbook:
                workbook_part = workbook.getinfo("xl/workbook.xml")
            self.assertTrue(workbook_part.flag_bits & 0x0001)

            result, report = self.run_validator(artifact)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        self.assertNotIn("traceback", result.stderr.lower())
        failure_details = json.dumps(failures, ensure_ascii=False).lower()
        self.assertIn("encrypted", failure_details)
        self.assertIn("xl/workbook.xml", failure_details)

    def test_unsupported_compression_on_required_workbook_part_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "unsupported-compression-workbook-part.xlsx"
            write_workbook(artifact)
            _patch_zip_member_metadata(
                artifact,
                "xl/workbook.xml",
                compression_method=99,
            )
            with zipfile.ZipFile(artifact) as workbook:
                workbook_part = workbook.getinfo("xl/workbook.xml")
            self.assertEqual(99, workbook_part.compress_type)

            result, report = self.run_validator(artifact)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        self.assertNotIn("traceback", result.stderr.lower())
        failure_details = json.dumps(failures, ensure_ascii=False).lower()
        self.assertIn("compression", failure_details)
        self.assertIn("unsupported", failure_details)
        self.assertIn("xl/workbook.xml", failure_details)

    def test_highly_compressed_xml_over_uncompressed_limit_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "oversized-compressed-xml-part.xlsx"
            write_workbook(
                artifact,
                oversized_xml_payload_bytes=64 * MEBIBYTE + 1,
            )
            with zipfile.ZipFile(artifact) as workbook:
                oversized = workbook.getinfo("xl/oversized.xml")
            self.assertGreater(oversized.file_size, 64 * MEBIBYTE)
            self.assertLess(oversized.compress_size, MEBIBYTE)

            started = time.monotonic()
            result, report = self.run_validator(artifact, timeout_seconds=10)
            elapsed = time.monotonic() - started

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "validation_prerequisite",
        )
        self.assertLess(elapsed, 10)
        self.assertIn(
            "xl/oversized.xml",
            json.dumps(failures, ensure_ascii=False),
        )

    def test_nonexistent_confirmed_summary_sheet_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            artifact = directory / "bogus-summary-mapping.xlsx"
            write_workbook(artifact)
            contract = write_contract_with_summary_sheet(directory, "BogusSummary")

            result, report = self.run_validator(artifact, contract=contract)

        failed_checks = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "confirmed_summary_sheet",
        )
        rejection_details = json.dumps(
            {
                "failed_checks": failed_checks,
                "reasons": [
                    reason
                    for layer in report["layers"].values()
                    for reason in layer["reasons"]
                ],
            },
            ensure_ascii=False,
        )
        self.assertIn("BogusSummary", rejection_details)

    def test_formula_cell_outside_confirmed_summary_sheet_fails_formula_cache(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            artifact = directory / "formula-outside-confirmed-summary.xlsx"
            write_workbook(artifact)
            contract = write_contract_with_formula_sheet(
                directory,
                formula_name="in_progress",
                formula_sheet="Issues",
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            "confirmed_formula_sheet_mapping",
        )
        failed_formula_checks = [
            evidence
            for evidence in report["layers"]["formula_cache"]["evidence"]
            if evidence.get("status") == "FAIL"
        ]
        self.assertIn(
            "Issues",
            json.dumps(failed_formula_checks, ensure_ascii=False),
        )

    def test_formula_contract_with_double_equals_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            artifact = directory / "double-equals-formula-contract.xlsx"
            write_workbook(artifact)
            contract = write_contract_with_formula_text(
                directory,
                formula_name="in_progress",
                formula='==COUNTIF(Issues!$B$2:$B$45,"IN_PROGRESS")',
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            ("formula:in_progress", "validation_prerequisite"),
        )

    def test_additional_confirmed_formula_with_cached_value_is_supported(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            formula = "(B2-29)/29"
            artifact = directory / "additional-formula.xlsx"
            write_workbook(
                artifact,
                additional_formula_cells={"in_progress_change": ("B7", formula, 0)},
            )
            contract = write_contract_with_additional_formula(
                directory,
                name="in_progress_change",
                cell="B7",
                formula=formula,
                cached_value=0,
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        formula_layer = report["layers"]["formula_cache"]
        self.assertEqual("PASS", formula_layer["status"])
        self.assertTrue(
            any(
                evidence["check"] == "cached_value:in_progress_change"
                and evidence["status"] == "PASS"
                for evidence in formula_layer["evidence"]
            ),
        )

    def test_changed_protected_sheet_semantics_fail_data_correctness(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_workbook = directory / "source.xlsx"
            artifact = directory / "artifact.xlsx"
            write_workbook(source_workbook)
            write_workbook(artifact)
            with zipfile.ZipFile(artifact) as workbook:
                summary_xml = workbook.read("xl/worksheets/sheet2.xml")
            rewrite_zip_member(
                artifact,
                "xl/worksheets/sheet2.xml",
                summary_xml.replace(b">Statistic<", b">Changed<", 1),
            )
            contract = write_contract_with_preservation(
                directory,
                source_workbook,
                protected_sheets=["Summary"],
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "protected_sheet_semantics:Summary",
        )

    def test_matching_protected_sheet_semantics_remain_valid(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_workbook = directory / "source.xlsx"
            artifact = directory / "artifact.xlsx"
            write_workbook(source_workbook)
            write_workbook(artifact)
            contract = write_contract_with_preservation(
                directory,
                source_workbook,
                protected_sheets=["Summary"],
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertTrue(
            any(
                evidence["check"] == "protected_sheet_semantics:Summary"
                and evidence["status"] == "PASS"
                for evidence in report["layers"]["data_correctness"]["evidence"]
            ),
        )

    def test_lost_versioned_rule_comment_fails_data_correctness(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_workbook = directory / "source-with-rule-comment.xlsx"
            artifact = directory / "artifact-without-rule-comment.xlsx"
            write_workbook(source_workbook)
            write_workbook(artifact)
            add_zip_member(
                source_workbook,
                "xl/comments1.xml",
                b'''<?xml version="1.0" encoding="UTF-8"?>
<comments xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <commentList><comment ref="E3"><text><t>MANTIS_RULE_V1:${in_progress}</t></text></comment></commentList>
</comments>''',
            )
            contract = write_contract_with_preservation(
                directory,
                source_workbook,
                preserve_rule_comments=True,
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "versioned_rule_comments",
        )

    def test_confirmed_forbidden_text_box_fails_data_correctness(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_workbook = directory / "source.xlsx"
            artifact = directory / "artifact-with-text-box.xlsx"
            write_workbook(source_workbook)
            write_workbook(artifact)
            add_zip_member(
                artifact,
                "xl/drawings/drawing1.xml",
                b'''<?xml version="1.0" encoding="UTF-8"?>
<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing">
  <xdr:twoCellAnchor><xdr:sp><xdr:nvSpPr><xdr:cNvPr id="21" name="Text Box 21"/></xdr:nvSpPr></xdr:sp></xdr:twoCellAnchor>
</xdr:wsDr>''',
            )
            contract = write_contract_with_preservation(
                directory,
                source_workbook,
                forbidden_drawing_names=["Text Box 21"],
            )

            result, report = self.run_validator(artifact, contract=contract)

        self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "forbidden_drawing_names",
        )

    def test_renderer_auto_with_confirmed_visual_verdict_passes_all_layers(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            renderer_directory = directory / "renderer"
            renderer_directory.mkdir()
            write_fake_libreoffice(renderer_directory)
            artifact = directory / "renderer-pass.xlsx"
            write_workbook(artifact)

            result, report = self.run_validator(
                artifact,
                renderer="auto",
                env=renderer_environment(renderer_directory),
                visual_verdict="pass",
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PASS", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "PASS"],
            [layer["status"] for layer in report["layers"].values()],
        )

    def test_renderer_pdf_export_without_visual_verdict_is_partial(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            renderer_directory = directory / "renderer"
            renderer_directory.mkdir()
            write_fake_libreoffice(renderer_directory)
            artifact = directory / "renderer-needs-visual-verdict.xlsx"
            write_workbook(artifact)

            result, report = self.run_validator(
                artifact,
                renderer="auto",
                env=renderer_environment(renderer_directory),
            )

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual("NOT RUN", report["layers"]["rendering"]["status"])
        self.assertTrue(
            any(
                evidence["check"] == "real_render" and evidence["status"] == "PASS"
                for evidence in report["layers"]["rendering"]["evidence"]
            ),
        )

    def test_renderer_probe_failure_fails_rendering(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            renderer_directory = directory / "renderer"
            renderer_directory.mkdir()
            write_fake_libreoffice(renderer_directory, probe_exit=7)
            artifact = directory / "renderer-probe-failure.xlsx"
            write_workbook(artifact)

            result, report = self.run_validator(
                artifact,
                renderer="auto",
                env=renderer_environment(renderer_directory),
            )

        self.assert_layer_failure(result, report, "rendering", "renderer_probe")

    def test_renderer_conversion_failure_fails_rendering(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            renderer_directory = directory / "renderer"
            renderer_directory.mkdir()
            write_fake_libreoffice(renderer_directory, convert_exit=8)
            artifact = directory / "renderer-conversion-failure.xlsx"
            write_workbook(artifact)

            result, report = self.run_validator(
                artifact,
                renderer="auto",
                env=renderer_environment(renderer_directory),
            )

        self.assert_layer_failure(result, report, "rendering", "real_render")

    def test_one_hidden_row_inside_updated_range_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "mixed-visible-and-hidden-rows.xlsx"
            write_workbook(artifact, hidden_rows={10})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "populated_issue_rows_visible",
        )

    def test_conflicting_tab_selected_sheet_view_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "conflicting-tab-selection.xlsx"
            write_workbook(artifact, issue_tab_selected=True)

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "conflicting_sheet_selection",
        )

    def test_zero_height_sheet_default_does_not_hide_explicit_populated_rows(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "explicit-rows-with-zero-height-default.xlsx"
            write_workbook(artifact, default_row_hidden=True)
            with zipfile.ZipFile(artifact) as workbook:
                issue_sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))
            sheet_format = issue_sheet.find(f"{{{SPREADSHEET_NS}}}sheetFormatPr")
            first_populated_row = issue_sheet.find(
                f".//{{{SPREADSHEET_NS}}}row[@r='2']",
            )
            self.assertIsNotNone(sheet_format)
            self.assertEqual("1", sheet_format.get("zeroHeight"))
            self.assertIsNotNone(first_populated_row)
            self.assertNotIn("hidden", first_populated_row.attrib)
            self.assertNotIn("ht", first_populated_row.attrib)

            result, report = self.run_validator(artifact)

        self.assertEqual(
            2,
            result.returncode,
            json.dumps(report, ensure_ascii=False, indent=2),
        )
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "NOT RUN"],
            [layer["status"] for layer in report["layers"].values()],
        )

    def test_zero_height_sheet_default_with_hidden_false_rows_remains_partial(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "visible-hidden-false-rows.xlsx"
            write_workbook(
                artifact,
                default_row_hidden=True,
                populated_row_visible_override="hidden",
            )

            result, report = self.run_validator(artifact)

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "NOT RUN"],
            [layer["status"] for layer in report["layers"].values()],
        )

    def test_zero_height_sheet_default_with_positive_height_rows_remains_partial(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "visible-positive-height-rows.xlsx"
            write_workbook(
                artifact,
                default_row_hidden=True,
                populated_row_visible_override="height",
            )

            result, report = self.run_validator(artifact)

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "NOT RUN"],
            [layer["status"] for layer in report["layers"].values()],
        )

    def test_hidden_required_column_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "hidden-required-column.xlsx"
            write_workbook(artifact, hidden_columns={"B"})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "required_columns_visible",
        )

    def test_zero_width_required_column_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "zero-width-required-column.xlsx"
            write_workbook(artifact, zero_width_columns={"C"})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "required_columns_visible",
        )

    def test_zero_default_column_width_without_overrides_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "zero-default-column-width.xlsx"
            write_workbook(artifact, default_column_width=0)

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "required_columns_visible",
        )

    def test_missing_workbook_view_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "missing-workbook-view.xlsx"
            write_workbook(artifact, include_workbook_view=False)

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "persisted_workbook_view",
        )

    def test_missing_expected_output_sheet_view_fails_visibility(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "missing-summary-sheet-view.xlsx"
            write_workbook(artifact, include_summary_sheet_view=False)

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "visibility",
            "persisted_sheet_view_selection",
        )

    def test_blank_formula_cache_fails_formula_cache_layer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "blank-formula-cache.xlsx"
            write_workbook(artifact, formula_cache_overrides={"pending_release": "blank"})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            "cached_value:pending_release",
        )

    def test_stale_formula_cache_fails_formula_cache_layer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "stale-formula-cache.xlsx"
            write_workbook(artifact, formula_cache_overrides={"resolved": 9})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            "cached_value:resolved",
        )

    def test_error_formula_cache_fails_formula_cache_layer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "error-formula-cache.xlsx"
            write_workbook(artifact, formula_cache_overrides={"total": "error"})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            "cached_value:total",
        )

    def test_numeric_text_formula_cache_fails_formula_cache_layer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "numeric-text-formula-cache.xlsx"
            write_workbook(artifact, string_formula_caches={"in_progress"})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            "cached_value:in_progress",
        )

    def test_formula_replaced_by_static_value_fails_formula_cache_layer(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "formula-replaced-by-static-value.xlsx"
            write_workbook(artifact, static_formula_cells={"unknown"})

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "formula_cache",
            "formula:unknown",
        )

    def test_lost_issue_id_leading_zero_fails_data_correctness(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            artifact = Path(temporary_directory) / "lost-leading-zero.xlsx"
            write_workbook(artifact, lose_leading_zero=True)

            result, report = self.run_validator(artifact)

        self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "issue_id_display_and_type",
        )

    def test_legacy_issue_id_in_expected_complete_set_fails_data_correctness(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            artifact = directory / "legacy-expected-issue-id.xlsx"
            write_workbook(artifact)
            expected_issue_ids = [f"{issue_id:06d}" for issue_id in range(1, 45)]
            expected_issue_ids[-1] = "000999"
            contract = write_contract_with_expected_issue_ids(directory, expected_issue_ids)

            result, report = self.run_validator(artifact, contract=contract)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "complete_issue_id_set",
        )
        failure_details = json.dumps(failures, ensure_ascii=False)
        self.assertIn("000044", failure_details)
        self.assertIn("000999", failure_details)

    def test_validation_does_not_modify_source_seed_or_pending_artifact(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_csv = directory / "source-issues.csv"
            shutil.copyfile(CSV_FIXTURE, source_csv)
            seed_workbook = directory / "seed.xlsx"
            write_workbook(seed_workbook)
            pending_artifact = directory / "pending-validation.xlsx"
            write_workbook(pending_artifact)
            contract = write_runtime_contract(directory, source_csv, seed_workbook)
            protected_paths = (source_csv, seed_workbook, pending_artifact)
            hashes_before = {path: sha256(path) for path in protected_paths}

            result, report = self.run_validator(pending_artifact, contract=contract)

            hashes_after = {path: sha256(path) for path in protected_paths}

        self.assertEqual(2, result.returncode, result.stderr)
        self.assertEqual("PARTIAL", report["outcome"])
        self.assertEqual(hashes_before, hashes_after)

    def test_changed_source_csv_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_csv = directory / "source-issues.csv"
            shutil.copyfile(CSV_FIXTURE, source_csv)
            seed_workbook = directory / "seed.xlsx"
            write_workbook(seed_workbook)
            pending_artifact = directory / "pending-validation.xlsx"
            write_workbook(pending_artifact)
            contract = write_runtime_contract(directory, source_csv, seed_workbook)
            with source_csv.open("ab") as source:
                source.write(b"\n")

            result, report = self.run_validator(pending_artifact, contract=contract)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "source_artifact_digest",
        )
        self.assertIn(source_csv.name, json.dumps(failures, ensure_ascii=False))

    def test_changed_seed_digest_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            directory = Path(temporary_directory)
            source_csv = directory / "source-issues.csv"
            shutil.copyfile(CSV_FIXTURE, source_csv)
            seed_workbook = directory / "seed.xlsx"
            write_workbook(seed_workbook)
            pending_artifact = directory / "pending-validation.xlsx"
            write_workbook(pending_artifact)
            contract = write_runtime_contract(directory, source_csv, seed_workbook)
            with seed_workbook.open("ab") as seed:
                seed.write(b"\x00")

            result, report = self.run_validator(pending_artifact, contract=contract)

        failures = self.assert_layer_failure(
            result,
            report,
            "data_correctness",
            "source_artifact_digest",
        )
        self.assertIn(seed_workbook.name, json.dumps(failures, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main(verbosity=2)
