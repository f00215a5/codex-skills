#!/usr/bin/env python3
"""Read-only structural audit for a UI-manual DOCX.

This helper checks only OOXML structure and package hashes.  By default it
does not read document text or image pixels, so it cannot prove redaction,
OCR, annotation meaning, or visual correctness.  Its opt-in default-layout
gate reads only the first update-record header tokens and never reports their
text.  A zero exit code means that the audit report was written; callers use
``mechanical_status`` and ``independent_review.status`` for delivery decisions.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import posixpath
import re
import sys
import zipfile
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence
from xml.etree import ElementTree as ET


SCHEMA_VERSION = 1
CHECK_NAMES = ("requirements", "redaction", "visual", "operation")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
REL_NAMESPACE = "http://schemas.openxmlformats.org/package/2006/relationships"


class AuditInputError(Exception):
    """An input package could not be inspected safely."""


def _local(element_or_tag: ET.Element | str) -> str:
    tag = element_or_tag.tag if isinstance(element_or_tag, ET.Element) else element_or_tag
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    if element is None:
        return []
    return [child for child in list(element) if _local(child) == name]


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    children = _children(element, name)
    return children[0] if children else None


def _descendants(element: ET.Element | None, name: str) -> Iterable[ET.Element]:
    if element is None:
        return ()
    return (child for child in element.iter() if _local(child) == name)


def _attr(element: ET.Element | None, name: str) -> str | None:
    if element is None:
        return None
    for key, value in element.attrib.items():
        if _local(key) == name:
            return value
    return None


def _integer(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _hash(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip().lower()
    return value if SHA256_RE.fullmatch(value) else None


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_xml(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise AuditInputError("xml_parse_error") from exc


def _status_rank(status: str) -> int:
    return {
        "pass": 0,
        "manual_review": 1,
        "blocked": 2,
        "fail": 3,
        "failed": 3,
    }.get(status, 2)


def _combine(statuses: Iterable[str], default: str = "manual_review") -> str:
    values = list(statuses)
    return max(values, key=_status_rank) if values else default


def _combine_mechanical(*statuses: str) -> str:
    status = _combine(statuses)
    return "failed" if status in {"fail", "failed"} else status


def _style_alignments(styles_root: ET.Element | None) -> dict[str, str | None]:
    """Resolve table style jc values through a bounded basedOn chain."""

    if styles_root is None:
        return {}
    styles: dict[str, tuple[str | None, str | None]] = {}
    for style in _children(styles_root, "style"):
        if _attr(style, "type") != "table":
            continue
        style_id = _attr(style, "styleId")
        if not style_id:
            continue
        table_pr = _child(style, "tblPr")
        jc = _attr(_child(table_pr, "jc"), "val")
        base = _attr(_child(style, "basedOn"), "val")
        styles[style_id] = (jc, base)

    resolved: dict[str, str | None] = {}

    def resolve(style_id: str, trail: set[str]) -> str | None:
        if style_id in resolved:
            return resolved[style_id]
        if style_id in trail:
            return None
        own, base = styles.get(style_id, (None, None))
        if own is not None:
            resolved[style_id] = own
            return own
        value = resolve(base, trail | {style_id}) if base else None
        resolved[style_id] = value
        return value

    for style_id in styles:
        resolve(style_id, set())
    return resolved


def _alignment(table: ET.Element, styles: Mapping[str, str | None]) -> dict[str, Any]:
    table_pr = _child(table, "tblPr")
    direct = _child(table_pr, "jc")
    value = _attr(direct, "val")
    source = "direct" if direct is not None and value is not None else "unknown"
    if source == "unknown":
        style_id = _attr(_child(table_pr, "tblStyle"), "val")
        value = styles.get(style_id) if style_id else None
        if style_id and style_id in styles and value is not None:
            source = "table_style"
    if value == "center":
        status = "pass"
    elif value in {"left", "right", "both", "distribute", "start", "end"}:
        status = "fail"
    else:
        status = "manual_review"
    result: dict[str, Any] = {"status": status, "source": source}
    if value is not None:
        result["value"] = value
    return result


def _table_width(table: ET.Element) -> dict[str, Any]:
    table_pr = _child(table, "tblPr")
    width = _child(table_pr, "tblW")
    width_type = _attr(width, "type") or "unknown"
    width_value = _integer(_attr(width, "w"))
    layout = _attr(_child(table_pr, "tblLayout"), "type") or "autofit"
    result: dict[str, Any] = {"layout": layout, "type": width_type}
    if width_value is not None:
        result["value"] = width_value

    # Percent widths and fixed+auto widths are dynamic/ambiguous, but valid
    # Word constructs.  Leave them for the independent visual reviewer.
    if width_type == "pct" or (layout == "fixed" and width_type == "auto"):
        result.update(status="manual_review", dynamic=True)
    elif width_type in {"dxa", "auto"}:
        result.update(status="pass", dynamic=width_type == "auto")
    else:
        result["status"] = "manual_review"
    return result


def _grid_columns(table: ET.Element) -> list[int] | None:
    grid = _child(table, "tblGrid")
    if grid is None:
        return None
    columns: list[int] = []
    for item in _children(grid, "gridCol"):
        width = _integer(_attr(item, "w"))
        if width is None or width <= 0:
            return None
        columns.append(width)
    return columns or None


def _cell_width(cell: ET.Element) -> tuple[str | None, int | None]:
    width = _child(_child(cell, "tcPr"), "tcW")
    return _attr(width, "type"), _integer(_attr(width, "w"))


def _row_offset(row: ET.Element, name: str) -> int:
    value = _integer(_attr(_child(_child(row, "trPr"), name), "val"))
    return value if value is not None and value >= 0 else 0


def _cell_span(cell: ET.Element) -> tuple[int | None, bool]:
    properties = _child(cell, "tcPr")
    span_element = _child(properties, "gridSpan")
    span = _integer(_attr(span_element, "val")) if span_element is not None else 1
    if span is None or span <= 0:
        return None, False
    complex_merge = _child(properties, "vMerge") is not None or _child(properties, "hMerge") is not None
    return span, complex_merge


def _grid_audit(table: ET.Element) -> dict[str, Any]:
    columns = _grid_columns(table)
    rows = _children(table, "tr")
    result: dict[str, Any] = {
        "status": "pass",
        "rows": len(rows),
        "checked_cells": 0,
        "merged_cells": 0,
    }
    if columns is None:
        result.update(status="manual_review", reason_code="grid_unavailable")
        return result
    result.update(columns=len(columns), grid_width_twips=sum(columns))
    mismatches: list[dict[str, Any]] = []
    review_reasons: set[str] = set()

    for row_index, row in enumerate(rows, start=1):
        cursor = _row_offset(row, "gridBefore")
        for cell_index, cell in enumerate(_children(row, "tc"), start=1):
            span, complex_merge = _cell_span(cell)
            if span is None:
                review_reasons.add("invalid_grid_span")
                continue
            if span > 1:
                result["merged_cells"] += 1
            if complex_merge:
                review_reasons.add("complex_merge")
            end = cursor + span
            if end > len(columns):
                review_reasons.add("grid_span_out_of_range")
                cursor = end
                continue
            expected = sum(columns[cursor:end])
            width_type, actual = _cell_width(cell)
            result["checked_cells"] += 1
            if width_type == "dxa" and actual is not None and actual >= 0:
                if actual != expected:
                    mismatches.append(
                        {
                            "code": "cell_width_mismatch",
                            "row_index": row_index,
                            "cell_index": cell_index,
                            "span": span,
                            "expected_twips": expected,
                            "actual_twips": actual,
                        }
                    )
            else:
                review_reasons.add("dynamic_or_missing_cell_width")
            cursor = end
        if cursor + _row_offset(row, "gridAfter") != len(columns):
            review_reasons.add("row_grid_coverage_uncertain")

    if mismatches:
        result.update(status="fail", findings=mismatches)
    elif review_reasons:
        result.update(status="manual_review", review_reasons=sorted(review_reasons))
    return result


def _top_level_tables(root: ET.Element) -> tuple[list[ET.Element], bool]:
    body = _child(root, "body")
    if body is None:
        return [], False
    tables: list[ET.Element] = []
    wrapped = False
    for child in list(body):
        if _local(child) == "tbl":
            tables.append(child)
        elif _local(child) in {"sdt", "customXml"} and any(_descendants(child, "tbl")):
            wrapped = True
    return tables, wrapped


def _cell_text(cell: ET.Element) -> str:
    """Collect cell text for the opt-in default-layout header gate only."""

    return "".join((node.text or "") for node in _descendants(cell, "t"))


def _default_layout_table(root: ET.Element) -> ET.Element | None:
    """Return the first body table, skipping only a structural one-cell wrapper.

    A one-cell table is treated as a layout container only when it contains a
    nested table.  A one-cell table without a nested table remains the
    candidate and therefore fails the three-column header check.
    """

    body = _child(root, "body")
    if body is None:
        return None
    table = next((child for child in list(body) if _local(child) == "tbl"), None)
    while table is not None:
        rows = _children(table, "tr")
        cells = _children(rows[0], "tc") if rows else []
        if len(cells) != 1:
            return table
        nested = [item for item in _descendants(cells[0], "tbl") if item is not table]
        if not nested:
            return table
        table = nested[0]
    return None


def _default_layout_header_audit(root: ET.Element) -> tuple[str, list[str]]:
    """Check only the default update-record header, without returning text."""

    table = _default_layout_table(root)
    if table is None:
        return "fail", ["update_record_table_missing"]
    rows = _children(table, "tr")
    if not rows:
        return "fail", ["update_record_header_row_missing"]
    cells = _children(rows[0], "tc")
    if len(cells) != 3:
        return "fail", ["update_record_header_columns_invalid"]
    normalized = [re.sub(r"\s+", "", _cell_text(cell)) for cell in cells]
    required = ("版本", "日期", "更新內容")
    if any(token not in value for token, value in zip(required, normalized)):
        return "fail", ["update_record_header_missing"]
    return "pass", []


def _numbering_audit(numbering_root: ET.Element | None, document_root: ET.Element) -> list[dict[str, str]]:
    """Check bounded numbering.xml structure and references without reading text."""

    document_num_ids = {
        value
        for element in _descendants(document_root, "numId")
        if (value := _attr(element, "val")) is not None and _integer(value) != 0
    }
    findings: list[dict[str, str]] = []
    if numbering_root is None:
        if document_num_ids or any(_attr(element, "val") is None for element in _descendants(document_root, "numId")):
            findings.append({"code": "numbering_num_id_missing"})
        return findings

    top_level = list(numbering_root)
    abstract_indexes = [index for index, element in enumerate(top_level) if _local(element) == "abstractNum"]
    num_indexes = [index for index, element in enumerate(top_level) if _local(element) == "num"]
    if abstract_indexes and num_indexes and max(abstract_indexes) > min(num_indexes):
        findings.append({"code": "numbering_abstract_num_after_num"})

    for level in _descendants(numbering_root, "lvl"):
        child_names = [_local(child) for child in list(level)]
        try:
            suff_index = child_names.index("suff")
            lvl_text_index = child_names.index("lvlText")
        except ValueError:
            continue
        if suff_index > lvl_text_index:
            findings.append({"code": "numbering_suff_after_lvl_text"})

    abstract_ids = {
        value
        for element in top_level
        if _local(element) == "abstractNum"
        if (value := _attr(element, "abstractNumId")) is not None
    }
    num_ids = {
        value
        for element in top_level
        if _local(element) == "num"
        if (value := _attr(element, "numId")) is not None
    }
    for value in document_num_ids:
        if value not in num_ids:
            findings.append({"code": "numbering_num_id_missing"})
            break
    if any(_attr(element, "val") is None for element in _descendants(document_root, "numId")):
        findings.append({"code": "numbering_num_id_missing"})

    for element in top_level:
        if _local(element) != "num":
            continue
        abstract_ref = _attr(_child(element, "abstractNumId"), "val")
        if abstract_ref is None or abstract_ref not in abstract_ids:
            findings.append({"code": "numbering_abstract_num_id_missing"})
            break
    return findings


def _relationship_source(path: str) -> str:
    marker = "/_rels/"
    if marker not in path or not path.endswith(".rels"):
        return ""
    parent, filename = path.split(marker, 1)
    return posixpath.join(parent, filename[:-5])


def _relationship_target(rels_path: str, target: str) -> str | None:
    if not target or "://" in target or target.startswith("mailto:"):
        return None
    source = _relationship_source(rels_path)
    if not source:
        return None
    target = target.replace("\\", "/")
    if target.startswith("/"):
        return posixpath.normpath(target[1:])
    return posixpath.normpath(posixpath.join(posixpath.dirname(source), target))


def _package_media(package: zipfile.ZipFile, names: Sequence[str]) -> dict[str, Any]:
    media_names = sorted(name for name in names if name.startswith("word/media/") and not name.endswith("/"))
    referenced: set[str] = set()
    for rels_name in names:
        if not rels_name.endswith(".rels"):
            continue
        try:
            root = _parse_xml(package.read(rels_name))
        except (KeyError, AuditInputError):
            continue
        for relation in _descendants(root, "Relationship"):
            target = _relationship_target(rels_name, _attr(relation, "Target") or "")
            if target in media_names:
                referenced.add(target)

    media: list[dict[str, Any]] = []
    unreferenced: list[str] = []
    for index, name in enumerate(media_names, start=1):
        data = package.read(name)
        item = {
            "index": index,
            "filename": name,
            "size_bytes": len(data),
            "sha256": _sha256_bytes(data),
            "referenced": name in referenced,
        }
        media.append(item)
        if name not in referenced:
            unreferenced.append(name)
    return {
        "status": "manual_review" if unreferenced else "pass",
        "media": media,
        "unreferenced_media": unreferenced,
    }


def _read_review(path: Path | None) -> tuple[Any, str | None]:
    if path is None:
        return None, None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream), None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "review_invalid"


def _review_identity(container: Any) -> str | None:
    if not isinstance(container, Mapping):
        return None
    value = container.get("id")
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.casefold() in {"pending", "independent review pending", "unknown", "todo", "tbd", "none", "null"}:
        return None
    return value


def _reviewed_path(path_value: Any, review_path: Path | None) -> Path | None:
    if not isinstance(path_value, str) or not path_value.strip():
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        if review_path is None:
            return None
        candidate = review_path.parent / candidate
    try:
        candidate = candidate.resolve()
    except OSError:
        return None
    return candidate if candidate.is_file() else None


def _filename(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return posixpath.basename(value.replace("\\", "/").rstrip("/")) or None


def _check_evidence_refs(evidence: Any, reviewed_paths: set[str]) -> tuple[int, list[str]]:
    if not isinstance(evidence, list):
        return 0, ["evidence_missing"]
    if not evidence:
        return 0, []
    problems: list[str] = []
    for item in evidence:
        if not isinstance(item, str) or not item.strip():
            problems.append("evidence_invalid")
            continue
        # Evidence references are intentionally exact.  Prefixes, fragments,
        # and basename-only shortcuts could make a missing support file look
        # reviewed, so the reviewer must cite reviewed_files.path verbatim.
        reference = item.strip().replace("\\", "/")
        if reference not in reviewed_paths:
            problems.append("evidence_reference_missing")
    return len(evidence), problems


def _review_check(raw: Any, name: str, reviewed_paths: set[str]) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(raw, Mapping):
        return {"status": "blocked", "evidence_count": 0, "reason_provided": False}, [f"check_{name}_missing"]
    status = raw.get("status")
    status = status.strip().lower() if isinstance(status, str) else ""
    if status == "failed":
        status = "fail"
    reason = raw.get("reason")
    reason_provided = isinstance(reason, str) and bool(reason.strip())
    evidence_count, problems = _check_evidence_refs(raw.get("evidence"), reviewed_paths)
    result = {
        "status": status if status in {"pass", "fail", "blocked", "na"} else "blocked",
        "evidence_count": evidence_count,
        "reason_provided": reason_provided,
    }
    if status not in {"pass", "fail", "blocked", "na"}:
        problems.append(f"check_{name}_status_invalid")
    if not reason_provided:
        problems.append(f"check_{name}_reason_missing")
        if result["status"] == "pass":
            result["status"] = "blocked"
    if result["status"] == "pass" and evidence_count == 0:
        result["status"] = "blocked"
        problems.append(f"check_{name}_evidence_missing")
    if result["status"] == "na":
        if not reason_provided:
            result["status"] = "blocked"
            problems.append(f"check_{name}_na_reason_missing")
        if name in {"requirements", "visual"}:
            result["status"] = "fail"
            problems.append(f"check_{name}_cannot_be_na")
    if problems and result["status"] in {"pass", "na"}:
        result["status"] = "blocked"
    return result, problems


def _independent_review(
    review: Any,
    review_path: Path | None,
    docx: Path,
    docx_sha256: str | None,
    media_hashes: set[str],
) -> tuple[dict[str, Any], list[str]]:
    empty_checks = {name: {"status": "blocked", "evidence_count": 0, "reason_provided": False} for name in CHECK_NAMES}
    if review is None:
        return {"status": "blocked", "reason_code": "review_missing", "checks": empty_checks}, ["review_missing"]
    if not isinstance(review, Mapping):
        return {"status": "blocked", "reason_code": "review_invalid", "checks": empty_checks}, ["review_invalid"]

    reasons: list[str] = []
    schema = review.get("schema_version")
    if not isinstance(schema, int) or isinstance(schema, bool) or schema != SCHEMA_VERSION:
        reasons.append("review_schema_invalid")

    artifact = review.get("artifact")
    artifact = artifact if isinstance(artifact, Mapping) else {}
    declared_artifact_hash = _hash(artifact.get("sha256"))
    artifact_status = "match" if declared_artifact_hash and declared_artifact_hash == docx_sha256 else "blocked"
    if declared_artifact_hash is None:
        reasons.append("artifact_hash_missing_or_invalid")
    elif declared_artifact_hash != docx_sha256:
        reasons.append("artifact_hash_mismatch")

    builder = _review_identity(review.get("builder"))
    reviewer = _review_identity(review.get("reviewer"))
    identities_explicit = builder is not None and reviewer is not None
    identities_distinct = identities_explicit and builder.casefold() != reviewer.casefold()
    if not identities_explicit:
        reasons.append("identities_missing")
    elif not identities_distinct:
        reasons.append("reviewer_not_distinct")

    reviewed_files = review.get("reviewed_files")
    reviewed_files = reviewed_files if isinstance(reviewed_files, list) else []
    reviewed_paths: set[str] = set()
    reviewed_results: list[dict[str, Any]] = []
    file_statuses: list[str] = []
    page_count = image_count = support_count = 0
    for index, item in enumerate(reviewed_files, start=1):
        kind = item.get("kind") if isinstance(item, Mapping) else None
        raw_path = item.get("path") if isinstance(item, Mapping) else None
        declared_hash = _hash(item.get("sha256")) if isinstance(item, Mapping) else None
        path = _reviewed_path(raw_path, review_path)
        actual_hash = _sha256_file(path) if path else None
        status = "pass" if kind in {"page", "image", "support"} and declared_hash and actual_hash == declared_hash else "blocked"
        file_statuses.append(status)
        if isinstance(raw_path, str):
            reviewed_paths.add(raw_path.replace("\\", "/"))
        if kind == "page":
            page_count += 1
        elif kind == "image":
            image_count += 1
        elif kind == "support":
            support_count += 1
        result: dict[str, Any] = {"index": index, "status": status, "kind": kind if kind in {"page", "image", "support"} else "unknown"}
        name = _filename(raw_path)
        if name:
            result["filename"] = name
        if declared_hash:
            result["sha256"] = declared_hash
        reviewed_results.append(result)
    if not page_count:
        reasons.append("page_evidence_missing")
    if not support_count:
        reasons.append("support_evidence_missing")
    media_count = len(media_hashes)
    image_hashes: set[str] = set()
    for item, status in zip(reviewed_files, file_statuses):
        if status == "pass" and isinstance(item, Mapping) and item.get("kind") == "image":
            digest = _hash(item.get("sha256"))
            if digest:
                image_hashes.add(digest)
    if media_count and not image_count:
        reasons.append("image_evidence_missing")
    elif media_count and image_count < media_count:
        reasons.append("image_evidence_incomplete")
    if media_hashes - image_hashes:
        reasons.append("image_evidence_unmatched")
    if any(status != "pass" for status in file_statuses):
        reasons.append("reviewed_file_hash_unverified")

    raw_checks = review.get("checks")
    raw_checks = raw_checks if isinstance(raw_checks, Mapping) else {}
    checks: dict[str, dict[str, Any]] = {}
    for name in CHECK_NAMES:
        check, check_reasons = _review_check(raw_checks.get(name), name, reviewed_paths)
        checks[name] = check
        reasons.extend(check_reasons)
    if checks["visual"]["status"] == "pass" and not page_count:
        checks["visual"]["status"] = "blocked"
        reasons.append("visual_page_evidence_missing")
    if media_count and checks["redaction"]["status"] == "pass" and not image_count:
        checks["redaction"]["status"] = "blocked"
        reasons.append("redaction_image_evidence_missing")

    aggregate_statuses = (
        "pass" if name in {"redaction", "operation"} and check["status"] == "na" else check["status"]
        for name, check in checks.items()
    )
    check_status = _combine(aggregate_statuses, default="blocked")
    declared_overall = review.get("overall")
    if not isinstance(declared_overall, str) or declared_overall.strip().lower() not in {"pass", "fail", "blocked"}:
        reasons.append("overall_invalid")
        declared_overall = "blocked"
    else:
        declared_overall = declared_overall.strip().lower()

    if declared_overall == "fail" or check_status == "fail":
        status = "fail"
    elif (
        not isinstance(schema, int)
        or isinstance(schema, bool)
        or schema != SCHEMA_VERSION
        or artifact_status != "match"
        or not identities_distinct
        or any(status != "pass" for status in file_statuses)
        or not page_count
        or not support_count
        or (media_count and not image_count)
        or (media_count and image_count < media_count)
        or bool(media_hashes - image_hashes)
        or check_status != "pass"
        or declared_overall != "pass"
    ):
        status = "blocked"
    else:
        status = "pass"

    result: dict[str, Any] = {
        "status": status,
        "artifact": {"sha256": declared_artifact_hash, "status": artifact_status},
        "identities": {"explicit": identities_explicit, "distinct": identities_distinct},
        "reviewed_files": reviewed_results,
        "checks": checks,
    }
    if reasons:
        result["reason_codes"] = sorted(set(reasons))
    return result, sorted(set(reasons))


def audit_docx(
    docx_path: str | Path,
    review_path: str | Path | None = None,
    require_default_layout: bool = False,
) -> dict[str, Any]:
    """Return a safe report for a DOCX and optional independent review JSON."""

    docx = Path(docx_path)
    review = Path(review_path) if review_path is not None else None
    document_info: dict[str, Any] = {"filename": docx.name}
    docx_sha256: str | None = None
    try:
        document_info["size_bytes"] = docx.stat().st_size
        docx_sha256 = _sha256_file(docx)
        document_info["sha256"] = docx_sha256
    except OSError:
        document_info["status"] = "unreadable"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "docx": document_info,
        "tables": [],
        "package": {"status": "blocked", "media": [], "unreferenced_media": []},
        "limitations": [
            "document_text_not_inspected",
            "image_pixels_and_redaction_not_inspected",
            "ocr_not_run",
            "visual_and_operation_not_proven_by_structure",
            "numbering_only_checks_direct_document_numId_refs_styles_not_resolved",
        ],
    }
    if require_default_layout:
        report["limitations"].remove("document_text_not_inspected")
        report["limitations"].append("document_text_only_checked_for_default_update_header_tokens")
    mechanical_status = "failed" if docx_sha256 is None else "pass"
    findings: list[dict[str, Any]] = []
    media_hashes: set[str] = set()

    try:
        with zipfile.ZipFile(docx, "r") as package:
            names = [info.filename for info in package.infolist() if not info.is_dir()]
            media = _package_media(package, names)
            report["package"] = media
            media_hashes = {item["sha256"] for item in media["media"] if item.get("sha256")}
            if media["status"] != "pass":
                mechanical_status = _combine_mechanical(mechanical_status, "manual_review")
                for item in media["media"]:
                    if not item["referenced"]:
                        findings.append(
                            {
                                "code": "unreferenced_media",
                                "media_index": item["index"],
                                "filename": item["filename"],
                                "size_bytes": item["size_bytes"],
                                "sha256": item["sha256"],
                            }
                        )

            try:
                document_root = _parse_xml(package.read("word/document.xml"))
            except KeyError as exc:
                raise AuditInputError("document_xml_missing") from exc
            numbering_root: ET.Element | None = None
            if "word/numbering.xml" in names:
                try:
                    numbering_root = _parse_xml(package.read("word/numbering.xml"))
                except AuditInputError:
                    findings.append({"code": "numbering_xml_unavailable"})
                    mechanical_status = _combine_mechanical(mechanical_status, "failed")
            numbering_findings = _numbering_audit(numbering_root, document_root)
            findings.extend(numbering_findings)
            if numbering_findings:
                mechanical_status = _combine_mechanical(mechanical_status, "failed")
            styles_root: ET.Element | None = None
            if "word/styles.xml" in names:
                try:
                    styles_root = _parse_xml(package.read("word/styles.xml"))
                except AuditInputError:
                    findings.append({"code": "styles_xml_unavailable"})
                    mechanical_status = _combine_mechanical(mechanical_status, "manual_review")

            styles = _style_alignments(styles_root)
            tables, wrapped = _top_level_tables(document_root)
            if wrapped:
                findings.append({"code": "table_container_uncertain"})
                mechanical_status = _combine_mechanical(mechanical_status, "manual_review")
            if not tables:
                findings.append({"code": "top_level_table_missing"})
                mechanical_status = _combine_mechanical(mechanical_status, "manual_review")

            if require_default_layout:
                layout_status, layout_findings = _default_layout_header_audit(document_root)
                report["default_layout"] = {"status": layout_status}
                for code in layout_findings:
                    findings.append({"code": code})
                if layout_status == "fail":
                    mechanical_status = _combine_mechanical(mechanical_status, "failed")

            for index, table in enumerate(tables, start=1):
                alignment = _alignment(table, styles)
                width = _table_width(table)
                grid = _grid_audit(table)
                table_status = _combine((alignment["status"], width["status"], grid["status"]), default="manual_review")
                report["tables"].append(
                    {
                        "index": index,
                        "status": table_status,
                        "alignment": alignment,
                        "width": width,
                        "grid": grid,
                    }
                )
                if alignment["status"] == "fail":
                    findings.append({"code": "table_alignment_not_center", "table_index": index})
                if grid.get("status") == "fail":
                    for item in grid.get("findings", []):
                        finding = {"table_index": index}
                        finding.update(item)
                        findings.append(finding)
                if width.get("status") == "manual_review" and width.get("layout") == "fixed":
                    findings.append({"code": "fixed_table_width_needs_review", "table_index": index})
                mechanical_status = _combine_mechanical(mechanical_status, table_status)
    except (OSError, zipfile.BadZipFile, AuditInputError):
        findings.append({"code": "docx_package_unreadable"})
        mechanical_status = "failed"

    report["mechanical_status"] = mechanical_status
    report["findings"] = findings
    review_value, review_error = _read_review(review)
    independent, _ = _independent_review(review_value, review, docx, docx_sha256, media_hashes)
    if review_error:
        independent = {"status": "blocked", "reason_code": review_error, "checks": {name: {"status": "blocked", "evidence_count": 0, "reason_provided": False} for name in CHECK_NAMES}}
    report["independent_review"] = independent

    return report


def _write_report(report: Mapping[str, Any], output: str) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output == "-":
        sys.stdout.write(payload)
        return
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _output_conflicts(output: str, docx: str | Path, review: str | Path | None) -> bool:
    """Prevent an output path from replacing an input or reviewed evidence."""

    if output == "-":
        return False
    destination = _resolved(output)
    inputs = [_resolved(docx)]
    if review is not None:
        review_input = _resolved(review)
        inputs.append(review_input)
        try:
            with review_input.open("r", encoding="utf-8") as stream:
                review_value = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError):
            review_value = None
        if isinstance(review_value, Mapping) and isinstance(review_value.get("reviewed_files"), list):
            for item in review_value["reviewed_files"]:
                if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                    continue
                evidence_path = Path(item["path"])
                if not evidence_path.is_absolute():
                    evidence_path = review_input.parent / evidence_path
                inputs.append(evidence_path.resolve())
    return any(os.path.normcase(destination) == os.path.normcase(path) for path in inputs)


def _execution_failed(report: Mapping[str, Any]) -> bool:
    if report.get("docx", {}).get("status") == "unreadable":
        return True
    return any(item.get("code") == "docx_package_unreadable" for item in report.get("findings", []))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a UI-manual DOCX without reading text or image pixels.")
    parser.add_argument("--docx", required=True, help="DOCX path to inspect")
    parser.add_argument("--output", required=True, help="JSON output path, or - for stdout")
    parser.add_argument("--review", help="Optional independent review JSON path")
    parser.add_argument(
        "--require-default-layout",
        action="store_true",
        help="Require the first default-layout update-record table header",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if _output_conflicts(args.output, args.docx, args.review):
        return 2
    report = audit_docx(args.docx, args.review, args.require_default_layout)
    try:
        _write_report(report, args.output)
    except OSError:
        return 2
    return 2 if _execution_failed(report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
