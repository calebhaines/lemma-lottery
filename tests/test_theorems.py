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


class CatalogTests(unittest.TestCase):
    def test_all_official_subjects_have_exactly_twenty_entries(self):
        catalog = Catalog()
        self.assertEqual(
            catalog.validate(), {"status": "ok", "subject_count": 32, "theorem_count": 640}
        )
        subjects = catalog.subjects()
        self.assertEqual({subject["code"] for subject in subjects}, EXPECTED_CODES)
        self.assertTrue(all(subject["theorem_count"] == 20 for subject in subjects))
        self.assertEqual(
            {subject["code"]: subject["label"] for subject in subjects},
            {
                "math.AC": "Commutative Algebra",
                "math.AG": "Algebraic Geometry",
                "math.AP": "Analysis of PDEs",
                "math.AT": "Algebraic Topology",
                "math.CA": "Classical Analysis and ODEs",
                "math.CO": "Combinatorics",
                "math.CT": "Category Theory",
                "math.CV": "Complex Variables",
                "math.DG": "Differential Geometry",
                "math.DS": "Dynamical Systems",
                "math.FA": "Functional Analysis",
                "math.GM": "General Mathematics",
                "math.GN": "General Topology",
                "math.GR": "Group Theory",
                "math.GT": "Geometric Topology",
                "math.HO": "History and Overview",
                "math.IT": "Information Theory",
                "math.KT": "K-Theory and Homology",
                "math.LO": "Logic",
                "math.MG": "Metric Geometry",
                "math.MP": "Mathematical Physics",
                "math.NA": "Numerical Analysis",
                "math.NT": "Number Theory",
                "math.OA": "Operator Algebras",
                "math.OC": "Optimization and Control",
                "math.PR": "Probability",
                "math.QA": "Quantum Algebra",
                "math.RA": "Rings and Algebras",
                "math.RT": "Representation Theory",
                "math.SG": "Symplectic Geometry",
                "math.SP": "Spectral Theory",
                "math.ST": "Statistics Theory",
            },
        )

    def test_random_and_stable_retrieval_for_every_subject(self):
        catalog = Catalog()
        for code in EXPECTED_CODES:
            with self.subTest(subject=code):
                result = catalog.random(code)
                self.assertEqual(result["subject"], code)
                self.assertEqual(catalog.get(result["id"]), result)
                self.assertEqual(len(catalog.list(code)["items"]), 20)

    def test_unfiltered_random_chooses_subject_then_entry_and_loads_one_file(self):
        catalog = Catalog()
        calls = []

        def choose(candidates):
            calls.append(candidates)
            return "math.NT" if isinstance(candidates, tuple) else candidates[-1]

        with patch("theorem_catalog.catalog.secrets.choice", side_effect=choose):
            result = catalog.random()
        self.assertEqual(set(calls[0]), EXPECTED_CODES)
        self.assertEqual(len(calls[1]), 20)
        self.assertEqual(result["id"], "math.NT.20")
        self.assertEqual(set(catalog._loaded), {"math.NT"})

    def test_subject_random_passes_exactly_twenty_candidates(self):
        with patch(
            "theorem_catalog.catalog.secrets.choice", side_effect=lambda entries: entries[0]
        ) as choice:
            result = Catalog().random("math.NT")
        self.assertEqual(result["id"], "math.NT.01")
        self.assertEqual(choice.call_count, 1)
        self.assertEqual(len(choice.call_args.args[0]), 20)

    def test_repeated_results_are_allowed(self):
        with patch(
            "theorem_catalog.catalog.secrets.choice", side_effect=lambda entries: entries[0]
        ):
            catalog = Catalog()
            self.assertEqual(catalog.random("math.NT"), catalog.random("math.NT"))

    def test_pagination_traverses_whole_database(self):
        catalog = Catalog()
        ids = []
        for offset in range(0, 640, 100):
            page = catalog.list(limit=100, offset=offset)
            self.assertEqual(page["total"], 640)
            ids.extend(entry["id"] for entry in page["items"])
        self.assertEqual(len(ids), 640)
        self.assertEqual(len(set(ids)), 640)
        self.assertEqual(ids[19], "math.AC.20")
        self.assertEqual(ids[20], "math.AG.01")

    def test_filtered_pagination_and_offset_past_end(self):
        catalog = Catalog()
        page = catalog.list("math.NT", limit=3, offset=7)
        self.assertEqual(
            [entry["id"] for entry in page["items"]], ["math.NT.08", "math.NT.09", "math.NT.10"]
        )
        self.assertEqual(page["total"], 20)
        self.assertEqual(catalog.list("math.NT", offset=20)["items"], [])

    def test_listing_reads_only_files_that_intersect_the_page(self):
        catalog = Catalog()
        catalog.list(limit=3, offset=19)
        self.assertEqual(set(catalog._loaded), {"math.AC", "math.AG"})

    def test_unknown_subject_and_id(self):
        for code in ("math.XX", "nt", "math.nt", "", "math-ph"):
            with self.subTest(code=code), self.assertRaises(CatalogError) as caught:
                Catalog().random(code)
            self.assertEqual(caught.exception.code, "unknown_subject")
        for theorem_id in ("math.NT.99", "math.XX.01", "../subjects.json", "math.NT.00"):
            with self.subTest(id=theorem_id), self.assertRaises(CatalogError) as caught:
                Catalog().get(theorem_id)
            self.assertEqual(caught.exception.code, "unknown_theorem")

    def test_invalid_pagination(self):
        for limit, offset in ((0, 0), (101, 0), (20, -1)):
            with (
                self.subTest(limit=limit, offset=offset),
                self.assertRaises(CatalogError) as caught,
            ):
                Catalog().list(limit=limit, offset=offset)
            self.assertEqual(caught.exception.code, "invalid_query")


class DatabaseValidationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "data"
        shutil.copytree(DATA_DIRECTORY, self.directory)

    def rewrite(self, change):
        path = self.directory / "theorems" / "math.NT.json"
        entries = json.loads(path.read_text(encoding="utf-8"))
        change(entries)
        path.write_text(json.dumps(entries, ensure_ascii=False), encoding="utf-8")

    def test_missing_subject_file(self):
        (self.directory / "theorems" / "math.NT.json").unlink()
        with self.assertRaisesRegex(CatalogError, "missing=.*math.NT"):
            Catalog(self.directory).validate()

    def test_missing_theorem_directory(self):
        shutil.rmtree(self.directory / "theorems")
        with self.assertRaisesRegex(CatalogError, "Cannot scan theorem database"):
            Catalog(self.directory).validate()

    def test_missing_metadata_field(self):
        path = self.directory / "subjects.json"
        metadata = json.loads(path.read_text(encoding="utf-8"))
        del metadata["selection_policy"]
        path.write_text(json.dumps(metadata), encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "selection_policy"):
            Catalog(self.directory)

    def test_extra_subject_file(self):
        (self.directory / "theorems" / "math.XX.json").write_text("[]", encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "extra=.*math.XX"):
            Catalog(self.directory).validate()

    def test_missing_theorem(self):
        self.rewrite(lambda entries: entries.pop())
        with self.assertRaisesRegex(CatalogError, "exactly 20"):
            Catalog(self.directory).validate()

    def test_duplicate_id_and_name(self):
        self.rewrite(lambda entries: entries[1].update(id=entries[0]["id"]))
        with self.assertRaisesRegex(CatalogError, "duplicate"):
            Catalog(self.directory).validate()
        self.rewrite(
            lambda entries: entries[1].update(id="math.NT.02", name=entries[0]["name"].upper())
        )
        with self.assertRaisesRegex(CatalogError, "duplicate"):
            Catalog(self.directory).validate()

    def test_wrong_subject(self):
        self.rewrite(lambda entries: entries[0].update(subject="math.AG"))
        with self.assertRaisesRegex(CatalogError, "wrong subject"):
            Catalog(self.directory).validate()

    def test_invalid_record_fields(self):
        original = (self.directory / "theorems" / "math.NT.json").read_text(encoding="utf-8")
        for replacement in (
            {"name": " "},
            {"statement": ""},
            {"references": []},
            {"references": [{"title": "Source", "url": "not-a-url"}]},
            {"references": [{"title": "Source", "url": "ftp://example.com"}]},
            {"id": "math.NT.99"},
            {"unexpected": "field"},
        ):
            with self.subTest(replacement=replacement):
                (self.directory / "theorems" / "math.NT.json").write_text(
                    original, encoding="utf-8"
                )
                self.rewrite(lambda entries: entries[0].update(replacement))
                with self.assertRaises(CatalogError):
                    Catalog(self.directory).validate()

    def test_invalid_json(self):
        (self.directory / "theorems" / "math.NT.json").write_text("{", encoding="utf-8")
        with self.assertRaisesRegex(CatalogError, "Cannot read database"):
            Catalog(self.directory).random("math.NT")


class CommandTests(unittest.TestCase):
    def invoke(self, arguments):
        stdout, stderr = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            code = main(arguments)
        return code, stdout.getvalue(), stderr.getvalue()

    def test_default_command_returns_one_json_object(self):
        code, stdout, stderr = self.invoke([])
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertEqual(len(stdout.splitlines()), 1)
        # JSON escapes keep mathematical Unicode portable across process locales.
        stdout.encode("ascii")
        self.assertIn(json.loads(stdout)["subject"], EXPECTED_CODES)

    def test_all_commands_and_pretty_output(self):
        for arguments in (
            ["random", "--subject", "math.NT"],
            ["subjects"],
            ["list", "--subject", "math.NT"],
            ["get", "math.NT.01"],
            ["info"],
            ["validate"],
            ["get", "math.NT.01", "--pretty"],
            ["--pretty", "get", "math.NT.01"],
        ):
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(arguments)
                self.assertEqual(code, 0)
                self.assertEqual(stderr, "")
                self.assertTrue(json.loads(stdout))

    def test_bad_queries_emit_json_on_stderr_and_exit_two(self):
        for arguments in (
            ["random", "--subject", "math.XX"],
            ["get", "math.NT.99"],
            ["list", "--limit", "0"],
            ["list", "--limit", "abc"],
            ["list", "--offset", "-1"],
            ["nonsense"],
            ["random", "--subject"],
        ):
            with self.subTest(arguments=arguments):
                code, stdout, stderr = self.invoke(arguments)
                self.assertEqual(code, 2)
                self.assertEqual(stdout, "")
                self.assertIn("error", json.loads(stderr))

    def test_database_failure_is_json_and_exit_one(self):
        with patch("theorem_catalog.cli.Catalog", side_effect=CatalogError("Missing database")):
            code, stdout, stderr = self.invoke(["random"])
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertEqual(json.loads(stderr)["error"]["code"], "invalid_database")

    def test_script_works_from_any_directory_without_site_packages(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(
                [sys.executable, "-S", str(ROOT / "theorem.py"), "random", "--subject", "math.NT"],
                cwd=directory,
                capture_output=True,
                text=True,
                check=True,
            )
        self.assertEqual(json.loads(result.stdout)["subject"], "math.NT")
        self.assertEqual(result.stderr, "")

    def test_module_entry_point(self):
        result = subprocess.run(
            [sys.executable, "-S", "-m", "theorem_catalog", "validate"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout)["theorem_count"], 640)


if __name__ == "__main__":
    unittest.main()
