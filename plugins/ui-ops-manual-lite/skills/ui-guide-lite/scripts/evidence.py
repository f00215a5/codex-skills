"""Shared per-image evidence helpers for the lite screenshot workflow.

The screenshot manifest is the single source of truth.  ``redact.py``,
``annotate.py`` and ``validate_screenshot_manifest.py`` use these helpers so
the legacy single-purpose commands remain adapters over the same capture,
hash, size and coordinate contract.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from PIL import Image


SOURCE_KINDS = {"captured", "provided", "reused", "schematic"}
CAPTURE_KINDS = {"full-page", "viewport-sequence", "detail"}
SHA256_HEX_LENGTH = 64
REDACTION_CATEGORIES = {
    "name",
    "identity-id",
    "customer-id",
    "member-id",
    "employee-id",
    "address",
    "phone",
    "email",
    "policy-number",
    "bill-number",
    "contract-number",
    "transaction-id",
    "case-id",
    "password",
    "token",
    "api-key",
    "session-value",
    "internal-account",
    "amount",
}
REDACTION_INPUT_SCHEMA_VERSION = 1
ANNOTATION_INPUT_SCHEMA_VERSION = 1


def is_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def is_sha256(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != SHA256_HEX_LENGTH:
        return False
    try:
        int(value, 16)
    except ValueError:
        return False
    return True


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_bytes(value: bytes) -> str:
    """Return a deterministic SHA-256 digest for generated evidence input."""

    return hashlib.sha256(value).hexdigest()


def canonical_json(value: Any) -> str:
    """Serialize safe tool inputs without depending on dict insertion order."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _coordinate(value: Any) -> Any:
    """Normalize numeric JSON values while rejecting booleans as coordinates."""

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return value
    number = float(value)
    return int(number) if number.is_integer() else number


