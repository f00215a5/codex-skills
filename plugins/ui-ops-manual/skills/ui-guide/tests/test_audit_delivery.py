"""Contract tests for the read-only DOCX delivery audit."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
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
    first_row_texts: list[str] | None = None,
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

    for row_index, row_values in enumerate(rows):
        row = ET.SubElement(table, w("tr"))
        for cell_index, (span, width) in enumerate(row_values):
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
            if row_index == 0 and first_row_texts is not None and cell_index < len(first_row_texts):
                text.text = first_row_texts[cell_index]
            else:
                text.text = secret
    return table


def _document(table: ET.Element, *, num_id: str | None = None) -> bytes:
    root = ET.Element(w("document"))
    body = ET.SubElement(root, w("body"))
    if num_id is not None:
        paragraph = ET.SubElement(body, w("p"))
        properties = ET.SubElement(paragraph, w("pPr"))
        numbering = ET.SubElement(properties, w("numPr"))
        number = ET.SubElement(numbering, w("numId"))
        number.set(wattr("val"), num_id)
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


def _numbering(
    *,
    abstract_first: bool = True,
    suff_after_lvl_text: bool = False,
    abstract_id: str = "1",
    num_id: str = "1",
    abstract_ref: str = "1",
) -> bytes:
    root = ET.Element(w("numbering"))

    def add_abstract() -> None:
        abstract = ET.SubElement(root, w("abstractNum"))
        abstract.set(wattr("abstractNumId"), abstract_id)
        level = ET.SubElement(abstract, w("lvl"))
        level.set(wattr("ilvl"), "0")
        start = ET.SubElement(level, w("start"))
        start.set(wattr("val"), "1")
        num_format = ET.SubElement(level, w("numFmt"))
        num_format.set(wattr("val"), "decimal")
        if not suff_after_lvl_text:
            suffix = ET.SubElement(level, w("suff"))
            suffix.set(wattr("val"), "tab")
        level_text = ET.SubElement(level, w("lvlText"))
        level_text.set(wattr("val"), "%1.")
        if suff_after_lvl_text:
            suffix = ET.SubElement(level, w("suff"))
            suffix.set(wattr("val"), "tab")

    def add_num() -> None:
        number = ET.SubElement(root, w("num"))
        number.set(wattr("numId"), num_id)
        abstract = ET.SubElement(number, w("abstractNumId"))
        abstract.set(wattr("val"), abstract_ref)

    if abstract_first:
        add_abstract()
        add_num()
    else:
        add_num()
        add_abstract()
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
    numbering: bytes | None = None,
    num_id: str | None = None,
    media: list[str] | None = None,
    referenced_media: list[str] | None = None,
) -> Path:
    media = media or []
    referenced_media = referenced_media or []
    path = directory / name
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as package:
        package.writestr("word/document.xml", _document(table, num_id=num_id))
        if styles is not None:
            package.writestr("word/styles.xml", styles)
        if numbering is not None:
            package.writestr("word/numbering.xml", numbering)
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

    def test_numbering_structure_and_references_pass(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        path = _write_docx(self.root, "numbering-valid.docx", table, numbering=_numbering(), num_id="1")

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["mechanical_status"], "pass")
        self.assertNotIn("numbering_abstract_num_after_num", {item["code"] for item in report["findings"]})
        self.assertNotIn("numbering_suff_after_lvl_text", {item["code"] for item in report["findings"]})
        self.assertNotIn("numbering_num_id_missing", {item["code"] for item in report["findings"]})
        self.assertNotIn("numbering_abstract_num_id_missing", {item["code"] for item in report["findings"]})

    def test_numbering_num_id_zero_removes_numbering_without_definition(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        path = _write_docx(self.root, "numbering-remove.docx", table, num_id="0")

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["mechanical_status"], "pass")
        self.assertNotIn("numbering_num_id_missing", {item["code"] for item in report["findings"]})

    def test_numbering_abstract_num_must_precede_num(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        path = _write_docx(
            self.root,
            "numbering-abstract-after-num.docx",
            table,
            numbering=_numbering(abstract_first=False),
            num_id="1",
        )

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["mechanical_status"], "failed")
        self.assertIn("numbering_abstract_num_after_num", {item["code"] for item in report["findings"]})

    def test_numbering_suff_must_precede_lvl_text(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        path = _write_docx(
            self.root,
            "numbering-suff-after-lvl-text.docx",
            table,
            numbering=_numbering(suff_after_lvl_text=True),
            num_id="1",
        )

        report = audit_delivery.audit_docx(path)

        self.assertEqual(report["mechanical_status"], "failed")
        self.assertIn("numbering_suff_after_lvl_text", {item["code"] for item in report["findings"]})

    def test_numbering_references_must_exist(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        path = _write_docx(
            self.root,
            "numbering-missing-references.docx",
            table,
            numbering=_numbering(abstract_ref="9"),
            num_id="9",
        )

        report = audit_delivery.audit_docx(path)
        codes = {item["code"] for item in report["findings"]}

        self.assertEqual(report["mechanical_status"], "failed")
        self.assertIn("numbering_num_id_missing", codes)
        self.assertIn("numbering_abstract_num_id_missing", codes)
        self.assertNotIn("private-value-should-not-appear", json.dumps(report))

    def test_default_layout_flag_accepts_update_record_header(self) -> None:
        table = _table(
            [1000, 1000, 1000],
            [[(1, 1000), (1, 1000), (1, 1000)]],
            first_row_texts=["版本", "日期", "更新\n內容"],
        )
        path = _write_docx(self.root, "default-layout.docx", table)

        report = audit_delivery.audit_docx(path, require_default_layout=True)

        self.assertEqual(report["default_layout"]["status"], "pass")
        self.assertEqual(report["mechanical_status"], "pass")
        self.assertNotIn("update_record_header_missing", {item["code"] for item in report["findings"]})

    def test_cli_exposes_default_layout_flag_without_echoing_header_text(self) -> None:
        table = _table(
            [1000, 1000, 1000],
            [[(1, 1000), (1, 1000), (1, 1000)]],
            first_row_texts=["版本", "日期", "PRIVATE-UPDATE-CONTENT"],
        )
        path = _write_docx(self.root, "default-layout-cli.docx", table)
        output = self.root / "default-layout.json"

        code = audit_delivery.main([
            "--docx", str(path),
            "--output", str(output),
            "--require-default-layout",
        ])

        self.assertEqual(code, 0)
        report = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(report["default_layout"]["status"], "fail")
        self.assertIn("update_record_header_missing", {item["code"] for item in report["findings"]})
        self.assertNotIn("PRIVATE-UPDATE-CONTENT", output.read_text(encoding="utf-8"))

    def test_default_layout_flag_rejects_generic_field_table(self) -> None:
        table = _table(
            [750, 750, 750, 750],
            [[(1, 750), (1, 750), (1, 750), (1, 750)]],
            first_row_texts=["欄位", "定義", "必填", "限制"],
        )
        path = _write_docx(self.root, "generic-layout.docx", table)

        report = audit_delivery.audit_docx(path, require_default_layout=True)

        self.assertEqual(report["default_layout"]["status"], "fail")
        self.assertEqual(report["mechanical_status"], "failed")
        self.assertIn("update_record_header_columns_invalid", {item["code"] for item in report["findings"]})
        self.assertNotIn("欄位", json.dumps(report, ensure_ascii=False))

    def test_default_layout_flag_is_opt_in_and_preserves_old_behavior(self) -> None:
        table = _table(
            [750, 750, 750, 750],
            [[(1, 750), (1, 750), (1, 750), (1, 750)]],
            first_row_texts=["欄位", "定義", "必填", "限制"],
        )
        path = _write_docx(self.root, "opt-in-layout.docx", table)

        report = audit_delivery.audit_docx(path)

        self.assertNotIn("default_layout", report)
        self.assertEqual(report["mechanical_status"], "pass")
        self.assertNotIn("update_record_header_columns_invalid", {item["code"] for item in report["findings"]})

    def test_default_layout_flag_rejects_merged_header_and_empty_table(self) -> None:
        merged = _table(
            [1000, 1000, 1000],
            [[(3, 3000)]],
            first_row_texts=["版本 日期 更新內容"],
        )
        merged_path = _write_docx(self.root, "merged-header.docx", merged)
        merged_report = audit_delivery.audit_docx(merged_path, require_default_layout=True)
        self.assertEqual(merged_report["default_layout"]["status"], "fail")
        self.assertIn("update_record_header_columns_invalid", {item["code"] for item in merged_report["findings"]})

        empty = _table([1000, 1000, 1000], [])
        empty_path = _write_docx(self.root, "empty-header.docx", empty)
        empty_report = audit_delivery.audit_docx(empty_path, require_default_layout=True)
        self.assertEqual(empty_report["default_layout"]["status"], "fail")
        self.assertIn("update_record_header_row_missing", {item["code"] for item in empty_report["findings"]})

    def test_default_layout_flag_skips_explicit_single_cell_table_container(self) -> None:
        inner = _table(
            [1000, 1000, 1000],
            [[(1, 1000), (1, 1000), (1, 1000)]],
            first_row_texts=["版本", "日期", "更新內容"],
        )
        container = _table([3000], [[(1, 3000)]])
        first_cell = next(item for item in container.iter() if item.tag == w("tc"))
        first_cell.append(inner)
        path = _write_docx(self.root, "layout-container.docx", container)

        report = audit_delivery.audit_docx(path, require_default_layout=True)

        self.assertEqual(report["default_layout"]["status"], "pass")

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

    def test_image_evidence_accepts_current_relative_delivered_asset(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(
            self.root,
            "image-current.docx",
            table,
            media=["image1.png"],
            referenced_media=["image1.png"],
        )
        delivered = self.root / "delivered"
        delivered.mkdir()
        asset = delivered / "image1.png"
        asset.write_bytes(b"image1.png")
        evidence = self.root / "delivered-images.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [{"path": "delivered/image1.png", "sha256": _sha256(asset)}],
                }
            ),
            encoding="utf-8",
        )

        report = audit_delivery.audit_docx(docx, image_evidence_path=evidence)

        self.assertEqual(report["image_evidence"]["status"], "pass")
        self.assertEqual(report["image_evidence"]["assets"][0]["path"], "delivered/image1.png")
        self.assertEqual(report["mechanical_status"], "pass")

    def test_image_evidence_rejects_old_embedded_media(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(
            self.root,
            "image-old-embedded.docx",
            table,
            media=["image1.png"],
            referenced_media=["image1.png"],
        )
        delivered = self.root / "delivered"
        delivered.mkdir()
        asset = delivered / "image1.png"
        asset.write_bytes(b"new-redacted-image")
        evidence = self.root / "delivered-images.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [{"path": "delivered/image1.png", "sha256": _sha256(asset)}],
                }
            ),
            encoding="utf-8",
        )

        report = audit_delivery.audit_docx(docx, image_evidence_path=evidence)

        self.assertEqual(report["image_evidence"]["status"], "fail")
        self.assertIn("image_evidence_embedded_media_not_allowlisted", report["image_evidence"]["reason_codes"])
        self.assertEqual(report["mechanical_status"], "failed")

    def test_image_evidence_rejects_changed_asset_since_freeze(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(
            self.root,
            "image-stale-list.docx",
            table,
            media=["image1.png"],
            referenced_media=["image1.png"],
        )
        delivered = self.root / "delivered"
        delivered.mkdir()
        asset = delivered / "image1.png"
        asset.write_bytes(b"frozen-image")
        frozen_hash = _sha256(asset)
        asset.write_bytes(b"changed-after-freeze")
        evidence = self.root / "delivered-images.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [{"path": "delivered/image1.png", "sha256": frozen_hash}],
                }
            ),
            encoding="utf-8",
        )

        report = audit_delivery.audit_docx(docx, image_evidence_path=evidence)

        self.assertEqual(report["image_evidence"]["status"], "fail")
        self.assertIn("image_evidence_asset_hash_mismatch", report["image_evidence"]["reason_codes"])

    def test_image_evidence_rejects_raw_asset_and_protects_inputs(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(
            self.root,
            "image-raw.docx",
            table,
            media=["image1.png"],
            referenced_media=["image1.png"],
        )
        raw_dir = self.root / "raw"
        raw_dir.mkdir()
        asset = raw_dir / "image1.png"
        asset.write_bytes(b"image1.png")
        evidence = self.root / "delivered-images.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [{"path": "raw/image1.png", "sha256": _sha256(asset)}],
                }
            ),
            encoding="utf-8",
        )
        original_evidence = evidence.read_bytes()
        original_asset = asset.read_bytes()

        report = audit_delivery.audit_docx(docx, image_evidence_path=evidence)
        self.assertEqual(report["image_evidence"]["status"], "fail")
        self.assertIn("image_evidence_raw_path_forbidden", report["image_evidence"]["reason_codes"])

        overwrite_manifest = audit_delivery.main(
            ["--docx", str(docx), "--output", str(evidence), "--image-evidence", str(evidence)]
        )
        overwrite_asset = audit_delivery.main(
            ["--docx", str(docx), "--output", str(asset), "--image-evidence", str(evidence)]
        )
        self.assertEqual(overwrite_manifest, 2)
        self.assertEqual(overwrite_asset, 2)
        self.assertEqual(evidence.read_bytes(), original_evidence)
        self.assertEqual(asset.read_bytes(), original_asset)

        absolute_evidence = self.root / "invalid-path-images.json"
        absolute_evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [{"path": str(asset), "sha256": _sha256(asset)}],
                }
            ),
            encoding="utf-8",
        )
        overwrite_invalid = audit_delivery.main(
            ["--docx", str(docx), "--output", str(asset), "--image-evidence", str(absolute_evidence)]
        )
        self.assertEqual(overwrite_invalid, 2)
        self.assertEqual(asset.read_bytes(), original_asset)

    def test_output_conflict_falls_back_when_relative_asset_resolution_fails(self) -> None:
        table = _table([1000], [[(1, 1000)]])
        docx = _write_docx(self.root, "image-resolution-fallback.docx", table)
        delivered = self.root / "delivered"
        delivered.mkdir()
        asset = delivered / "image1.png"
        asset.write_bytes(b"delivered-image")
        evidence = self.root / "delivered-images.json"
        evidence.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "assets": [{"path": "delivered/image1.png", "sha256": _sha256(asset)}],
                }
            ),
            encoding="utf-8",
        )
        original_asset = asset.read_bytes()

        with patch.object(audit_delivery, "_resolve_image_asset", return_value=None):
            overwrite_exit = audit_delivery.main(
                ["--docx", str(docx), "--output", str(asset), "--image-evidence", str(evidence)]
            )

        self.assertEqual(overwrite_exit, 2)
        self.assertEqual(asset.read_bytes(), original_asset)


if __name__ == "__main__":
    unittest.main()
