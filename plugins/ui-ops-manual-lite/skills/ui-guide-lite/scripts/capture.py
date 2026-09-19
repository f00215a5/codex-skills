#!/usr/bin/env python3
"""Preserve a screenshot capture and create a canonical PNG evidence source.

The capture entry point runs before redaction or annotation.  It detects the
actual format from Pillow, copies the untouched bytes to a new QA path, writes
an same-size PNG from decoded pixels, and records hashes plus capture metadata.
It never resizes, crops, or overwrites an existing input/output artifact.

Examples::

    python capture.py canonicalize --input capture.png \
        --raw-output qa/raw/create-task.capture \
        --canonical-output qa/raw/create-task.png \
        --provenance-output qa/create-task-capture.json \
        --capture-id create-task-01

For compatibility, the subcommand may be omitted when the first argument is
an option.  ``normalize`` and ``prepare`` are aliases for ``canonicalize``.
"""

from __future__ import annotations

import argparse
import io
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any, Sequence

from PIL import Image

try:
    from evidence import CAPTURE_KINDS, file_alias, is_sha256, sha256_bytes
except ImportError:  # pragma: no cover - package import fallback
    from .evidence import CAPTURE_KINDS, file_alias, is_sha256, sha256_bytes  # type: ignore[no-redef]


FORMAT_MIME = {
    "BMP": "image/bmp",
    "GIF": "image/gif",
    "JPEG": "image/jpeg",
    "JPG": "image/jpeg",
    "PNG": "image/png",
    "TIFF": "image/tiff",
    "WEBP": "image/webp",
}
COMMANDS = {"canonicalize", "normalize", "prepare"}


