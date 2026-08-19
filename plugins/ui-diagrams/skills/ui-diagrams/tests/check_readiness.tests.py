import importlib.util
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "check_readiness.py"


def load_module() -> object | None:
    if not SCRIPT.is_file():
        return None
    spec = importlib.util.spec_from_file_location("check_readiness", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CheckReadinessTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_path = Path(__file__).parent / "fixtures" / "empty-home"

    def test_reports_needs_install_when_skill_and_cli_are_missing(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        self.assertTrue(hasattr(check_readiness, "inspect_environment"))
        if not hasattr(check_readiness, "inspect_environment"):
            return
        report = check_readiness.inspect_environment(
            home=self.temp_path,
            platform="win32",
            which=lambda _: None,
            exists=lambda _: False,
            probe=lambda _: None,
        )
        self.assertEqual(report["status"], "needs-install")
        self.assertEqual(report["missing"], ["drawio-skill", "drawio-desktop"])

    def test_reports_ready_for_a_codex_skill_and_successful_cli_probe(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        self.assertTrue(hasattr(check_readiness, "ProbeResult"))
        if not hasattr(check_readiness, "ProbeResult"):
            return
        skill = (
            Path(__file__).parent
            / "fixtures/ready-home/.codex/skills/drawio-skill/skills/drawio-skill/SKILL.md"
        )
        self.assertTrue(skill.is_file())
        report = check_readiness.inspect_environment(
            home=Path(__file__).parent / "fixtures" / "ready-home",
            platform="win32",
            which=lambda name: "C:/Program Files/draw.io/draw.io.exe" if name == "drawio" else None,
            exists=lambda _: False,
            probe=lambda _: check_readiness.ProbeResult(0, "29.0.0", ""),
        )
        self.assertEqual(report["status"], "ready")

    def test_reports_unavailable_when_present_cli_fails_probe(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        self.assertTrue(hasattr(check_readiness, "ProbeResult"))
        if not hasattr(check_readiness, "ProbeResult"):
            return
        report = check_readiness.inspect_environment(
            home=self.temp_path,
            platform="darwin",
            which=lambda name: "/Applications/draw.io.app/Contents/MacOS/draw.io" if name == "drawio" else None,
            exists=lambda _: False,
            probe=lambda _: check_readiness.ProbeResult(1, "", "Electron failed"),
        )
        self.assertEqual(report["status"], "unavailable")
        self.assertEqual(report["drawioCli"]["state"], "unavailable")


if __name__ == "__main__":
    unittest.main()
