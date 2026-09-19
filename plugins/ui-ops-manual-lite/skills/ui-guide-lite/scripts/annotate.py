#!/usr/bin/env python3
"""Draw and verify red-box/number annotations on UI screenshots (Pillow only).

Subcommands:
    draw  --image REDACTED --annotations ANN.json --output OUT.png
    check --image REDACTED --annotations ANN.json

Manifest schema (same shape as the QA reference):

    {
      "sourceImage": "redacted/create-task.png",
      "originalImageSize": {"width": 1920, "height": 1080},
      "annotations": [
        {
          "id": "1",
          "controlName": "儲存",
          "caption": "紅框 1：儲存按鈕。",
          "bbox": {"x": 1050, "y": 670, "width": 92, "height": 40},
          "cursor": {"x": 900, "y": 700},   # optional
          "status": "proposed"              # preview; approval is a separate review step
        }
      ]
    }

`check` validates geometry and caption references.  It deliberately permits
``proposed`` annotations so a preview can be drawn before semantic review.
Use ``--require-approved`` for the build gate.  ``manual-adjusted`` is a
provenance value (accepted for compatibility when used as ``status``), never
an approval by itself.  Visual QA (box hugging the control, not covering
text) stays a human 100% side-by-side check per references/annotation-qa.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

try:
    from evidence import (
        annotation_input_payload,
        annotation_input_sha256,
        capture_binding_errors,
        file_alias,
        image_size,
        is_sha256,
        is_text,
    )
except ImportError:  # pragma: no cover - package import fallback
    from .evidence import (  # type: ignore[no-redef]
        annotation_input_payload,
        annotation_input_sha256,
        capture_binding_errors,
        file_alias,
        image_size,
        is_sha256,
        is_text,
    )

RED = (214, 69, 69)  # kept distinct from the teal brand so it reads as an alert
PREVIEW_STATUSES = {"proposed", "pending", "manual-adjusted"}
APPROVED_STATUSES = {"approved", "verified", "checked"}
KNOWN_STATUSES = PREVIEW_STATUSES | APPROVED_STATUSES | {"blocked"}
KNOWN_PROVENANCE = {"dom-derived", "manual-adjusted", "captured", "provided", "reused"}
CAPTION_PATTERN = re.compile(r"紅框\s*(\d+)")


def load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("annotations"), list):
        raise ValueError(f"{path}: manifest must contain an 'annotations' list")
    return payload


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hard_errors(
    manifest: dict[str, Any],
    image_path: Path,
    *,
    manifest_path: Path | None = None,
    stroke: int = 3,
    font_size: int = 26,
    require_approved: bool = False,
) -> list[str]:
    """Return hard errors before drawing or passing a build gate.

    The image input is the redacted screenshot that is eligible for
    annotation; the raw capture stays outside the document workflow.
    Geometry is safe to check mechanically.  Whether a box actually hugs the
    intended control remains a human/reviewer decision and is not inferred
    from a status value.
    """

    errors: list[str] = []
    try:
        width, height = image_size(image_path)
    except (OSError, ValueError) as error:
        return [f"cannot open image {image_path}: {error}"]

    declared_hash = manifest.get("sourceSha256")
    if declared_hash is not None:
        if not isinstance(declared_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", declared_hash):
            errors.append("sourceSha256 must be a SHA-256 hex digest")
        else:
            # A canonical per-image manifest hashes the raw source.  The
            # annotation command intentionally receives the redacted image;
            # do not compare a raw hash to redacted bytes.  Legacy annotation
            # manifests without redactedImage retain the old direct binding.
            redacted_ref = manifest.get("redactedImage")
            redacted_path = None
            if isinstance(redacted_ref, str) and manifest_path is not None:
                redacted_path = (manifest_path.parent / redacted_ref).expanduser().resolve()
            image_resolved = image_path.expanduser().resolve()
            if redacted_path is None or redacted_path != image_resolved:
                try:
                    actual_hash = file_sha256(image_path)
                except OSError as error:
                    errors.append(f"cannot hash source image: {error}")
                else:
                    if actual_hash.casefold() != declared_hash.casefold():
                        errors.append("sourceSha256 does not match source image")

    # In the canonical manifest the annotation input is the redacted image,
    # while sourceSha256 intentionally remains bound to the raw capture.  If
    # the derived redacted hash has been declared, bind it to the actual
    # annotation input instead of silently trusting the path.
    declared_redacted_hash = manifest.get("redactedSha256")
    if declared_redacted_hash is not None:
        if not isinstance(declared_redacted_hash, str) or not re.fullmatch(r"[0-9a-fA-F]{64}", declared_redacted_hash):
            errors.append("redactedSha256 must be a SHA-256 hex digest")
        else:
            try:
                actual_redacted_hash = file_sha256(image_path)
            except OSError as error:
                errors.append(f"cannot hash redacted image: {error}")
            else:
                if actual_redacted_hash.casefold() != declared_redacted_hash.casefold():
                    errors.append("redactedSha256 does not match redacted image")

    declared_size = manifest.get("originalImageSize")
    if isinstance(declared_size, dict):
        if declared_size.get("width") != width or declared_size.get("height") != height:
            errors.append(
                "originalImageSize does not match raw image "
                f"({declared_size.get('width')}x{declared_size.get('height')} != {width}x{height})"
            )

    if require_approved:
        if isinstance(manifest.get("redactedImage"), str) and "redactedSha256" not in manifest:
            errors.append("redactedSha256 is required for the formal annotation gate")
        errors.extend(capture_binding_errors(manifest, (width, height), require=True))

    annotations = manifest.get("annotations", [])
    if not isinstance(annotations, list):
        return ["annotations must be a list"]
    seen_ids: set[str] = set()
    caption_numbers: set[str] = set()
    for index, item in enumerate(annotations):
        label = f"annotations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label}: annotation must be an object")
            continue
        annotation_id = item.get("id")
        if annotation_id is None or str(annotation_id) == "":
            errors.append(f"{label}: missing 'id'")
            continue
        annotation_id = str(annotation_id)
        if annotation_id in seen_ids:
            errors.append(f"{label}: duplicate id {annotation_id!r}")
        seen_ids.add(annotation_id)

        bbox = item.get("bbox")
        if not isinstance(bbox, dict) or not {"x", "y", "width", "height"} <= set(bbox):
            errors.append(f"{label}: missing or malformed 'bbox'")
            continue
        x, y, w, h = bbox["x"], bbox["y"], bbox["width"], bbox["height"]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (x, y, w, h)):
            errors.append(f"{label}: bbox values must be finite numbers")
            continue
        if w <= 0 or h <= 0:
            errors.append(f"{label}: box width/height must be positive")
        if x < 0 or y < 0 or x + w > width or y + h > height:
            errors.append(
                f"{label}: box ({x},{y},{w},{h}) is outside the {width}x{height} raw image"
            )

        border = max(3, math.ceil(font_size * 0.16))
        badge_w = font_size + 2 * border
        badge_h = font_size + 2 * border
        badge = badge_box(
            x,
            y,
            badge_w,
            badge_h,
            width,
            height,
            bbox_width=w,
            bbox_height=h,
            badge_spec=item.get("badgePosition", item.get("badge")),
        )
        if badge is None:
            errors.append(f"{label}: badge position is outside the {width}x{height} image")

        status = item.get("status", "proposed")
        if not isinstance(status, str) or status.casefold() not in KNOWN_STATUSES:
            errors.append(f"{label}: unknown annotation status {status!r}")
        elif require_approved:
            approval = item.get("approvalStatus")
            approved = (
                isinstance(approval, str) and approval.casefold() in APPROVED_STATUSES
            ) or status.casefold() in APPROVED_STATUSES
            if not approved:
                errors.append(
                    f"{label}: approval required before build (status={status!r}; "
                    "manual-adjusted is provenance only)"
                )

        provenance = item.get("provenance")
        if provenance is not None:
            if not isinstance(provenance, str) or provenance.casefold() not in KNOWN_PROVENANCE:
                errors.append(f"{label}: unknown annotation provenance {provenance!r}")
        if require_approved and not is_text(item.get("source", provenance)):
            errors.append(f"{label}: source/provenance is required before the formal annotation gate")

        caption = item.get("caption")
        if not isinstance(caption, str) or not caption.strip():
            errors.append(f"{label}: missing caption")
        else:
            match = CAPTION_PATTERN.match(caption)
            if match is None:
                errors.append(f"{label}: caption does not begin with 紅框 <id>：")
            else:
                caption_numbers.add(match.group(1))
                if match.group(1) != annotation_id:
                    errors.append(
                        f"{label}: caption number {match.group(1)!r} != id {annotation_id!r}"
                    )
        cursor = item.get("cursor")
        if cursor is not None:
            if not isinstance(cursor, dict) or not {"x", "y"} <= set(cursor):
                errors.append(f"{label}: cursor must contain x and y")
            elif not all(
                isinstance(cursor[key], (int, float)) and math.isfinite(cursor[key])
                for key in ("x", "y")
            ):
                errors.append(f"{label}: cursor values must be finite numbers")
            elif not (0 <= cursor["x"] <= width and 0 <= cursor["y"] <= height):
                errors.append(f"{label}: cursor is outside the raw image")

    if caption_numbers != seen_ids:
        errors.append(
            f"caption numbers {sorted(caption_numbers)} != annotation ids {sorted(seen_ids)}"
        )
    return errors


def _badge_point(spec: Any) -> tuple[float, float] | None:
    if not isinstance(spec, dict):
        return None
    candidate = spec
    if isinstance(spec.get("position"), dict):
        candidate = spec["position"]
    if not {"x", "y"} <= set(candidate):
        return None
    values = (candidate.get("x"), candidate.get("y"))
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) for value in values):
        return None
    return float(values[0]), float(values[1])


def _badge_anchor(spec: Any) -> str | None:
    if not isinstance(spec, dict):
        return None
    value = spec.get("anchor", spec.get("placement", spec.get("position")))
    if not isinstance(value, str):
        return None
    normalized = value.strip().casefold().replace("_", "-")
    return normalized if normalized in {"top-left", "top-right", "bottom-left", "bottom-right"} else None


def _badge_offset(spec: Any) -> tuple[float, float] | None:
    if not isinstance(spec, dict) or spec.get("offset") is None:
        return (0.0, 0.0)
    value = spec.get("offset")
    if not isinstance(value, dict) or not {"x", "y"} <= set(value):
        return None
    values = (value.get("x"), value.get("y"))
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) or not math.isfinite(item) for item in values):
        return None
    return float(values[0]), float(values[1])


def badge_box(
    bbox_x: int,
    bbox_y: int,
    badge_w: int,
    badge_h: int,
    img_w: int,
    img_h: int,
    *,
    bbox_width: int = 0,
    bbox_height: int = 0,
    badge_spec: Any = None,
) -> tuple[int, int, int, int] | None:
    """Resolve a bounded badge rectangle from the integrated annotation item.

    With no optional position this preserves the existing top-left placement
    and inward fallback.  ``badgePosition``/``badge`` may provide a direct
    top-left ``x``/``y`` point, or a named anchor plus an optional ``offset``.
    Explicit points fail closed when they leave the image so a reviewer can
    adjust that same manifest and redraw it.
    """

    gap = 4
    explicit_point = _badge_point(badge_spec)
    offset = _badge_offset(badge_spec)
    if offset is None:
        return None
    if explicit_point is not None:
        x0, y0 = explicit_point[0] + offset[0], explicit_point[1] + offset[1]
        if x0 < 0 or y0 < 0 or x0 + badge_w > img_w or y0 + badge_h > img_h:
            return None
        return (round(x0), round(y0), badge_w, badge_h)
    if isinstance(badge_spec, dict) and ({"x", "y"} <= set(badge_spec) or isinstance(badge_spec.get("position"), dict)):
        # A malformed direct point must not silently fall back to the default.
        return None

    anchor = _badge_anchor(badge_spec)
    if anchor is None and badge_spec is not None:
        if not isinstance(badge_spec, dict) or any(
            key in badge_spec for key in ("anchor", "placement", "position", "offset")
        ):
            return None
    if anchor == "top-right":
        x0, y0 = bbox_x + bbox_width + gap, bbox_y - gap - badge_h
    elif anchor == "bottom-left":
        x0, y0 = bbox_x - gap - badge_w, bbox_y + bbox_height + gap
    elif anchor == "bottom-right":
        x0, y0 = bbox_x + bbox_width + gap, bbox_y + bbox_height + gap
    else:
        x0, y0 = bbox_x - gap - badge_w, bbox_y - gap - badge_h
    x0 += offset[0]
    y0 += offset[1]
    if anchor is not None or badge_spec is not None:
        # A named anchor may use the same safe inward fallback as the default;
        # an explicit offset remains strict so it cannot hide a bad location.
        if anchor is not None and (x0 < 0 or y0 < 0 or x0 + badge_w > img_w or y0 + badge_h > img_h):
            x0, y0 = bbox_x + gap, bbox_y + gap
            if x0 + badge_w > img_w:
                x0 = bbox_x + gap - badge_w
            if y0 + badge_h > img_h:
                y0 = bbox_y + gap - badge_h
        if x0 < 0 or y0 < 0 or x0 + badge_w > img_w or y0 + badge_h > img_h:
            return None
        return (round(x0), round(y0), badge_w, badge_h)

    if x0 >= 0 and y0 >= 0:
        return (round(x0), round(y0), badge_w, badge_h)
    x0, y0 = bbox_x + gap, bbox_y + gap
    if x0 + badge_w > img_w:
        x0 = max(0, bbox_x + gap - badge_w)
    if y0 + badge_h > img_h:
        y0 = max(0, bbox_y + gap - badge_h)
    if x0 < 0 or y0 < 0 or x0 + badge_w > img_w or y0 + badge_h > img_h:
        return None
    return (round(x0), round(y0), badge_w, badge_h)


def draw_cursor(draw: ImageDraw.ImageDraw, cursor: dict[str, Any], target: dict[str, Any]) -> None:
    cx, cy = int(cursor["x"]), int(cursor["y"])
    tx = min(max(cx, target["x"]), target["x"] + target["width"])
    ty = min(max(cy, target["y"]), target["y"] + target["height"])
    if (cx, cy) == (tx, ty):
        return
    length = 26
    angle = math.atan2(ty - cy, tx - cx)
    tip = (tx, ty)
    base_x = tx - length * math.cos(angle)
    base_y = ty - length * math.sin(angle)
    normal = math.pi / 2
    wing = 7
    left = (base_x - wing * math.cos(angle + normal), base_y - wing * math.sin(angle + normal))
    right = (base_x - wing * math.cos(angle - normal), base_y - wing * math.sin(angle - normal))
    # Draw a light outline first so the red cursor remains visible on dark UI
    # surfaces.  Keep each pair as (RGB color, line width); iterating over a
    # bare RGB tuple would try to unpack three values and fail at draw time.
    for stroke_color, stroke_width in (((255, 255, 255), 5), (RED, 3)):
        draw.line([cx, cy, base_x, base_y], fill=stroke_color, width=stroke_width)
        draw.polygon([tip, left, right], fill=stroke_color)


def draw_annotations(
    manifest: dict[str, Any], image_path: Path, output_path: Path, stroke: int, font_size: int
) -> dict[str, Any]:
    if file_alias(output_path, image_path):
        raise ValueError("annotation output must not overwrite the parent image")
    if output_path.exists():
        raise ValueError("annotation output already exists; choose a new immutable output path")
    with Image.open(image_path) as source:
        if source.mode in ("RGBA", "LA", "P"):
            image = source.convert("RGB")
        else:
            image = source.convert("RGB")
        width, height = image.size
    image.info.clear()

    draw = ImageDraw.Draw(image)
    for index, item in enumerate(manifest["annotations"]):
        bbox = item["bbox"]
        x, y, w, h = (int(bbox[k]) for k in ("x", "y", "width", "height"))
        draw.rectangle([x, y, x + w, y + h], outline=RED, width=stroke)
        if item.get("cursor"):
            draw_cursor(draw, item["cursor"], bbox)

        number = str(item["id"])
        border = max(3, math.ceil(font_size * 0.16))
        badge_w = font_size + 2 * border
        badge_h = font_size + 2 * border
        badge = badge_box(
            x,
            y,
            badge_w,
            badge_h,
            width,
            height,
            bbox_width=w,
            bbox_height=h,
            badge_spec=item.get("badgePosition", item.get("badge")),
        )
        if badge is None:
            raise ValueError(f"annotation {item.get('id')!r}: badge position is outside the image")
        bx, by, bw, bh = badge
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=4, fill=RED)
        draw.text(
            (bx + bw / 2, by + bh / 2),
            number,
            fill=(255, 255, 255),
            anchor="mm",
            font_size=font_size,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path, format="PNG")
    print(f"ANNOTATED_IMAGE={output_path}")
    parent_hash = file_sha256(image_path)
    output_hash = file_sha256(output_path)
    input_payload = annotation_input_payload(manifest, stroke=stroke, font_size=font_size)
    provenance = {
        "schema_version": 1,
        "tool": "annotate.py",
        "parentImage": str(manifest.get("redactedImage", image_path.name)),
        "parentSha256": parent_hash,
        "redactedImage": str(manifest.get("redactedImage", image_path.name)),
        "redactedSha256": parent_hash,
        "outputImage": str(manifest.get("annotatedImage", output_path.name)),
        "annotatedImage": str(manifest.get("annotatedImage", output_path.name)),
        "outputSha256": output_hash,
        "annotatedSha256": output_hash,
        "drawingInputSha256": annotation_input_sha256(manifest, stroke=stroke, font_size=font_size),
        "inputSha256": annotation_input_sha256(manifest, stroke=stroke, font_size=font_size),
        "drawingInputs": input_payload,
    }
    return provenance


def validate_annotation_provenance(
    provenance: dict[str, Any],
    manifest: dict[str, Any],
    parent_path: Path,
    annotated_path: Path,
    *,
    stroke: int = 3,
    font_size: int = 26,
) -> list[str]:
    """Validate the provenance emitted by ``draw`` against current inputs."""

    errors: list[str] = []
    parent_hash = file_sha256(parent_path)
    output_hash = file_sha256(annotated_path)
    declared_parent = provenance.get("parentSha256", provenance.get("redactedSha256"))
    declared_output = provenance.get("outputSha256", provenance.get("annotatedSha256"))
    if declared_parent != parent_hash:
        errors.append("annotation provenance parent hash does not match redacted image")
    if declared_output != output_hash:
        errors.append("annotation provenance output hash does not match annotated image")
    expected_inputs = annotation_input_payload(manifest, stroke=stroke, font_size=font_size)
    expected_hash = annotation_input_sha256(manifest, stroke=stroke, font_size=font_size)
    if provenance.get("drawingInputs") != expected_inputs:
        errors.append("annotation provenance drawing inputs do not match manifest")
    if provenance.get("drawingInputSha256", provenance.get("inputSha256")) != expected_hash:
        errors.append("annotation provenance input hash does not match manifest")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    draw = subparsers.add_parser("draw", help="Draw red boxes, badges and cursors.")
    draw.add_argument("--image", required=True, type=Path)
    draw.add_argument("--annotations", required=True, type=Path)
    draw.add_argument("--output", required=True, type=Path)
    draw.add_argument("--stroke", type=int, default=3, help="Red box stroke width in px.")
    draw.add_argument("--font-size", type=int, default=26, help="Badge font size in px.")
    draw.add_argument("--provenance-output", type=Path, help="Tool-generated parent/input/output provenance JSON.")
    draw.add_argument(
        "--require-approved",
        action="store_true",
        help="Require approved/verified annotation status before drawing.",
    )

    check = subparsers.add_parser("check", help="Validate the manifest without drawing.")
    check.add_argument("--image", required=True, type=Path)
    check.add_argument("--annotations", required=True, type=Path)
    check.add_argument("--stroke", type=int, default=3, help="Red box stroke width used by draw.")
    check.add_argument("--font-size", type=int, default=26, help="Badge font size used by draw.")
    check.add_argument("--provenance", type=Path, help="Optional provenance JSON produced by draw.")
    check.add_argument(
        "--require-approved",
        action="store_true",
        help="Require approved/verified status instead of allowing a preview.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        manifest = load_manifest(args.annotations)
        errors = hard_errors(
            manifest,
            args.image,
            manifest_path=args.annotations.expanduser().resolve(),
            stroke=args.stroke,
            font_size=args.font_size,
            require_approved=args.require_approved,
        )
        if errors:
            for message in errors:
                print(f"annotate.py check: {message}", file=sys.stderr)
            return 1
        if args.command == "check" and args.provenance is not None:
            try:
                provenance = json.loads(args.provenance.expanduser().resolve().read_text(encoding="utf-8"))
            except (OSError, UnicodeError, json.JSONDecodeError) as error:
                raise ValueError(f"cannot read provenance {args.provenance}: {error}") from error
            if not isinstance(provenance, dict):
                raise ValueError("provenance must be a JSON object")
            output_value = provenance.get("outputImage", provenance.get("annotatedImage"))
            if isinstance(output_value, str) and output_value.strip():
                output_path = Path(output_value).expanduser()
                if not output_path.is_absolute():
                    # The provenance records manifest-relative image names in
                    # the integrated schema.  Resolve those names from the
                    # manifest location instead of the caller's CWD.
                    output_path = args.annotations.expanduser().resolve().parent / output_path
                output_path = output_path.resolve()
            else:
                output_path = args.image.expanduser().resolve()
            provenance_errors = validate_annotation_provenance(
                provenance,
                manifest,
                args.image.expanduser().resolve(),
                output_path,
                stroke=args.stroke,
                font_size=args.font_size,
            )
            if provenance_errors:
                for message in provenance_errors:
                    print(f"annotate.py check: {message}", file=sys.stderr)
                return 1
        if args.command == "draw":
            image_path = args.image.expanduser().resolve()
            annotation_path = args.annotations.expanduser().resolve()
            output_path = args.output.expanduser().resolve()
            if file_alias(output_path, annotation_path):
                raise ValueError("annotation output must not overwrite annotation manifest")
            provenance_path = (
                args.provenance_output.expanduser().resolve() if args.provenance_output else None
            )
            if provenance_path is not None:
                if file_alias(provenance_path, image_path) or file_alias(provenance_path, annotation_path):
                    raise ValueError("provenance output must not overwrite annotation inputs")
                if file_alias(provenance_path, output_path):
                    raise ValueError("provenance output must be different from annotated image output")
                if provenance_path.exists():
                    raise ValueError("provenance output already exists; choose a new immutable output path")
            provenance = draw_annotations(manifest, image_path, output_path, args.stroke, args.font_size)
            if provenance_path is not None:
                provenance_path.parent.mkdir(parents=True, exist_ok=True)
                provenance_path.write_text(
                    json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
            print("PROVENANCE=" + json.dumps(provenance, ensure_ascii=False, sort_keys=True))
        else:
            print(
                f"annotate.py check: OK ({len(manifest['annotations'])} annotations, "
                f"status={sorted({a.get('status', 'proposed') for a in manifest['annotations']})})"
            )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"annotate.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
