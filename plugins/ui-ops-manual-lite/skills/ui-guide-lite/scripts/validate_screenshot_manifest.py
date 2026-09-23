#!/usr/bin/env python3
"""Validate one lite per-image screenshot evidence manifest.

This is a read-only mechanical gate.  It verifies file/hash binding,
capture-state/calibration metadata and bbox geometry for raw, redacted and
annotated PNGs.  It does not inspect image pixels, OCR or control semantics;
those remain direct image review and independent review responsibilities.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

try:
    from annotate import badge_box
    from evidence import (
        CAPTURE_KINDS,
        REDACTION_CATEGORIES,
        SOURCE_KINDS,
        annotation_input_payload,
        annotation_input_sha256,
        bbox,
        capture_binding_errors,
        file_alias,
        image_size,
        is_sha256,
        is_text,
        overlap,
        positive_size,
        protected_items,
        redaction_input_payload,
        redaction_input_sha256,
        sha256,
    )
except ImportError:  # pragma: no cover - package import fallback
    from .annotate import badge_box  # type: ignore[no-redef]
    from .evidence import (  # type: ignore[no-redef]
        CAPTURE_KINDS,
        REDACTION_CATEGORIES,
        SOURCE_KINDS,
        annotation_input_payload,
        annotation_input_sha256,
        bbox,
        capture_binding_errors,
        file_alias,
        image_size,
        is_sha256,
        is_text,
        overlap,
        positive_size,
        protected_items,
        redaction_input_payload,
        redaction_input_sha256,
        sha256,
    )


SCHEMA_VERSION = 1
REVIEW_STATUSES = {"pending", "checked", "verified", "approved", "blocked"}
REDACTION_STATUSES = {"pending", "checked", "blocked"}
ANNOTATION_STATUSES = {"pending", "verified", "checked", "blocked"}
PENDING_CODES = {
    "approval_pending",
    "approval_blocked",
    "approval_status_missing",
}
COORDINATE_BLOCKED_CODES = {
    "coordinate_capture_kind_unsupported",
    "coordinate_capture_state_mismatch",
    "coordinate_provenance_missing",
    "coordinate_source_unsupported",
    "coordinate_source_sha256_invalid",
    "coordinate_source_sha256_mismatch",
    "coordinate_transform_missing",
    "coordinate_transform_invalid",
    "coordinate_viewport_invalid",
    "coordinate_clip_invalid",
    "coordinate_screenshot_size_invalid",
    "coordinate_scroll_offset_invalid",
    "coordinate_dpr_invalid",
    "coordinate_clip_out_of_viewport",
    "coordinate_scale_invalid",
    "coordinate_scale_mismatch",
    "coordinate_screenshot_size_mismatch",
    "coordinate_adjustment_reason_missing",
    "coordinate_transformed_bbox_missing",
    "coordinate_transformed_bbox_mismatch",
    "coordinate_manual_adjustment_pending",
    "coordinate_source_bbox_invalid",
    "coordinate_source_bbox_out_of_clip",
    "coordinate_output_bbox_out_of_bounds",
    "coordinate_bbox_mismatch",
}
DOM_ANNOTATION_SOURCES = {"dom", "dom-manual-adjusted"}


class CoordinateTransformError(ValueError):
    """A coordinate transform cannot be proven from manifest metadata."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _finding(code: str, *, role: str | None = None, index: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"code": code}
    if role is not None:
        result["role"] = role
    if index is not None:
        result["index"] = index
    return result


