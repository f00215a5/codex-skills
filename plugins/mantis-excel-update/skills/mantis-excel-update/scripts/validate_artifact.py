#!/usr/bin/env python3
"""Validate a closed, persisted Mantis workbook through its OOXML artifact."""

from __future__ import annotations

import argparse
from collections import Counter
import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Sequence
import xml.etree.ElementTree as ET
import zipfile


SCHEMA_VERSION = 1
EXIT_PASS = 0
EXIT_FAIL = 1
EXIT_PARTIAL = 2
EXIT_USAGE = 64

SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

EXPECTED_STATISTIC_KEYS = (
    "in_progress",
    "pending_release",
    "resolved",
    "unknown",
    "total",
)
STATUS_STATISTIC_KEYS = EXPECTED_STATISTIC_KEYS[:-1]

MAX_ZIP_ENTRIES = 10_000
MAX_UNCOMPRESSED_BYTES = 512 * 1024 * 1024
MAX_XML_BYTES = 64 * 1024 * 1024

CELL_RE = re.compile(r"^\$?([A-Za-z]+)\$?([1-9][0-9]*)$")
RANGE_RE = re.compile(
    r"^\$?([A-Za-z]+)\$?([1-9][0-9]*):\$?([A-Za-z]+)\$?([1-9][0-9]*)$"
)


class ValidationInputError(ValueError):
    """Raised when an input cannot define a safe, deterministic validation."""


class UsageParser(argparse.ArgumentParser):
    """Keep the PARTIAL result code distinct from command-line usage errors."""

    def error(self, message: str) -> None:
        self.print_usage(sys.stderr)
        self.exit(EXIT_USAGE, f"{self.prog}: error: {message}\n")


def qualified(namespace: str, name: str) -> str:
    return f"{{{namespace}}}{name}"


def spreadsheet_tag(name: str) -> str:
    return qualified(SPREADSHEET_NS, name)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_issue_id(value: str) -> str:
    stripped = value.strip()
    if stripped.isdecimal():
        return stripped.lstrip("0") or "0"
    return stripped


def formula_without_optional_prefix(value: str) -> str:
    """Remove at most one optional leading equals sign from a formula."""

    return value[1:] if value.startswith("=") else value


def json_object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValidationInputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        with path.open(encoding="utf-8-sig") as stream:
            value = json.load(stream, object_pairs_hook=json_object_without_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationInputError) as error:
        raise ValidationInputError(f"cannot read {label} {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValidationInputError(f"{label} must contain one JSON object: {path}")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ValidationInputError(
            f"{label}.schema_version must be {SCHEMA_VERSION}, got {value.get('schema_version')!r}"
        )
    return value


def require_object(parent: dict[str, Any], key: str, location: str) -> dict[str, Any]:
    value = parent.get(key)
    if not isinstance(value, dict):
        raise ValidationInputError(f"{location}.{key} must be an object")
    return value


def require_string(parent: dict[str, Any], key: str, location: str) -> str:
    value = parent.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValidationInputError(f"{location}.{key} must be a non-empty string")
    return value


def require_positive_int(parent: dict[str, Any], key: str, location: str) -> int:
    value = parent.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValidationInputError(f"{location}.{key} must be a positive integer")
    return value


