import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from measurement import OWNERS

ROOT = Path(__file__).resolve().parent
CHARTS = (
    "lesson-velocity-swimlanes.svg",
    "lesson-impact-effort-quadrant.svg",
    "lesson-days-to-impact-by-team.svg",
)
BANNED = (
    "interview",
    "hiring manager",
    "job search",
    "job-search",
    "portfolio",
    "how i'd",
    "how i would",
    "hiring-manager",
)


def charts_module():
    spec = importlib.util.spec_from_file_location("make_charts", ROOT / "scripts" / "make_charts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def labor_cost(lesson, rate):
    return (
        lesson["repeats_per_month"] * lesson["hours_per_escalation"]
        + lesson["workaround_hours_per_month"]
    ) * rate


class LessonVelocityChartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = charts_module()
        cls.data = cls.mod.load_data(cls.mod.DEFAULT_DATA)

    def test_example_file_uses_the_scorecard_teams(self):
        owners = [name for name, _blurb in OWNERS]
        self.assertEqual(
            [row["owner"] for row in self.data["days_to_impact_by_team"]],
            owners,
        )
        self.assertEqual({lesson["owner"] for lesson in self.data["lessons"]}, set(owners))
        self.assertEqual(self.data["loaded_hourly_cost"], 150)
        self.assertEqual(self.data["impact_target_days"], 45)
        self.assertGreaterEqual(len(self.data["blocked_reason_codes"]), 8)
        for lesson in self.data["lessons"]:
            if lesson["status"] == "open":
                self.assertIn(lesson["blocker"], self.data["blocked_reason_codes"])

    def test_cost_of_delay_ranks_the_worked_examples(self):
        ranked = []
        for lesson in self.data["lessons"]:
            if lesson.get("repeats_per_month") is None:
                continue
            ranked.append((labor_cost(lesson, self.data["loaded_hourly_cost"]), lesson["name"]))
        ranked.sort(key=lambda item: item[0], reverse=True)
        self.assertEqual(
            [name for _cost, name in ranked],
            [
                "Scheduler preemption bug",
                "Quota pre-flight validator",
                "Onboarding config linter",
                "Quarterly health review on repeats",
            ],
        )
        self.assertEqual([cost for cost, _name in ranked], [10200, 5100, 3450, 1800])
        doc = (ROOT / "docs" / "lesson-velocity.md").read_text(encoding="utf-8")
        for figure in ("$10,200", "$5,100", "$3,450", "$1,800"):
            self.assertIn(figure, doc)

    def test_docs_embed_the_charts_as_example_data(self):
        velocity = (ROOT / "docs" / "lesson-velocity.md").read_text(encoding="utf-8")
        influence = (ROOT / "docs" / "measuring-influence.md").read_text(encoding="utf-8")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        for name in CHARTS:
            self.assertIn(name, velocity)
            self.assertIn(name, influence)
            svg = ROOT / "docs" / "images" / name
            self.assertTrue(svg.is_file(), name)
            self.assertIn("EXAMPLE DATA", svg.read_text(encoding="utf-8"))
            self.assertGreater(svg.stat().st_size, 2000)
        self.assertIn("scripts/make_charts.py", readme)
        self.assertIn("docs/lesson-velocity.md", readme)
        self.assertIn("lesson-velocity.md", influence)
        lowered = velocity.lower()
        for phrase in BANNED:
            self.assertNotIn(phrase, lowered)
        for code in self.data["blocked_reason_codes"]:
            self.assertIn(code, velocity)

    def test_generator_writes_three_stamped_charts(self):
        try:
            import matplotlib  # noqa: F401
        except ImportError:
            if os.environ.get("CI"):
                self.fail("matplotlib is required in CI. Install requirements-dev.txt.")
            self.skipTest("matplotlib is not installed. pip install -r requirements-dev.txt")
        with tempfile.TemporaryDirectory() as tmp:
            result = subprocess.run(
                [sys.executable, "scripts/make_charts.py", "--out", tmp],
                cwd=ROOT,
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            for name in CHARTS:
                path = Path(tmp) / name
                self.assertTrue(path.is_file(), name)
                text = path.read_text(encoding="utf-8")
                self.assertIn("EXAMPLE DATA", text)
                self.assertGreater(path.stat().st_size, 2000)
            swim = (Path(tmp) / CHARTS[0]).read_text(encoding="utf-8")
            days = (Path(tmp) / CHARTS[2]).read_text(encoding="utf-8")
            self.assertIn("BLOCKED", swim)
            self.assertIn("Scheduler preemption bug", swim)
            for snippet in (
                "Support",
                "Customer Success",
                "Technical Account Managers",
                "Strategic TAMs",
                "Solutions Architects",
                "hardware operations",
                "Product management",
                "services engineers",
                "Engineering",
                "EXAMPLE DATA",
            ):
                self.assertIn(snippet, days)
