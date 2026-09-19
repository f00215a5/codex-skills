#!/usr/bin/env python3
"""Create and check pixel-redacted screenshot evidence (Pillow only).

The redaction manifest contains categories and source-image coordinates, never
the source values themselves.  ``draw`` accepts pending redactions so that a
reviewable flattened preview exists before anybody records an approval.  Use
``check --require-checked`` at the evidence gate after a direct image review.

Examples::

    python redact.py draw --image raw/page.png --manifest redaction.json \
        --output redacted/page.png --provenance-output qa/page-provenance.json
    python redact.py check --image raw/page.png --redacted redacted/page.png \
        --manifest redaction.json --require-checked

The script can verify file identity, dimensions and rectangle bounds.  It
cannot prove that a human found every sensitive value; the independent lite
reviewer must inspect the raw/redacted pair when available.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

try:
    from evidence import bbox as evidence_bbox
    from evidence import (
        REDACTION_CATEGORIES,
        capture_binding_errors,
        file_alias,
        overlap,
        protected_items,
        redaction_input_payload,
        redaction_input_sha256,
    )
except ImportError:  # pragma: no cover - package import fallback
    from .evidence import bbox as evidence_bbox  # type: ignore[no-redef]
    from .evidence import (  # type: ignore[no-redef]
        REDACTION_CATEGORIES,
        capture_binding_errors,
        file_alias,
        overlap,
        protected_items,
        redaction_input_payload,
        redaction_input_sha256,
    )


DEFAULT_FILL = (31, 31, 31)
SOURCE_KINDS = {"captured", "provided", "reused", "schematic"}
REDACTION_METHODS = {"opaque-rectangle", "pixelate"}
REDACTION_STATUSES = {"pending", "checked", "blocked"}
# Kept as a descriptive compatibility alias for callers importing the old
# constant.  The shared helper is the single legal-category source.
SENSITIVE_CATEGORIES = REDACTION_CATEGORIES
FORBIDDEN_VALUE_KEYS = {
    "value",
    "rawvalue",
    "raw_value",
    "originalvalue",
    "original_value",
    "secret",
    "plaintext",
    "textvalue",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read manifest {path}: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("manifest must be a JSON object")
    if not isinstance(payload.get("redactions"), list):
        raise ValueError("manifest must contain a 'redactions' list")
    return payload


def _contains_forbidden_key(value: Any, path: str = "$") -> str | None:
    if isinstance(value, dict):
        for key, nested in value.items():
            if str(key).casefold().replace("-", "_") in {
                item.replace("-", "_") for item in FORBIDDEN_VALUE_KEYS
            }:
                return f"{path}.{key}: sensitive value fields are not allowed"
            found = _contains_forbidden_key(nested, f"{path}.{key}")
            if found:
                return found
    elif isinstance(value, list):
        for index, nested in enumerate(value):
            found = _contains_forbidden_key(nested, f"{path}[{index}]")
            if found:
                return found
    return None


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _resolve_reference(value: Any, manifest_path: Path) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if not path.is_absolute():
        path = manifest_path.parent / path
    try:
        return path.expanduser().resolve()
    except OSError:
        return None


def _schematic_error(manifest: dict[str, Any]) -> str | None:
    source = manifest.get("screenshotSource")
    source_kind = manifest.get("sourceKind")
    if not isinstance(source_kind, str) or not source_kind.strip():
        return "sourceKind is required (captured, provided, reused or schematic)"
    kind = source_kind.strip().casefold()
    if kind == "schematic" and not (
        manifest.get("schematicApproved") is True
        or manifest.get("allowSchematic") is True
        or (isinstance(source, dict) and source.get("approved") is True)
    ):
        return "schematic source requires explicit user approval (set schematicApproved=true)"
    if kind not in SOURCE_KINDS:
        return f"unknown sourceKind {kind!r}"
    return None


def validate_manifest(
    manifest: dict[str, Any],
    image_path: Path,
    manifest_path: Path,
    *,
    redacted_path: Path | None = None,
    require_checked: bool = False,
) -> list[str]:
    errors: list[str] = []
    forbidden = _contains_forbidden_key(manifest)
    if forbidden:
        errors.append(forbidden)
    if schematic_error := _schematic_error(manifest):
        errors.append(schematic_error)

    try:
        with Image.open(image_path) as probe:
            width, height = probe.size
    except (OSError, ValueError) as error:
        return [f"cannot open raw image {image_path}: {error}"]

    declared_size = manifest.get("originalImageSize")
    if isinstance(declared_size, dict):
        if declared_size.get("width") != width or declared_size.get("height") != height:
            errors.append(
                "originalImageSize does not match raw image "
                f"({declared_size.get('width')}x{declared_size.get('height')} != {width}x{height})"
            )
    elif declared_size is not None:
        errors.append("originalImageSize must contain width and height")

    source_hash = manifest.get("sourceSha256")
    if source_hash is not None:
        if not isinstance(source_hash, str) or len(source_hash) != 64:
            errors.append("sourceSha256 must be a SHA-256 hex digest")
        else:
            try:
                actual = sha256(image_path)
            except OSError as error:
                errors.append(f"cannot hash raw image: {error}")
            else:
                if actual.casefold() != source_hash.casefold():
                    errors.append("sourceSha256 does not match raw image")

    redactions = manifest["redactions"]
    for index, item in enumerate(redactions):
        label = f"redactions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: entry must be an object")
            continue
        category = item.get("category")
        if not isinstance(category, str) or not category.strip():
            errors.append(f"{label}: missing category")
        elif category.strip().casefold() not in SENSITIVE_CATEGORIES:
            errors.append(f"{label}: unknown category")
        elif category.strip().casefold() == "amount" and manifest.get("amountPolicy") not in {"mask", "masked"}:
            errors.append(f"{label}: amount redaction requires explicit amountPolicy=mask")

        method = item.get("method", "opaque-rectangle")
        if method not in REDACTION_METHODS:
            errors.append(f"{label}: method must be one of {sorted(REDACTION_METHODS)}")
        status = item.get("status", "pending")
        if status not in REDACTION_STATUSES:
            errors.append(f"{label}: status must be one of {sorted(REDACTION_STATUSES)}")
        elif require_checked and status != "checked":
            errors.append(f"{label}: status must be checked before the evidence gate")

        bbox = item.get("bbox")
        if not isinstance(bbox, dict) or not {"x", "y", "width", "height"} <= set(bbox):
            errors.append(f"{label}: bbox must contain x, y, width and height")
            continue
        x, y, box_width, box_height = (bbox[key] for key in ("x", "y", "width", "height"))
        if not all(_finite_number(value) for value in (x, y, box_width, box_height)):
            errors.append(f"{label}: bbox values must be finite numbers")
            continue
        if box_width <= 0 or box_height <= 0:
            errors.append(f"{label}: bbox width and height must be positive")
        if x < 0 or y < 0 or x + box_width > width or y + box_height > height:
            errors.append(
                f"{label}: bbox ({x},{y},{box_width},{box_height}) is outside {width}x{height} raw image"
            )

    protected_boxes = []
    protected = manifest.get("protectedAreas", manifest.get("protectedControls", []))
    if protected is not None and not isinstance(protected, list):
        errors.append("protectedAreas/protectedControls must be a list")
    elif isinstance(protected, list):
        for index, item in enumerate(protected):
            box = evidence_bbox(item.get("bbox") if isinstance(item, dict) else None, (width, height))
            if box is None:
                errors.append(f"protectedAreas[{index}]: bbox must be inside raw image")
            else:
                protected_boxes.append((index, box))

    for redaction_index, item in enumerate(redactions):
        if not isinstance(item, dict):
            continue
        redaction_box = evidence_bbox(item.get("bbox"), (width, height))
        if redaction_box is None:
            continue
        for protected_index, protected_box in protected_boxes:
            if overlap(redaction_box, protected_box):
                errors.append(
                    f"redactions[{redaction_index}]: bbox overlaps protected control area {protected_index}"
                )

    if redacted_path is not None:
        try:
            redacted_resolved = redacted_path.expanduser().resolve()
            image_resolved = image_path.expanduser().resolve()
        except OSError:
            redacted_resolved = redacted_path
            image_resolved = image_path
        if file_alias(redacted_path, image_path):
            errors.append("redacted output must not overwrite the raw image")
        if not redacted_path.is_file():
            errors.append(f"redacted image not found: {redacted_path}")
        else:
            try:
                with Image.open(redacted_path) as probe:
                    if probe.size != (width, height):
                        errors.append("redacted image dimensions do not match raw image")
                    if probe.format != "PNG":
                        errors.append("redacted image must be a flattened PNG")
            except (OSError, ValueError) as error:
                errors.append(f"cannot open redacted image {redacted_path}: {error}")
            declared_redacted_hash = manifest.get("redactedSha256")
            if declared_redacted_hash is not None:
                if not isinstance(declared_redacted_hash, str) or len(declared_redacted_hash) != 64:
                    errors.append("redactedSha256 must be a SHA-256 hex digest")
                elif sha256(redacted_path).casefold() != declared_redacted_hash.casefold():
                    errors.append("redactedSha256 does not match redacted image")
    if require_checked:
        # Legacy redaction-only manifests remain usable as adapters.  A
        # canonical schema/capture state opts into the shared formal binding
        # gate, which prevents checked status from masking stale coordinates.
        canonical_manifest = manifest.get("schema_version") is not None or manifest.get("captureState") is not None or manifest.get("captureBinding") is not None
        if canonical_manifest:
            errors.extend(capture_binding_errors(manifest, (width, height), require=True))
        if not isinstance(source_hash, str) or not source_hash.strip():
            errors.append("sourceSha256 is required for the checked evidence gate")
        if redacted_path is None:
            errors.append("redacted image is required for the checked evidence gate")
        if not canonical_manifest and (not isinstance(manifest.get("redactedSha256"), str) or not manifest.get("redactedSha256", "").strip()):
            errors.append("redactedSha256 is required for the checked evidence gate")
    return errors


def _rectangle(bbox: dict[str, Any]) -> tuple[int, int, int, int]:
    """Convert a fractional box to an inclusive pixel rectangle safely."""

    x0 = int(math.floor(float(bbox["x"])))
    y0 = int(math.floor(float(bbox["y"])))
    x1 = int(math.ceil(float(bbox["x"]) + float(bbox["width"]))) - 1
    y1 = int(math.ceil(float(bbox["y"]) + float(bbox["height"]))) - 1
    return x0, y0, max(x0, x1), max(y0, y1)


def _pixelate(image: Image.Image, bbox: dict[str, Any], block_size: int = 12) -> None:
    x0, y0, x1, y1 = _rectangle(bbox)
    crop = image.crop((x0, y0, x1 + 1, y1 + 1))
    small = crop.resize(
        (max(1, crop.width // block_size), max(1, crop.height // block_size)),
        Image.Resampling.BOX,
    )
    pixelated = small.resize(crop.size, Image.Resampling.NEAREST)
    image.paste(pixelated, (x0, y0))


def draw_redactions(
    manifest: dict[str, Any], raw_path: Path, output_path: Path, manifest_path: Path
) -> dict[str, Any]:
    errors = validate_manifest(manifest, raw_path, manifest_path)
    if errors:
        raise ValueError("; ".join(errors))
    try:
        if file_alias(output_path, raw_path):
            raise ValueError("redacted output must not overwrite the raw image")
        if file_alias(output_path, manifest_path):
            raise ValueError("redacted output must not overwrite the manifest")
        if output_path.exists():
            raise ValueError("redacted output already exists; choose a new immutable output path")
    except OSError:
        pass
    with Image.open(raw_path) as source:
        image = source.convert("RGB")
    # Conversion drops alpha/palette metadata; clear any remaining metadata so
    # EXIF/comments from the raw evidence cannot reach the delivered PNG.
    image.info.clear()
    drawer = ImageDraw.Draw(image)
    for item in manifest["redactions"]:
        bbox = item["bbox"]
        method = item.get("method", "opaque-rectangle")
        if method == "pixelate":
            _pixelate(image, bbox)
        else:
            drawer.rectangle(_rectangle(bbox), fill=DEFAULT_FILL)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    provenance = {
        "schema_version": 1,
        "tool": "redact.py",
        "sourceImage": str(manifest.get("sourceImage", raw_path.name)),
        # validate_manifest requires this field; normalize it so provenance
        # cannot silently claim a default kind when the manifest omitted or
        # differently cased the source declaration.
        "sourceKind": str(manifest["sourceKind"]).strip().casefold(),
        "sourceSha256": sha256(raw_path),
        "redactedImage": str(manifest.get("redactedImage", output_path.name)),
        "redactedSha256": sha256(output_path),
        "parentImage": str(manifest.get("sourceImage", raw_path.name)),
        "parentSha256": sha256(raw_path),
        "outputImage": str(manifest.get("redactedImage", output_path.name)),
        "outputSha256": sha256(output_path),
        "redactionInputSha256": redaction_input_sha256(manifest),
        "redactionInputs": redaction_input_payload(manifest),
        "redactions": [
            {
                "category": item.get("category"),
                "bbox": item.get("bbox"),
                "method": item.get("method", "opaque-rectangle"),
                "status": item.get("status", "pending"),
            }
            for item in manifest["redactions"]
        ],
    }
    state = manifest.get("captureState")
    if isinstance(state, dict):
        # Keep the binding evidence safe and compact; do not copy arbitrary
        # capture payloads or page text into provenance.
        provenance["captureState"] = {
            key: state[key]
            for key in ("id", "rawSha256", "viewportCssSize", "scroll", "calibration")
            if key in state
        }
    binding = manifest.get("captureBinding")
    if isinstance(binding, dict):
        provenance["captureBinding"] = {
            key: binding[key]
            for key in ("id", "captureStateId", "captureId", "rawSha256", "sourceSha256", "calibration")
            if key in binding
        }
    return provenance


def validate_redaction_provenance(
    provenance: dict[str, Any],
    manifest: dict[str, Any],
    raw_path: Path,
    redacted_path: Path,
) -> list[str]:
    """Check provenance emitted by ``draw`` against the current manifest.

    This is deliberately separate from visual review.  It proves that the
    checked files and the listed pixel-affecting redaction inputs are the ones
    used by the tool; it cannot prove a human found every sensitive value.
    """

    errors: list[str] = []
    source_hash = sha256(raw_path)
    redacted_hash = sha256(redacted_path)
    if provenance.get("sourceSha256", provenance.get("parentSha256")) != source_hash:
        errors.append("redaction provenance parent hash does not match raw image")
    if provenance.get("redactedSha256", provenance.get("outputSha256")) != redacted_hash:
        errors.append("redaction provenance output hash does not match redacted image")
    if provenance.get("redactionInputSha256") != redaction_input_sha256(manifest):
        errors.append("redaction provenance inputs do not match manifest redactions")
    expected_inputs = redaction_input_payload(manifest)
    if provenance.get("redactionInputs") != expected_inputs:
        errors.append("redaction provenance redaction inputs do not match manifest")
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    draw = subparsers.add_parser("draw", help="Create a flattened PNG redaction preview.")
    draw.add_argument("--image", required=True, type=Path, help="Raw screenshot path.")
    draw.add_argument("--manifest", required=True, type=Path, help="Redaction manifest JSON.")
    draw.add_argument("--output", required=True, type=Path, help="Redacted PNG output path.")
    draw.add_argument("--provenance-output", type=Path, help="Optional safe provenance JSON path.")

    check = subparsers.add_parser("check", help="Check redaction coordinates and hashes.")
    check.add_argument("--image", required=True, type=Path)
    check.add_argument("--manifest", required=True, type=Path)
    check.add_argument("--redacted", type=Path, help="Redacted PNG to compare, if already drawn.")
    check.add_argument("--provenance", type=Path, help="Optional provenance JSON produced by draw.")
    check.add_argument("--require-checked", action="store_true", help="Require checked status for every rectangle.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    manifest_path = args.manifest.expanduser().resolve()
    try:
        manifest = load_manifest(manifest_path)
        if args.command == "draw":
            raw_path = args.image.expanduser().resolve()
            output_path = args.output.expanduser().resolve()
            provenance_path = args.provenance_output.expanduser().resolve() if args.provenance_output else None
            forbidden = {raw_path, manifest_path}
            if any(file_alias(output_path, path) for path in forbidden) or (
                provenance_path is not None and any(file_alias(provenance_path, path) for path in forbidden)
            ):
                raise ValueError("output and provenance paths must not overwrite raw image or manifest")
            if provenance_path is not None and file_alias(provenance_path, output_path):
                raise ValueError("provenance output must be different from redacted image output")
            if output_path.exists():
                raise ValueError("redacted output already exists; choose a new immutable output path")
            if provenance_path is not None and provenance_path.exists():
                raise ValueError("provenance output already exists; choose a new immutable output path")
            provenance = draw_redactions(
                manifest,
                raw_path,
                output_path,
                manifest_path,
            )
            if provenance_path is not None:
                destination = provenance_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(
                    json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
            print(f"REDACTED_IMAGE={output_path}")
            print("PROVENANCE=" + json.dumps(provenance, ensure_ascii=False, sort_keys=True))
        else:
            raw = args.image.expanduser().resolve()
            redacted = args.redacted
            if redacted is None:
                redacted = _resolve_reference(manifest.get("redactedImage"), manifest_path)
            provenance = None
            if args.provenance:
                try:
                    provenance = json.loads(args.provenance.expanduser().resolve().read_text(encoding="utf-8"))
                except (OSError, UnicodeError, json.JSONDecodeError) as error:
                    raise ValueError(f"cannot read provenance {args.provenance}: {error}") from error
                if not isinstance(provenance, dict):
                    raise ValueError("provenance must be a JSON object")
                if manifest.get("sourceSha256") is None:
                    manifest["sourceSha256"] = provenance.get("sourceSha256")
                if manifest.get("redactedSha256") is None:
                    manifest["redactedSha256"] = provenance.get("redactedSha256")
                if redacted is None or not redacted.is_file():
                    raise ValueError("redacted image is required when checking provenance")
                provenance_errors = validate_redaction_provenance(
                    provenance, manifest, raw, redacted.expanduser().resolve()
                )
                if provenance_errors:
                    raise ValueError("; ".join(provenance_errors))
                if args.require_checked:
                    for field in ("sourceSha256", "redactedSha256"):
                        declared = manifest.get(field)
                        observed = provenance.get(field)
                        if isinstance(declared, str) and isinstance(observed, str) and declared.casefold() != observed.casefold():
                            raise ValueError(f"provenance {field} does not match manifest")
                    state = manifest.get("captureState")
                    provenance_state = provenance.get("captureState")
                    if isinstance(state, dict) and isinstance(provenance_state, dict):
                        if state.get("id") != provenance_state.get("id") or str(state.get("rawSha256", "")).casefold() != str(provenance_state.get("rawSha256", "")).casefold():
                            raise ValueError("provenance captureState does not match manifest")
            errors = validate_manifest(
                manifest,
                raw,
                manifest_path,
                redacted_path=redacted,
                require_checked=args.require_checked,
            )
            if errors:
                for message in errors:
                    print(f"redact.py check: {message}", file=sys.stderr)
                return 1
            print(
                f"redact.py check: OK ({len(manifest['redactions'])} redactions; "
                f"sourceSha256={sha256(raw)})"
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"redact.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
