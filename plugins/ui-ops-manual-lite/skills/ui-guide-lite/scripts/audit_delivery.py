#!/usr/bin/env python3
"""Read-only delivery audit for a lite UI-manual DOCX.

The audit reads OOXML structure, package media and hashes.  It deliberately
does not inspect document text or image pixels and therefore cannot prove that
all sensitive values were found, that a redaction is irreversible, or that a
box points at the right control.  A zero exit code means only that the JSON
report was written; callers must inspect ``mechanical_status`` and
``independent_review.status``.

Lite review differs from the full UI-manual profile: no rendered page is
required.  The review artifact records ``render_visual`` as
``not_performed`` or ``out_of_scope``.  ``pass`` is intentionally rejected for
that field because this package has no renderer.
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
CHECK_NAMES = ("requirements", "redaction", "operation", "layout_structure")
SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class AuditInputError(Exception):
    """Raised when a package cannot be safely inspected."""


def _local(element_or_tag: ET.Element | str) -> str:
    tag = element_or_tag.tag if isinstance(element_or_tag, ET.Element) else element_or_tag
    return tag.rsplit("}", 1)[-1]


def _children(element: ET.Element | None, name: str) -> list[ET.Element]:
    if element is None:
        return []
    return [child for child in list(element) if _local(child) == name]


def _child(element: ET.Element | None, name: str) -> ET.Element | None:
    values = _children(element, name)
    return values[0] if values else None


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_xml(data: bytes) -> ET.Element:
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise AuditInputError("xml_parse_error") from error


def _rank(status: str) -> int:
    return {"pass": 0, "manual_review": 1, "blocked": 2, "fail": 3, "failed": 3}.get(status, 2)


def _combine(statuses: Iterable[str], default: str = "manual_review") -> str:
    values = list(statuses)
    return max(values, key=_rank) if values else default


def _style_alignments(styles_root: ET.Element | None) -> dict[str, str | None]:
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
        styles[style_id] = (
            _attr(_child(table_pr, "jc"), "val"),
            _attr(_child(style, "basedOn"), "val"),
        )
    resolved: dict[str, str | None] = {}

    def resolve(style_id: str, trail: set[str]) -> str | None:
        if style_id in resolved:
            return resolved[style_id]
        if style_id in trail:
            return None
        own, base = styles.get(style_id, (None, None))
        value = own if own is not None else (resolve(base, trail | {style_id}) if base else None)
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
        if style_id and value is not None:
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
    if width_type == "pct":
        # Percentage table width and twip grid columns are independent OOXML
        # units.  Do not compare their numeric values.  Autofit percentage
        # tables are a valid dynamic layout; fixed percentage geometry needs
        # an explicit reviewer decision.
        if width_value is not None and not 0 <= width_value <= 5000:
            result.update(status="fail", reason_code="percentage_width_out_of_range")
        elif layout == "autofit":
            result.update(status="pass", dynamic=True, units_independent=True)
        else:
            result.update(status="manual_review", dynamic=True, units_independent=True)
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


def _grid_audit(table: ET.Element) -> dict[str, Any]:
    columns = _grid_columns(table)
    rows = _children(table, "tr")
    result: dict[str, Any] = {"status": "pass", "rows": len(rows), "checked_cells": 0, "merged_cells": 0}
    if columns is None:
        result.update(status="manual_review", reason_code="grid_unavailable")
        return result
    result["columns"] = len(columns)
    result["grid_width_twips"] = sum(columns)
    mismatches: list[dict[str, Any]] = []
    review_reasons: set[str] = set()
    for row_index, row in enumerate(rows, start=1):
        cursor = _integer(_attr(_child(_child(row, "trPr"), "gridBefore"), "val")) or 0
        for cell_index, cell in enumerate(_children(row, "tc"), start=1):
            properties = _child(cell, "tcPr")
            span_value = _integer(_attr(_child(properties, "gridSpan"), "val")) or 1
            if span_value <= 0:
                review_reasons.add("invalid_grid_span")
                continue
            if span_value > 1:
                result["merged_cells"] += 1
            end = cursor + span_value
            if end > len(columns):
                review_reasons.add("grid_span_out_of_range")
                cursor = end
                continue
            expected = sum(columns[cursor:end])
            width_type, actual = _cell_width(cell)
            result["checked_cells"] += 1
            if width_type == "dxa" and actual is not None and actual >= 0:
                if actual != expected:
                    mismatches.append({
                        "code": "cell_width_mismatch",
                        "row_index": row_index,
                        "cell_index": cell_index,
                        "span": span_value,
                        "expected_twips": expected,
                        "actual_twips": actual,
                    })
            else:
                review_reasons.add("dynamic_or_missing_cell_width")
            cursor = end
        grid_after = _integer(_attr(_child(_child(row, "trPr"), "gridAfter"), "val")) or 0
        if cursor + grid_after != len(columns):
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
    return {"status": "manual_review" if unreferenced else "pass", "media": media, "unreferenced_media": unreferenced}


def _read_json(path: Path | None) -> tuple[Any, str | None]:
    if path is None:
        return None, None
    try:
        with path.open("r", encoding="utf-8") as stream:
            return json.load(stream), None
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, "review_invalid"


def _review_identity(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    identity = value.get("id")
    if not isinstance(identity, str) or not identity.strip():
        return None
    identity = identity.strip()
    if identity.casefold() in {"pending", "independent review pending", "unknown", "todo", "tbd", "none", "null"}:
        return None
    return identity


def _resolved_reviewed_path(value: Any, review_path: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = review_path.parent / candidate
    try:
        candidate = candidate.expanduser().resolve()
    except OSError:
        return None
    return candidate if candidate.is_file() else None


def _filename(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    return posixpath.basename(value.replace("\\", "/").rstrip("/")) or None


def _evidence_refs(evidence: Any, reviewed_paths: set[str]) -> tuple[int, list[str]]:
    if not isinstance(evidence, list):
        return 0, ["evidence_missing"]
    problems: list[str] = []
    for item in evidence:
        if not isinstance(item, str) or not item.strip():
            problems.append("evidence_invalid")
            continue
        if item.strip().replace("\\", "/") not in reviewed_paths:
            problems.append("evidence_reference_missing")
    return len(evidence), problems


def _check_entry(raw: Any, name: str, reviewed_paths: set[str]) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(raw, Mapping):
        return {"status": "blocked", "evidence_count": 0, "reason_provided": False}, [f"check_{name}_missing"]
    status = raw.get("status")
    status = status.strip().casefold() if isinstance(status, str) else ""
    if status == "failed":
        status = "fail"
    reason = raw.get("reason")
    reason_ok = isinstance(reason, str) and bool(reason.strip())
    evidence_count, problems = _evidence_refs(raw.get("evidence"), reviewed_paths)
    result = {"status": status if status in {"pass", "fail", "blocked", "na"} else "blocked", "evidence_count": evidence_count, "reason_provided": reason_ok}
    if status not in {"pass", "fail", "blocked", "na"}:
        problems.append(f"check_{name}_status_invalid")
    if not reason_ok:
        problems.append(f"check_{name}_reason_missing")
        if result["status"] == "pass":
            result["status"] = "blocked"
    if result["status"] == "pass" and evidence_count == 0:
        result["status"] = "blocked"
        problems.append(f"check_{name}_evidence_missing")
    if result["status"] == "na":
        if name in {"requirements", "layout_structure"}:
            result["status"] = "fail"
            problems.append(f"check_{name}_cannot_be_na")
        elif not reason_ok:
            result["status"] = "blocked"
            problems.append(f"check_{name}_na_reason_missing")
    if problems and result["status"] == "pass":
        result["status"] = "blocked"
    return result, problems


def _normal_path(value: Any) -> str:
    return value.strip().replace("\\", "/") if isinstance(value, str) else ""


def _evidence_ref(value: Any) -> tuple[str, str]:
    """Return (path, declared role) from a string or role/path object."""

    if isinstance(value, str):
        return _normal_path(value), ""
    if isinstance(value, Mapping):
        return _normal_path(value.get("path")), _normal_path(value.get("role"))
    return "", ""


def _resolved_manifest_reference(value: Any, manifest_path: Path) -> Path | None:
    """Resolve a path stored inside a screenshot manifest."""

    path_value, _ = _evidence_ref(value)
    if not path_value:
        return None
    candidate = Path(path_value)
    if not candidate.is_absolute():
        candidate = manifest_path.parent / candidate
    try:
        return candidate.expanduser().resolve()
    except OSError:
        return None


def _same_resolved_path(left: Path | None, right: Path | None) -> bool:
    return left is not None and right is not None and left == right


def _manifest_declares_image_chain(path: Path | None) -> bool:
    """Whether the build manifest opts into per-image evidence-chain checks."""

    if path is None or not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    if not isinstance(payload, Mapping):
        return False
    if isinstance(payload.get("imageEvidence"), list) and payload["imageEvidence"]:
        return True
    chapters = payload.get("chapters")
    if chapters is None:
        chapter = payload.get("chapter")
        chapters = [chapter] if isinstance(chapter, Mapping) else []
    if not isinstance(chapters, list):
        return False
    for chapter in chapters:
        if not isinstance(chapter, Mapping):
            continue
        blocks: list[Any] = [chapter.get("entry")]
        blocks.extend(
            step
            for section in chapter.get("sections", [])
            if isinstance(section, Mapping)
            for step in section.get("steps", [])
        )
        for block in blocks:
            if not isinstance(block, Mapping):
                continue
            evidence = block.get("evidence", block.get("imageEvidence"))
            if isinstance(evidence, Mapping) and evidence:
                return True
    return False


def _validate_image_evidence_chain(
    review: Mapping[str, Any],
    reviewed_files: Sequence[Any],
    reviewed_paths: set[str],
    reviewed_by_path: Mapping[str, Mapping[str, Any]],
    image_evidence_paths: set[str],
    media_hashes: set[str],
    *,
    required: bool,
) -> tuple[dict[str, Any], list[str]]:
    """Validate optional/declared per-image redaction→annotation evidence."""

    raw_chain = review.get("imageEvidence", review.get("image_evidence"))
    if raw_chain is None:
        if required:
            return {"status": "blocked", "images": []}, ["image_evidence_chain_missing"]
        return {"status": "not_declared", "images": []}, []
    if not isinstance(raw_chain, list):
        return {"status": "blocked", "images": []}, ["image_evidence_chain_invalid"]

    chain_results: list[dict[str, Any]] = []
    reasons: list[str] = []
    required_roles = {
        "redaction": ("redaction", "redactionManifest", "redaction_manifest"),
        "annotation": ("annotation", "annotationManifest", "annotation_manifest"),
        "provenance": (
            "provenance",
            "redactionProvenance",
            "redaction_provenance",
        ),
        "annotation_provenance": (
            "annotationProvenance",
            "annotation_provenance",
            "annotatedProvenance",
        ),
    }
    seen_images: set[str] = set()
    for index, item in enumerate(raw_chain):
        if not isinstance(item, Mapping):
            reasons.append("image_evidence_chain_entry_invalid")
            continue
        image_path = _normal_path(item.get("image", item.get("imagePath")))
        if not image_path or image_path in seen_images:
            reasons.append("image_evidence_chain_image_invalid")
            continue
        seen_images.add(image_path)
        image_record = reviewed_by_path.get(image_path)
        image_ok = (
            image_path in image_evidence_paths
            and image_record is not None
            and image_record.get("kind") == "image"
            and image_record.get("sha256") in media_hashes
        )
        if not image_ok:
            reasons.append("image_evidence_chain_image_unbound")
        entry_blocked = not image_ok
        canonical_manifest_value = item.get("manifest", item.get("screenshotManifest"))
        roles: dict[str, str] = {}
        for role, aliases in required_roles.items():
            value = next((item.get(alias) for alias in aliases if alias in item), None)
            if value is None and role in {"redaction", "annotation"}:
                value = canonical_manifest_value
            evidence_path, declared_role = _evidence_ref(value)
            roles[role] = evidence_path
            evidence_record = reviewed_by_path.get(evidence_path)
            if not evidence_path or evidence_path not in reviewed_paths:
                reasons.append(f"image_evidence_chain_{role}_missing")
                entry_blocked = True
            elif evidence_record and evidence_record.get("kind") != "support":
                reasons.append(f"image_evidence_chain_{role}_not_support")
                entry_blocked = True
            elif declared_role and declared_role.casefold() not in {
                role.casefold(), f"{role}_manifest", f"{role}-manifest", "provenance",
                "screenshot_manifest", "screenshot-manifest", "manifest",
            }:
                reasons.append(f"image_evidence_chain_{role}_role_mismatch")
                entry_blocked = True
        manifest_paths = []
        for role in ("redaction", "annotation"):
            manifest_record = reviewed_by_path.get(roles[role])
            resolved_manifest = manifest_record.get("resolvedPath") if manifest_record else None
            if isinstance(resolved_manifest, Path):
                manifest_paths.append(resolved_manifest)
        canonical_manifest_path = manifest_paths[0] if manifest_paths else None
        if len(manifest_paths) == 2 and not _same_resolved_path(manifest_paths[0], manifest_paths[1]):
            reasons.append("image_evidence_chain_manifest_mismatch")
            entry_blocked = True
        canonical_manifest: Mapping[str, Any] | None = None
        if canonical_manifest_path is None or not canonical_manifest_path.is_file():
            reasons.append("image_evidence_chain_manifest_unreadable")
            entry_blocked = True
        else:
            canonical_payload, canonical_error = _read_json(canonical_manifest_path)
            if canonical_error or not isinstance(canonical_payload, Mapping):
                reasons.append("image_evidence_chain_manifest_invalid")
                entry_blocked = True
            else:
                canonical_manifest = canonical_payload
        if canonical_manifest is not None and canonical_manifest_path is not None:
            manifest_image = _resolved_manifest_reference(
                canonical_manifest.get("annotatedImage"), canonical_manifest_path
            )
            evidence_image = image_record.get("resolvedPath") if image_record else None
            if not _same_resolved_path(manifest_image, evidence_image if isinstance(evidence_image, Path) else None):
                reasons.append("image_evidence_chain_image_not_manifest_annotated")
                entry_blocked = True

            expected_provenance_refs = {
                "provenance": canonical_manifest.get(
                    "redactionProvenance",
                    canonical_manifest.get("redactProvenance", canonical_manifest.get("provenance")),
                ),
                "annotation_provenance": canonical_manifest.get(
                    "annotationProvenance", canonical_manifest.get("annotatedProvenance")
                ),
            }
            for role, manifest_ref in expected_provenance_refs.items():
                expected_path = _resolved_manifest_reference(manifest_ref, canonical_manifest_path)
                declared_path = roles.get(role)
                declared_record = reviewed_by_path.get(declared_path)
                declared_resolved = declared_record.get("resolvedPath") if declared_record else None
                if not _same_resolved_path(
                    expected_path,
                    declared_resolved if isinstance(declared_resolved, Path) else None,
                ):
                    reasons.append(f"image_evidence_chain_{role}_not_manifest_provenance")
                    entry_blocked = True
                    continue
                if declared_record is None or declared_record.get("kind") != "support" or declared_record.get("status") != "pass":
                    reasons.append(f"image_evidence_chain_{role}_support_unverified")
                    entry_blocked = True
                    continue
                provenance_payload, provenance_error = _read_json(expected_path)
                if provenance_error or not isinstance(provenance_payload, Mapping):
                    reasons.append(f"image_evidence_chain_{role}_invalid")
                    entry_blocked = True
                    continue
                if role == "provenance":
                    expected_parent_hash = canonical_manifest.get("sourceSha256")
                    expected_output_hash = canonical_manifest.get("redactedSha256")
                    expected_parent_image = _resolved_manifest_reference(
                        canonical_manifest.get("sourceImage"), canonical_manifest_path
                    )
                    expected_output_image = _resolved_manifest_reference(
                        canonical_manifest.get("redactedImage"), canonical_manifest_path
                    )
                    declared_parent_hash = provenance_payload.get(
                        "sourceSha256", provenance_payload.get("parentSha256")
                    )
                    declared_output_hash = provenance_payload.get(
                        "redactedSha256", provenance_payload.get("outputSha256")
                    )
                    parent_image_key, output_image_key = "parentImage", "outputImage"
                else:
                    expected_parent_hash = canonical_manifest.get("redactedSha256")
                    expected_output_hash = canonical_manifest.get("annotatedSha256")
                    expected_parent_image = _resolved_manifest_reference(
                        canonical_manifest.get("redactedImage"), canonical_manifest_path
                    )
                    expected_output_image = _resolved_manifest_reference(
                        canonical_manifest.get("annotatedImage"), canonical_manifest_path
                    )
                    declared_parent_hash = provenance_payload.get(
                        "parentSha256", provenance_payload.get("redactedSha256")
                    )
                    declared_output_hash = provenance_payload.get(
                        "outputSha256", provenance_payload.get("annotatedSha256")
                    )
                    parent_image_key, output_image_key = "parentImage", "outputImage"
                if (
                    not _hash(expected_parent_hash)
                    or not _hash(declared_parent_hash)
                    or str(expected_parent_hash).casefold() != str(declared_parent_hash).casefold()
                    or not _hash(expected_output_hash)
                    or not _hash(declared_output_hash)
                    or str(expected_output_hash).casefold() != str(declared_output_hash).casefold()
                ):
                    reasons.append(f"image_evidence_chain_{role}_hash_mismatch")
                    entry_blocked = True
                declared_parent_image = _resolved_manifest_reference(
                    provenance_payload.get(parent_image_key), canonical_manifest_path
                )
                declared_output_image = _resolved_manifest_reference(
                    provenance_payload.get(output_image_key), canonical_manifest_path
                )
                if not _same_resolved_path(expected_parent_image, declared_parent_image) or not _same_resolved_path(
                    expected_output_image, declared_output_image
                ):
                    reasons.append(f"image_evidence_chain_{role}_path_mismatch")
                    entry_blocked = True

            for image_field, image_hash_field in (
                ("sourceImage", "sourceSha256"),
                ("redactedImage", "redactedSha256"),
                ("annotatedImage", "annotatedSha256"),
            ):
                image_file = _resolved_manifest_reference(canonical_manifest.get(image_field), canonical_manifest_path)
                declared_hash = _hash(canonical_manifest.get(image_hash_field))
                if image_file is None or not image_file.is_file() or declared_hash is None:
                    reasons.append(f"image_evidence_chain_{image_field}_unreadable")
                    entry_blocked = True
                elif _sha256_file(image_file) != declared_hash:
                    reasons.append(f"image_evidence_chain_{image_field}_hash_mismatch")
                    entry_blocked = True
        chain_results.append({"image": image_path, "status": "blocked" if entry_blocked else "pass", "evidence": roles})
    if required and not seen_images:
        reasons.append("image_evidence_chain_empty")
    media_image_paths = {
        path for path, record in reviewed_by_path.items()
        if record.get("kind") == "image" and record.get("sha256") in media_hashes
    }
    if required and media_image_paths - seen_images:
        reasons.append("image_evidence_chain_incomplete")
    return {"status": "pass" if not reasons else "blocked", "images": chain_results}, reasons


def _independent_review(
    review: Any,
    review_path: Path | None,
    docx: Path,
    docx_sha256: str | None,
    media_hashes: set[str],
    build_manifest: Path | None = None,
) -> dict[str, Any]:
    empty_checks = {name: {"status": "blocked", "evidence_count": 0, "reason_provided": False} for name in CHECK_NAMES}
    empty_render = {"status": "blocked", "reason": "independent review missing"}
    if review is None or review_path is None:
        return {"status": "blocked", "reason_code": "review_missing", "checks": empty_checks, "render_visual": empty_render}
    if not isinstance(review, Mapping):
        return {"status": "blocked", "reason_code": "review_invalid", "checks": empty_checks, "render_visual": empty_render}

    reasons: list[str] = []
    if review.get("schema_version") != SCHEMA_VERSION or isinstance(review.get("schema_version"), bool):
        reasons.append("review_schema_invalid")
    artifact = review.get("artifact") if isinstance(review.get("artifact"), Mapping) else {}
    artifact_hash = _hash(artifact.get("sha256"))
    artifact_status = "match" if artifact_hash and artifact_hash == docx_sha256 else "blocked"
    if artifact_hash is None:
        reasons.append("artifact_hash_missing_or_invalid")
    elif artifact_hash != docx_sha256:
        reasons.append("artifact_hash_mismatch")
    builder = _review_identity(review.get("builder"))
    reviewer = _review_identity(review.get("reviewer"))
    identities_distinct = bool(builder and reviewer and builder.casefold() != reviewer.casefold())
    if not builder or not reviewer:
        reasons.append("identities_missing")
    elif not identities_distinct:
        reasons.append("reviewer_not_distinct")

    reviewed_files = review.get("reviewed_files") if isinstance(review.get("reviewed_files"), list) else []
    reviewed_paths: set[str] = set()
    reviewed_by_path: dict[str, dict[str, Any]] = {}
    reviewed_results: list[dict[str, Any]] = []
    file_statuses: list[str] = []
    page_count = image_count = support_count = 0
    image_hashes: set[str] = set()
    support_paths: set[str] = set()
    for index, item in enumerate(reviewed_files, start=1):
        item = item if isinstance(item, Mapping) else {}
        kind = item.get("kind")
        raw_path = item.get("path")
        declared_hash = _hash(item.get("sha256"))
        normalized_path = raw_path.strip().replace("\\", "/") if isinstance(raw_path, str) else ""
        path = _resolved_reviewed_path(raw_path, review_path)
        actual_hash = _sha256_file(path) if path else None
        status = "pass" if kind in {"image", "support", "page"} and declared_hash and actual_hash == declared_hash else "blocked"
        if normalized_path in reviewed_paths:
            reasons.append("reviewed_file_duplicate")
        reviewed_paths.add(normalized_path)
        reviewed_by_path[normalized_path] = {
            "kind": kind if kind in {"image", "support", "page"} else "unknown",
            "role": item.get("role"),
            "sha256": declared_hash,
            "resolvedPath": path,
            "status": status,
        }
        if path and path == review_path:
            reasons.append("review_self_reference")
            status = "blocked"
        if path and path == docx:
            reasons.append("docx_must_be_bound_by_artifact")
            status = "blocked"
        if kind == "page":
            page_count += 1
        elif kind == "image":
            image_count += 1
            if status == "pass" and declared_hash:
                image_hashes.add(declared_hash)
        elif kind == "support":
            support_count += 1
            if normalized_path:
                support_paths.add(normalized_path)
        elif kind not in {"image", "support"}:
            reasons.append("reviewed_file_kind_invalid")
        file_statuses.append(status)
        result: dict[str, Any] = {"index": index, "status": status, "kind": kind if kind in {"image", "support", "page"} else "unknown"}
        name = _filename(raw_path)
        if name:
            result["filename"] = name
        if declared_hash:
            result["sha256"] = declared_hash
        reviewed_results.append(result)

    if any(status != "pass" for status in file_statuses):
        reasons.append("reviewed_file_hash_unverified")
    if not support_count:
        reasons.append("support_evidence_missing")
    support_by_role: dict[str, tuple[Path | None, str | None]] = {}
    for item in reviewed_files:
        if not isinstance(item, Mapping) or item.get("kind") != "support":
            continue
        role = item.get("role")
        if isinstance(role, str) and role.strip():
            item_path = _resolved_reviewed_path(item.get("path"), review_path)
            support_by_role[role.strip().casefold()] = (item_path, _hash(item.get("sha256")))

    def declared_support(key: str, aliases: set[str]) -> tuple[Path | None, str | None]:
        candidates: list[Any] = []
        for container in (review, review.get("inputs") if isinstance(review.get("inputs"), Mapping) else {}):
            for alias in aliases | {key}:
                if isinstance(container, Mapping) and isinstance(container.get(alias), Mapping):
                    candidates.append(container[alias])
        for candidate in candidates:
            path_value = candidate.get("path")
            candidate_path = _resolved_reviewed_path(path_value, review_path)
            candidate_hash = _hash(candidate.get("sha256"))
            candidate_ref = path_value.strip().replace("\\", "/") if isinstance(path_value, str) else ""
            if candidate_path is not None and candidate_hash is not None and candidate_ref in support_paths:
                return candidate_path, candidate_hash
        for alias in aliases | {key}:
            if alias in support_by_role:
                return support_by_role[alias]
        return None, None

    requirements_path, requirements_hash = declared_support("requirements", {"requirements-snapshot", "requirements_snapshot"})
    manifest_path, manifest_hash = declared_support("build_manifest", {"build-manifest", "build-manifest-snapshot", "manifest"})
    if requirements_path is None or requirements_hash is None:
        reasons.append("requirements_evidence_missing")
    elif _sha256_file(requirements_path) != requirements_hash:
        reasons.append("requirements_hash_unmatched")
    if manifest_path is None or manifest_hash is None:
        reasons.append("build_manifest_evidence_missing")
    elif _sha256_file(manifest_path) != manifest_hash:
        reasons.append("build_manifest_hash_unmatched")
    if media_hashes and not image_count:
        reasons.append("image_evidence_missing")
    elif image_count < len(media_hashes):
        reasons.append("image_evidence_incomplete")
    if media_hashes - image_hashes:
        reasons.append("image_evidence_unmatched")
    if build_manifest is not None:
        expected = _sha256_file(build_manifest) if build_manifest.is_file() else None
        if expected is None:
            reasons.append("build_manifest_unreadable")
        else:
            manifest_matches = manifest_path == build_manifest and manifest_hash == expected
            if not manifest_matches:
                reasons.append("build_manifest_hash_unmatched")

    checks: dict[str, dict[str, Any]] = {}
    raw_checks = review.get("checks") if isinstance(review.get("checks"), Mapping) else {}
    for name in CHECK_NAMES:
        check, check_reasons = _check_entry(raw_checks.get(name), name, reviewed_paths)
        checks[name] = check
        reasons.extend(check_reasons)
    image_evidence_paths = {
        normalized_path
        for item in reviewed_files
        if isinstance(item, Mapping) and item.get("kind") == "image"
        for normalized_path in [str(item.get("path", "")).replace("\\", "/")]
    }
    image_chain, image_chain_reasons = _validate_image_evidence_chain(
        review,
        reviewed_files,
        reviewed_paths,
        reviewed_by_path,
        image_evidence_paths,
        media_hashes,
        required=build_manifest is not None or _manifest_declares_image_chain(build_manifest),
    )
    reasons.extend(image_chain_reasons)
    if media_hashes:
        for name in ("redaction", "operation"):
            raw_check = raw_checks.get(name)
            if isinstance(raw_check, Mapping) and str(raw_check.get("status", "")).casefold() == "na" and not raw_check.get("not_applicable"):
                checks[name]["status"] = "blocked"
                reasons.append(f"{name}_na_without_scope")
            if isinstance(raw_check, Mapping) and str(raw_check.get("status", "")).casefold() == "pass":
                evidence = raw_check.get("evidence")
                if not isinstance(evidence, list) or not any(
                    isinstance(item, str) and item.replace("\\", "/") in image_evidence_paths for item in evidence
                ):
                    checks[name]["status"] = "blocked"
                    reasons.append(f"{name}_image_evidence_missing")

    render_raw = review.get("render_visual")
    render_visual: dict[str, Any]
    render_status = render_raw.get("status") if isinstance(render_raw, Mapping) else None
    render_status = render_status.strip().casefold() if isinstance(render_status, str) else ""
    render_reason = render_raw.get("reason") if isinstance(render_raw, Mapping) else None
    render_visual = {
        "status": render_status if render_status in {"not_performed", "out_of_scope", "blocked", "fail"} else "blocked",
        "reason_provided": isinstance(render_reason, str) and bool(render_reason.strip()),
    }
    if render_status == "pass":
        reasons.append("render_visual_must_not_pass")
        render_visual["status"] = "fail"
    elif render_status not in {"not_performed", "out_of_scope", "blocked", "fail"}:
        reasons.append("render_visual_status_invalid")
    if not render_visual["reason_provided"]:
        reasons.append("render_visual_reason_missing")
        if render_visual["status"] in {"not_performed", "out_of_scope"}:
            render_visual["status"] = "blocked"

    check_status = _combine(
        [
            (
                "pass"
                if name in {"redaction", "operation"} and check["status"] == "na"
                else check["status"]
            )
            for name, check in checks.items()
        ],
        default="blocked",
    )
    declared_overall = review.get("overall")
    declared_overall = declared_overall.strip().casefold() if isinstance(declared_overall, str) else ""
    if declared_overall not in {"pass", "fail", "blocked"}:
        reasons.append("overall_invalid")
        declared_overall = "blocked"

    if declared_overall == "fail" or check_status == "fail" or render_visual["status"] == "fail":
        status = "fail"
    elif (
        review.get("schema_version") != SCHEMA_VERSION
        or artifact_status != "match"
        or not identities_distinct
        or any(file_status != "pass" for file_status in file_statuses)
        or not support_count
        or (media_hashes and not image_count)
        or (media_hashes and image_count < len(media_hashes))
        or bool(media_hashes - image_hashes)
        or check_status != "pass"
        or render_visual["status"] not in {"not_performed", "out_of_scope"}
        or declared_overall != "pass"
        or reasons
    ):
        status = "blocked"
    else:
        status = "pass"

    result: dict[str, Any] = {
        "status": status,
        "artifact": {"sha256": artifact_hash, "status": artifact_status},
        "identities": {"explicit": bool(builder and reviewer), "distinct": identities_distinct},
        "reviewed_files": reviewed_results,
        "checks": checks,
        "render_visual": render_visual,
        "image_evidence_chain": image_chain,
    }
    if reasons:
        result["reason_codes"] = sorted(set(reasons))
    return result


def audit_docx(
    docx_path: str | Path,
    review_path: str | Path | None = None,
    manifest_path: str | Path | None = None,
) -> dict[str, Any]:
    docx = Path(docx_path).expanduser().resolve()
    review = Path(review_path).expanduser().resolve() if review_path is not None else None
    build_manifest = Path(manifest_path).expanduser().resolve() if manifest_path is not None else None
    docx_info: dict[str, Any] = {"filename": docx.name}
    docx_sha: str | None = None
    try:
        docx_info["size_bytes"] = docx.stat().st_size
        docx_sha = _sha256_file(docx)
        docx_info["sha256"] = docx_sha
    except OSError:
        docx_info["status"] = "unreadable"

    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "docx": docx_info,
        "tables": [],
        "package": {"status": "blocked", "media": [], "unreferenced_media": []},
        "limitations": [
            "document_text_not_inspected",
            "image_pixels_and_redaction_not_inspected",
            "ocr_not_run",
            "render_visual_not_performed_by_lite_workflow",
            "operation_semantics_not_proven_by_structure",
        ],
    }
    mechanical_status = "failed" if docx_sha is None else "pass"
    findings: list[dict[str, Any]] = []
    media_hashes: set[str] = set()
    try:
        with zipfile.ZipFile(docx, "r") as package:
            names = [info.filename for info in package.infolist() if not info.is_dir()]
            media = _package_media(package, names)
            report["package"] = media
            media_hashes = {item["sha256"] for item in media["media"] if item.get("sha256")}
            if media["status"] != "pass":
                mechanical_status = _combine([mechanical_status, "manual_review"])
                for item in media["media"]:
                    if not item["referenced"]:
                        findings.append({"code": "unreferenced_media", "media_index": item["index"], "filename": item["filename"], "size_bytes": item["size_bytes"], "sha256": item["sha256"]})
            try:
                document_root = _parse_xml(package.read("word/document.xml"))
            except KeyError as error:
                raise AuditInputError("document_xml_missing") from error
            styles_root: ET.Element | None = None
            if "word/styles.xml" in names:
                try:
                    styles_root = _parse_xml(package.read("word/styles.xml"))
                except AuditInputError:
                    findings.append({"code": "styles_xml_unavailable"})
                    mechanical_status = _combine([mechanical_status, "manual_review"])
            styles = _style_alignments(styles_root)
            tables, wrapped = _top_level_tables(document_root)
            if wrapped:
                findings.append({"code": "table_container_uncertain"})
                mechanical_status = _combine([mechanical_status, "manual_review"])
            if not tables:
                findings.append({"code": "top_level_table_missing"})
                mechanical_status = _combine([mechanical_status, "manual_review"])
            for index, table in enumerate(tables, start=1):
                alignment = _alignment(table, styles)
                width = _table_width(table)
                grid = _grid_audit(table)
                table_status = _combine((alignment["status"], width["status"], grid["status"]), default="manual_review")
                report["tables"].append({"index": index, "status": table_status, "alignment": alignment, "width": width, "grid": grid})
                if alignment["status"] == "fail":
                    findings.append({"code": "table_alignment_not_center", "table_index": index})
                if grid.get("status") == "fail":
                    for item in grid.get("findings", []):
                        finding = {"table_index": index}
                        finding.update(item)
                        findings.append(finding)
                mechanical_status = _combine([mechanical_status, "failed" if table_status == "fail" else table_status])
    except (OSError, zipfile.BadZipFile, AuditInputError):
        findings.append({"code": "docx_package_unreadable"})
        mechanical_status = "failed"

    report["mechanical_status"] = "failed" if mechanical_status in {"fail", "failed"} else mechanical_status
    report["findings"] = findings
    review_value, review_error = _read_json(review)
    if review_error:
        report["independent_review"] = {"status": "blocked", "reason_code": review_error, "checks": {name: {"status": "blocked", "evidence_count": 0, "reason_provided": False} for name in CHECK_NAMES}, "render_visual": {"status": "blocked", "reason": review_error}}
    else:
        report["independent_review"] = _independent_review(review_value, review, docx, docx_sha, media_hashes, build_manifest)
    return report


def _resolved(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _output_conflicts(
    output: str,
    docx: str | Path,
    review: str | Path | None,
    manifest: str | Path | None = None,
) -> bool:
    if output == "-":
        return False
    destination = _resolved(output)
    inputs = [_resolved(docx)]
    if manifest is not None:
        inputs.append(_resolved(manifest))
    review_input: Path | None = None
    if review is not None:
        review_input = _resolved(review)
        inputs.append(review_input)
        review_value, _ = _read_json(review_input)
        if isinstance(review_value, Mapping) and isinstance(review_value.get("reviewed_files"), list):
            for item in review_value["reviewed_files"]:
                if not isinstance(item, Mapping) or not isinstance(item.get("path"), str):
                    continue
                evidence = Path(item["path"])
                if not evidence.is_absolute():
                    evidence = review_input.parent / evidence
                try:
                    inputs.append(evidence.resolve())
                except OSError:
                    continue
    return any(os.path.normcase(destination) == os.path.normcase(path) for path in inputs)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit a lite UI-manual DOCX without reading text or image pixels.")
    parser.add_argument("--docx", required=True, help="DOCX path to inspect")
    parser.add_argument("--output", required=True, help="JSON output path, or - for stdout")
    parser.add_argument("--review", help="Optional independent lite review JSON path")
    parser.add_argument("--manifest", help="Optional final build manifest path to bind in the review")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if _output_conflicts(args.output, args.docx, args.review, args.manifest):
        return 2
    report = audit_docx(args.docx, args.review, args.manifest)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        try:
            destination = _resolved(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        except OSError:
            return 2
    return 2 if report.get("docx", {}).get("status") == "unreadable" or any(item.get("code") == "docx_package_unreadable" for item in report.get("findings", [])) else 0


if __name__ == "__main__":
    raise SystemExit(main())