def resolve_relative(base_file: Path, value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base_file.parent / path
    return path.resolve()


def column_number(letters: str) -> int:
    result = 0
    for character in letters.upper():
        if not "A" <= character <= "Z":
            raise ValidationInputError(f"invalid column letters: {letters!r}")
        result = result * 26 + ord(character) - ord("A") + 1
    return result


def column_letters(number: int) -> str:
    if number < 1:
        raise ValidationInputError(f"column number must be positive, got {number}")
    characters: list[str] = []
    while number:
        number, remainder = divmod(number - 1, 26)
        characters.append(chr(ord("A") + remainder))
    return "".join(reversed(characters))


def parse_cell_reference(reference: str) -> tuple[int, int]:
    match = CELL_RE.fullmatch(reference)
    if match is None:
        raise ValidationInputError(f"invalid A1 cell reference: {reference!r}")
    return column_number(match.group(1)), int(match.group(2))


@dataclass(frozen=True)
class CellRange:
    start_column: int
    start_row: int
    end_column: int
    end_row: int

    @classmethod
    def parse(cls, value: str) -> "CellRange":
        match = RANGE_RE.fullmatch(value)
        if match is None:
            raise ValidationInputError(f"invalid A1 range: {value!r}")
        start_column = column_number(match.group(1))
        start_row = int(match.group(2))
        end_column = column_number(match.group(3))
        end_row = int(match.group(4))
        if end_column < start_column or end_row < start_row:
            raise ValidationInputError(f"range must run top-left to bottom-right: {value!r}")
        return cls(start_column, start_row, end_column, end_row)

    def contains(self, column: int, row: int) -> bool:
        return (
            self.start_column <= column <= self.end_column
            and self.start_row <= row <= self.end_row
        )


@dataclass
class Evidence:
    check: str
    status: str
    source: str
    expected: Any
    actual: Any

    def as_dict(self) -> dict[str, Any]:
        return {
            "check": self.check,
            "status": self.status,
            "source": self.source,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class LayerResult:
    heading: str
    evidence: list[Evidence] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    forced_status: str | None = None

    def check(
        self,
        name: str,
        passed: bool,
        *,
        source: str,
        expected: Any,
        actual: Any,
        reason: str | None = None,
    ) -> None:
        status = "PASS" if passed else "FAIL"
        self.evidence.append(Evidence(name, status, source, expected, actual))
        if not passed:
            failure = reason or f"{name}: expected {expected!r}, got {actual!r}"
            if failure not in self.reasons:
                self.reasons.append(failure)

    def not_run(
        self,
        reason: str,
        *,
        source: str,
        actual: Any,
        check: str = "renderer_availability",
        expected: Any = "available read-only renderer",
    ) -> None:
        self.forced_status = "NOT RUN"
        self.evidence.append(
            Evidence(
                check,
                "NOT RUN",
                source,
                expected,
                actual,
            )
        )
        if reason not in self.reasons:
            self.reasons.append(reason)

    @property
    def status(self) -> str:
        if any(item.status == "FAIL" for item in self.evidence):
            return "FAIL"
        if self.forced_status == "NOT RUN":
            return "NOT RUN"
        if not self.evidence:
            return "FAIL"
        return "PASS"

    def as_dict(self) -> dict[str, Any]:
        counts = Counter(item.status for item in self.evidence)
        return {
            "heading": self.heading,
            "status": self.status,
            "summary": {
                "checks": len(self.evidence),
                "passed": counts["PASS"],
                "failed": counts["FAIL"],
                "not_run": counts["NOT RUN"],
            },
            "evidence": [item.as_dict() for item in self.evidence],
            "reasons": list(self.reasons),
        }


@dataclass(frozen=True)
class Cell:
    reference: str
    column: int
    row: int
    data_type: str | None
    value: str | None
    formula: str | None
    cached_value: str | None


@dataclass
class Sheet:
    name: str
    index: int
    state: str
    part_name: str
    root: ET.Element
    cells: dict[str, Cell]
    row_elements: dict[int, ET.Element]

    def cell(self, reference: str) -> Cell | None:
        return self.cells.get(reference.replace("$", "").upper())

    def row_element(self, row: int) -> ET.Element | None:
        return self.row_elements.get(row)

    def cells_in_row(self, row: int) -> list[Cell]:
        return sorted(
            (cell for cell in self.cells.values() if cell.row == row),
            key=lambda cell: cell.column,
        )


@dataclass
class WorkbookArtifact:
    path: Path
    workbook_root: ET.Element
    sheets: list[Sheet]

    def sheet(self, name: str) -> Sheet | None:
        return next((sheet for sheet in self.sheets if sheet.name == name), None)


def parse_xml(data: bytes, source: str) -> ET.Element:
    if len(data) > MAX_XML_BYTES:
        raise ValidationInputError(f"XML part exceeds {MAX_XML_BYTES} bytes: {source}")
    markup_without_encoding_nuls = data.replace(b"\x00", b"")
    if (
        b"<!DOCTYPE" in markup_without_encoding_nuls
        or b"<!ENTITY" in markup_without_encoding_nuls
    ):
        raise ValidationInputError(
            f"DTD and entity declarations are not allowed in OOXML parts: {source}"
        )
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ValidationInputError(f"invalid XML in {source}: {error}") from error


def ensure_xml_part_size(information: zipfile.ZipInfo) -> None:
    if information.file_size > MAX_XML_BYTES:
        raise ValidationInputError(
            f"XML part exceeds {MAX_XML_BYTES} bytes: {information.filename}"
        )


def read_xml_part(archive: zipfile.ZipFile, part_name: str) -> ET.Element:
    information = archive.getinfo(part_name)
    ensure_xml_part_size(information)
    try:
        with archive.open(information, "r") as stream:
            data = stream.read(MAX_XML_BYTES + 1)
    except RuntimeError as error:
        raise ValidationInputError(f"cannot read OOXML part {part_name}: {error}") from error
    return parse_xml(data, part_name)


def resolve_relationship_target(base_part: str, target: str) -> str:
    if not target or ":" in target.split("/", 1)[0]:
        raise ValidationInputError(f"unsupported relationship target: {target!r}")
    if target.startswith("/"):
        resolved = target.lstrip("/")
    else:
        resolved = posixpath.normpath(posixpath.join(posixpath.dirname(base_part), target))
    pure = PurePosixPath(resolved)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValidationInputError(f"relationship target escapes the package: {target!r}")
    return pure.as_posix()


def read_shared_strings(archive: zipfile.ZipFile, names: set[str]) -> list[str]:
    part = "xl/sharedStrings.xml"
    if part not in names:
        return []
    root = read_xml_part(archive, part)
    return [
        "".join(text.text or "" for text in item.iter(spreadsheet_tag("t")))
        for item in root.findall(spreadsheet_tag("si"))
    ]


def cell_text(element: ET.Element, shared_strings: Sequence[str]) -> str | None:
    data_type = element.get("t")
    if data_type == "inlineStr":
        inline = element.find(spreadsheet_tag("is"))
        if inline is None:
            return None
        return "".join(text.text or "" for text in inline.iter(spreadsheet_tag("t")))
    value = element.find(spreadsheet_tag("v"))
    if value is None or value.text is None:
        return None
    if data_type == "s":
        try:
            index = int(value.text)
        except ValueError as error:
            raise ValidationInputError(
                f"invalid shared string index {value.text!r} in {element.get('r')!r}"
            ) from error
        if not 0 <= index < len(shared_strings):
            raise ValidationInputError(
                f"invalid shared string index {value.text!r} in {element.get('r')!r}"
            )
        return shared_strings[index]
    return value.text


def read_sheet(
    archive: zipfile.ZipFile,
    *,
    name: str,
    index: int,
    state: str,
    part_name: str,
    shared_strings: Sequence[str],
) -> Sheet:
    root = read_xml_part(archive, part_name)
    cells: dict[str, Cell] = {}
    rows: dict[int, ET.Element] = {}
    sheet_data = root.find(spreadsheet_tag("sheetData"))
    if sheet_data is not None:
        previous_row = 0
        for row_element in sheet_data.findall(spreadsheet_tag("row")):
            raw_row = row_element.get("r")
            row_number = int(raw_row) if raw_row and raw_row.isdecimal() else previous_row + 1
            previous_row = row_number
            rows[row_number] = row_element
            previous_column = 0
            for cell_element in row_element.findall(spreadsheet_tag("c")):
                reference = (cell_element.get("r") or "").replace("$", "").upper()
                if reference:
                    column, cell_row = parse_cell_reference(reference)
                else:
                    column = previous_column + 1
                    cell_row = row_number
                    reference = f"{column_letters(column)}{cell_row}"
                previous_column = column
                formula_element = cell_element.find(spreadsheet_tag("f"))
                value_element = cell_element.find(spreadsheet_tag("v"))
                cells[reference] = Cell(
                    reference=reference,
                    column=column,
                    row=cell_row,
                    data_type=cell_element.get("t"),
                    value=cell_text(cell_element, shared_strings),
                    formula=formula_element.text if formula_element is not None else None,
                    cached_value=(
                        value_element.text if value_element is not None and value_element.text is not None else None
                    ),
                )
    return Sheet(name, index, state, part_name, root, cells, rows)


def read_workbook_artifact(path: Path) -> WorkbookArtifact:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            information = archive.infolist()
            if len(information) > MAX_ZIP_ENTRIES:
                raise ValidationInputError(
                    f"OOXML package has too many entries: {len(information)} > {MAX_ZIP_ENTRIES}"
                )
            total_size = sum(item.file_size for item in information)
            if total_size > MAX_UNCOMPRESSED_BYTES:
                raise ValidationInputError(
                    f"OOXML package is too large after decompression: {total_size} bytes"
                )
            filenames = [item.filename for item in information]
            duplicate_names = sorted(
                name for name, count in Counter(filenames).items() if count > 1
            )
            if duplicate_names:
                raise ValidationInputError(
                    f"OOXML package contains duplicate part names: {duplicate_names}"
                )
            for item in information:
                if item.filename.lower().endswith((".xml", ".rels")):
                    ensure_xml_part_size(item)
            names = set(filenames)
            required = {
                "[Content_Types].xml",
                "_rels/.rels",
                "xl/workbook.xml",
                "xl/_rels/workbook.xml.rels",
            }
            missing = sorted(required - names)
            if missing:
                raise ValidationInputError(f"OOXML package is missing required parts: {missing}")

            workbook_part = "xl/workbook.xml"
            workbook_root = read_xml_part(archive, workbook_part)
            relationships_root = read_xml_part(archive, "xl/_rels/workbook.xml.rels")
            relationship_targets: dict[str, str] = {}
            for relationship in relationships_root.findall(qualified(PACKAGE_REL_NS, "Relationship")):
                if relationship.get("TargetMode") == "External":
                    continue
                identifier = relationship.get("Id")
                target = relationship.get("Target")
                relation_type = relationship.get("Type", "")
                if identifier and target and relation_type.endswith("/worksheet"):
                    relationship_targets[identifier] = resolve_relationship_target(workbook_part, target)

            shared_strings = read_shared_strings(archive, names)
            sheets_element = workbook_root.find(spreadsheet_tag("sheets"))
            if sheets_element is None:
                raise ValidationInputError("workbook has no sheets collection")
            sheets: list[Sheet] = []
            for index, sheet_element in enumerate(sheets_element.findall(spreadsheet_tag("sheet"))):
                name = sheet_element.get("name")
                relation_id = sheet_element.get(qualified(OFFICE_REL_NS, "id"))
                if not name or not relation_id or relation_id not in relationship_targets:
                    raise ValidationInputError(
                        f"worksheet relationship cannot be resolved for sheet {name!r}"
                    )
                part_name = relationship_targets[relation_id]
                if part_name not in names:
                    raise ValidationInputError(
                        f"worksheet part for {name!r} is missing: {part_name}"
                    )
                sheets.append(
                    read_sheet(
                        archive,
                        name=name,
                        index=index,
                        state=sheet_element.get("state", "visible"),
                        part_name=part_name,
                        shared_strings=shared_strings,
                    )
                )
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValidationInputError(f"cannot reopen OOXML artifact {path}: {error}") from error
    return WorkbookArtifact(path, workbook_root, sheets)


def row_is_visible(sheet: Sheet, row: ET.Element | None) -> bool:
    if row is None:
        return False
    hidden = (row.get("hidden") or "").lower()
    if hidden in {"1", "true"}:
        return False
    raw_height = row.get("ht")
    if raw_height is not None:
        try:
            if Decimal(raw_height) <= 0:
                return False
        except InvalidOperation:
            return False
        return True
    sheet_format = sheet.root.find(spreadsheet_tag("sheetFormatPr"))
    if sheet_format is None:
        return True
    # zeroHeight is the default only for omitted rows; every row here is explicit.
    default_height = sheet_format.get("defaultRowHeight")
    if default_height is not None:
        try:
            if Decimal(default_height) <= 0:
                return False
        except InvalidOperation:
            return False
    return True


def column_visibility(sheet: Sheet, column: int) -> tuple[bool, dict[str, Any]]:
    sheet_format = sheet.root.find(spreadsheet_tag("sheetFormatPr"))
    default_width = (
        sheet_format.get("defaultColWidth") if sheet_format is not None else None
    )
    definitions = sheet.root.findall(
        f"{spreadsheet_tag('cols')}/{spreadsheet_tag('col')}"
    )
    matching: list[ET.Element] = []
    for definition in definitions:
        try:
            minimum = int(definition.get("min", "0"))
            maximum = int(definition.get("max", "0"))
        except ValueError:
            continue
        if minimum <= column <= maximum:
            matching.append(definition)
    definition = matching[-1] if matching else None
    hidden = (
        definition is not None
        and definition.get("hidden") in {"1", "true", "True"}
    )
    raw_width = definition.get("width") if definition is not None else None
    if raw_width is None:
        raw_width = default_width
    zero_width = False
    if raw_width is not None:
        try:
            zero_width = Decimal(raw_width) <= 0
        except InvalidOperation:
            zero_width = True
    return not hidden and not zero_width, {
        "column": column_letters(column),
        "definition": "column" if definition is not None else "sheet default",
        "hidden": hidden,
        "width": raw_width if raw_width is not None else "default",
    }


def resolve_header_columns(
    sheet: Sheet,
    header_row: int,
    labels: Iterable[str],
) -> tuple[dict[str, int], dict[str, list[str]]]:
    values: dict[str, list[int]] = {}
    for cell in sheet.cells_in_row(header_row):
        if cell.value is not None:
            values.setdefault(cell.value, []).append(cell.column)
    resolved: dict[str, int] = {}
    problems: dict[str, list[str]] = {}
    for label in labels:
        matches = values.get(label, [])
        if len(matches) == 1:
            resolved[label] = matches[0]
        elif not matches:
            problems[label] = ["missing"]
        else:
            problems[label] = [column_letters(column) for column in matches]
    return resolved, problems


def classify_status(value: str, status_groups: dict[str, list[str]]) -> str | None:
    matches = [key for key, values in status_groups.items() if value in values]
    return matches[0] if len(matches) == 1 else None


@dataclass
class LoadedInputs:
    artifact: Path
    contract_path: Path
    preflight_path: Path
    csv_path: Path
    contract: dict[str, Any]
    preflight: dict[str, Any]
    csv_rows: list[dict[str, str]]
    source_artifacts: list[tuple[Path, str]]
    issue_mapping: dict[str, Any]
    summary_mapping: dict[str, Any]
    status_groups: dict[str, list[str]]
    expected_statistics: dict[str, int]
    expected_issue_ids: list[str]
    updated_range: CellRange
    preservation: dict[str, Any] | None


def load_inputs(artifact: Path, contract_path: Path) -> LoadedInputs:
    artifact = artifact.expanduser().resolve()
    contract_path = contract_path.expanduser().resolve()
    contract = load_json_object(contract_path, "contract")
    mapping = require_object(contract, "mapping", "contract")
    issue_mapping = require_object(mapping, "issues", "contract.mapping")
    summary_mapping = require_object(mapping, "summary", "contract.mapping")
    require_string(issue_mapping, "sheet", "contract.mapping.issues")
    require_positive_int(issue_mapping, "header_row", "contract.mapping.issues")
    require_string(issue_mapping, "issue_id_column", "contract.mapping.issues")
    require_string(issue_mapping, "status_column", "contract.mapping.issues")
    required_columns = issue_mapping.get("required_columns")
    if (
        not isinstance(required_columns, list)
        or not required_columns
        or any(not isinstance(item, str) or not item for item in required_columns)
    ):
        raise ValidationInputError(
            "contract.mapping.issues.required_columns must be a non-empty string array"
        )
    require_string(summary_mapping, "sheet", "contract.mapping.summary")

    csv_config = require_object(contract, "csv", "contract")
    csv_path = resolve_relative(
        contract_path,
        require_string(csv_config, "path", "contract.csv"),
    )
    csv_id_column = require_string(csv_config, "issue_id_column", "contract.csv")
    csv_status_column = require_string(csv_config, "status_column", "contract.csv")
    try:
        with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
            reader = csv.DictReader(csv_file)
            if reader.fieldnames is None:
                raise ValidationInputError(f"CSV has no header: {csv_path}")
            missing_headers = sorted({csv_id_column, csv_status_column} - set(reader.fieldnames))
            if missing_headers:
                raise ValidationInputError(
                    f"CSV is missing confirmed columns {missing_headers}: {csv_path}"
                )
            csv_rows = [
                {key: value if value is not None else "" for key, value in row.items()}
                for row in reader
            ]
    except (OSError, UnicodeError, csv.Error) as error:
        raise ValidationInputError(f"cannot read CSV {csv_path}: {error}") from error

    raw_status_groups = require_object(contract, "status_groups", "contract")
    if set(raw_status_groups) != set(STATUS_STATISTIC_KEYS):
        raise ValidationInputError(
            "contract.status_groups must contain exactly "
            + ", ".join(STATUS_STATISTIC_KEYS)
        )
    status_groups: dict[str, list[str]] = {}
    seen_statuses: dict[str, str] = {}
    for key in STATUS_STATISTIC_KEYS:
        values = raw_status_groups[key]
        if not isinstance(values, list) or any(not isinstance(item, str) for item in values):
            raise ValidationInputError(f"contract.status_groups.{key} must be a string array")
        status_groups[key] = list(values)
        for value in values:
            if value in seen_statuses:
                raise ValidationInputError(
                    f"status {value!r} belongs to both {seen_statuses[value]} and {key}"
                )
            seen_statuses[value] = key

    raw_statistics = require_object(contract, "expected_statistics", "contract")
    if set(raw_statistics) != set(EXPECTED_STATISTIC_KEYS):
        raise ValidationInputError(
            "contract.expected_statistics must contain exactly "
            + ", ".join(EXPECTED_STATISTIC_KEYS)
        )
    expected_statistics: dict[str, int] = {}
    for key in EXPECTED_STATISTIC_KEYS:
        value = raw_statistics[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise ValidationInputError(
                f"contract.expected_statistics.{key} must be a non-negative integer"
            )
        expected_statistics[key] = value

    range_config = require_object(contract, "updated_range", "contract")
    range_sheet = require_string(range_config, "sheet", "contract.updated_range")
    if range_sheet != issue_mapping["sheet"]:
        raise ValidationInputError(
            "contract.updated_range.sheet must equal contract.mapping.issues.sheet"
        )
    updated_range = CellRange.parse(require_string(range_config, "range", "contract.updated_range"))
    if updated_range.start_row <= issue_mapping["header_row"]:
        raise ValidationInputError(
            "contract.updated_range must start below the confirmed header row"
        )

    preflight_config = require_object(contract, "preflight_snapshot", "contract")
    preflight_path = resolve_relative(
        contract_path,
        require_string(preflight_config, "path", "contract.preflight_snapshot"),
    )
    preflight = load_json_object(preflight_path, "preflight snapshot")
    raw_expected_issue_ids = preflight.get("expected_issue_ids")
    if (
        not isinstance(raw_expected_issue_ids, list)
        or not raw_expected_issue_ids
        or any(
            not isinstance(item, str) or not item.strip()
            for item in raw_expected_issue_ids
        )
    ):
        raise ValidationInputError(
            "preflight.expected_issue_ids must be a non-empty string array"
        )
    expected_issue_ids = list(raw_expected_issue_ids)
    normalized_expected_issue_ids = [
        normalize_issue_id(issue_id) for issue_id in expected_issue_ids
    ]
    duplicate_expected_issue_ids = sorted(
        key
        for key, count in Counter(normalized_expected_issue_ids).items()
        if count > 1
    )
    if duplicate_expected_issue_ids:
        raise ValidationInputError(
            "preflight.expected_issue_ids must be unique after normalization: "
            f"{duplicate_expected_issue_ids}"
        )
    if len(expected_issue_ids) != expected_statistics["total"]:
        raise ValidationInputError(
            "preflight.expected_issue_ids length must equal "
            "contract.expected_statistics.total"
        )
    sheet_order = preflight.get("sheet_order")
    if (
        not isinstance(sheet_order, list)
        or not sheet_order
        or any(not isinstance(item, str) or not item for item in sheet_order)
        or len(set(sheet_order)) != len(sheet_order)
    ):
        raise ValidationInputError("preflight snapshot sheet_order must be unique strings")
    expected_view = require_object(preflight, "expected_output_view", "preflight")
    require_string(expected_view, "active_sheet", "preflight.expected_output_view")
    parse_cell_reference(
        require_string(expected_view, "active_cell", "preflight.expected_output_view")
    )
    formula_cells = require_object(preflight, "formula_cells", "preflight")
    if not formula_cells:
        raise ValidationInputError("preflight.formula_cells must not be empty")
    statistic_formula_names: list[str] = []
    for name, formula_config in formula_cells.items():
        if not isinstance(name, str) or not isinstance(formula_config, dict):
            raise ValidationInputError("preflight.formula_cells entries must be named objects")
        require_string(formula_config, "sheet", f"preflight.formula_cells.{name}")
        parse_cell_reference(
            require_string(formula_config, "cell", f"preflight.formula_cells.{name}")
        )
        require_string(formula_config, "formula", f"preflight.formula_cells.{name}")
        statistic = formula_config.get("statistic")
        if statistic is not None:
            if "cached_value" in formula_config:
                raise ValidationInputError(
                    f"preflight.formula_cells.{name} must use either statistic or cached_value"
                )
            statistic = require_string(
                formula_config,
                "statistic",
                f"preflight.formula_cells.{name}",
            )
            if statistic not in expected_statistics:
                raise ValidationInputError(
                    f"preflight.formula_cells.{name}.statistic is unknown: {statistic}"
                )
            statistic_formula_names.append(statistic)
            continue
        raw_cached_value = formula_config.get("cached_value")
        if isinstance(raw_cached_value, bool) or not isinstance(
            raw_cached_value,
            (int, float, str),
        ):
            raise ValidationInputError(
                f"preflight.formula_cells.{name}.cached_value must be a numeric JSON value"
            )
        try:
            Decimal(str(raw_cached_value))
        except InvalidOperation as error:
            raise ValidationInputError(
                f"preflight.formula_cells.{name}.cached_value must be numeric"
            ) from error
    if set(statistic_formula_names) != set(EXPECTED_STATISTIC_KEYS) or len(
        statistic_formula_names
    ) != len(EXPECTED_STATISTIC_KEYS):
        raise ValidationInputError(
            "preflight.formula_cells must include each expected statistic exactly once"
        )

    raw_sources = preflight.get("source_artifacts")
    if not isinstance(raw_sources, list):
        raise ValidationInputError("preflight.source_artifacts must be an array")
    source_artifacts: list[tuple[Path, str]] = []
    for index, item in enumerate(raw_sources):
        if not isinstance(item, dict):
            raise ValidationInputError(f"preflight.source_artifacts[{index}] must be an object")
        source_path = resolve_relative(
            preflight_path,
            require_string(item, "path", f"preflight.source_artifacts[{index}]"),
        )
        digest = require_string(item, "sha256", f"preflight.source_artifacts[{index}]")
        if re.fullmatch(r"[0-9a-fA-F]{64}", digest) is None:
            raise ValidationInputError(
                f"preflight.source_artifacts[{index}].sha256 must be 64 hex characters"
            )
        source_artifacts.append((source_path, digest.lower()))
    if csv_path not in {path for path, _ in source_artifacts}:
        raise ValidationInputError(
            "preflight.source_artifacts must pin the confirmed CSV path and SHA-256"
        )

    preservation: dict[str, Any] | None = None
    raw_preservation = preflight.get("preservation")
    if raw_preservation is not None:
        if not isinstance(raw_preservation, dict):
            raise ValidationInputError("preflight.preservation must be an object")
        preservation_source = resolve_relative(
            preflight_path,
            require_string(raw_preservation, "source_workbook", "preflight.preservation"),
        )
        if preservation_source not in {path for path, _ in source_artifacts}:
            raise ValidationInputError(
                "preflight.preservation.source_workbook must be pinned in source_artifacts"
            )
        protected_sheets = raw_preservation.get("protected_sheets")
        if (
            not isinstance(protected_sheets, list)
            or any(not isinstance(name, str) or not name.strip() for name in protected_sheets)
            or len(set(protected_sheets)) != len(protected_sheets)
        ):
            raise ValidationInputError(
                "preflight.preservation.protected_sheets must be a unique string array"
            )
        preserve_rule_comments = raw_preservation.get("preserve_rule_comments", False)
        if not isinstance(preserve_rule_comments, bool):
            raise ValidationInputError(
                "preflight.preservation.preserve_rule_comments must be boolean"
            )
        forbidden_drawing_names = raw_preservation.get("forbidden_drawing_names", [])
        if (
            not isinstance(forbidden_drawing_names, list)
            or any(not isinstance(name, str) or not name.strip() for name in forbidden_drawing_names)
            or len(set(forbidden_drawing_names)) != len(forbidden_drawing_names)
        ):
            raise ValidationInputError(
                "preflight.preservation.forbidden_drawing_names must be a unique string array"
            )
        if not protected_sheets and not preserve_rule_comments and not forbidden_drawing_names:
            raise ValidationInputError(
                "preflight.preservation must declare a protected sheet, rule comments, or forbidden drawing"
            )
        preservation = {
            "source_workbook": preservation_source,
            "protected_sheets": protected_sheets,
            "preserve_rule_comments": preserve_rule_comments,
            "forbidden_drawing_names": forbidden_drawing_names,
        }

    return LoadedInputs(
        artifact=artifact,
        contract_path=contract_path,
        preflight_path=preflight_path,
        csv_path=csv_path,
        contract=contract,
        preflight=preflight,
        csv_rows=csv_rows,
        source_artifacts=source_artifacts,
        issue_mapping=issue_mapping,
        summary_mapping=summary_mapping,
        status_groups=status_groups,
        expected_statistics=expected_statistics,
        expected_issue_ids=expected_issue_ids,
        updated_range=updated_range,
        preservation=preservation,
    )


def initial_layers() -> dict[str, LayerResult]:
    return {
        "data_correctness": LayerResult("資料正確性"),
        "visibility": LayerResult("可見性"),
        "formula_cache": LayerResult("公式快取"),
        "rendering": LayerResult("真實渲染"),
    }


def fail_unavailable_layers(layers: dict[str, LayerResult], reason: str, source: str) -> None:
    for key in ("data_correctness", "visibility", "formula_cache"):
        layers[key].check(
            "validation_prerequisite",
            False,
            source=source,
            expected="readable validated inputs and OOXML artifact",
            actual=reason,
            reason=reason,
        )
    layers["rendering"].not_run(
        "真實渲染未執行：artifact readback 前置條件失敗",
        source=source,
        actual="prerequisite failed",
    )


def source_hashes(
    inputs: LoadedInputs,
    layer: LayerResult,
) -> dict[Path, str | None]:
    actual_hashes: dict[Path, str | None] = {}
    for path, expected_hash in inputs.source_artifacts:
        try:
            actual_hash = sha256_file(path)
        except OSError as error:
            actual_hash = None
            reason = f"cannot hash declared source artifact {path}: {error}"
        else:
            reason = f"declared source artifact digest changed before validation: {path}"
        actual_hashes[path] = actual_hash
        layer.check(
            "source_artifact_digest",
            actual_hash == expected_hash,
            source=str(inputs.preflight_path),
            expected={"path": str(path), "sha256": expected_hash},
            actual={"path": str(path), "sha256": actual_hash},
            reason=reason,
        )
        layer.check(
            "artifact_is_not_a_source",
            inputs.artifact != path,
            source=str(inputs.preflight_path),
            expected="output artifact path distinct from every source/seed path",
            actual={"artifact": str(inputs.artifact), "source": str(path)},
            reason="validator refuses to treat a declared source/seed as the output artifact",
        )
    return actual_hashes


def local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def style_signatures(path: Path) -> list[str]:
    """Resolve cell style IDs to stable cell-XF descriptions for sheet comparison."""

    try:
        with zipfile.ZipFile(path, "r") as archive:
            if "xl/styles.xml" not in archive.namelist():
                return []
            root = read_xml_part(archive, "xl/styles.xml")
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValidationInputError(f"cannot read styles from {path}: {error}") from error
    cell_xfs = root.find(spreadsheet_tag("cellXfs"))
    if cell_xfs is None:
        return []
    return [
        json.dumps(canonical_xml(child, []), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for child in cell_xfs.findall(spreadsheet_tag("xf"))
    ]


def canonical_xml(element: ET.Element, styles: Sequence[str]) -> dict[str, Any]:
    """Represent worksheet XML independent of serialization order and cell style IDs."""

    element_name = local_name(element.tag)
    attributes: dict[str, Any] = {}
    for raw_name, value in element.attrib.items():
        name = local_name(raw_name)
        if raw_name == qualified(OFFICE_REL_NS, "id"):
            continue
        if name in {"s", "style"} and element_name in {"c", "row", "col"}:
            try:
                attributes[name] = {"cell_xf": styles[int(value)]}
            except (IndexError, ValueError):
                attributes[name] = {"invalid_cell_xf": value}
            continue
        attributes[name] = value
    children = [canonical_xml(child, styles) for child in list(element)]
    children.sort(
        key=lambda child: json.dumps(child, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
    )
    return {
        "tag": element.tag,
        "attributes": attributes,
        "text": (element.text or "").strip(),
        "children": children,
    }


def sheet_semantics(path: Path, sheet: Sheet) -> dict[str, Any]:
    return {
        "state": sheet.state,
        "worksheet": canonical_xml(sheet.root, style_signatures(path)),
    }


def versioned_rule_comments(path: Path) -> Counter[tuple[str, str]]:
    """Read MANTIS_RULE_V1 payloads from legacy and threaded comments without double-counting."""

    rules: set[tuple[str, str]] = set()
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for part_name in archive.namelist():
                if not (
                    part_name.startswith("xl/comments")
                    or part_name.startswith("xl/threadedComments/")
                ):
                    continue
                root = read_xml_part(archive, part_name)
                for element in root.iter():
                    if local_name(element.tag) not in {"comment", "threadedComment"}:
                        continue
                    payload = "".join(element.itertext()).strip()
                    if "MANTIS_RULE_V1" in payload:
                        rules.add((element.get("ref", ""), payload))
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValidationInputError(f"cannot inspect comment rules in {path}: {error}") from error
    return Counter(rules)


def drawing_names(path: Path) -> list[str]:
    names: list[str] = []
    try:
        with zipfile.ZipFile(path, "r") as archive:
            for part_name in archive.namelist():
                if not part_name.startswith("xl/drawings/") or not part_name.endswith(".xml"):
                    continue
                root = read_xml_part(archive, part_name)
                names.extend(
                    name.strip()
                    for element in root.iter()
                    for name in [element.get("name")]
                    if name and name.strip()
                )
    except (OSError, zipfile.BadZipFile, KeyError) as error:
        raise ValidationInputError(f"cannot inspect drawings in {path}: {error}") from error
    return sorted(names)


def validate_preservation(
    inputs: LoadedInputs,
    workbook: WorkbookArtifact,
    layer: LayerResult,
) -> None:
    preservation = inputs.preservation
    if preservation is None:
        return
    source_path: Path = preservation["source_workbook"]
    try:
        source_workbook = read_workbook_artifact(source_path)
    except ValidationInputError as error:
        layer.check(
            "preservation_source_workbook",
            False,
            source=str(source_path),
            expected="readable source workbook for semantic comparison",
            actual=str(error),
            reason="cannot reopen the preservation source workbook",
        )
        return
    for sheet_name in preservation["protected_sheets"]:
        source_sheet = source_workbook.sheet(sheet_name)
        artifact_sheet = workbook.sheet(sheet_name)
        try:
            expected = sheet_semantics(source_path, source_sheet) if source_sheet else None
            actual = sheet_semantics(inputs.artifact, artifact_sheet) if artifact_sheet else None
        except ValidationInputError as error:
            layer.check(
                f"protected_sheet_semantics:{sheet_name}",
                False,
                source=f"{source_path} -> {inputs.artifact}",
                expected="readable normalized worksheet semantics",
                actual=str(error),
                reason=f"cannot compare protected sheet semantics: {sheet_name}",
            )
            continue
        layer.check(
            f"protected_sheet_semantics:{sheet_name}",
            source_sheet is not None and artifact_sheet is not None and expected == actual,
            source=f"{source_path} -> {inputs.artifact}",
            expected=expected,
            actual=actual,
            reason=f"protected sheet changed semantically or is missing: {sheet_name}",
        )
    if preservation["preserve_rule_comments"]:
        try:
            expected_rules = versioned_rule_comments(source_path)
            actual_rules = versioned_rule_comments(inputs.artifact)
        except ValidationInputError as error:
            layer.check(
                "versioned_rule_comments",
                False,
                source=f"{source_path} -> {inputs.artifact}:comments/threadedComments",
                expected="readable legacy and threaded MANTIS rules",
                actual=str(error),
                reason="cannot compare versioned MANTIS rule comments",
            )
            expected_rules = actual_rules = None
        if expected_rules is not None and actual_rules is not None:
            layer.check(
                "versioned_rule_comments",
                expected_rules == actual_rules,
                source=f"{source_path} -> {inputs.artifact}:comments/threadedComments",
                expected={"count": sum(expected_rules.values()), "rules": sorted(expected_rules.elements())},
                actual={"count": sum(actual_rules.values()), "rules": sorted(actual_rules.elements())},
                reason="versioned MANTIS rule comments changed or were lost",
            )
    forbidden_names = preservation["forbidden_drawing_names"]
    if forbidden_names:
        try:
            actual_names = drawing_names(inputs.artifact)
        except ValidationInputError as error:
            layer.check(
                "forbidden_drawing_names",
                False,
                source=f"{inputs.artifact}:xl/drawings/*.xml",
                expected={"absent": forbidden_names},
                actual=str(error),
                reason="cannot inspect drawings for confirmed forbidden objects",
            )
            return
        present = sorted(set(forbidden_names) & set(actual_names))
        layer.check(
            "forbidden_drawing_names",
            not present,
            source=f"{inputs.artifact}:xl/drawings/*.xml",
            expected={"absent": forbidden_names},
            actual={"present": present, "drawing_names": actual_names},
            reason="a confirmed forbidden floating drawing remains in the artifact",
        )


def validate_data(
    inputs: LoadedInputs,
    workbook: WorkbookArtifact,
    layer: LayerResult,
) -> tuple[Sheet | None, dict[str, int], list[Cell], dict[str, tuple[Cell, Cell | None]]]:
    summary_sheet_name = inputs.summary_mapping["sheet"]
    summary_sheet = workbook.sheet(summary_sheet_name)
    layer.check(
        "confirmed_summary_sheet",
        summary_sheet is not None,
        source=f"{inputs.artifact}:xl/workbook.xml",
        expected=summary_sheet_name,
        actual=[sheet.name for sheet in workbook.sheets],
        reason=f"confirmed summary sheet is missing: {summary_sheet_name}",
    )

    issue_sheet_name = inputs.issue_mapping["sheet"]
    issue_sheet = workbook.sheet(issue_sheet_name)
    layer.check(
        "confirmed_issue_sheet",
        issue_sheet is not None,
        source=f"{inputs.artifact}:xl/workbook.xml",
        expected=issue_sheet_name,
        actual=[sheet.name for sheet in workbook.sheets],
        reason=f"confirmed issue sheet is missing: {issue_sheet_name}",
    )
    if issue_sheet is None:
        return None, {}, [], {}

    labels = [
        inputs.issue_mapping["issue_id_column"],
        inputs.issue_mapping["status_column"],
        *inputs.issue_mapping["required_columns"],
    ]
    unique_labels = list(dict.fromkeys(labels))
    resolved_columns, problems = resolve_header_columns(
        issue_sheet,
        inputs.issue_mapping["header_row"],
        unique_labels,
    )
    layer.check(
        "confirmed_column_mapping",
        not problems,
        source=f"{inputs.artifact}:{issue_sheet.name}!{inputs.issue_mapping['header_row']}:{inputs.issue_mapping['header_row']}",
        expected=unique_labels,
        actual={
            label: column_letters(column) for label, column in resolved_columns.items()
        }
        | {"problems": problems},
        reason=f"confirmed header labels are missing or duplicated: {problems}",
    )
    if problems:
        return issue_sheet, resolved_columns, [], {}

    issue_id_column = resolved_columns[inputs.issue_mapping["issue_id_column"]]
    status_column = resolved_columns[inputs.issue_mapping["status_column"]]
    columns_within_range = all(
        inputs.updated_range.start_column <= resolved_columns[label] <= inputs.updated_range.end_column
        for label in unique_labels
    )
    layer.check(
        "updated_range_covers_confirmed_columns",
        columns_within_range,
        source=str(inputs.contract_path),
        expected={"range": inputs.contract["updated_range"]["range"], "columns": unique_labels},
        actual={label: column_letters(resolved_columns[label]) for label in unique_labels},
        reason="updated range does not cover every confirmed column",
    )

    csv_config = inputs.contract["csv"]
    csv_id_column = csv_config["issue_id_column"]
    csv_status_column = csv_config["status_column"]
    expected_ids = [row[csv_id_column].strip() for row in inputs.csv_rows]
    normalized_expected = [normalize_issue_id(value) for value in expected_ids]
    blank_csv_rows = [index + 2 for index, value in enumerate(expected_ids) if not value]
    duplicate_csv_keys = sorted(
        key for key, count in Counter(normalized_expected).items() if key and count > 1
    )
    layer.check(
        "csv_issue_ids_are_non_blank_and_unique",
        not blank_csv_rows and not duplicate_csv_keys,
        source=str(inputs.csv_path),
        expected="non-blank issue identifiers unique after confirmed normalization",
        actual={"blank_rows": blank_csv_rows, "duplicate_keys": duplicate_csv_keys},
        reason="CSV issue identifiers are blank or duplicated after normalization",
    )

    actual_issue_cells: list[Cell] = []
    actual_pairs: dict[str, tuple[Cell, Cell | None]] = {}
    duplicate_artifact_keys: list[str] = []
    for row_number in sorted(issue_sheet.row_elements):
        if row_number <= inputs.issue_mapping["header_row"]:
            continue
        issue_cell = issue_sheet.cell(f"{column_letters(issue_id_column)}{row_number}")
        if issue_cell is None or issue_cell.value is None or not issue_cell.value.strip():
            continue
        actual_issue_cells.append(issue_cell)
        key = normalize_issue_id(issue_cell.value)
        status_cell = issue_sheet.cell(f"{column_letters(status_column)}{row_number}")
        if key in actual_pairs:
            duplicate_artifact_keys.append(key)
        else:
            actual_pairs[key] = (issue_cell, status_cell)
    layer.check(
        "artifact_issue_ids_are_unique",
        not duplicate_artifact_keys,
        source=f"{inputs.artifact}:{issue_sheet.name}!{column_letters(issue_id_column)}:{column_letters(issue_id_column)}",
        expected="unique normalized issue identifiers",
        actual={"duplicates": sorted(set(duplicate_artifact_keys))},
        reason="artifact contains duplicate normalized issue identifiers",
    )

    expected_issue_ids_by_key = {
        normalize_issue_id(issue_id): issue_id for issue_id in inputs.expected_issue_ids
    }
    complete_missing_ids = [
        issue_id
        for key, issue_id in expected_issue_ids_by_key.items()
        if key not in actual_pairs
    ]
    complete_extra_ids = [
        issue_cell.value
        for key, (issue_cell, _) in actual_pairs.items()
        if key not in expected_issue_ids_by_key
    ]
    complete_display_mismatches = [
        {
            "expected": expected_issue_id,
            "actual": actual_pairs[key][0].value,
            "cell": actual_pairs[key][0].reference,
        }
        for key, expected_issue_id in expected_issue_ids_by_key.items()
        if key in actual_pairs and actual_pairs[key][0].value != expected_issue_id
    ]
    layer.check(
        "complete_issue_id_set",
        not complete_missing_ids
        and not complete_extra_ids
        and not complete_display_mismatches,
        source=f"{inputs.preflight_path} -> {inputs.artifact}:{issue_sheet.name}",
        expected={"count": len(inputs.expected_issue_ids), "issue_ids": inputs.expected_issue_ids},
        actual={
            "count": len(actual_pairs),
            "missing": complete_missing_ids,
            "extra": complete_extra_ids,
            "display_mismatches": complete_display_mismatches,
        },
        reason="artifact issue identifiers do not exactly match the preflight snapshot",
    )

    missing_ids: list[str] = []
    display_mismatches: list[dict[str, Any]] = []
    non_text_ids: list[dict[str, Any]] = []
    outside_range: list[dict[str, Any]] = []
    category_mismatches: list[dict[str, Any]] = []
    comparable_columns = [
        label
        for label in inputs.issue_mapping["required_columns"]
        if inputs.csv_rows
        and label in inputs.csv_rows[0]
        and label
        not in {
            inputs.issue_mapping["issue_id_column"],
            inputs.issue_mapping["status_column"],
        }
    ]
    field_mismatches: list[dict[str, Any]] = []
    for csv_row, expected_id, normalized in zip(
        inputs.csv_rows,
        expected_ids,
        normalized_expected,
    ):
        pair = actual_pairs.get(normalized)
        if pair is None:
            missing_ids.append(expected_id)
            continue
        issue_cell, status_cell = pair
        if issue_cell.value != expected_id:
            display_mismatches.append(
                {"expected": expected_id, "actual": issue_cell.value, "cell": issue_cell.reference}
            )
        if issue_cell.data_type not in {"inlineStr", "s", "str"}:
            non_text_ids.append(
                {"issue_id": issue_cell.value, "cell": issue_cell.reference, "type": issue_cell.data_type}
            )
        if not inputs.updated_range.contains(issue_cell.column, issue_cell.row):
            outside_range.append({"issue_id": expected_id, "cell": issue_cell.reference})
        csv_category = classify_status(csv_row[csv_status_column], inputs.status_groups)
        artifact_status = status_cell.value.strip() if status_cell and status_cell.value else ""
        artifact_category = classify_status(artifact_status, inputs.status_groups)
        if csv_category is None or artifact_category != csv_category:
            category_mismatches.append(
                {
                    "issue_id": expected_id,
                    "csv_status": csv_row[csv_status_column],
                    "artifact_status": artifact_status,
                    "cell": status_cell.reference if status_cell else None,
                }
            )
        for label in comparable_columns:
            column = resolved_columns[label]
            artifact_cell = issue_sheet.cell(f"{column_letters(column)}{issue_cell.row}")
            artifact_value = artifact_cell.value if artifact_cell and artifact_cell.value is not None else ""
            expected_value = csv_row[label]
            if artifact_value != expected_value:
                field_mismatches.append(
                    {
                        "issue_id": expected_id,
                        "field": label,
                        "cell": artifact_cell.reference if artifact_cell else None,
                        "expected": expected_value,
                        "actual": artifact_value,
                    }
                )

    layer.check(
        "csv_issue_ids_present",
        not missing_ids,
        source=f"{inputs.csv_path} -> {inputs.artifact}:{issue_sheet.name}",
        expected={"count": len(expected_ids)},
        actual={"matched": len(expected_ids) - len(missing_ids), "missing": missing_ids},
        reason="one or more CSV issue identifiers are absent from the artifact",
    )
    layer.check(
        "issue_id_display_and_type",
        not display_mismatches and not non_text_ids,
        source=f"{inputs.artifact}:{issue_sheet.name}!{column_letters(issue_id_column)}:{column_letters(issue_id_column)}",
        expected="exact CSV text identifiers, including leading zeroes",
        actual={"display_mismatches": display_mismatches, "non_text": non_text_ids},
        reason="artifact changed an issue identifier's display text or stored it as a number",
    )
    layer.check(
        "csv_rows_within_updated_range",
        not outside_range,
        source=f"{inputs.artifact}:{issue_sheet.name}!{inputs.contract['updated_range']['range']}",
        expected="every CSV issue row inside the confirmed observed update range",
        actual={"outside": outside_range},
        reason="one or more CSV issue rows fall outside the confirmed update range",
    )
    layer.check(
        "csv_and_artifact_status_categories",
        not category_mismatches,
        source=f"{inputs.csv_path} -> {inputs.artifact}:{issue_sheet.name}",
        expected="same confirmed status category per CSV issue",
        actual={"mismatches": category_mismatches},
        reason="CSV and artifact status categories differ or are unclassified",
    )
    layer.check(
        "confirmed_csv_fields_match",
        not field_mismatches,
        source=f"{inputs.csv_path} -> {inputs.artifact}:{issue_sheet.name}",
        expected={"columns": comparable_columns, "mismatches": []},
        actual={"columns": comparable_columns, "mismatches": field_mismatches},
        reason="one or more confirmed CSV fields differ in the persisted artifact",
    )

    status_counts = {key: 0 for key in STATUS_STATISTIC_KEYS}
    unclassified: list[dict[str, Any]] = []
    for issue_cell in actual_issue_cells:
        status_cell = issue_sheet.cell(f"{column_letters(status_column)}{issue_cell.row}")
        status = status_cell.value.strip() if status_cell and status_cell.value else ""
        category = classify_status(status, inputs.status_groups)
        if category is None:
            unclassified.append(
                {
                    "row": issue_cell.row,
                    "issue_id": issue_cell.value,
                    "status": status,
                }
            )
        else:
            status_counts[category] += 1
    actual_statistics = status_counts | {"total": len(actual_issue_cells)}
    layer.check(
        "all_artifact_statuses_are_classified",
        not unclassified,
        source=f"{inputs.artifact}:{issue_sheet.name}!{column_letters(status_column)}:{column_letters(status_column)}",
        expected="exactly one confirmed category per populated issue row",
        actual={"unclassified": unclassified},
        reason="artifact contains blank, unknown, or ambiguously classified statuses",
    )
    layer.check(
        "independent_statistics",
        actual_statistics == inputs.expected_statistics,
        source=f"{inputs.artifact}:{issue_sheet.name} independent row count",
        expected=inputs.expected_statistics,
        actual=actual_statistics,
        reason="independent artifact statistics do not match the confirmed expected statistics",
    )
    return issue_sheet, resolved_columns, actual_issue_cells, actual_pairs


def validate_visibility(
    inputs: LoadedInputs,
    workbook: WorkbookArtifact,
    issue_sheet: Sheet | None,
    resolved_columns: dict[str, int],
    actual_issue_cells: list[Cell],
    layer: LayerResult,
) -> None:
    actual_sheet_order = [sheet.name for sheet in workbook.sheets]
    expected_sheet_order = inputs.preflight["sheet_order"]
    layer.check(
        "sheet_order_readback",
        actual_sheet_order == expected_sheet_order,
        source=f"{inputs.artifact}:xl/workbook.xml",
        expected=expected_sheet_order,
        actual=actual_sheet_order,
        reason="persisted worksheet order differs from the preflight snapshot",
    )

    expected_view = inputs.preflight["expected_output_view"]
    expected_active_sheet = expected_view["active_sheet"]
    expected_active_cell = expected_view["active_cell"].replace("$", "").upper()
    active_sheet = workbook.sheet(expected_active_sheet)
    expected_index = active_sheet.index if active_sheet is not None else None
    workbook_view = workbook.workbook_root.find(
        f"{spreadsheet_tag('bookViews')}/{spreadsheet_tag('workbookView')}"
    )
    raw_active_tab = workbook_view.get("activeTab") if workbook_view is not None else None
    try:
        active_tab = int(raw_active_tab) if raw_active_tab is not None else None
    except ValueError:
        active_tab = None
    layer.check(
        "persisted_workbook_view",
        workbook_view is not None and active_tab == expected_index,
        source=f"{inputs.artifact}:xl/workbook.xml/bookViews/workbookView",
        expected={"active_sheet": expected_active_sheet, "active_tab": expected_index},
        actual={"workbook_view": workbook_view is not None, "active_tab": raw_active_tab},
        reason="workbook view is missing or its activeTab does not select the confirmed sheet",
    )
    layer.check(
        "active_sheet_visibility",
        active_sheet is not None and active_sheet.state == "visible",
        source=f"{inputs.artifact}:xl/workbook.xml/sheets",
        expected={"sheet": expected_active_sheet, "state": "visible"},
        actual={"sheet": expected_active_sheet, "state": active_sheet.state if active_sheet else None},
        reason="confirmed active sheet is missing, hidden, or veryHidden",
    )

    summary_sheet_name = inputs.summary_mapping["sheet"]
    summary_sheet = workbook.sheet(summary_sheet_name)
    layer.check(
        "summary_sheet_visibility",
        summary_sheet is not None and summary_sheet.state == "visible",
        source=f"{inputs.artifact}:xl/workbook.xml/sheets",
        expected={"sheet": summary_sheet_name, "state": "visible"},
        actual={
            "sheet": summary_sheet_name,
            "state": summary_sheet.state if summary_sheet is not None else None,
        },
        reason="confirmed summary sheet is missing, hidden, or veryHidden",
    )

    selected_sheet_views: list[str] = []
    for candidate_sheet in workbook.sheets:
        candidate_views = candidate_sheet.root.find(spreadsheet_tag("sheetViews"))
        if candidate_views is None:
            continue
        if any(
            (view.get("tabSelected") or "").strip().lower() in {"1", "true"}
            for view in candidate_views.findall(spreadsheet_tag("sheetView"))
        ):
            selected_sheet_views.append(candidate_sheet.name)
    layer.check(
        "conflicting_sheet_selection",
        not selected_sheet_views or selected_sheet_views == [expected_active_sheet],
        source=f"{inputs.artifact}:xl/worksheets/*/sheetViews/sheetView@tabSelected",
        expected={"selected_sheets": [], "or_single_active_sheet": expected_active_sheet},
        actual={"selected_sheets": selected_sheet_views},
        reason="sheet view selection conflicts with the confirmed active workbook sheet",
    )

    selection: ET.Element | None = None
    if active_sheet is not None:
        sheet_views = active_sheet.root.find(spreadsheet_tag("sheetViews"))
        sheet_view = (
            sheet_views.find(spreadsheet_tag("sheetView")) if sheet_views is not None else None
        )
        if sheet_view is not None:
            selections = sheet_view.findall(spreadsheet_tag("selection"))
            selection = next(
                (
                    candidate
                    for candidate in selections
                    if (candidate.get("activeCell") or "").replace("$", "").upper()
                    == expected_active_cell
                ),
                selections[0] if selections else None,
            )
    actual_selection = {
        "activeCell": selection.get("activeCell") if selection is not None else None,
        "sqref": selection.get("sqref") if selection is not None else None,
    }
    layer.check(
        "persisted_sheet_view_selection",
        selection is not None
        and (selection.get("activeCell") or "").replace("$", "").upper()
        == expected_active_cell
        and (selection.get("sqref") or "").replace("$", "").upper()
        == expected_active_cell,
        source=(
            f"{inputs.artifact}:{active_sheet.part_name}/sheetViews"
            if active_sheet is not None
            else f"{inputs.artifact}:missing sheet {expected_active_sheet}"
        ),
        expected={"activeCell": expected_active_cell, "sqref": expected_active_cell},
        actual=actual_selection,
        reason="sheet view or its persisted activeCell/sqref selection is missing or wrong",
    )

    if issue_sheet is None:
        layer.check(
            "issue_sheet_visibility",
            False,
            source=f"{inputs.artifact}:xl/workbook.xml/sheets",
            expected={"sheet": inputs.issue_mapping["sheet"], "state": "visible"},
            actual=None,
            reason="confirmed issue sheet is missing",
        )
        return

    layer.check(
        "issue_sheet_visibility",
        issue_sheet.state == "visible",
        source=f"{inputs.artifact}:xl/workbook.xml/sheets",
        expected={"sheet": issue_sheet.name, "state": "visible"},
        actual={"sheet": issue_sheet.name, "state": issue_sheet.state},
        reason="confirmed issue sheet is hidden or veryHidden",
    )
    header_row = inputs.issue_mapping["header_row"]
    layer.check(
        "header_row_visibility",
        row_is_visible(issue_sheet, issue_sheet.row_element(header_row)),
        source=f"{inputs.artifact}:{issue_sheet.part_name}/sheetData/row[@r='{header_row}']",
        expected={"row": header_row, "visible": True, "height_gt_zero": True},
        actual={
            "row": header_row,
            "attributes": dict(issue_sheet.row_element(header_row).attrib)
            if issue_sheet.row_element(header_row) is not None
            else None,
        },
        reason="confirmed header row is missing, hidden, or has zero height",
    )

    hidden_data_rows = [
        cell.row
        for cell in actual_issue_cells
        if not row_is_visible(issue_sheet, issue_sheet.row_element(cell.row))
    ]
    visible_count = len(actual_issue_cells) - len(hidden_data_rows)
    layer.check(
        "populated_issue_rows_visible",
        not hidden_data_rows,
        source=f"{inputs.artifact}:{issue_sheet.part_name}/sheetData",
        expected={"hidden_populated_rows": [], "visible_rows": inputs.expected_statistics["total"]},
        actual={"hidden_populated_rows": hidden_data_rows, "visible_rows": visible_count},
        reason="one or more populated issue rows remain hidden or have zero height",
    )
    layer.check(
        "visible_issue_row_count",
        visible_count == inputs.expected_statistics["total"],
        source=f"{inputs.artifact}:{issue_sheet.part_name}/sheetData",
        expected=inputs.expected_statistics["total"],
        actual=visible_count,
        reason="visible populated issue row count differs from expected total",
    )

    required_columns = inputs.issue_mapping["required_columns"]
    missing_required = [label for label in required_columns if label not in resolved_columns]
    visibility_details: list[dict[str, Any]] = []
    invisible_columns: list[str] = []
    for label in required_columns:
        column = resolved_columns.get(label)
        if column is None:
            continue
        visible, detail = column_visibility(issue_sheet, column)
        detail["label"] = label
        visibility_details.append(detail)
        if not visible:
            invisible_columns.append(label)
    layer.check(
        "required_columns_visible",
        not missing_required and not invisible_columns,
        source=f"{inputs.artifact}:{issue_sheet.part_name}/cols",
        expected={"required": required_columns, "visible": True, "width_gt_zero": True},
        actual={
            "missing": missing_required,
            "invisible": invisible_columns,
            "details": visibility_details,
        },
        reason="one or more confirmed required columns are missing, hidden, or zero width",
    )


def validate_formula_cache(
    inputs: LoadedInputs,
    workbook: WorkbookArtifact,
    layer: LayerResult,
) -> None:
    formula_cells = inputs.preflight["formula_cells"]
    statistics = [
        config["statistic"]
        for config in formula_cells.values()
        if "statistic" in config
    ]
    coordinates = [
        (config["sheet"], config["cell"].replace("$", "").upper())
        for config in formula_cells.values()
    ]
    duplicate_statistics = sorted(
        statistic for statistic, count in Counter(statistics).items() if count > 1
    )
    duplicate_coordinates = sorted(
        f"{sheet}!{cell}"
        for (sheet, cell), count in Counter(coordinates).items()
        if count > 1
    )
    expected_formula_sheet = inputs.summary_mapping["sheet"]
    formula_sheet_mismatches = {
        name: config["sheet"]
        for name, config in formula_cells.items()
        if config["sheet"] != expected_formula_sheet
    }
    layer.check(
        "confirmed_formula_sheet_mapping",
        not formula_sheet_mismatches,
        source=str(inputs.preflight_path),
        expected={"sheet": expected_formula_sheet},
        actual={"mismatches": formula_sheet_mismatches},
        reason="one or more confirmed formula cells are outside the confirmed summary sheet",
    )
    layer.check(
        "confirmed_formula_set",
        set(statistics) == set(EXPECTED_STATISTIC_KEYS)
        and not duplicate_statistics
        and not duplicate_coordinates,
        source=str(inputs.preflight_path),
        expected=list(EXPECTED_STATISTIC_KEYS),
        actual={
            "statistics": statistics,
            "duplicate_statistics": duplicate_statistics,
            "duplicate_cells": duplicate_coordinates,
        },
        reason=(
            "preflight formula set does not cover each expected statistic exactly once "
            "at a unique cell"
        ),
    )
    for name, config in formula_cells.items():
        sheet_name = config["sheet"]
        reference = config["cell"].replace("$", "").upper()
        sheet = workbook.sheet(sheet_name)
        cell = sheet.cell(reference) if sheet is not None else None
        expected_formula = formula_without_optional_prefix(config["formula"])
        actual_formula = (
            formula_without_optional_prefix(cell.formula)
            if cell and cell.formula is not None
            else None
        )
        source = (
            f"{inputs.artifact}:{sheet.part_name}:{reference}"
            if sheet is not None
            else f"{inputs.artifact}:missing sheet {sheet_name}:{reference}"
        )
        layer.check(
            f"formula:{name}",
            actual_formula == expected_formula,
            source=source,
            expected=expected_formula,
            actual=actual_formula,
            reason=f"confirmed formula is missing or changed at {sheet_name}!{reference}",
        )

        statistic = config.get("statistic")
        expected_value = (
            inputs.expected_statistics[statistic]
            if statistic is not None
            else config["cached_value"]
        )
        raw_cached = cell.cached_value if cell is not None else None
        cached_error = cell is not None and cell.data_type == "e"
        numeric_cache_type = cell is not None and cell.data_type in {None, "n"}
        numeric_value: Decimal | None = None
        if (
            raw_cached is not None
            and raw_cached.strip()
            and not cached_error
            and numeric_cache_type
        ):
            try:
                numeric_value = Decimal(raw_cached)
            except InvalidOperation:
                numeric_value = None
        cache_matches = numeric_cache_type and numeric_value == Decimal(str(expected_value))
        layer.check(
            f"cached_value:{name}",
            cache_matches and not cached_error,
            source=source,
            expected=expected_value,
            actual={
                "value": raw_cached,
                "cell_type": cell.data_type if cell is not None else None,
                "numeric_type": numeric_cache_type,
                "error": cached_error,
            },
            reason=(
                f"formula cache is blank, stale, non-numeric, or an error at "
                f"{sheet_name}!{reference}"
            ),
        )


def find_renderer() -> Path | None:
    for name in ("libreoffice", "soffice"):
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()
    macos_path = Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")
    if macos_path.is_file() and os.access(macos_path, os.X_OK):
        return macos_path
    return None


def validate_rendering(
    inputs: LoadedInputs,
    workbook: WorkbookArtifact,
    layer: LayerResult,
    renderer_mode: str,
    visual_verdict: str,
) -> None:
    if renderer_mode == "none":
        layer.not_run(
            "未完成真實渲染驗證：呼叫端明確宣告 renderer 不可用",
            source="--renderer none",
            actual="renderer disabled",
        )
        return
    executable = find_renderer()
    if executable is None:
        layer.not_run(
            "未完成真實渲染驗證：環境中找不到 LibreOffice renderer",
            source="PATH and standard LibreOffice application path",
            actual="renderer unavailable",
        )
        return

    try:
        version_result = subprocess.run(
            [str(executable), "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        layer.check(
            "renderer_probe",
            False,
            source=str(executable),
            expected="renderer version probe completes",
            actual=str(error),
            reason=f"renderer probe failed: {error}",
        )
        return
    version = (version_result.stdout or version_result.stderr).strip()
    layer.check(
        "renderer_probe",
        version_result.returncode == 0,
        source=str(executable),
        expected={"exit": 0},
        actual={"exit": version_result.returncode, "version": version},
        reason="LibreOffice renderer version probe failed",
    )
    if version_result.returncode != 0:
        return

    try:
        with tempfile.TemporaryDirectory(prefix="mantis-artifact-render-") as temporary:
            temporary_path = Path(temporary)
            render_input = temporary_path / inputs.artifact.name
            shutil.copy2(inputs.artifact, render_input)
            profile = temporary_path / "profile"
            profile.mkdir()
            command = [
                str(executable),
                f"-env:UserInstallation={profile.as_uri()}",
                "--headless",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temporary_path),
                str(render_input),
            ]
            result = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            rendered = temporary_path / f"{render_input.stem}.pdf"
            rendered_size = rendered.stat().st_size if rendered.is_file() else 0
    except (OSError, subprocess.TimeoutExpired) as error:
        layer.check(
            "real_render",
            False,
            source=f"read-only temporary copy of {inputs.artifact}",
            expected="renderer produces a non-empty PDF",
            actual=str(error),
            reason=f"real renderer failed: {error}",
        )
        return

    layer.check(
        "real_render",
        result.returncode == 0 and rendered_size > 0,
        source=f"{executable} using read-only temporary copy of {inputs.artifact}",
        expected={
            "exit": 0,
            "non_empty_pdf": True,
            "sheets": [sheet.name for sheet in workbook.sheets],
            "observed_ranges": [
                f"{inputs.issue_mapping['sheet']}!{inputs.contract['updated_range']['range']}",
                f"{inputs.summary_mapping['sheet']}!confirmed formula cells",
            ],
        },
        actual={
            "exit": result.returncode,
            "pdf_bytes": rendered_size,
            "renderer": version,
            "stdout": result.stdout[-2000:],
            "stderr": result.stderr[-2000:],
        },
        reason="real renderer did not produce a non-empty PDF from the persisted workbook",
    )
    if result.returncode != 0 or rendered_size == 0:
        return
    if visual_verdict == "pass":
        layer.check(
            "visual_inspection",
            True,
            source="--visual-verdict pass",
            expected="a capable renderer or reviewer confirmed the visible workbook content",
            actual={"verdict": "pass", "renderer": version, "pdf_bytes": rendered_size},
        )
        return
    if visual_verdict == "fail":
        layer.check(
            "visual_inspection",
            False,
            source="--visual-verdict fail",
            expected="a capable renderer or reviewer confirmed the visible workbook content",
            actual={"verdict": "fail", "renderer": version, "pdf_bytes": rendered_size},
            reason="visual inspection found a workbook presentation defect",
        )
        return
    layer.not_run(
        "renderer generated a PDF, but no visual content inspection was recorded",
        source="--visual-verdict not-run",
        actual={"renderer": version, "pdf_bytes": rendered_size},
        check="visual_inspection",
        expected="visual confirmation when a capable rendering workflow is available",
    )


def outcome_for(layers: dict[str, LayerResult]) -> str:
    first_three = [
        layers["data_correctness"].status,
        layers["visibility"].status,
        layers["formula_cache"].status,
    ]
    rendering = layers["rendering"].status
    if any(status == "FAIL" for status in first_three) or rendering == "FAIL":
        return "FAIL"
    if first_three == ["PASS", "PASS", "PASS"] and rendering == "PASS":
        return "PASS"
    if first_three == ["PASS", "PASS", "PASS"] and rendering == "NOT RUN":
        return "PARTIAL"
    return "FAIL"


def build_report(
    artifact: Path,
    layers: dict[str, LayerResult],
    artifact_hash: str | None,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "outcome": outcome_for(layers),
        "artifact": {
            "path": str(artifact),
            "sha256": artifact_hash,
        },
        "layers": {name: layer.as_dict() for name, layer in layers.items()},
    }


def validate_artifact(
    artifact: Path,
    contract_path: Path,
    renderer_mode: str,
    visual_verdict: str,
) -> dict[str, Any]:
    layers = initial_layers()
    resolved_artifact = artifact.expanduser().resolve()
    artifact_hash_before: str | None = None
    try:
        inputs = load_inputs(resolved_artifact, contract_path)
    except ValidationInputError as error:
        fail_unavailable_layers(layers, str(error), str(contract_path))
        return build_report(resolved_artifact, layers, None)

    data_layer = layers["data_correctness"]
    source_hashes_before = source_hashes(inputs, data_layer)
    try:
        artifact_hash_before = sha256_file(inputs.artifact)
    except OSError as error:
        fail_unavailable_layers(
            layers,
            f"cannot read required output artifact {inputs.artifact}: {error}",
            str(inputs.artifact),
        )
        return build_report(inputs.artifact, layers, None)

    try:
        workbook = read_workbook_artifact(inputs.artifact)
    except ValidationInputError as error:
        fail_unavailable_layers(layers, str(error), str(inputs.artifact))
        return build_report(inputs.artifact, layers, artifact_hash_before)

    data_layer.check(
        "independent_ooxml_reader",
        True,
        source=str(inputs.artifact),
        expected="fresh read-only ZIP/XML reopen after writer completion",
        actual={"reader": "python zipfile + ElementTree", "sheets": [s.name for s in workbook.sheets]},
    )
    issue_sheet, resolved_columns, actual_issue_cells, _ = validate_data(
        inputs,
        workbook,
        data_layer,
    )
    validate_preservation(inputs, workbook, data_layer)
    validate_visibility(
        inputs,
        workbook,
        issue_sheet,
        resolved_columns,
        actual_issue_cells,
        layers["visibility"],
    )
    validate_formula_cache(inputs, workbook, layers["formula_cache"])
    validate_rendering(
        inputs,
        workbook,
        layers["rendering"],
        renderer_mode,
        visual_verdict,
    )

    for path, expected_hash in inputs.source_artifacts:
        try:
            actual_hash = sha256_file(path)
        except OSError:
            actual_hash = None
        data_layer.check(
            "source_artifact_unchanged_by_validation",
            source_hashes_before.get(path) == actual_hash == expected_hash,
            source=str(path),
            expected=expected_hash,
            actual=actual_hash,
            reason=f"source/seed changed while the read-only validator was running: {path}",
        )

    try:
        artifact_hash_after = sha256_file(inputs.artifact)
    except OSError:
        artifact_hash_after = None
    layers["rendering"].check(
        "artifact_unchanged_by_validation",
        artifact_hash_after == artifact_hash_before,
        source=str(inputs.artifact),
        expected=artifact_hash_before,
        actual=artifact_hash_after,
        reason="the validator or renderer changed the artifact under validation",
    )
    return build_report(inputs.artifact, layers, artifact_hash_after)


def parse_arguments(argv: Sequence[str]) -> argparse.Namespace:
    parser = UsageParser(description=__doc__)
    parser.add_argument(
        "artifact",
        type=Path,
        help="closed, persisted .xlsx output to reopen read-only",
    )
    parser.add_argument(
        "--contract",
        type=Path,
        required=True,
        help="JSON contract containing confirmed mapping, CSV, statistics, range, and preflight path",
    )
    parser.add_argument(
        "--renderer",
        choices=("auto", "none"),
        default="auto",
        help="probe an existing LibreOffice renderer, or declare it unavailable",
    )
    parser.add_argument(
        "--visual-verdict",
        choices=("pass", "fail", "not-run"),
        default="not-run",
        help="record a visual inspection result; without it, rendering remains NOT RUN",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = parse_arguments(sys.argv[1:] if argv is None else argv)
    report = validate_artifact(
        arguments.artifact,
        arguments.contract,
        arguments.renderer,
        arguments.visual_verdict,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return {
        "PASS": EXIT_PASS,
        "PARTIAL": EXIT_PARTIAL,
        "FAIL": EXIT_FAIL,
    }[report["outcome"]]


if __name__ == "__main__":
    raise SystemExit(main())
