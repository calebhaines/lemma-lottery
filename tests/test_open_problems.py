import contextlib
import io
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from theorem_catalog.catalog import DATA_DIRECTORY, EXPECTED_CODES, Catalog, CatalogError
from theorem_catalog.cli import main

ROOT = Path(__file__).resolve().parent.parent
PROBLEM_FIELDS = {
    "id",
    "subject",
    "name",
    "statement",
    "importance",
    "status",
    "status_note",
    "references",
}


class OpenProblemCatalogTests(unittest.TestCase):
    def test_all_subjects_have_ten_valid_open_problems(self):
        catalog = Catalog(kind="problem")
        self.assertEqual(
            catalog.validate(), {"status": "ok", "subject_count": 32, "problem_count": 320}
        )
        subjects = catalog.subjects()
        self.assertEqual({subject["code"] for subject in subjects}, EXPECTED_CODES)
        self.assertTrue(all(subject["problem_count"] == 10 for subject in subjects))
        self.assertTrue(all("theorem_count" not in subject for subject in subjects))
        for subject in subjects:
            code = subject["code"]
            entries = catalog.list(code)["items"]
            with self.subTest(subject=code):
                self.assertEqual(len(entries), 10)
                self.assertEqual(
                    {entry["id"] for entry in entries},
                    {f"{code}.open.{number:02d}" for number in range(1, 11)},
                )
                for entry in entries:
                    self.assertEqual(set(entry), PROBLEM_FIELDS)
                    self.assertEqual(entry["status"], "open")
                    self.assertEqual(catalog.get(entry["id"]), entry)
                result = catalog.random(code)
                self.assertIn(result, entries)

    def test_unfiltered_random_chooses_uniform_subject_then_ten_entries(self):
        catalog = Catalog(kind="problem")
        calls = []

        def choose(candidates):
            calls.append(candidates)
            return "math.NT" if isinstance(candidates, tuple) else candidates[-1]

        with patch("theorem_catalog.catalog.secrets.choice", side_effect=choose):
            result = catalog.random()
        self.assertEqual(set(calls[0]), EXPECTED_CODES)
        self.assertEqual(len(calls[1]), 10)
        self.assertEqual(result["id"], "math.NT.open.10")
        self.assertEqual(set(catalog._loaded), {"math.NT"})

    def test_subject_random_uses_one_choice_and_all_ten_candidates(self):
        with patch(
            "theorem_catalog.catalog.secrets.choice", side_effect=lambda entries: entries[0]
        ) as choice:
            result = Catalog(kind="problem").random("math.NT")
        self.assertEqual(result["id"], "math.NT.open.01")
        self.assertEqual(choice.call_count, 1)
        self.assertEqual(len(choice.call_args.args[0]), 10)

    def test_pagination_traverses_all_320_entries(self):
        catalog = Catalog(kind="problem")
        ids = []
        for offset in range(0, 320, 100):
            page = catalog.list(limit=100, offset=offset)
            self.assertEqual(page["total"], 320)
            ids.extend(entry["id"] for entry in page["items"])
        self.assertEqual(len(ids), 320)
        self.assertEqual(len(set(ids)), 320)
        self.assertEqual(ids[9], "math.AC.open.10")
        self.assertEqual(ids[10], "math.AG.open.01")

    def test_pages_load_only_intersecting_files_and_handle_offsets(self):
        catalog = Catalog(kind="problem")
        page = catalog.list(limit=3, offset=9)
        self.assertEqual(set(catalog._loaded), {"math.AC", "math.AG"})
        self.assertEqual(
            [entry["id"] for entry in page["items"]],
            ["math.AC.open.10", "math.AG.open.01", "math.AG.open.02"],
        )
        filtered = catalog.list("math.NT", limit=3, offset=8)
        self.assertEqual(filtered["total"], 10)
        self.assertEqual(
            [entry["id"] for entry in filtered["items"]],
            ["math.NT.open.09", "math.NT.open.10"],
        )
        self.assertEqual(catalog.list("math.NT", offset=10)["items"], [])
        self.assertEqual(catalog.list(offset=320)["items"], [])

    def test_problem_errors_and_separate_id_namespaces(self):
        catalog = Catalog(kind="problem")
        for problem_id in (
            "math.NT.01",
            "math.NT.open.00",
            "math.NT.open.11",
            "math.XX.open.01",
            "../subjects.json",
            "math.NT.open.1",
            "math.nt.open.01",
        ):
            with self.subTest(id=problem_id), self.assertRaises(CatalogError) as caught:
                catalog.get(problem_id)
            self.assertEqual(caught.exception.code, "unknown_problem")
        with self.assertRaises(CatalogError) as caught:
            Catalog().get("math.NT.open.01")
        self.assertEqual(caught.exception.code, "unknown_theorem")
        with self.assertRaises(CatalogError) as caught:
            catalog.random("math.XX")
        self.assertEqual(caught.exception.code, "unknown_subject")
        for limit, offset in ((0, 0), (101, 0), (20, -1)):
            with (
                self.subTest(limit=limit, offset=offset),
                self.assertRaises(CatalogError) as caught,
            ):
                catalog.list(limit=limit, offset=offset)
            self.assertEqual(caught.exception.code, "invalid_query")

    def test_kind_is_validated_before_reading_files(self):
        for kind in ("problems", "", None, [], {}):
            with self.subTest(kind=kind), self.assertRaises(CatalogError) as caught:
                Catalog("/missing-database", kind=kind)
            self.assertEqual(caught.exception.code, "invalid_query")

    def test_info_reports_problem_curation_and_review_metadata(self):
        info = Catalog(kind="problem").info()
        metadata = json.loads((DATA_DIRECTORY / "open_problems.json").read_text(encoding="utf-8"))
        self.assertEqual(info["version"], "1.1.0")
        self.assertEqual(info["subject_count"], 32)
        self.assertEqual(info["problem_count"], 320)
        self.assertEqual(info["problems_per_subject"], 10)
        self.assertEqual(info["selection_policy"], metadata["selection_policy"])
        self.assertEqual(info["status_reviewed_on"], metadata["status_reviewed_on"])
        self.assertNotIn("theorem_count", info)


