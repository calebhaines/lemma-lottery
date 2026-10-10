# Lemma Lottery 🎲

[![Checks](https://github.com/calebhaines/lemma-lottery/actions/workflows/checks.yml/badge.svg)](https://github.com/calebhaines/lemma-lottery/actions/workflows/checks.yml)

*A little mathematical serendipity for AI agents.*

Lemma Lottery is a tiny, offline **mathematical inspiration tool for AI agents**.
It offers random encounters with classic mathematical results, served as JSON.

The bundled finite database has **640 curated theorem entries: exactly 20 for
each of arXiv's 32 mathematics subjects**. Requires Python 3.10 or newer, with
**zero runtime dependencies**. All the excitement of mathematical roulette,
with substantially less financial ruin.

## Take a spin

Download [lemma-lottery.pyz](https://github.com/calebhaines/lemma-lottery/raw/refs/heads/main/lemma-lottery.pyz)
and run it with Python:

```bash
# Random theorem from the whole database
python lemma-lottery.pyz

# Random theorem from Number Theory
python lemma-lottery.pyz random --subject math.NT

# Discover all arXiv subject codes and labels
python lemma-lottery.pyz subjects
```

No installation, server, network connection, or API key is needed. The `.pyz`
file contains the code and the complete database. Use its absolute path to run
it from any directory. Source users can substitute `python theorem.py` or
`python -m theorem_catalog` for `python lemma-lottery.pyz`.

## Commands

| Command | Result |
| --- | --- |
| No arguments, or `random` | One uniformly random theorem |
| `random --subject math.NT` | One random theorem from that subject's 20 entries |
| `subjects` | All 32 official subject codes, labels, and counts |
| `list --subject math.NT` | All 20 entries in a subject |
| `list --limit 100 --offset 100` | A page from the whole database |
| `get math.NT.01` | One theorem by stable ID |
| `info` | Database size, taxonomy source, and editorial policy |
| `validate` | Check all subjects and theorem records |
| `--help` | Human-readable command help |

Successful commands print one JSON value to stdout with no logs. Add `--pretty`
for indented JSON. Each theorem has this structure:

```json
{
  "id": "math.NT.01",
  "subject": "math.NT",
  "name": "Euclid’s theorem on primes",
  "statement": "There are infinitely many prime numbers.",
  "references": [
    {"title": "Euclid’s theorem on primes", "url": "https://en.wikipedia.org/wiki/Euclid's_theorem"}
  ]
}
```

`list` returns an object with `total`, `limit`, `offset`, and `items`.
The limit must be 1..100; the offset must be nonnegative. Offsets beyond the end
produce an empty `items` array. Subject codes are case-sensitive and exact; use
`math.NT` rather than a free-text topic.

Errors print a JSON object to stderr, leave stdout empty, and exit nonzero:

```json
{"error": {"code": "unknown_subject", "message": "Unknown subject 'math.XX'. Run 'subjects' for valid arXiv math codes."}}
```

Exit codes: `0` success, `2` invalid query/unknown subject/unknown theorem, `1`
invalid or unreadable database. Errors do not print Python tracebacks.

## Python interfaces

Example CLI call from Python:

```python
import json
import subprocess
import sys

result = subprocess.run(
    [sys.executable, "/absolute/path/lemma-lottery.pyz", "random", "--subject", "math.NT"],
    capture_output=True,
    text=True,
    check=True,
)
theorem = json.loads(result.stdout)
```

Source users can also call the library directly and reuse a catalogue:

```python
from theorem_catalog import Catalog

catalog = Catalog()
theorem = catalog.random("math.NT")
another = catalog.random()
```

Random queries load only one small subject file. Unfiltered queries choose a
subject uniformly, then a theorem uniformly; since every subject has 20 entries,
this is uniform across all 640 category-specific entries. Repeated results are
possible because each query is independent. Results shared by multiple subjects
have a distinct entry and ID in each subject.

## Dataset

Codes and labels match the [official arXiv taxonomy](https://arxiv.org/category_taxonomy),
checked on 2026-10-10. This includes `math.IT`, an alias of `cs.IT`, and `math.MP`,
an alias of `math-ph`.

The 20 results per subject are curated foundational or influential theorems,
rather than an official arXiv ranking or a universal consensus. Standard proved
lemmas and other foundational results are included. General mathematics covers
accessible foundations; history and overview covers historical milestones and
recreational results. These categories have no single specialist theorem
syllabus. Cross-subject overlap is intentional.

Each entry includes a concise statement with essential hypotheses and specific
references for further reading. These are educational summaries rather than
proofs or formal machine-checked statements. Reference pages are never fetched
at runtime. No theorem is generated dynamically, and unresolved conjectures
are excluded.

The source database lives in `theorem_catalog/data/subjects.json` and
`theorem_catalog/data/theorems/math.XX.json`. Each subject has IDs `math.XX.01`
through `math.XX.20`. `validate` checks subject coverage, file counts, record
counts, unique IDs and names within a subject, subject assignments, nonempty
statements, and valid reference URL syntax. Each queried subject is also
validated when loaded. Keep existing IDs stable when revising the database.

## Development and optional installation

Everything below works with the Python standard library:

```bash
python -m unittest discover -s tests -v
python theorem.py validate
python scripts/build_zipapp.py
python lemma-lottery.pyz validate
```

Tests cover all 32 categories and counts, random selection from the correct
pool, lazy loading, pagination, stable retrieval, JSON errors, and corrupt data.

Optionally install the `theorem` command in your Python environment:

```bash
python -m pip install .
theorem random --subject math.NT
```

The package includes the database and declares no runtime dependencies. Optional
lint checks use `python -m ruff check theorem_catalog theorem.py scripts tests`.
