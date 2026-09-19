#!/usr/bin/env python3
"""Validate one UI-manual screenshot manifest without inspecting its meaning.

The validator is intentionally small and read-only.  It checks the file
binding, PNG dimensions, hashes, coordinate geometry, and review-state fields
that a builder must provide for one screenshot.  It does not inspect pixels,
OCR, captions, or the UI, so a successful report is not a redaction or
annotation review.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from PIL import Image
except ImportError:  # pragma: no cover - exercised by the CLI environment
    Image = None  # type: ignore[assignment,misc]


SCHEMA_VERSION = 1
SOURCE_KINDS = {"captured", "provided", "reused", "schematic"}
CAPTURE_KINDS = {"full-page", "viewport-sequence", "detail"}
REVIEW_STATUSES = {"pending", "checked", "blocked"}
REDACTION_STATUSES = {"pending", "checked", "blocked"}
ANNOTATION_STATUSES = {"pending", "verified", "blocked", "checked"}
PENDING_CODES = {"approval_pending", "approval_blocked", "approval_status_missing", "no_sensitive_reason_missing"}


def _is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 64:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def _finding(code: str, *, role: str | None = None, index: int | None = None,
             other_index: int | None = None) -> dict[str, Any]:
    """Return a finding with only non-sensitive, structural context."""

    result: dict[str, Any] = {"code": code}
    if role is not None:
        result["role"] = role
    if index is not None:
        result["index"] = index
    if other_index is not None:
        result["other_index"] = other_index
    return result


def _sha256(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _png_size(path: Path) -> tuple[int, int] | None:
    if Image is None:
        return None
    try:
        with Image.open(path) as image:
            if image.format != "PNG":
                return None
            image.load()
            width, height = image.size
            if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                return width, height
    except Exception:  # Pillow raises several format-specific exceptions.
        return None
    return None


def _positive_size(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, Mapping):
        return None
    width = value.get("width")
    height = value.get("height")
    if isinstance(width, bool) or isinstance(height, bool):
        return None
    if not isinstance(width, int) or not isinstance(height, int):
        return None
    if width <= 0 or height <= 0:
        return None
    return width, height


def _bbox(value: Any, image_size: tuple[int, int] | None) -> tuple[float, float, float, float] | None:
    if not isinstance(value, Mapping):
        return None
    values = [value.get(name) for name in ("x", "y", "width", "height")]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        return None
    x, y, width, height = (float(item) for item in values)
    if not all(math.isfinite(item) for item in (x, y, width, height)):
        return None
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        return None
    if image_size is not None:
        image_width, image_height = image_size
        if x + width > image_width or y + height > image_height:
            return None
    return x, y, width, height


def _overlap(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return (
        max(left_x, right_x) < min(left_x + left_width, right_x + right_width)
        and max(left_y, right_y) < min(left_y + left_height, right_y + right_height)
    )


def _resolve_file(value: Any, manifest_path: Path, base_dir: str | Path | None) -> Path | None:
    if not _is_text(value):
        return None
    try:
        base = manifest_path.parent if base_dir is None else manifest_path.parent / Path(base_dir)
        return (base / value).resolve()
    except (OSError, TypeError, ValueError):
        return None


def _safe_status(value: Any, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    status = value.strip().lower()
    return status if status in allowed else None


def _add_required_text(raw: Mapping[str, Any], field: str, findings: list[dict[str, Any]]) -> bool:
    if not _is_text(raw.get(field)):
        findings.append(_finding("field_missing", role=field))
        return False
    return True


def _load_manifest(path: Path) -> Mapping[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def validate_manifest(manifest_path: str | Path, base_dir: str | Path | None = None) -> dict[str, Any]:
    """Return a safe validation report for a single screenshot manifest."""

    path = Path(manifest_path).expanduser().resolve()
    findings: list[dict[str, Any]] = []
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "geometry_status": "blocked",
        "manifest_status": "blocked",
        "semantic_review": "not_performed",
        "files": [],
        "findings": findings,
        "limitations": [
            "does_not_read_image_pixels_or_ocr",
            "does_not_prove_redaction_or_annotation_semantics",
            "builder_must_directly_review_each_image",
            "independent_review_is_still_required",
        ],
    }

    if Image is None:
        findings.append(_finding("pillow_unavailable"))

    raw = _load_manifest(path)
    if raw is None:
        findings.append(_finding("manifest_unreadable"))
        return report

    schema = raw.get("schema_version")
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != SCHEMA_VERSION:
        findings.append(_finding("schema_version_invalid"))

    source_sha = raw.get("sourceSha256")
    if not _is_sha256(source_sha):
        findings.append(_finding("source_sha256_invalid", role="sourceSha256"))

    source_kind = raw.get("sourceKind")
    if not _is_text(source_kind):
        findings.append(_finding("field_missing", role="sourceKind"))
    elif source_kind not in SOURCE_KINDS:
        findings.append(_finding("source_kind_invalid"))

    capture_kind = raw.get("captureKind")
    if not _is_text(capture_kind):
        findings.append(_finding("field_missing", role="captureKind"))
    elif capture_kind not in CAPTURE_KINDS:
        findings.append(_finding("capture_kind_invalid"))

    expected_size = _positive_size(raw.get("originalImageSize"))
    if expected_size is None:
        findings.append(_finding("original_image_size_invalid", role="originalImageSize"))

    state = raw.get("captureState")
    state_sha: Any = None
    if not isinstance(state, Mapping):
        findings.append(_finding("capture_state_invalid", role="captureState"))
    else:
        if not _is_text(state.get("id")):
            findings.append(_finding("capture_state_id_missing", role="captureState"))
        state_sha = state.get("rawSha256")
        if not _is_sha256(state_sha):
            findings.append(_finding("capture_state_sha256_invalid", role="captureState"))
        elif _is_sha256(source_sha) and state_sha.lower() != source_sha.lower():
            findings.append(_finding("capture_state_sha256_mismatch", role="captureState"))

    review_status = _safe_status(raw.get("reviewStatus"), REVIEW_STATUSES)
    if review_status is None:
        findings.append(_finding("approval_status_missing", role="reviewStatus"))
    elif review_status == "pending":
        findings.append(_finding("approval_pending", role="reviewStatus"))
    elif review_status == "blocked":
        findings.append(_finding("approval_blocked", role="reviewStatus"))

    file_paths: dict[str, Path] = {}
    for role, field in (("raw", "sourceImage"), ("redacted", "redactedImage"), ("annotated", "annotatedImage")):
        if not _add_required_text(raw, field, findings):
            continue
        resolved = _resolve_file(raw.get(field), path, base_dir)
        if resolved is None:
            findings.append(_finding("file_path_invalid", role=role))
            continue
        file_paths[role] = resolved

    roles = list(file_paths)
    for left_index, left_role in enumerate(roles):
        left_path = file_paths[left_role]
        for right_role in roles[left_index + 1:]:
            right_path = file_paths[right_role]
            same = left_path == right_path
            if not same:
                try:
                    same = os.path.samefile(left_path, right_path)
                except OSError:
                    same = False
            if same:
                findings.append(_finding("file_alias", role=left_role, other_index=roles.index(right_role)))

    actual_sizes: dict[str, tuple[int, int]] = {}
    for role, image_path in file_paths.items():
        digest = _sha256(image_path)
        image_size = _png_size(image_path)
        file_report: dict[str, Any] = {"role": role, "status": "pass" if digest and image_size else "blocked"}
        if digest:
            file_report["sha256"] = digest
        if image_size:
            actual_sizes[role] = image_size
            file_report["width"], file_report["height"] = image_size
        report["files"].append(file_report)
        if digest is None:
            findings.append(_finding("file_unreadable", role=role))
        if image_size is None:
            findings.append(_finding("png_invalid", role=role))

    raw_size = actual_sizes.get("raw")
    if expected_size is not None:
        if raw_size is not None and raw_size != expected_size:
            findings.append(_finding("raw_size_mismatch", role="raw"))
        for role in ("redacted", "annotated"):
            if role in actual_sizes and actual_sizes[role] != expected_size:
                findings.append(_finding("image_dimensions_mismatch", role=role))
    if raw_size is not None:
        for role in ("redacted", "annotated"):
            if role in actual_sizes and actual_sizes[role] != raw_size:
                findings.append(_finding("image_dimensions_mismatch", role=role))

    if _is_sha256(source_sha) and "raw" in file_paths:
        actual_source_sha = _sha256(file_paths["raw"])
        if actual_source_sha is not None and actual_source_sha.lower() != source_sha.lower():
            findings.append(_finding("source_sha256_mismatch", role="raw"))

    redactions = raw.get("redactions")
    redaction_boxes: list[tuple[float, float, float, float] | None] = []
    if not isinstance(redactions, list):
        findings.append(_finding("redactions_invalid", role="redactions"))
    else:
        if not redactions and not _is_text(raw.get("noSensitiveDataReason")):
            findings.append(_finding("no_sensitive_reason_missing", role="noSensitiveDataReason"))
        for index, item in enumerate(redactions):
            if not isinstance(item, Mapping):
                findings.append(_finding("redaction_invalid", index=index))
                redaction_boxes.append(None)
                continue
            box = _bbox(item.get("bbox"), expected_size)
            redaction_boxes.append(box)
            if box is None:
                findings.append(_finding("bbox_invalid", role="redaction", index=index))
            if not _is_text(item.get("category")):
                findings.append(_finding("redaction_category_missing", index=index))
            if not _is_text(item.get("method")):
                findings.append(_finding("redaction_method_missing", index=index))
            status = _safe_status(item.get("status"), REDACTION_STATUSES)
            if status is None:
                findings.append(_finding("redaction_status_missing", index=index))
            elif status == "pending":
                findings.append(_finding("approval_pending", role="redaction", index=index))
            elif status == "blocked":
                findings.append(_finding("approval_blocked", role="redaction", index=index))

    annotations = raw.get("annotations")
    annotation_ids: set[str] = set()
    if not isinstance(annotations, list):
        findings.append(_finding("annotations_invalid", role="annotations"))
    else:
        for index, item in enumerate(annotations):
            if not isinstance(item, Mapping):
                findings.append(_finding("annotation_invalid", index=index))
                continue
            annotation_id = item.get("id")
            if not _is_text(annotation_id):
                findings.append(_finding("annotation_id_missing", index=index))
            elif annotation_id in annotation_ids:
                findings.append(_finding("annotation_id_duplicate", index=index))
            else:
                annotation_ids.add(annotation_id)
            for field in ("controlName", "caption", "source"):
                if not _is_text(item.get(field)):
                    findings.append(_finding("annotation_field_missing", role=field, index=index))
            if _bbox(item.get("bbox"), expected_size) is None:
                findings.append(_finding("bbox_invalid", role="annotation", index=index))
            status = _safe_status(item.get("status"), ANNOTATION_STATUSES)
            if status is None:
                findings.append(_finding("annotation_status_missing", index=index))
            elif status == "pending":
                findings.append(_finding("approval_pending", role="annotation", index=index))
            elif status == "blocked":
                findings.append(_finding("approval_blocked", role="annotation", index=index))

    protected = raw.get("protectedAreas", [])
    protected_boxes: list[tuple[float, float, float, float] | None] = []
    if not isinstance(protected, list):
        findings.append(_finding("protected_areas_invalid", role="protectedAreas"))
    else:
        for index, item in enumerate(protected):
            box = _bbox(item.get("bbox") if isinstance(item, Mapping) else None, expected_size)
            protected_boxes.append(box)
            if box is None:
                findings.append(_finding("bbox_invalid", role="protected-area", index=index))

    for redaction_index, redaction_box in enumerate(redaction_boxes):
        if redaction_box is None:
            continue
        for protected_index, protected_box in enumerate(protected_boxes):
            if protected_box is not None and _overlap(redaction_box, protected_box):
                findings.append(_finding(
                    "redaction_overlaps_protected_area",
                    role="redaction",
                    index=redaction_index,
                    other_index=protected_index,
                ))

    geometry_findings = [item for item in findings if item["code"] not in PENDING_CODES]
    report["geometry_status"] = "fail" if geometry_findings else "pass"
    if geometry_findings:
        report["manifest_status"] = "fail"
    elif findings:
        report["manifest_status"] = "blocked"
    else:
        report["manifest_status"] = "pass"
    # ``status`` is the manifest decision.  A preview with pending approval
    # may have geometry_status=pass, but it must never look delivery-ready.
    report["status"] = report["manifest_status"]
    return report


def _resolved(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def _output_conflicts(output: str, manifest: str | Path, base_dir: str | Path | None = None) -> bool:
    if output == "-":
        return False
    try:
        destination = _resolved(output)
        manifest_path = _resolved(manifest)
        input_paths = [manifest_path]
        raw = _load_manifest(manifest_path)
        if raw is None:
            # A malformed manifest may still have been used to name source
            # images.  Refuse every file output when those paths cannot be
            # parsed; stdout remains available for a safe blocked report.
            return True
        for field in ("sourceImage", "redactedImage", "annotatedImage"):
            resolved = _resolve_file(raw.get(field), manifest_path, base_dir)
            if resolved is not None:
                input_paths.append(resolved)
        provenance = raw.get("captureProvenance")
        if isinstance(provenance, Mapping):
            for field in ("originalFile", "decodedSourceImage"):
                resolved = _resolve_file(provenance.get(field), manifest_path, base_dir)
                if resolved is not None:
                    input_paths.append(resolved)
        for source_container in (raw, raw.get("captureState")):
            if isinstance(source_container, Mapping):
                for field in ("originalCapturePath", "captureArtifact"):
                    resolved = _resolve_file(source_container.get(field), manifest_path, base_dir)
                    if resolved is not None:
                        input_paths.append(resolved)
        for input_path in input_paths:
            if os.path.normcase(destination) == os.path.normcase(input_path):
                return True
            try:
                if os.path.exists(destination) and os.path.samefile(destination, input_path):
                    return True
            except OSError:
                pass
        return False
    except (OSError, TypeError, ValueError):
        return True


def _write_report(report: Mapping[str, Any], output: str) -> None:
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if output == "-":
        sys.stdout.write(payload)
        return
    destination = _resolved(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload, encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate one UI-manual screenshot manifest.")
    parser.add_argument("--manifest", required=True, help="Path to one per-image manifest JSON")
    parser.add_argument("--base-dir", help="Image path base, relative to the manifest directory")
    parser.add_argument("--output", required=True, help="JSON report path, or - for stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if _output_conflicts(args.output, args.manifest, args.base_dir):
        return 2
    report = validate_manifest(args.manifest, args.base_dir)
    try:
        _write_report(report, args.output)
    except OSError:
        return 2
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
