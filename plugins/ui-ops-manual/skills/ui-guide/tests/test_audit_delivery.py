"""Contract tests for the read-only DOCX delivery audit."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_ROOT))
import audit_delivery  # noqa: E402


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"

ET.register_namespace("w", W)
ET.register_namespace("r", R)


def w(tag: str) -> str:
    return f"{{{W}}}{tag}"


def wattr(name: str) -> str:
    return w(name)


def _table(
    grid: list[int],
    rows: list[list[tuple[int, int]]],
    *,
    alignment: str | None = "center",
    style: str | None = None,
    tblw_type: str = "dxa",
    tblw_value: int = 3000,
    layout: str | None = None,
    secret: str = "private-value-should-not-appear",
) -> ET.Element:
    table = ET.Element(w("tbl"))
    properties = ET.SubElement(table, w("tblPr"))
    tblw = ET.SubElement(properties, w("tblW"))
    tblw.set(wattr("type"), tblw_type)
    tblw.set(wattr("w"), str(tblw_value))
    if layout is not None:
        tbl_layout = ET.SubElement(properties, w("tblLayout"))
        tbl_layout.set(wattr("type"), layout)
    if alignment is not None:
        jc = ET.SubElement(properties, w("jc"))
        jc.set(wattr("val"), alignment)
    if style is not None:
        tbl_style = ET.SubElement(properties, w("tblStyle"))
        tbl_style.set(wattr("val"), style)

    grid_element = ET.SubElement(table, w("tblGrid"))
    for width in grid:
        column = ET.SubElement(grid_element, w("gridCol"))
        column.set(wattr("w"), str(width))

    for row_values in rows:
        row = ET.SubElement(table, w("tr"))
        for span, width in row_values:
            cell = ET.SubElement(row, w("tc"))
            cell_pr = ET.SubElement(cell, w("tcPr"))
            tcw = ET.SubElement(cell_pr, w("tcW"))
            tcw.set(wattr("type"), "dxa")
            tcw.set(wattr("w"), str(width))
            if span != 1:
                grid_span = ET.SubElement(cell_pr, w("gridSpan"))
                grid_span.set(wattr("val"), str(span))
            paragraph = ET.SubElement(cell, w("p"))
            run = ET.SubElement(paragraph, w("r"))
            text = ET.SubElement(run, w("t"))
            text.text = secret
    return table


def _document(table: ET.Element) -> bytes:
    root = ET.Element(w("document"))
    body = ET.SubElement(root, w("body"))
    body.append(table)
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _styles_center() -> bytes:
    root = ET.Element(w("styles"))
    style = ET.SubElement(root, w("style"))
    style.set(wattr("type"), "table")
    style.set(wattr("styleId"), "CenteredTable")
    tbl_pr = ET.SubElement(style, w("tblPr"))
    jc = ET.SubElement(tbl_pr, w("jc"))
    jc.set(wattr("val"), "center")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _relationships(media: list[str]) -> bytes:
    root = ET.Element(f"{{{PKG_REL}}}Relationships")
    for index, name in enumerate(media, start=1):
        relation = ET.SubElement(root, f"{{{PKG_REL}}}Relationship")
        relation.set("Id", f"rId{index}")
        relation.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
        relation.set("Target", f"media/{name}")
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_docx(
    directory: Path,
    name: str,
    table: ET.Element,
    *,
    styles: bytes | None = None,
    media: list[str] | None = None,
    referenced_media: list[str] | None = None,
) -> Path:
    media = media or []
    referenced_media = referenced_media or []
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", _document(table))
        if styles is not None:
            package.writestr("word/styles.xml", styles)
        if referenced_media:
            package.writestr("word/_rels/document.xml.rels", _relationships(referenced_media))
        for media_name in media:
            package.writestr(f"word/media/{media_name}", media_name.encode("ascii"))
    return path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class AuditDeliveryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_center_and_legal_gridspan_are_reported_without_text_leakage(self) -> None:
        table = _table([1000, 2000], [[(2, 3000)]])
        path = _write_docx(self.root, "merged.docx", table, media=["image1.png", "image2.png"], referenced_media=["image1.png"])

        report = audit_delivery.audit_docx(path)
        table_report = report["tables"][0]

        self.assertEqual(table_report["alignment"]["status"], "pass")
        self.assertEqual(table_report["alignment"]["source"], "direct")
        self.assertEqual(table_report["grid"]["status"], "pass")
        self.assertEqual(table_report["grid"]["merged_cells"], 1)
        self.assertEqual(report["package"]["media"][0]["referenced"], True)
        self.assertEqual(report["package"]["unreferenced_media"], ["word/media/image2.png"])
        self.assertNotIn("private-value-should-not-appear", json.dumps(report))

    def test_center_can_be_inherited_from_table_style(self) -> None:
        table = _table([1000, 2000], [[(1, 1000), (1, 2000)]], alignment=None, style="CenteredTable")
        path = _write_docx(self.root, "style.docx", table, styles=_styles_center())

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["tables"][0]["alignment"]["status"], "pass")
        self.assertEqual(report["tables"][0]["alignment"]["source"], "table_style")

    def test_left_alignment_is_a_mechanical_failure(self) -> None:
        table = _table([1000], [[(1, 1000)]], alignment="left")
        path = _write_docx(self.root, "left.docx", table)

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["tables"][0]["alignment"]["status"], "fail")
        self.assertEqual(report["mechanical_status"], "failed")
        self.assertIn({"code": "table_alignment_not_center", "table_index": 1}, report["findings"])

    def test_gridspan_width_mismatch_is_detected(self) -> None:
        table = _table([1000, 2000], [[(2, 2500)]])
        path = _write_docx(self.root, "mismatch.docx", table)

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["tables"][0]["grid"]["status"], "fail")
        self.assertEqual(report["mechanical_status"], "failed")
        self.assertEqual(report["tables"][0]["grid"]["findings"][0]["expected_twips"], 3000)

    def test_fixed_auto_width_is_manual_review_not_failure(self) -> None:
        table = _table([1000], [[(1, 1000)]], tblw_type="auto", tblw_value=0, layout="fixed")
        path = _write_docx(self.root, "fixed-auto.docx", table)

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["tables"][0]["width"]["status"], "manual_review")
        self.assertEqual(report["tables"][0]["status"], "manual_review")
        self.assertEqual(report["mechanical_status"], "manual_review")
        self.assertNotIn({"code": "table_alignment_not_center", "table_index": 1}, report["findings"])

    def test_stale_review_is_blocked_and_does_not_echo_review_text(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(self.root, "reviewed.docx", table)
        page = self.root / "page-001.png"
        page.write_bytes(b"rendered page")
        support = self.root / "requirements.md"
        support.write_bytes(b"requirements snapshot")
        review = {
            "schema_version": 1,
            "artifact": {"sha256": "0" * 64},
            "builder": {"id": "builder-1"},
            "reviewer": {"id": "reviewer-1"},
            "reviewed_files": [
                {"kind": "page", "path": page.name, "sha256": _sha256(page)},
                {"kind": "support", "path": support.name, "sha256": _sha256(support)},
            ],
            "checks": {
                name: {
                    "status": "pass",
                    "reason": "checked",
                    "evidence": [support.name if name == "requirements" else page.name],
                }
                for name in ("requirements", "redaction", "visual", "operation")
            },
            "overall": "pass",
            "private_note": "private-review-text-should-not-appear",
        }
        review_path = self.root / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")

        report = audit_delivery.audit_docx(docx, review_path)
        serialized = json.dumps(report)

        self.assertEqual(report["independent_review"]["status"], "blocked")
        self.assertIn("artifact_hash_mismatch", report["independent_review"]["reason_codes"])
        self.assertNotIn("private-review-text-should-not-appear", serialized)

    def test_valid_review_requires_exact_evidence_paths_and_hashes(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(self.root, "valid.docx", table)
        page = self.root / "page-001.png"
        page.write_bytes(b"rendered page")
        support = self.root / "requirements.md"
        support.write_bytes(b"requirements snapshot")
        review = {
            "schema_version": 1,
            "artifact": {"sha256": _sha256(docx)},
            "builder": {"id": "builder-1"},
            "reviewer": {"id": "reviewer-1"},
            "reviewed_files": [
                {"kind": "page", "path": page.name, "sha256": _sha256(page)},
                {"kind": "support", "path": support.name, "sha256": _sha256(support)},
            ],
            "checks": {
                "requirements": {"status": "pass", "reason": "checked", "evidence": [support.name]},
                "redaction": {"status": "na", "reason": "no screenshots", "evidence": []},
                "visual": {"status": "pass", "reason": "checked", "evidence": [page.name]},
                "operation": {"status": "pass", "reason": "checked", "evidence": [page.name]},
            },
            "overall": "pass",
        }
        review_path = self.root / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")

        report = audit_delivery.audit_docx(docx, review_path)

        self.assertEqual(report["independent_review"]["status"], "pass")
        self.assertEqual(report["mechanical_status"], "pass")
        self.assertNotIn("overall", report)

    def test_evidence_fragment_is_not_accepted_as_exact_path(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(self.root, "evidence.docx", table)
        page = self.root / "page-001.png"
        page.write_bytes(b"rendered page")
        support = self.root / "requirements.md"
        support.write_bytes(b"requirements snapshot")
        review = {
            "schema_version": 1,
            "artifact": {"sha256": _sha256(docx)},
            "builder": {"id": "builder-1"},
            "reviewer": {"id": "reviewer-1"},
            "reviewed_files": [
                {"kind": "page", "path": page.name, "sha256": _sha256(page)},
                {"kind": "support", "path": support.name, "sha256": _sha256(support)},
            ],
            "checks": {
                "requirements": {"status": "pass", "reason": "checked", "evidence": [f"{support.name}#scope"]},
                "redaction": {"status": "na", "reason": "not applicable", "evidence": []},
                "visual": {"status": "pass", "reason": "checked", "evidence": [page.name]},
                "operation": {"status": "pass", "reason": "checked", "evidence": [page.name]},
            },
            "overall": "pass",
        }
        review_path = self.root / "review.json"
        review_path.write_text(json.dumps(review), encoding="utf-8")

        report = audit_delivery.audit_docx(docx, review_path)

        self.assertEqual(report["independent_review"]["status"], "blocked")
        self.assertIn("evidence_reference_missing", report["independent_review"]["reason_codes"])

    def test_cli_refuses_to_overwrite_docx_and_reports_unreadable_input(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(self.root, "protected.docx", table)
        original = docx.read_bytes()

        overwrite_exit = audit_delivery.main(["--docx", str(docx), "--output", str(docx)])

        self.assertEqual(overwrite_exit, 2)
        self.assertEqual(docx.read_bytes(), original)

        output = self.root / "missing.json"
        missing_exit = audit_delivery.main(["--docx", str(self.root / "missing.docx"), "--output", str(output)])

        self.assertEqual(missing_exit, 2)
        self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["docx"]["status"], "unreadable")


if __name__ == "__main__":
    unittest.main()
