import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


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

    def test_bounds_hostile_probe_output_and_marks_the_report_as_truncated(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        result = check_readiness.probe_command(
            [
                sys.executable,
                "-c",
                "import sys; sys.stdout.write('o' * 49152); sys.stderr.write('e' * 49152)",
            ]
        )
        self.assertEqual(result.returncode, 0)
        self.assertLessEqual(len(result.stdout.encode("utf-8")), 16384)
        self.assertLessEqual(len(result.stderr.encode("utf-8")), 16384)
        report = check_readiness.inspect_environment(
            home=Path(__file__).parent / "fixtures" / "ready-home",
            platform="linux",
            which=lambda name: "/usr/bin/drawio" if name == "drawio" else None,
            exists=lambda _: False,
            probe=lambda _: result,
        )
        self.assertIn("truncated", report["drawioCli"]["detail"])

    def test_classifies_a_timeout_or_no_result_as_unavailable_when_command_exists(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        for name, probe, detail in (
            (
                "timeout",
                lambda _: check_readiness.ProbeResult(None, "", "timed out"),
                "timed out",
            ),
            ("no result", lambda _: None, "no usable result"),
        ):
            with self.subTest(name=name):
                report = check_readiness.inspect_environment(
                    home=Path(__file__).parent / "fixtures" / "ready-home",
                    platform="linux",
                    which=lambda command: "/usr/bin/drawio" if command == "drawio" else None,
                    exists=lambda _: False,
                    probe=probe,
                )
                self.assertEqual(report["status"], "unavailable")
                self.assertEqual(report["drawioCli"]["state"], "unavailable")
                self.assertIn(detail, report["drawioCli"]["detail"])

    def test_resolves_windows_paths_after_path_commands_are_absent(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        searched: list[str] = []
        existing: list[Path] = []

        def which(name: str) -> str | None:
            searched.append(name)
            return None

        def exists(path: Path) -> bool:
            existing.append(path)
            return path == Path("D:/Program Files (x86)/draw.io/draw.io.exe")

        with patch.dict(
            check_readiness.os.environ,
            {
                "ProgramFiles": "D:/Program Files",
                "ProgramFiles(x86)": "D:/Program Files (x86)",
            },
        ):
            command = check_readiness.resolve_drawio_command("win32", which, exists)

        self.assertEqual(searched, ["drawio", "draw.io"])
        self.assertEqual(
            existing,
            [
                Path("D:/Program Files/draw.io/draw.io.exe"),
                Path("D:/Program Files (x86)/draw.io/draw.io.exe"),
            ],
        )
        self.assertEqual(command, [str(Path("D:/Program Files (x86)/draw.io/draw.io.exe"))])

    def test_resolves_macos_and_linux_in_the_declared_order(self) -> None:
        check_readiness = load_module()
        self.assertIsNotNone(check_readiness)
        if check_readiness is None:
            return
        mac_names: list[str] = []
        mac_paths: list[Path] = []

        mac_command = check_readiness.resolve_drawio_command(
            "darwin",
            lambda name: mac_names.append(name) or None,
            lambda path: mac_paths.append(path) or True,
        )
        linux_names: list[str] = []

        def linux_which(name: str) -> str | None:
            linux_names.append(name)
            return "/opt/draw.io" if name == "draw.io" else None

        linux_command = check_readiness.resolve_drawio_command(
            "linux",
            linux_which,
            lambda _: self.fail("Linux should not inspect platform app paths"),
        )

        self.assertEqual(mac_names, ["drawio", "draw.io"])
        self.assertEqual(mac_paths, [Path("/Applications/draw.io.app/Contents/MacOS/draw.io")])
        self.assertEqual(
            mac_command, [str(Path("/Applications/draw.io.app/Contents/MacOS/draw.io"))]
        )
        self.assertEqual(linux_names, ["drawio", "draw.io"])
        self.assertEqual(linux_command, ["/opt/draw.io"])


if __name__ == "__main__":
    unittest.main()