class OpenProblemValidationTests(unittest.TestCase):
    """Malformed fixtures exercise schema validation independently of curation."""

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        shutil.copyfile(DATA_DIRECTORY / "subjects.json", self.directory / "subjects.json")
        self.metadata_path = self.directory / "open_problems.json"
        self.metadata_path.write_text(
            json.dumps({"selection_policy": "Test fixture", "status_reviewed_on": "2026-10-10"}),
            encoding="utf-8",
        )
        (self.directory / "open_problems").mkdir()
        self.subject_path = self.directory / "open_problems" / "math.NT.json"
        self.entries = [
            {
                "id": f"math.NT.open.{number:02d}",
                "subject": "math.NT",
                "name": f"Fixture problem {number}",
                "statement": "A test statement.",
                "importance": "A test reason.",
                "status": "open",
                "status_note": "A test status note.",
                "references": [{"title": "Test reference", "url": "https://example.org/problem"}],
            }
            for number in range(1, 11)
        ]
        self.subject_path.write_text(json.dumps(self.entries), encoding="utf-8")

    def rewrite_entry(self, replacement):
        entries = [dict(entry) for entry in self.entries]
        entries[0].update(replacement)
        self.subject_path.write_text(json.dumps(entries), encoding="utf-8")

    def test_problem_specific_fields_are_required_nonempty_and_open(self):
        for replacement in (
            {"importance": " "},
            {"importance": 1},
            {"status_note": ""},
            {"status": "solved"},
            {"status": "Open"},
            {"status": " open "},
            {"unexpected": "field"},
            {"subject": "math.AG"},
            {"name": ""},
            {"statement": " "},
            {"id": "math.NT.01"},
            {"id": "math.NT.open.11"},
            {"references": []},
            {"references": [{"title": "Source", "url": "bad-url"}]},
        ):
            with self.subTest(replacement=replacement):
                self.rewrite_entry(replacement)
                with self.assertRaises(CatalogError):
                    Catalog(self.directory, kind="problem").random("math.NT")
        for field in PROBLEM_FIELDS:
            with self.subTest(missing=field):
                entries = [dict(entry) for entry in self.entries]
                del entries[0][field]
                self.subject_path.write_text(json.dumps(entries), encoding="utf-8")
                with self.assertRaisesRegex(CatalogError, "invalid problem object"):
                    Catalog(self.directory, kind="problem").get("math.NT.open.01")

    def test_wrong_count_duplicate_id_and_duplicate_name(self):
        for entries in (
            self.entries[:-1],
            self.entries + [dict(self.entries[0])],
            [dict(self.entries[0]), dict(self.entries[0]), *self.entries[2:]],
            [
                dict(self.entries[0]),
                {**self.entries[1], "name": self.entries[0]["name"].upper()},
                *self.entries[2:],
            ],
        ):
            with self.subTest(count=len(entries)):
                self.subject_path.write_text(json.dumps(entries), encoding="utf-8")
                with self.assertRaises(CatalogError):
                    Catalog(self.directory, kind="problem").random("math.NT")

    def test_problem_metadata_requires_object_and_nonempty_fields(self):
        for metadata in (
            [],
            {},
            {"selection_policy": "Test"},
            {"status_reviewed_on": "2026-10-10"},
            {"selection_policy": " ", "status_reviewed_on": "2026-10-10"},
            {"selection_policy": "Test", "status_reviewed_on": ""},
            {"selection_policy": "Test", "status_reviewed_on": 123},
        ):
            with self.subTest(metadata=metadata):
                self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaises(CatalogError):
                    Catalog(self.directory, kind="problem")

    def test_missing_or_invalid_metadata_file(self):
        self.metadata_path.unlink()
        with self.assertRaisesRegex(CatalogError, "Cannot read database file open_problems.json"):
            Catalog(self.directory, kind="problem")
        self.metadata_path.write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "Cannot read database"):
            Catalog(self.directory, kind="problem")

    def test_problem_subject_notes_override_shared_notes_and_are_validated(self):
        metadata = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        metadata["subject_notes"] = {"math.HO": "Historically influential open questions."}
        self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
        subjects = Catalog(self.directory, kind="problem").subjects()
        self.assertEqual(
            next(subject for subject in subjects if subject["code"] == "math.HO")["note"],
            "Historically influential open questions.",
        )
        for notes in ([], None, {"math.XX": "Unknown subject"}, {"math.HO": " "}, {"math.HO": 1}):
            with self.subTest(notes=notes):
                metadata["subject_notes"] = notes
                self.metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
                with self.assertRaisesRegex(CatalogError, "subject_notes"):
                    Catalog(self.directory, kind="problem")

    def test_full_validation_detects_missing_extra_and_absent_directory(self):
        with self.assertRaisesRegex(CatalogError, "missing=.*math.AC"):
            Catalog(self.directory, kind="problem").validate()
        (self.directory / "open_problems" / "math.XX.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "extra=.*math.XX"):
            Catalog(self.directory, kind="problem").validate()
        shutil.rmtree(self.directory / "open_problems")
        with self.assertRaisesRegex(CatalogError, "Cannot scan problem database"):
            Catalog(self.directory, kind="problem").validate()

    def test_theorem_metadata_queries_do_not_require_problem_files(self):
        self.metadata_path.unlink()
        catalog = Catalog(self.directory)
        self.assertEqual(catalog.info()["theorem_count"], 640)
        self.assertEqual(len(catalog.subjects()), 32)


class OpenProblemCommandTests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_kind_before_after_and_default_random(self):
        for arguments in (
            ["--kind", "problem"],
            ["--kind", "problem", "random", "--subject", "math.NT"],
            ["random", "--kind", "problem", "--subject", "math.NT"],
            ["--pretty", "--kind", "problem", "random", "--subject", "math.NT"],
            ["random", "--subject", "math.NT", "--pretty", "--kind", "problem"],
        ):
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(arguments)
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                stdout.encode("ascii")
                result = json.loads(stdout)
                self.assertEqual(result["status"], "open")
                self.assertIn(result["subject"], EXPECTED_CODES)
                if "--subject" in arguments:
                    self.assertEqual(result["subject"], "math.NT")

    def test_all_problem_commands(self):
        for arguments in (
            ["subjects"],
            ["list", "--subject", "math.NT"],
            ["get", "math.NT.open.01"],
            ["info"],
            ["validate"],
        ):
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke([*arguments, "--kind", "problem"])
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertTrue(json.loads(stdout))

    def test_query_errors_are_json_and_exit_two(self):
        for arguments, expected_code in (
            (["--kind", "unknown", "random"], "invalid_query"),
            (["random", "--kind", "unknown"], "invalid_query"),
            (["get", "math.NT.open.11", "--kind", "problem"], "unknown_problem"),
            (["get", "math.NT.01", "--kind", "problem"], "unknown_problem"),
            (["get", "math.NT.open.01"], "unknown_theorem"),
            (["random", "--kind", "problem", "--subject", "math.XX"], "unknown_subject"),
        ):
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(arguments)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertEqual(json.loads(stderr)["error"]["code"], expected_code)

    def test_problem_script_works_without_dependencies_from_any_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [
                    sys.executable,
                    "-S",
                    str(ROOT / "theorem.py"),
                    "random",
                    "--kind",
                    "problem",
                    "--subject",
                    "math.NT",
                ],
                cwd=directory,
                capture_output=True,
                text=True,
                check=True,
            )
        self.assertEqual(json.loads(result.stdout)["subject"], "math.NT")
        self.assertEqual(json.loads(result.stdout)["status"], "open")
        self.assertEqual(result.stderr, "")

    def test_problem_module_entry_point(self):
        result = subprocess.run(
            [sys.executable, "-S", "-m", "theorem_catalog", "validate", "--kind", "problem"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["problem_count"], 320)


if __name__ == "__main__":
    unittest.main()