def redaction_input_payload(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the fields that affect raw-to-redacted pixels.

    Review statuses and category labels are deliberately excluded: changing a
    pending item to checked must not make an already drawn image stale.  The
    geometry and method are included because either changes pixels.
    """

    redactions = manifest.get("redactions", [])
    values: list[dict[str, Any]] = []
    if isinstance(redactions, list):
        for item in redactions:
            if not isinstance(item, Mapping):
                values.append({"invalid": item})
                continue
            box = item.get("bbox")
            values.append(
                {
                    "bbox": {
                        key: _coordinate(box.get(key))
                        for key in ("x", "y", "width", "height")
                    }
                    if isinstance(box, Mapping)
                    else box,
                    "method": item.get("method", "opaque-rectangle"),
                }
            )
    else:
        values.append({"invalid": redactions})
    return {"schema_version": REDACTION_INPUT_SCHEMA_VERSION, "redactions": values}


def redaction_input_sha256(manifest: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(redaction_input_payload(manifest)).encode("utf-8"))


def annotation_input_payload(
    manifest: Mapping[str, Any], *, stroke: int = 3, font_size: int = 26
) -> dict[str, Any]:
    """Return the pixel-affecting annotation inputs.

    Text-only fields such as ``caption``, ``controlName`` and review statuses
    are intentionally omitted.  They are reviewed content, not pixels drawn by
    ``annotate.py``.  Badge configuration is retained as supplied in the one
    integrated manifest so a manual badge adjustment invalidates old output.
    """

    annotations = manifest.get("annotations", [])
    values: list[dict[str, Any]] = []
    if isinstance(annotations, list):
        for item in annotations:
            if not isinstance(item, Mapping):
                values.append({"invalid": item})
                continue
            box = item.get("bbox")
            value: dict[str, Any] = {
                "id": item.get("id"),
                "bbox": {
                    key: _coordinate(box.get(key))
                    for key in ("x", "y", "width", "height")
                }
                if isinstance(box, Mapping)
                else box,
            }
            cursor = item.get("cursor")
            if isinstance(cursor, Mapping):
                value["cursor"] = {
                    key: _coordinate(cursor.get(key)) for key in ("x", "y")
                }
            elif cursor is not None:
                value["cursor"] = cursor
            for key in ("badge", "badgePosition"):
                if key in item:
                    value[key] = item[key]
            values.append(value)
    else:
        values.append({"invalid": annotations})
    return {
        "schema_version": ANNOTATION_INPUT_SCHEMA_VERSION,
        "stroke": stroke,
        "font_size": font_size,
        "annotations": values,
    }


def annotation_input_sha256(
    manifest: Mapping[str, Any], *, stroke: int = 3, font_size: int = 26
) -> str:
    return sha256_bytes(
        canonical_json(annotation_input_payload(manifest, stroke=stroke, font_size=font_size)).encode(
            "utf-8"
        )
    )


def image_size(path: Path, *, require_png: bool = False) -> tuple[int, int]:
    with Image.open(path) as image:
        if require_png and image.format != "PNG":
            raise ValueError(f"image must be PNG: {path}")
        width, height = image.size
        if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
            raise ValueError(f"image dimensions must be positive: {path}")
        image.load()
        return width, height


def positive_size(value: Any) -> tuple[int, int] | None:
    if not isinstance(value, Mapping):
        return None
    width, height = value.get("width"), value.get("height")
    if isinstance(width, bool) or isinstance(height, bool):
        return None
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return None
    return width, height


def bbox(value: Any, image_dimensions: tuple[int, int] | None = None) -> tuple[float, float, float, float] | None:
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
    if image_dimensions is not None:
        image_width, image_height = image_dimensions
        if x + width > image_width or y + height > image_height:
            return None
    return x, y, width, height


def overlap(left: tuple[float, float, float, float], right: tuple[float, float, float, float]) -> bool:
    left_x, left_y, left_width, left_height = left
    right_x, right_y, right_width, right_height = right
    return (
        max(left_x, right_x) < min(left_x + left_width, right_x + right_width)
        and max(left_y, right_y) < min(left_y + left_height, right_y + right_height)
    )


def protected_items(manifest: Mapping[str, Any]) -> list[Any]:
    """Read the canonical protectedAreas list with a compatibility alias."""

    value = manifest.get("protectedAreas")
    if value is None:
        value = manifest.get("protectedControls", [])
    return list(value) if isinstance(value, list) else []


def _calibration_errors(
    calibration: Any,
    *,
    capture_kind: str | None,
    image_dimensions: tuple[int, int] | None,
    require: bool = False,
) -> list[str]:
    if not is_text(calibration) and not isinstance(calibration, Mapping):
        return ["captureState.calibration is required for formal evidence"]
    if isinstance(calibration, str):
        return ["captureState.calibration must be a structured per-image record"] if require else []
    errors: list[str] = []
    mode = calibration.get("mode", calibration.get("method"))
    if mode is not None and not is_text(mode):
        errors.append("captureState.calibration.mode must be text")
    png_size = calibration.get("pngSize", calibration.get("imageSize"))
    if require and png_size is None:
        errors.append("captureState.calibration.pngSize is required for formal evidence")
    if png_size is not None:
        declared = positive_size(png_size)
        if declared is None:
            errors.append("captureState.calibration.pngSize must be positive")
        elif image_dimensions is not None and declared != image_dimensions:
            errors.append("captureState.calibration.pngSize does not match image")
    viewport = calibration.get("viewportCssSize")
    if require and viewport is None:
        errors.append("captureState.calibration.viewportCssSize is required for formal evidence")
    if viewport is not None and positive_size(viewport) is None:
        errors.append("captureState.calibration.viewportCssSize must be positive")
    has_explicit_calibration = False
    for key in ("pixelScale", "scale"):
        if key not in calibration:
            continue
        value = calibration[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            errors.append(f"captureState.calibration.{key} must be a positive finite number")
        else:
            has_explicit_calibration = True
    for key in ("controlCalibration", "knownControl"):
        if key not in calibration:
            continue
        value = calibration[key]
        if not isinstance(value, Mapping):
            errors.append(f"captureState.calibration.{key} must be an object")
            continue
        control_box = bbox(value.get("bbox"), image_dimensions)
        if control_box is None:
            errors.append(f"captureState.calibration.{key}.bbox must be within the image")
        else:
            has_explicit_calibration = True
    if require and not has_explicit_calibration:
        errors.append(
            "captureState.calibration must include an explicit per-image scale or known control calibration"
        )
    if capture_kind == "full-page":
        # Full-page output may be taller than the viewport and may be
        # re-laid out.  A height ratio is therefore not a device-pixel scale.
        has_explicit_scale = any(
            key in calibration for key in ("pixelScale", "scale", "controlCalibration", "knownControl")
        )
        has_naive_ratio_inputs = "pngHeight" in calibration and "viewportHeight" in calibration
        if has_naive_ratio_inputs and not has_explicit_scale:
            errors.append(
                "full-page calibration must provide an explicit per-image scale/control calibration; "
                "pngHeight/viewportHeight cannot define DPR"
            )
    return errors


def capture_binding_errors(
    manifest: Mapping[str, Any],
    image_dimensions: tuple[int, int] | None,
    *,
    require: bool = False,
) -> list[str]:
    """Validate hash, capture state and per-image coordinate calibration.

    ``captureState`` is the canonical binding name.  ``captureBinding`` is
    accepted as an explicit adapter alias for callers that use that wording;
    if both are present their id/hash must agree.
    """

    errors: list[str] = []
    source_hash = manifest.get("sourceSha256")
    if require and not is_sha256(source_hash):
        errors.append("sourceSha256 is required for the formal evidence gate")
    elif source_hash is not None and not is_sha256(source_hash):
        errors.append("sourceSha256 must be a SHA-256 hex digest")

    declared_size = manifest.get("originalImageSize")
    if require and positive_size(declared_size) is None:
        errors.append("originalImageSize is required for the formal evidence gate")
    elif declared_size is not None and positive_size(declared_size) is None:
        errors.append("originalImageSize must contain positive width and height")
    if image_dimensions is not None and positive_size(declared_size) is not None:
        if positive_size(declared_size) != image_dimensions:
            errors.append("originalImageSize does not match source image")

    state = manifest.get("captureState")
    binding = manifest.get("captureBinding")
    if require and not isinstance(state, Mapping) and not isinstance(binding, Mapping):
        errors.append("captureState/captureBinding is required for the formal evidence gate")
    if state is not None and not isinstance(state, Mapping):
        errors.append("captureState must be an object")
    if binding is not None and not isinstance(binding, Mapping):
        errors.append("captureBinding must be an object")

    ids: list[str] = []
    hashes: list[str] = []
    for label, container in (("captureState", state), ("captureBinding", binding)):
        if not isinstance(container, Mapping):
            continue
        identifier = container.get("id", container.get("captureStateId", container.get("captureId")))
        if require and not is_text(identifier):
            errors.append(f"{label}.id is required for the formal evidence gate")
        elif identifier is not None and not is_text(identifier):
            errors.append(f"{label}.id must be non-empty text")
        elif is_text(identifier):
            ids.append(identifier.strip())
        state_hash = container.get("rawSha256", container.get("sourceSha256"))
        if require and not is_sha256(state_hash):
            errors.append(f"{label}.rawSha256 is required for the formal evidence gate")
        elif state_hash is not None and not is_sha256(state_hash):
            errors.append(f"{label}.rawSha256 must be a SHA-256 hex digest")
        elif is_sha256(state_hash):
            hashes.append(state_hash.casefold())
            if is_sha256(source_hash) and state_hash.casefold() != source_hash.casefold():
                errors.append(f"{label}.rawSha256 does not match sourceSha256")

    metadata_label, metadata = (
        ("captureState", state) if isinstance(state, Mapping)
        else ("captureBinding", binding) if isinstance(binding, Mapping)
        else (None, None)
    )
    if require and isinstance(metadata, Mapping):
        if positive_size(metadata.get("viewportCssSize")) is None:
            errors.append(f"{metadata_label}.viewportCssSize is required and must be positive")
        scroll = metadata.get("scroll")
        if not isinstance(scroll, Mapping):
            errors.append(f"{metadata_label}.scroll is required for the formal evidence gate")
        else:
            for axis in ("x", "y"):
                value = scroll.get(axis)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                    errors.append(f"{metadata_label}.scroll.{axis} must be a finite non-negative number")

    if len(ids) == 2 and ids[0] != ids[1]:
        errors.append("captureState and captureBinding ids do not match")
    if len(hashes) == 2 and hashes[0] != hashes[1]:
        errors.append("captureState and captureBinding hashes do not match")

    capture_kind = manifest.get("captureKind")
    if require and not is_text(capture_kind):
        errors.append("captureKind is required for the formal evidence gate")
    elif capture_kind is not None and capture_kind not in CAPTURE_KINDS:
        errors.append(f"unknown captureKind {capture_kind!r}")
    if capture_kind == "detail" and not is_text(manifest.get("detailOf", manifest.get("mainImage"))):
        errors.append("detail capture must identify its complete main image")

    calibration = None
    if isinstance(state, Mapping):
        calibration = state.get("calibration", state.get("coordinateCalibration"))
    if calibration is None and isinstance(binding, Mapping):
        calibration = binding.get("calibration", binding.get("coordinateCalibration"))
    if calibration is None:
        calibration = manifest.get("coordinateCalibration")
    if require or calibration is not None:
        errors.extend(
            _calibration_errors(
                calibration,
                capture_kind=capture_kind if isinstance(capture_kind, str) else None,
                image_dimensions=image_dimensions,
                require=require,
            )
        )
    return errors


def file_alias(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve() or left.samefile(right)
    except OSError:
        return left.resolve() == right.resolve()
