#!/usr/bin/env python3
"""Create a per-job Fontconfig file for a confirmed CJK font directory."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from xml.sax.saxutils import escape


def existing_directory(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise argparse.ArgumentTypeError(f"font directory does not exist or is not a directory: {path}")
    return path


def output_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def build_config(font_dirs: list[Path], cache_dir: Path) -> str:
    directories = "\n".join(f"  <dir>{escape(str(path))}</dir>" for path in font_dirs)
    return (
        "<?xml version=\"1.0\"?>\n"
        "<!DOCTYPE fontconfig SYSTEM \"fonts.dtd\">\n"
        "<fontconfig>\n"
        f"{directories}\n"
        f"  <cachedir>{escape(str(cache_dir))}</cachedir>\n"
        "</fontconfig>\n"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an isolated Fontconfig file for a single DOCX render job."
    )
    parser.add_argument(
        "--font-dir",
        action="append",
        required=True,
        type=existing_directory,
        help="Existing directory containing an approved CJK font file. Repeat for additional directories.",
    )
    parser.add_argument(
        "--cache-dir",
        required=True,
        type=output_path,
        help="Writable cache directory inside the current job workspace.",
    )
    parser.add_argument(
        "--output",
        required=True,
        type=output_path,
        help="Path for the generated per-job Fontconfig XML file.",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    cache_dir: Path = arguments.cache_dir
    output: Path = arguments.output
    cache_dir.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_config(arguments.font_dir, cache_dir), encoding="utf-8")
    print(f"FONTCONFIG_FILE={output}")
    print(f"FONTCONFIG_CACHE_DIR={cache_dir}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except argparse.ArgumentTypeError as error:
        print(f"create_fontconfig_config.py: {error}", file=sys.stderr)
        raise SystemExit(2)
