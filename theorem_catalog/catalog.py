"""Dependency-free access to the finite JSON mathematics databases."""

import json
import re
import secrets
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIRECTORY = files("theorem_catalog").joinpath("data")
THEOREMS_PER_SUBJECT = 20
PROBLEMS_PER_SUBJECT = 10
EXPECTED_CODES = frozenset(
    "math." + suffix
    for suffix in (
        "AC AG AP AT CA CO CT CV DG DS FA GM GN GR GT HO IT KT LO MG MP NA NT OA OC PR "
        "QA RA RT SG SP ST"
    ).split()
)


class CatalogError(ValueError):
    """A database or query error with a machine-readable code."""

    def __init__(self, message: str, code: str = "invalid_database"):
        super().__init__(message)
        self.code = code


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise CatalogError(f"Cannot read database file {path.name}: {error}") from error


class Catalog:
    """Read metadata once, then load only the subjects a command needs."""

    def __init__(self, data_directory=DATA_DIRECTORY, *, kind: str = "theorem"):
        if kind not in ("theorem", "problem"):
            raise CatalogError("kind must be 'theorem' or 'problem'.", "invalid_query")
        self.kind = kind
        self.entries_per_subject = (
            THEOREMS_PER_SUBJECT if kind == "theorem" else PROBLEMS_PER_SUBJECT
        )
        self.entry_directory = "theorems" if kind == "theorem" else "open_problems"
        self.directory = Path(data_directory) if isinstance(data_directory, str) else data_directory
        self.metadata = read_json(self.directory / "subjects.json")
        if not isinstance(self.metadata, dict):
            raise CatalogError("Subject metadata must be a JSON object.")
        for field in ("selection_policy", "taxonomy_source", "taxonomy_checked_on"):
            value = self.metadata.get(field)
            if not isinstance(value, str) or not value.strip():
                raise CatalogError(f"Subject metadata requires a nonempty {field} string.")
        subjects = self.metadata.get("subjects")
        if not isinstance(subjects, list) or len(subjects) != 32:
            raise CatalogError("The database must contain all 32 arXiv mathematics subjects.")
        self._subjects = {}
        for subject in subjects:
            if not isinstance(subject, dict):
                raise CatalogError("Every subject must be an object.")
            code = subject.get("code")
            label = subject.get("label")
            if not isinstance(code, str) or code not in EXPECTED_CODES:
                raise CatalogError(f"Invalid arXiv math subject code: {code!r}")
            if code in self._subjects or not isinstance(label, str) or not label.strip():
                raise CatalogError(f"Duplicate subject or missing label: {code}")
            self._subjects[code] = subject
        if set(self._subjects) != EXPECTED_CODES:
            raise CatalogError("The database must contain all 32 arXiv mathematics subjects.")
        if kind == "problem":
            self.problem_metadata = read_json(self.directory / "open_problems.json")
            if not isinstance(self.problem_metadata, dict):
                raise CatalogError("Open problem metadata must be a JSON object.")
            for field in ("selection_policy", "status_reviewed_on"):
                value = self.problem_metadata.get(field)
                if not isinstance(value, str) or not value.strip():
                    raise CatalogError(f"Open problem metadata requires a nonempty {field} string.")
            subject_notes = self.problem_metadata.get("subject_notes", {})
            if not isinstance(subject_notes, dict) or any(
                code not in self._subjects or not isinstance(note, str) or not note.strip()
                for code, note in subject_notes.items()
            ):
                raise CatalogError(
                    "Open problem subject_notes must map valid codes to nonempty text."
                )
            for code, note in subject_notes.items():
                self._subjects[code] = {**self._subjects[code], "note": note}
        self._loaded = {}

    def subjects(self) -> list[dict]:
        return [
            {**subject, f"{self.kind}_count": self.entries_per_subject}
            for subject in self._subjects.values()
        ]

    def _check_subject(self, subject: str):
        if subject not in self._subjects:
            raise CatalogError(
                f"Unknown subject '{subject}'. Run 'subjects' for valid arXiv math codes.",
                "unknown_subject",
            )

    def _load_subject(self, subject: str) -> list[dict]:
        self._check_subject(subject)
        if subject in self._loaded:
            return self._loaded[subject]
        entries = read_json(self.directory / self.entry_directory / f"{subject}.json")
        if not isinstance(entries, list) or len(entries) != self.entries_per_subject:
            raise CatalogError(
                f"{subject} must contain exactly {self.entries_per_subject} {self.kind}s."
            )
        ids = set()
        names = set()
        fields = {"id", "subject", "name", "statement", "references"}
        text_fields = ("id", "subject", "name", "statement")
        if self.kind == "problem":
            fields |= {"importance", "status", "status_note"}
            text_fields += ("importance", "status", "status_note")
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != fields:
                raise CatalogError(f"{subject} contains an invalid {self.kind} object.")
            for field in text_fields:
                if not isinstance(entry[field], str) or not entry[field].strip():
                    raise CatalogError(f"{subject} has a missing or empty {field}.")
            if entry["subject"] != subject:
                raise CatalogError(f"A {self.kind} in {subject} has the wrong subject.")
            if self.kind == "problem" and entry["status"] != "open":
                raise CatalogError(f"{entry['id']} must have status 'open'.")
            if entry["id"] in ids or entry["name"].strip().casefold() in names:
                raise CatalogError(f"{subject} contains duplicate {self.kind} IDs or names.")
            ids.add(entry["id"])
            names.add(entry["name"].strip().casefold())
            references = entry["references"]
            if not isinstance(references, list) or not references:
                raise CatalogError(f"{entry['id']} needs at least one reference.")
            for reference in references:
                if not isinstance(reference, dict) or set(reference) != {"title", "url"}:
                    raise CatalogError(f"{entry['id']} has an invalid reference object.")
                if not isinstance(reference["title"], str) or not reference["title"].strip():
                    raise CatalogError(f"{entry['id']} has an empty reference title.")
                url = reference["url"]
                if not isinstance(url, str) or any(char.isspace() for char in url):
                    raise CatalogError(f"{entry['id']} has an invalid reference URL.")
                try:
                    parts = urlsplit(url)
                    valid_url = parts.scheme in {"https", "http"} and bool(parts.hostname)
                except ValueError:
                    valid_url = False
                if not valid_url:
                    raise CatalogError(f"{entry['id']} has an invalid reference URL.")
        prefix = subject if self.kind == "theorem" else f"{subject}.open"
        expected_ids = {
            f"{prefix}.{number:02d}" for number in range(1, self.entries_per_subject + 1)
        }
        if ids != expected_ids:
            raise CatalogError(
                f"{subject} must have IDs {prefix}.01 through "
                f"{prefix}.{self.entries_per_subject:02d}."
            )
        self._loaded[subject] = entries
        return entries

    def random(self, subject: str | None = None) -> dict:
        # Equal-size subjects: a uniform subject followed by a uniform entry
        # is uniform over the selected database, reading just one small file.
        if subject is None:
            subject = secrets.choice(tuple(self._subjects))
        return secrets.choice(self._load_subject(subject))

    def get(self, theorem_id: str) -> dict:
        pattern = (
            r"math\.[A-Z]{2}\.(?:0[1-9]|1[0-9]|20)"
            if self.kind == "theorem"
            else r"math\.[A-Z]{2}\.open\.(?:0[1-9]|10)"
        )
        if not re.fullmatch(pattern, theorem_id):
            raise CatalogError(f"Unknown {self.kind} ID '{theorem_id}'.", f"unknown_{self.kind}")
        subject = theorem_id[:7]
        if subject not in self._subjects:
            raise CatalogError(f"Unknown {self.kind} ID '{theorem_id}'.", f"unknown_{self.kind}")
        return next(entry for entry in self._load_subject(subject) if entry["id"] == theorem_id)

    def list(self, subject: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        if not 1 <= limit <= 100 or offset < 0:
            raise CatalogError(
                "limit must be 1..100 and offset must be nonnegative.", "invalid_query"
            )
        if subject is not None:
            self._check_subject(subject)
        codes = [subject] if subject is not None else list(self._subjects)
        total = len(codes) * self.entries_per_subject
        items = []
        # Only read files that intersect the requested page.
        for index in range(offset, min(offset + limit, total)):
            code = codes[index // self.entries_per_subject]
            items.append(self._load_subject(code)[index % self.entries_per_subject])
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def info(self) -> dict:
        metadata = self.metadata if self.kind == "theorem" else self.problem_metadata
        result = {
            "name": "Lemma Lottery",
            "version": "1.1.0",
            "subject_count": len(self._subjects),
            f"{self.kind}_count": len(self._subjects) * self.entries_per_subject,
            f"{self.kind}s_per_subject": self.entries_per_subject,
            "selection_policy": metadata["selection_policy"],
            "taxonomy_source": self.metadata["taxonomy_source"],
            "taxonomy_checked_on": self.metadata["taxonomy_checked_on"],
        }
        if self.kind == "problem":
            result["status_reviewed_on"] = self.problem_metadata["status_reviewed_on"]
        return result

    def validate(self) -> dict:
        expected_files = {f"{code}.json" for code in self._subjects}
        try:
            actual_files = {
                path.name
                for path in (self.directory / self.entry_directory).iterdir()
                if path.is_file() and path.name.endswith(".json")
            }
        except (OSError, ValueError) as error:
            raise CatalogError(f"Cannot scan {self.kind} database directory: {error}") from error
        if actual_files != expected_files:
            raise CatalogError(
                f"Unexpected {self.kind} files; missing={sorted(expected_files - actual_files)}, "
                f"extra={sorted(actual_files - expected_files)}"
            )
        for subject in self._subjects:
            self._load_subject(subject)
        return {
            "status": "ok",
            "subject_count": len(self._subjects),
            f"{self.kind}_count": len(self._subjects) * self.entries_per_subject,
        }