def _mime(image_format: str | None, path: Path) -> str:
    if isinstance(image_format, str) and image_format.upper() in FORMAT_MIME:
        return FORMAT_MIME[image_format.upper()]
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def _load_state(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ValueError(f"cannot read capture state {path}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError("capture state must be a JSON object")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{label} must be a positive integer")
    return value


def _non_negative_number(value: Any, label: str) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
        raise ValueError(f"{label} must be a non-negative number")
    return value


def _capture_state(args: argparse.Namespace, canonical_hash: str, size: tuple[int, int]) -> dict[str, Any]:
    state = _load_state(args.capture_state)
    capture_id = args.capture_id if args.capture_id is not None else state.get("id")
    if capture_id is not None:
        if not isinstance(capture_id, str) or not capture_id.strip():
            raise ValueError("capture id must be non-empty text")
        state["id"] = capture_id.strip()
    else:
        state.pop("id", None)
    state["rawSha256"] = canonical_hash
    viewport = state.get("viewportCssSize")
    if viewport is None and args.viewport_width is not None and args.viewport_height is not None:
        viewport = {"width": args.viewport_width, "height": args.viewport_height}
    if viewport is not None:
        if not isinstance(viewport, dict):
            raise ValueError("capture state viewportCssSize must be an object")
        state["viewportCssSize"] = {
            "width": _positive_int(viewport.get("width"), "viewportCssSize.width"),
            "height": _positive_int(viewport.get("height"), "viewportCssSize.height"),
        }
    else:
        state.pop("viewportCssSize", None)
    scroll = state.get("scroll")
    if scroll is None and args.scroll_x is not None and args.scroll_y is not None:
        scroll = {"x": args.scroll_x, "y": args.scroll_y}
    if scroll is not None:
        if not isinstance(scroll, dict):
            raise ValueError("capture state scroll must be an object")
        state["scroll"] = {
            "x": _non_negative_number(scroll.get("x"), "scroll.x"),
            "y": _non_negative_number(scroll.get("y"), "scroll.y"),
        }
    else:
        state.pop("scroll", None)
    calibration = state.get("calibration")
    if calibration is not None and not isinstance(calibration, dict):
        raise ValueError("capture state calibration must be an object")
    capture_kind = args.capture_kind if args.capture_kind is not None else state.get("captureKind")
    if capture_kind is not None:
        if capture_kind not in CAPTURE_KINDS:
            raise ValueError("capture-kind must be full-page, viewport-sequence or detail")
        state["captureKind"] = capture_kind
    required = ("id", "viewportCssSize", "scroll", "calibration", "captureKind")
    missing = [key for key in required if key not in state]
    state["metadataStatus"] = "complete" if not missing else "incomplete"
    if missing:
        state["missingMetadata"] = missing
    else:
        state.pop("missingMetadata", None)
    return state


def _pixel_view(image: Image.Image) -> Image.Image:
    has_alpha = image.mode in {"RGBA", "LA"} or "transparency" in image.info
    return image.convert("RGBA" if has_alpha else "RGB")


def _write_new_bytes(path: Path, data: bytes, *, label: str, aliases: Sequence[Path]) -> None:
    if any(file_alias(path, alias) for alias in aliases):
        raise ValueError(f"{label} must not overwrite an input or another output")
    if path.exists():
        raise ValueError(f"{label} already exists; choose a new immutable output path")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def canonicalize(args: argparse.Namespace) -> dict[str, Any]:
    input_path = args.input.expanduser().resolve()
    if not input_path.is_file():
        raise ValueError(f"capture input not found: {input_path}")
    raw_path = (args.raw_output or input_path.with_name(input_path.name + ".capture")).expanduser().resolve()
    canonical_path = args.canonical_output.expanduser().resolve()
    provenance_path = (
        (args.provenance_output or canonical_path.with_suffix(".provenance.json"))
        .expanduser()
        .resolve()
    )
    output_paths = {
        "raw capture output": raw_path,
        "canonical PNG output": canonical_path,
        "capture provenance output": provenance_path,
    }
    for label, output in output_paths.items():
        if file_alias(output, input_path):
            raise ValueError(f"{label} must not alias the input capture")
        if output.exists():
            raise ValueError(f"{label} already exists; choose a new immutable output path")
    output_items = list(output_paths.items())
    for index, (left_label, left_path) in enumerate(output_items):
        for right_label, right_path in output_items[index + 1:]:
            if file_alias(left_path, right_path):
                raise ValueError(f"{left_label} and {right_label} must be distinct paths")
    source_bytes = input_path.read_bytes()
    with Image.open(input_path) as opened:
        actual_format = opened.format
        opened.load()
        decoded = opened.copy()
        size = tuple(opened.size)
        original_pixels = _pixel_view(opened)
    if size[0] <= 0 or size[1] <= 0:
        raise ValueError("capture image dimensions must be positive")
    canonical_buffer = io.BytesIO()
    decoded.save(canonical_buffer, format="PNG")
    canonical_bytes = canonical_buffer.getvalue()
    with Image.open(io.BytesIO(canonical_bytes)) as canonical:
        canonical.load()
        if canonical.format != "PNG":
            raise ValueError("canonical output is not PNG")
        if tuple(canonical.size) != size:
            raise ValueError("canonical output changed image dimensions")
        canonical_pixels = _pixel_view(canonical)
        equal = canonical_pixels.mode == original_pixels.mode and canonical_pixels.tobytes() == original_pixels.tobytes()
    if not equal:
        raise ValueError("canonical PNG pixels do not equal the decoded capture")
    canonical_hash = sha256_bytes(canonical_bytes)
    raw_hash = sha256_bytes(source_bytes)
    state = _capture_state(args, canonical_hash, size)
    state["sourceKind"] = args.source_kind.casefold()
    if args.capture_kind is not None:
        state["captureKind"] = args.capture_kind
    provenance = {
        "schema_version": 1,
        "tool": "capture.py",
        "originalFile": str(raw_path),
        "originalMime": _mime(actual_format, input_path),
        "originalFormat": actual_format or "unknown",
        "originalSha256": raw_hash,
        "decodedSourceImage": str(canonical_path),
        "canonicalFile": str(canonical_path),
        "canonicalMime": "image/png",
        "canonicalSha256": canonical_hash,
        "originalImageSize": {"width": size[0], "height": size[1]},
        "canonicalImageSize": {"width": size[0], "height": size[1]},
        "pixelEquality": "verified",
        "captureState": state,
    }
    if not is_sha256(provenance["canonicalSha256"]) or not is_sha256(provenance["originalSha256"]):
        raise ValueError("capture provenance hashes are invalid")
    if isinstance(state.get("captureKind"), str):
        provenance["captureKind"] = state["captureKind"]
    _write_new_bytes(
        raw_path,
        source_bytes,
        label="raw capture output",
        aliases=(input_path, canonical_path, provenance_path),
    )
    _write_new_bytes(
        canonical_path,
        canonical_bytes,
        label="canonical PNG output",
        aliases=(input_path, raw_path, provenance_path),
    )
    provenance_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path.write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"RAW_CAPTURE={raw_path}")
    print(f"CANONICAL_PNG={canonical_path}")
    print(f"PROVENANCE={provenance_path}")
    print(json.dumps(provenance, ensure_ascii=False, sort_keys=True))
    return provenance


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command")
    for name in sorted(COMMANDS):
        command = subparsers.add_parser(name, help="Preserve bytes and emit a canonical PNG.")
        command.add_argument("--input", "--capture", "--source", dest="input", required=True, type=Path)
        command.add_argument("--raw-output", "--raw", "--original-output", dest="raw_output", type=Path)
        command.add_argument("--canonical-output", "--canonical", "--output", dest="canonical_output", required=True, type=Path)
        command.add_argument("--provenance-output", "--provenance", dest="provenance_output", type=Path)
        command.add_argument("--capture-id")
        command.add_argument("--source-kind", default="captured")
        command.add_argument("--capture-kind")
        command.add_argument("--capture-state", "--capture-metadata", dest="capture_state", type=Path)
        command.add_argument("--viewport-width", type=int)
        command.add_argument("--viewport-height", type=int)
        command.add_argument("--scroll-x", type=float)
        command.add_argument("--scroll-y", type=float)
    return parser


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    values = list(argv if argv is not None else sys.argv[1:])
    if values and values[0] not in COMMANDS and values[0].startswith("--"):
        values.insert(0, "canonicalize")
    parser = build_parser()
    args = parser.parse_args(values)
    if args.command is None:
        parser.error("a canonicalize command or capture options are required")
    if args.source_kind.casefold() not in {"captured", "provided", "reused", "schematic"}:
        parser.error("source-kind must be captured, provided, reused or schematic")
    if args.capture_kind is not None and args.capture_kind not in CAPTURE_KINDS:
        parser.error("capture-kind must be full-page, viewport-sequence or detail")
    if (args.scroll_x is None) != (args.scroll_y is None):
        parser.error("scroll-x and scroll-y must be provided together")
    if (args.viewport_width is None) != (args.viewport_height is None):
        parser.error("viewport-width and viewport-height must be provided together")
    return args


def main(argv: Sequence[str] | None = None) -> int:
    try:
        canonicalize(parse_args(argv))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"capture.py: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
