#!/usr/bin/env python3
"""Artifact-level contract tests for ``scripts/validate_artifact.py``."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
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
    lose_leading_zero: bool,
) -> bytes:
    root, sheet_data = _sheet_root(active_cell="A1", include_sheet_view=True)
    if default_column_width is not None:
        sheet_format = ET.Element(
            _qualified(SPREADSHEET_NS, "sheetFormatPr"),
            {"defaultColWidth": str(default_column_width)},
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
    header = ET.SubElement(sheet_data, _qualified(SPREADSHEET_NS, "row"), {"r": "1"})
    for column, value in zip(("A", "B", "C"), ("Issue ID", "Status", "Summary")):
        _append_inline_cell(header, f"{column}1", value)

    with CSV_FIXTURE.open(newline="", encoding="utf-8") as csv_file:
        issues = list(csv.DictReader(csv_file))
    for excel_row, issue in enumerate(issues, start=2):
        attributes = {"r": str(excel_row)}
        if excel_row in hidden_rows:
            attributes["hidden"] = "1"
        row = ET.SubElement(sheet_data, _qualified(SPREADSHEET_NS, "row"), attributes)
        if lose_leading_zero and excel_row == 2:
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
) -> bytes:
    root, sheet_data = _sheet_root(
        active_cell="B2",
        include_sheet_view=include_sheet_view,
        tab_selected=True,
    )
    header = ET.SubElement(sheet_data, _qualified(SPREADSHEET_NS, "row"), {"r": "1"})
    _append_inline_cell(header, "A1", "Statistic")
    _append_inline_cell(header, "B1", "Value")

    for excel_row, (statistic, (cell_ref, formula, expected)) in enumerate(FORMULAS.items(), start=2):
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
    include_workbook_view: bool = True,
    include_workbook_internal_dtd: bool = False,
    include_summary_sheet_view: bool = True,
    duplicate_workbook_part: bool = False,
    duplicate_issue_worksheet_part: bool = False,
    oversized_xml_payload_bytes: int | None = None,
    formula_cache_overrides: dict[str, object] | None = None,
    string_formula_caches: set[str] | None = None,
    static_formula_cells: set[str] | None = None,
    lose_leading_zero: bool = False,
) -> None:
    hidden_rows = hidden_rows or set()
    hidden_columns = hidden_columns or set()
    zero_width_columns = zero_width_columns or set()
    formula_cache_overrides = formula_cache_overrides or {}
    string_formula_caches = string_formula_caches or set()
    static_formula_cells = static_formula_cells or set()
    workbook_xml = _workbook_xml(
        include_workbook_view=include_workbook_view,
        include_internal_dtd=include_workbook_internal_dtd,
    )
    issue_sheet_xml = _issues_sheet_xml(
        hidden_rows=hidden_rows,
        hidden_columns=hidden_columns,
        zero_width_columns=zero_width_columns,
        default_column_width=default_column_width,
        lose_leading_zero=lose_leading_zero,
    )
    summary_sheet_xml = _summary_sheet_xml(
        include_sheet_view=include_summary_sheet_view,
        formula_cache_overrides=formula_cache_overrides,
        string_formula_caches=string_formula_caches,
        static_formula_cells=static_formula_cells,
    )
    content_types = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="{CONTENT_TYPES_NS}">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
</Types>'''.encode()
    package_relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{REL_NS}/officeDocument" Target="xl/workbook.xml"/>
</Relationships>'''.encode()
    workbook_relationships = f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="{PACKAGE_REL_NS}">
  <Relationship Id="rId1" Type="{REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>
  <Relationship Id="rId2" Type="{REL_NS}/worksheet" Target="worksheets/sheet2.xml"/>
  <Relationship Id="rId3" Type="{REL_NS}/styles" Target="styles.xml"/>
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


def write_fake_libreoffice(
    directory: Path,
    *,
    probe_exit: int = 0,
    convert_exit: int = 0,
    create_pdf: bool = True,
) -> Path:
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
    environment["PATH"] = str(renderer_directory)
    return environment


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as artifact:
        for chunk in iter(lambda: artifact.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    contract = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    contract["mapping"]["summary"]["sheet"] = summary_sheet
    contract["csv"]["path"] = str(CSV_FIXTURE)
    contract["preflight_snapshot"]["path"] = str(PREFLIGHT_FIXTURE)
    contract_path = directory / "summary-sheet-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_formula_sheet(
    directory: Path,
    *,
    formula_name: str,
    formula_sheet: str,
) -> Path:
    preflight = json.loads(PREFLIGHT_FIXTURE.read_text(encoding="utf-8"))
    preflight["formula_cells"][formula_name]["sheet"] = formula_sheet
    for source in preflight["source_artifacts"]:
        source["path"] = str((PREFLIGHT_FIXTURE.parent / source["path"]).resolve())
    preflight_path = directory / "formula-sheet-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contract = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    contract["csv"]["path"] = str(CSV_FIXTURE)
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
    preflight = json.loads(PREFLIGHT_FIXTURE.read_text(encoding="utf-8"))
    preflight["formula_cells"][formula_name]["formula"] = formula
    for source in preflight["source_artifacts"]:
        source["path"] = str((PREFLIGHT_FIXTURE.parent / source["path"]).resolve())
    preflight_path = directory / "formula-text-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contract = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    contract["csv"]["path"] = str(CSV_FIXTURE)
    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "formula-text-contract.json"
    contract_path.write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    return contract_path


def write_contract_with_expected_issue_ids(
    directory: Path,
    expected_issue_ids: list[str],
) -> Path:
    preflight = json.loads(PREFLIGHT_FIXTURE.read_text(encoding="utf-8"))
    preflight["expected_issue_ids"] = expected_issue_ids
    for source in preflight["source_artifacts"]:
        source["path"] = str((PREFLIGHT_FIXTURE.parent / source["path"]).resolve())
    preflight_path = directory / "expected-issue-ids-preflight.json"
    preflight_path.write_text(json.dumps(preflight, indent=2) + "\n", encoding="utf-8")

    contract = json.loads(CONTRACT_FIXTURE.read_text(encoding="utf-8"))
    contract["csv"]["path"] = str(CSV_FIXTURE)
    contract["preflight_snapshot"]["path"] = str(preflight_path)
    contract_path = directory / "expected-issue-ids-contract.json"
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
    ):
        result = subprocess.run(
            [
                sys.executable,
                str(VALIDATOR),
                str(artifact),
                "--contract",
                str(contract),
                "--renderer",
                renderer,
            ],
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

    def test_renderer_auto_with_non_empty_pdf_passes_all_layers(self):
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
            )

        self.assertEqual(0, result.returncode, result.stderr)
        self.assertEqual("PASS", report["outcome"])
        self.assertEqual(
            ["PASS", "PASS", "PASS", "PASS"],
            [layer["status"] for layer in report["layers"].values()],
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
