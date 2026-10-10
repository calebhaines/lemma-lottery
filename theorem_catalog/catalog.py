"""Dependency-free access to the finite JSON theorem database."""

import json
import re
import secrets
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlsplit

DATA_DIRECTORY = files("theorem_catalog").joinpath("data")
THEOREMS_PER_SUBJECT = 20
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

    def __init__(self, data_directory=DATA_DIRECTORY):
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
        self._loaded = {}

    def subjects(self) -> list[dict]:
        return [
            {**subject, "theorem_count": THEOREMS_PER_SUBJECT}
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
        entries = read_json(self.directory / "theorems" / f"{subject}.json")
        if not isinstance(entries, list) or len(entries) != THEOREMS_PER_SUBJECT:
            raise CatalogError(f"{subject} must contain exactly 20 theorems.")
        ids = set()
        names = set()
        fields = {"id", "subject", "name", "statement", "references"}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != fields:
                raise CatalogError(f"{subject} contains an invalid theorem object.")
            for field in ("id", "subject", "name", "statement"):
                if not isinstance(entry[field], str) or not entry[field].strip():
                    raise CatalogError(f"{subject} has a missing or empty {field}.")
            if entry["subject"] != subject:
                raise CatalogError(f"A theorem in {subject} has the wrong subject.")
            if entry["id"] in ids or entry["name"].strip().casefold() in names:
                raise CatalogError(f"{subject} contains duplicate theorem IDs or names.")
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
        expected_ids = {f"{subject}.{number:02d}" for number in range(1, 21)}
        if ids != expected_ids:
            raise CatalogError(f"{subject} must have IDs {subject}.01 through {subject}.20.")
        self._loaded[subject] = entries
        return entries

    def random(self, subject: str | None = None) -> dict:
        # Equal-size subjects: a uniform subject followed by a uniform entry
        # is uniform over all 640 entries, while reading just one small file.
        if subject is None:
            subject = secrets.choice(tuple(self._subjects))
        return secrets.choice(self._load_subject(subject))

    def get(self, theorem_id: str) -> dict:
        if not re.fullmatch(r"math\.[A-Z]{2}\.(?:0[1-9]|1[0-9]|20)", theorem_id):
            raise CatalogError(f"Unknown theorem ID '{theorem_id}'.", "unknown_theorem")
        subject = theorem_id.rsplit(".", 1)[0]
        if subject not in self._subjects:
            raise CatalogError(f"Unknown theorem ID '{theorem_id}'.", "unknown_theorem")
        return next(entry for entry in self._load_subject(subject) if entry["id"] == theorem_id)

    def list(self, subject: str | None = None, limit: int = 20, offset: int = 0) -> dict:
        if not 1 <= limit <= 100 or offset < 0:
            raise CatalogError(
                "limit must be 1..100 and offset must be nonnegative.", "invalid_query"
            )
        if subject is not None:
            self._check_subject(subject)
        codes = [subject] if subject is not None else list(self._subjects)
        total = len(codes) * THEOREMS_PER_SUBJECT
        items = []
        # Only read files that intersect the requested page.
        for index in range(offset, min(offset + limit, total)):
            code = codes[index // THEOREMS_PER_SUBJECT]
            items.append(self._load_subject(code)[index % THEOREMS_PER_SUBJECT])
        return {"total": total, "limit": limit, "offset": offset, "items": items}

    def info(self) -> dict:
        return {
            "name": "Lemma Lottery",
            "version": "1.0.0",
            "subject_count": len(self._subjects),
            "theorem_count": len(self._subjects) * THEOREMS_PER_SUBJECT,
            "theorems_per_subject": THEOREMS_PER_SUBJECT,
            "selection_policy": self.metadata["selection_policy"],
            "taxonomy_source": self.metadata["taxonomy_source"],
            "taxonomy_checked_on": self.metadata["taxonomy_checked_on"],
        }

    def validate(self) -> dict:
        expected_files = {f"{code}.json" for code in self._subjects}
        try:
            actual_files = {
                path.name
                for path in (self.directory / "theorems").iterdir()
                if path.is_file() and path.name.endswith(".json")
            }
        except (OSError, ValueError) as error:
            raise CatalogError(f"Cannot scan theorem database directory: {error}") from error
        if actual_files != expected_files:
            raise CatalogError(
                f"Unexpected theorem files; missing={sorted(expected_files - actual_files)}, "
                f"extra={sorted(actual_files - expected_files)}"
            )
        for subject in self._subjects:
            self._load_subject(subject)
        return {"status": "ok", "subject_count": 32, "theorem_count": 640}