def _load(path: Path) -> Mapping[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return value if isinstance(value, Mapping) else None


def _resolve(value: Any, manifest_path: Path, base_dir: str | Path | None) -> Path | None:
    if not is_text(value):
        return None
    try:
        base = manifest_path.parent if base_dir is None else manifest_path.parent / Path(base_dir)
        return (base / str(value)).expanduser().resolve()
    except (OSError, TypeError, ValueError):
        return None


def _status(value: Any, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold()
    return normalized if normalized in allowed else None


def _coordinate_dimensions(value: Any, code: str) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise CoordinateTransformError(code)
    values = [value.get("width"), value.get("height")]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise CoordinateTransformError(code)
    width, height = (float(item) for item in values)
    if not all(math.isfinite(item) and item > 0 for item in (width, height)):
        raise CoordinateTransformError(code)
    return width, height


def _coordinate_rect(value: Any, code: str) -> tuple[float, float, float, float]:
    if not isinstance(value, Mapping):
        raise CoordinateTransformError(code)
    values = [value.get(name) for name in ("x", "y", "width", "height")]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise CoordinateTransformError(code)
    x, y, width, height = (float(item) for item in values)
    if not all(math.isfinite(item) for item in (x, y, width, height)):
        raise CoordinateTransformError(code)
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise CoordinateTransformError(code)
    return x, y, width, height


def _coordinate_offset(value: Any, code: str) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise CoordinateTransformError(code)
    values = [value.get("x"), value.get("y")]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise CoordinateTransformError(code)
    x, y = (float(item) for item in values)
    if not all(math.isfinite(item) and item >= 0 for item in (x, y)):
        raise CoordinateTransformError(code)
    return x, y


def _coordinate_scale(value: Any, code: str) -> tuple[float, float]:
    if not isinstance(value, Mapping):
        raise CoordinateTransformError(code)
    values = [value.get("x"), value.get("y")]
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
        raise CoordinateTransformError(code)
    x, y = (float(item) for item in values)
    if not all(math.isfinite(item) and item > 0 for item in (x, y)):
        raise CoordinateTransformError(code)
    return x, y


def transform_css_viewport_bbox(source_bbox: Any, transform: Any) -> dict[str, Any]:
    """Convert a CSS viewport bbox to PNG pixels using a calibrated clip.

    ``devicePixelRatio`` is provenance only.  Scale is derived once from the
    actual screenshot pixels divided by the CSS clip dimensions, so DPR is
    never multiplied a second time.  Full-page/sticky/unknown mappings are
    outside this helper's contract.
    """

    if not isinstance(transform, Mapping):
        raise CoordinateTransformError("coordinate_transform_missing")
    if transform.get("status") != "calibrated":
        raise CoordinateTransformError("coordinate_transform_invalid")
    if transform.get("sourceSpace") != "css-viewport" or transform.get("targetSpace") != "png-pixels":
        raise CoordinateTransformError("coordinate_transform_invalid")

    viewport_width, viewport_height = _coordinate_dimensions(
        transform.get("viewportSize"), "coordinate_viewport_invalid"
    )
    clip_x, clip_y, clip_width, clip_height = _coordinate_rect(
        transform.get("clip"), "coordinate_clip_invalid"
    )
    screenshot_size = positive_size(transform.get("screenshotSize"))
    if screenshot_size is None:
        raise CoordinateTransformError("coordinate_screenshot_size_invalid")
    _coordinate_offset(transform.get("scrollOffset"), "coordinate_scroll_offset_invalid")
    dpr = transform.get("devicePixelRatio")
    if isinstance(dpr, bool) or not isinstance(dpr, (int, float)):
        raise CoordinateTransformError("coordinate_dpr_invalid")
    if not math.isfinite(float(dpr)) or float(dpr) <= 0:
        raise CoordinateTransformError("coordinate_dpr_invalid")
    if clip_x + clip_width > viewport_width + 1e-6 or clip_y + clip_height > viewport_height + 1e-6:
        raise CoordinateTransformError("coordinate_clip_out_of_viewport")

    scale_x = screenshot_size[0] / clip_width
    scale_y = screenshot_size[1] / clip_height
    declared_scale = transform.get("scale")
    if declared_scale is not None:
        declared_x, declared_y = _coordinate_scale(declared_scale, "coordinate_scale_invalid")
        if not math.isclose(declared_x, scale_x, rel_tol=1e-6, abs_tol=1e-6) or not math.isclose(
            declared_y, scale_y, rel_tol=1e-6, abs_tol=1e-6
        ):
            raise CoordinateTransformError("coordinate_scale_mismatch")

    source = bbox(source_bbox, None)
    if source is None:
        raise CoordinateTransformError("coordinate_source_bbox_invalid")
    source_x, source_y, source_width, source_height = source
    if (
        source_x < clip_x - 1e-6
        or source_y < clip_y - 1e-6
        or source_x + source_width > clip_x + clip_width + 1e-6
        or source_y + source_height > clip_y + clip_height + 1e-6
    ):
        raise CoordinateTransformError("coordinate_source_bbox_out_of_clip")

    output_mapping = {
        "x": (source_x - clip_x) * scale_x,
        "y": (source_y - clip_y) * scale_y,
        "width": source_width * scale_x,
        "height": source_height * scale_y,
    }
    if bbox(output_mapping, screenshot_size) is None:
        raise CoordinateTransformError("coordinate_output_bbox_out_of_bounds")
    return {
        "bbox": {name: round(value, 6) for name, value in output_mapping.items()},
        "scale": {"x": round(scale_x, 12), "y": round(scale_y, 12)},
        "devicePixelRatioApplied": False,
    }


def _same_bbox(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    return all(math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-5) for a, b in zip(left, right))


def _annotation_coordinate_findings(
    item: Mapping[str, Any],
    index: int,
    source_sha: Any,
    state: Mapping[str, Any] | None,
    expected_size: tuple[int, int] | None,
) -> list[dict[str, Any]]:
    source = item.get("source", item.get("provenance"))
    source_name = source.strip().lower() if isinstance(source, str) else ""
    if source_name not in DOM_ANNOTATION_SOURCES:
        return [_finding("coordinate_source_unsupported", role="annotation", index=index)]

    provenance = item.get("coordinateProvenance")
    if not isinstance(provenance, Mapping):
        return [_finding("coordinate_provenance_missing", role="annotation", index=index)]

    findings: list[dict[str, Any]] = []
    state_id = state.get("id") if isinstance(state, Mapping) else None
    if not is_text(provenance.get("captureStateId")) or provenance.get("captureStateId") != state_id:
        findings.append(_finding("coordinate_capture_state_mismatch", role="annotation", index=index))
    provenance_sha = provenance.get("sourceSha256")
    if not is_sha256(provenance_sha):
        findings.append(_finding("coordinate_source_sha256_invalid", role="annotation", index=index))
    elif is_sha256(source_sha) and provenance_sha.casefold() != source_sha.casefold():
        findings.append(_finding("coordinate_source_sha256_mismatch", role="annotation", index=index))

    try:
        transformed = transform_css_viewport_bbox(
            provenance.get("sourceBbox"),
            state.get("coordinateTransform") if isinstance(state, Mapping) else None,
        )
    except CoordinateTransformError as error:
        findings.append(_finding(error.code, role="annotation", index=index))
        return findings

    actual = bbox(item.get("bbox"), expected_size)
    expected = bbox(transformed["bbox"], expected_size)
    if actual is None or expected is None:
        return findings
    if source_name == "dom":
        if not _same_bbox(actual, expected):
            findings.append(_finding("coordinate_bbox_mismatch", role="annotation", index=index))
        return findings

    adjustment_reason = provenance.get("adjustmentReason")
    if not is_text(adjustment_reason):
        findings.append(_finding("coordinate_adjustment_reason_missing", role="annotation", index=index))
    transformed_bbox = bbox(provenance.get("transformedBbox"), expected_size)
    if transformed_bbox is None:
        findings.append(_finding("coordinate_transformed_bbox_missing", role="annotation", index=index))
    elif not _same_bbox(transformed_bbox, expected):
        findings.append(_finding("coordinate_transformed_bbox_mismatch", role="annotation", index=index))
    if not _same_bbox(actual, expected):
        findings.append(_finding("coordinate_manual_adjustment_pending", role="annotation", index=index))
    return findings


def _provenance_value(
    value: Any, manifest_path: Path, base_dir: str | Path | None
) -> Mapping[str, Any] | None:
    """Load one tool-generated provenance object or a relative JSON path."""

    if isinstance(value, Mapping):
        return value
    path = _resolve(value, manifest_path, base_dir)
    if path is None or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, Mapping) else None


def _pixel_equal(left: Path, right: Path) -> bool:
    try:
        from PIL import Image

        with Image.open(left) as source, Image.open(right) as derived:
            source.load()
            derived.load()
            if source.size != derived.size:
                return False
            has_alpha = source.mode in {"RGBA", "LA"} or "transparency" in source.info
            mode = "RGBA" if has_alpha else "RGB"
            return source.convert(mode).tobytes() == derived.convert(mode).tobytes()
    except (OSError, ValueError):
        return False


def _validate_capture_provenance(
    raw: Mapping[str, Any],
    manifest_path: Path,
    base_dir: str | Path | None,
    files: Mapping[str, Path],
    findings: list[dict[str, Any]],
) -> None:
    value = raw.get("captureProvenance")
    if value is None:
        return
    provenance = _provenance_value(value, manifest_path, base_dir)
    if provenance is None:
        findings.append(_finding("capture_provenance_invalid", role="captureProvenance"))
        return
    original = _resolve(provenance.get("originalFile"), manifest_path, base_dir)
    if original is None or not original.is_file():
        findings.append(_finding("capture_provenance_file_missing", role="originalFile"))
    elif not is_sha256(provenance.get("originalSha256")):
        findings.append(_finding("capture_provenance_hash_invalid", role="originalSha256"))
    elif sha256(original).casefold() != str(provenance["originalSha256"]).casefold():
        findings.append(_finding("capture_provenance_hash_mismatch", role="originalFile"))
    if not is_text(provenance.get("originalMime")):
        findings.append(_finding("capture_provenance_mime_missing", role="originalMime"))
    canonical_value = provenance.get("decodedSourceImage", provenance.get("canonicalFile"))
    canonical = _resolve(canonical_value, manifest_path, base_dir)
    source = files.get("raw")
    if canonical is None or not canonical.is_file():
        findings.append(_finding("capture_provenance_canonical_missing", role="canonicalFile"))
    else:
        try:
            image_size(canonical, require_png=True)
        except (OSError, ValueError):
            findings.append(_finding("capture_provenance_canonical_invalid", role="canonicalFile"))
        if not is_sha256(provenance.get("canonicalSha256")):
            findings.append(_finding("capture_provenance_canonical_hash_invalid", role="canonicalSha256"))
        elif sha256(canonical).casefold() != str(provenance["canonicalSha256"]).casefold():
            findings.append(_finding("capture_provenance_canonical_hash_mismatch", role="canonicalFile"))
        if source is not None and not file_alias(canonical, source):
            findings.append(_finding("capture_provenance_source_not_canonical", role="canonicalFile"))
        if original is not None and original.is_file() and not _pixel_equal(original, canonical):
            findings.append(_finding("capture_provenance_pixel_mismatch", role="pixelEquality"))
    if provenance.get("pixelEquality") != "verified":
        findings.append(_finding("capture_provenance_pixel_equality_unverified", role="pixelEquality"))


def _validate_redaction_provenance(
    raw: Mapping[str, Any],
    provenance: Mapping[str, Any],
    files: Mapping[str, Path],
    findings: list[dict[str, Any]],
) -> None:
    source, redacted = files.get("raw"), files.get("redacted")
    if source is None or redacted is None:
        return
    source_hash, redacted_hash = sha256(source), sha256(redacted)
    parent_hash = provenance.get("sourceSha256", provenance.get("parentSha256"))
    output_hash = provenance.get("redactedSha256", provenance.get("outputSha256"))
    if not is_sha256(parent_hash) or str(parent_hash).casefold() != source_hash.casefold():
        findings.append(_finding("redaction_provenance_parent_mismatch", role="sourceSha256"))
    if not is_sha256(output_hash) or str(output_hash).casefold() != redacted_hash.casefold():
        findings.append(_finding("redaction_provenance_output_mismatch", role="redactedSha256"))
    expected_inputs = redaction_input_payload(raw)
    expected_hash = redaction_input_sha256(raw)
    if provenance.get("redactionInputSha256") != expected_hash:
        findings.append(_finding("redaction_provenance_input_mismatch", role="redactionInputSha256"))
    if provenance.get("redactionInputs") != expected_inputs:
        findings.append(_finding("redaction_provenance_geometry_mismatch", role="redactionInputs"))


def _validate_annotation_provenance(
    raw: Mapping[str, Any],
    provenance: Mapping[str, Any],
    files: Mapping[str, Path],
    findings: list[dict[str, Any]],
) -> None:
    redacted, annotated = files.get("redacted"), files.get("annotated")
    if redacted is None or annotated is None:
        return
    parent_hash, output_hash = sha256(redacted), sha256(annotated)
    declared_parent = provenance.get("parentSha256", provenance.get("redactedSha256"))
    declared_output = provenance.get("outputSha256", provenance.get("annotatedSha256"))
    if not is_sha256(declared_parent) or str(declared_parent).casefold() != parent_hash.casefold():
        findings.append(_finding("annotation_provenance_parent_mismatch", role="parentSha256"))
    if not is_sha256(declared_output) or str(declared_output).casefold() != output_hash.casefold():
        findings.append(_finding("annotation_provenance_output_mismatch", role="outputSha256"))
    drawing_inputs = provenance.get("drawingInputs")
    stroke, font_size = 3, 26
    if isinstance(drawing_inputs, Mapping):
        stroke = drawing_inputs.get("stroke", stroke)
        font_size = drawing_inputs.get("font_size", font_size)
    expected_inputs = annotation_input_payload(raw, stroke=stroke, font_size=font_size)
    expected_hash = annotation_input_sha256(raw, stroke=stroke, font_size=font_size)
    if drawing_inputs != expected_inputs:
        findings.append(_finding("annotation_provenance_geometry_mismatch", role="drawingInputs"))
    declared_input = provenance.get("drawingInputSha256", provenance.get("inputSha256"))
    if declared_input != expected_hash:
        findings.append(_finding("annotation_provenance_input_mismatch", role="drawingInputSha256"))


def validate_manifest(
    manifest_path: str | Path,
    base_dir: str | Path | None = None,
    require_coordinate_provenance: bool = False,
) -> dict[str, Any]:
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
    raw = _load(path)
    if raw is None:
        findings.append(_finding("manifest_unreadable"))
        return report

    if require_coordinate_provenance:
        report["limitations"].append("coordinate_provenance_does_not_prove_pixel_alignment")

    schema = raw.get("schema_version")
    if isinstance(schema, bool) or schema != SCHEMA_VERSION:
        findings.append(_finding("schema_version_invalid"))

    source_hash = raw.get("sourceSha256")
    if not is_sha256(source_hash):
        findings.append(_finding("source_sha256_invalid", role="sourceSha256"))
    source_kind = raw.get("sourceKind")
    if not is_text(source_kind):
        findings.append(_finding("field_missing", role="sourceKind"))
    elif source_kind.casefold() not in SOURCE_KINDS:
        findings.append(_finding("source_kind_invalid"))
    capture_kind = raw.get("captureKind")
    if not is_text(capture_kind):
        findings.append(_finding("field_missing", role="captureKind"))
    elif capture_kind not in CAPTURE_KINDS:
        findings.append(_finding("capture_kind_invalid"))

    expected_size = positive_size(raw.get("originalImageSize"))
    if expected_size is None:
        findings.append(_finding("original_image_size_invalid", role="originalImageSize"))
    state = raw.get("captureState")
    findings.extend(
        _finding("capture_binding_invalid", role="captureState")
        for _ in capture_binding_errors(raw, expected_size, require=True)
    )

    if require_coordinate_provenance:
        if capture_kind not in {"viewport-sequence", "detail"}:
            findings.append(_finding("coordinate_capture_kind_unsupported", role="captureKind"))
        coordinate_transform = state.get("coordinateTransform") if isinstance(state, Mapping) else None
        if not isinstance(coordinate_transform, Mapping):
            findings.append(_finding("coordinate_transform_missing", role="captureState"))
        else:
            try:
                clip = _coordinate_rect(coordinate_transform.get("clip"), "coordinate_clip_invalid")
                transform_css_viewport_bbox(
                    {"x": clip[0], "y": clip[1], "width": min(clip[2], 1.0), "height": min(clip[3], 1.0)},
                    coordinate_transform,
                )
            except CoordinateTransformError as error:
                findings.append(_finding(error.code, role="coordinateTransform"))
            screenshot_size = positive_size(coordinate_transform.get("screenshotSize"))
            if expected_size is not None and screenshot_size is not None and screenshot_size != expected_size:
                findings.append(_finding("coordinate_screenshot_size_mismatch", role="coordinateTransform"))
            elif expected_size is not None and screenshot_size is None:
                findings.append(_finding("coordinate_screenshot_size_invalid", role="coordinateTransform"))

    review_status = _status(raw.get("reviewStatus"), REVIEW_STATUSES)
    if review_status is None:
        findings.append(_finding("approval_status_missing", role="reviewStatus"))
    elif review_status == "pending":
        findings.append(_finding("approval_pending", role="reviewStatus"))
    elif review_status == "blocked":
        findings.append(_finding("approval_blocked", role="reviewStatus"))

    files: dict[str, Path] = {}
    for role, field in (("raw", "sourceImage"), ("redacted", "redactedImage"), ("annotated", "annotatedImage")):
        value = raw.get(field)
        if not is_text(value):
            findings.append(_finding("field_missing", role=field))
            continue
        resolved = _resolve(value, path, base_dir)
        if resolved is None:
            findings.append(_finding("file_path_invalid", role=role))
            continue
        files[role] = resolved
    file_roles = list(files)
    for left_index, left_role in enumerate(file_roles):
        for right_role in file_roles[left_index + 1:]:
            if file_alias(files[left_role], files[right_role]):
                findings.append(_finding("file_alias", role=left_role))

    actual_sizes: dict[str, tuple[int, int]] = {}
    for role, image_path in files.items():
        try:
            dimensions = image_size(image_path, require_png=True)
            digest = sha256(image_path)
        except (OSError, ValueError):
            findings.append(_finding("file_unreadable", role=role))
            report["files"].append({"role": role, "status": "blocked"})
            continue
        actual_sizes[role] = dimensions
        report["files"].append({"role": role, "status": "pass", "sha256": digest,
                                 "width": dimensions[0], "height": dimensions[1]})
    raw_size = actual_sizes.get("raw")
    if expected_size is not None:
        if raw_size is not None and raw_size != expected_size:
            findings.append(_finding("raw_size_mismatch", role="raw"))
        for role in ("redacted", "annotated"):
            if role in actual_sizes and actual_sizes[role] != expected_size:
                findings.append(_finding("image_dimensions_mismatch", role=role))
    if raw_size is not None and is_sha256(source_hash) and sha256(files["raw"]).casefold() != source_hash.casefold():
        findings.append(_finding("source_sha256_mismatch", role="raw"))
    for role, field in (("redacted", "redactedSha256"), ("annotated", "annotatedSha256")):
        if field not in raw:
            findings.append(_finding(f"{role}_sha256_missing", role=field))
            continue
        declared = raw.get(field)
        if not is_sha256(declared):
            findings.append(_finding(f"{role}_sha256_invalid", role=field))
        elif role in files and role in actual_sizes and sha256(files[role]).casefold() != str(declared).casefold():
            findings.append(_finding(f"{role}_sha256_mismatch", role=role))

    redactions = raw.get("redactions")
    redaction_boxes: list[tuple[float, float, float, float] | None] = []
    if not isinstance(redactions, list):
        findings.append(_finding("redactions_invalid", role="redactions"))
    else:
        if not redactions and not is_text(raw.get("noSensitiveDataReason")):
            findings.append(_finding("no_sensitive_reason_missing", role="noSensitiveDataReason"))
        for index, item in enumerate(redactions):
            if not isinstance(item, Mapping):
                findings.append(_finding("redaction_invalid", index=index))
                redaction_boxes.append(None)
                continue
            box = bbox(item.get("bbox"), expected_size)
            redaction_boxes.append(box)
            if box is None:
                findings.append(_finding("bbox_invalid", role="redaction", index=index))
            for field in ("category", "method"):
                if not is_text(item.get(field)):
                    findings.append(_finding("redaction_field_missing", role=field, index=index))
            category = item.get("category")
            if is_text(category) and category.strip().casefold() not in REDACTION_CATEGORIES:
                findings.append(_finding("redaction_category_invalid", index=index))
            if is_text(category) and category.strip().casefold() == "amount" and raw.get("amountPolicy") not in {"mask", "masked"}:
                findings.append(_finding("amount_policy_missing", index=index))
            status = _status(item.get("status"), REDACTION_STATUSES)
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
            identifier = item.get("id")
            if not is_text(identifier):
                findings.append(_finding("annotation_id_missing", index=index))
            elif str(identifier) in annotation_ids:
                findings.append(_finding("annotation_id_duplicate", index=index))
            else:
                annotation_ids.add(str(identifier))
            for field in ("controlName", "caption"):
                if not is_text(item.get(field)):
                    findings.append(_finding("annotation_field_missing", role=field, index=index))
            if not is_text(item.get("source", item.get("provenance"))):
                findings.append(_finding("annotation_source_missing", index=index))
            annotation_box = bbox(item.get("bbox"), expected_size)
            if annotation_box is None:
                findings.append(_finding("bbox_invalid", role="annotation", index=index))
            else:
                x, y, width, height = annotation_box
                border = max(3, math.ceil(26 * 0.16))
                badge = badge_box(
                    x,
                    y,
                    26 + 2 * border,
                    26 + 2 * border,
                    expected_size[0] if expected_size is not None else int(x + width),
                    expected_size[1] if expected_size is not None else int(y + height),
                    bbox_width=width,
                    bbox_height=height,
                    badge_spec=item.get("badgePosition", item.get("badge")),
                )
                if badge is None:
                    findings.append(_finding("badge_out_of_bounds", role="annotation", index=index))
            cursor = item.get("cursor")
            if cursor is not None:
                if not isinstance(cursor, Mapping) or any(
                    isinstance(cursor.get(axis), bool)
                    or not isinstance(cursor.get(axis), (int, float))
                    for axis in ("x", "y")
                ):
                    findings.append(_finding("cursor_invalid", index=index))
                elif expected_size is not None and not (
                    0 <= cursor["x"] <= expected_size[0] and 0 <= cursor["y"] <= expected_size[1]
                ):
                    findings.append(_finding("cursor_out_of_bounds", index=index))
            badge = item.get("badgePosition", item.get("badge"))
            if badge is not None and not isinstance(badge, Mapping):
                findings.append(_finding("badge_invalid", index=index))
            status = _status(item.get("status"), ANNOTATION_STATUSES)
            if status is None:
                findings.append(_finding("annotation_status_missing", index=index))
            elif status == "pending":
                findings.append(_finding("approval_pending", role="annotation", index=index))
            elif status == "blocked":
                findings.append(_finding("approval_blocked", role="annotation", index=index))
            if require_coordinate_provenance:
                findings.extend(
                    _annotation_coordinate_findings(
                        item,
                        index,
                        source_hash,
                        state if isinstance(state, Mapping) else None,
                        expected_size,
                    )
                )

    protected_boxes: list[tuple[float, float, float, float] | None] = []
    protected = raw.get("protectedAreas", raw.get("protectedControls", []))
    if not isinstance(protected, list):
        findings.append(_finding("protected_areas_invalid", role="protectedAreas"))
    else:
        for index, item in enumerate(protected):
            box = bbox(item.get("bbox") if isinstance(item, Mapping) else None, expected_size)
            protected_boxes.append(box)
            if box is None:
                findings.append(_finding("bbox_invalid", role="protected-area", index=index))
    for redaction_index, redaction_box in enumerate(redaction_boxes):
        if redaction_box is None:
            continue
        for protected_index, protected_box in enumerate(protected_boxes):
            if protected_box is not None and overlap(redaction_box, protected_box):
                findings.append(_finding("redaction_overlaps_protected_area", role="redaction", index=redaction_index))

    _validate_capture_provenance(raw, path, base_dir, files, findings)
    redaction_ref = raw.get("redactionProvenance", raw.get("redactProvenance", raw.get("provenance")))
    annotation_ref = raw.get("annotationProvenance", raw.get("annotatedProvenance"))
    # Canonical schema manifests must carry both tool-generated derivation
    # records.  Legacy adapter-only manifests are still accepted by redact.py
    # and annotate.py, but cannot pass this formal per-image gate.
    if schema == SCHEMA_VERSION:
        if redaction_ref is None:
            findings.append(_finding("redaction_provenance_missing", role="redactionProvenance"))
        else:
            redaction_provenance = _provenance_value(redaction_ref, path, base_dir)
            if redaction_provenance is None:
                findings.append(_finding("redaction_provenance_invalid", role="redactionProvenance"))
            else:
                _validate_redaction_provenance(raw, redaction_provenance, files, findings)
        if annotation_ref is None:
            findings.append(_finding("annotation_provenance_missing", role="annotationProvenance"))
        else:
            annotation_provenance = _provenance_value(annotation_ref, path, base_dir)
            if annotation_provenance is None:
                findings.append(_finding("annotation_provenance_invalid", role="annotationProvenance"))
            else:
                _validate_annotation_provenance(raw, annotation_provenance, files, findings)
    if require_coordinate_provenance:
        coordinate_findings = [item for item in findings if item["code"].startswith("coordinate_")]
        coordinate_status = "pass"
        if coordinate_findings:
            coordinate_status = (
                "blocked"
                if all(item["code"] in COORDINATE_BLOCKED_CODES for item in coordinate_findings)
                else "fail"
            )
        report["coordinate_provenance"] = {"required": True, "status": coordinate_status}

    geometry_codes = [
        item["code"]
        for item in findings
        if item["code"] not in PENDING_CODES and item["code"] not in COORDINATE_BLOCKED_CODES
    ]
    report["geometry_status"] = "fail" if geometry_codes else "pass"
    if geometry_codes:
        report["manifest_status"] = "fail"
    elif findings:
        report["manifest_status"] = "blocked"
    else:
        report["manifest_status"] = "pass"
    report["status"] = report["manifest_status"]
    return report


def _output_conflicts(output: str, manifest: str | Path, base_dir: str | Path | None) -> bool:
    if output == "-":
        return False
    manifest_path = Path(manifest).expanduser().resolve()
    destination = Path(output).expanduser().resolve()
    if destination.exists():
        return True
    if destination == manifest_path:
        return True
    raw = _load(manifest_path)
    if raw is None:
        return True
    for field in ("sourceImage", "redactedImage", "annotatedImage"):
        value = _resolve(raw.get(field), manifest_path, base_dir)
        if value is not None and (destination == value or (value.exists() and destination.exists() and file_alias(destination, value))):
            return True
    for field in ("captureProvenance", "redactionProvenance", "redactProvenance", "annotationProvenance", "annotatedProvenance", "provenance"):
        value = raw.get(field)
        if isinstance(value, str):
            resolved = _resolve(value, manifest_path, base_dir)
            if resolved is not None and file_alias(destination, resolved):
                return True
    return False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate one lite screenshot evidence manifest.")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--base-dir")
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--require-coordinate-provenance",
        action="store_true",
        help="Require calibrated CSS-viewport to PNG provenance for DOM annotations",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if _output_conflicts(args.output, args.manifest, args.base_dir):
        return 2
    report = validate_manifest(args.manifest, args.base_dir, args.require_coordinate_provenance)
    payload = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if args.output == "-":
        sys.stdout.write(payload)
    else:
        try:
            destination = Path(args.output).expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(payload, encoding="utf-8")
        except OSError:
            return 2
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
