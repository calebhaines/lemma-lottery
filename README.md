# Lemma Lottery 🎲

[![Checks](https://github.com/calebhaines/lemma-lottery/actions/workflows/checks.yml/badge.svg)](https://github.com/calebhaines/lemma-lottery/actions/workflows/checks.yml)

*A little mathematical serendipity for AI agents.*

Lemma Lottery is a tiny, offline **mathematical inspiration tool for AI agents**.
It offers random encounters with classic mathematical results and important
open problems, served as JSON.

The bundled finite database has **640 curated theorem entries: exactly 20 for
each of arXiv's 32 mathematics subjects**, plus **320 curated open-problem
entries: exactly 10 per subject**. Requires Python 3.10 or newer, with
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

# Random open problem from the whole database
python lemma-lottery.pyz random --kind problem

# Random open problem from Number Theory's 10 entries
python lemma-lottery.pyz random --kind problem --subject math.NT

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
| `random --kind problem` | One uniformly random open-problem entry |
| `random --kind problem --subject math.NT` | One random open problem from that subject's 10 entries |
| `subjects` | All 32 official subject codes, labels, and counts |
| `list --subject math.NT` | All 20 entries in a subject |
| `list --limit 100 --offset 100` | A page from the whole database |
| `get math.NT.01` | One theorem by stable ID |
| `list --kind problem --subject math.NT` | All 10 open problems in a subject |
| `get --kind problem math.NT.open.01` | One open problem by stable ID |
| `info` | Database size, taxonomy source, and editorial policy |
| `validate` | Check all subjects and theorem records |
| `validate --kind problem` | Check all 32 subjects and 320 open-problem records |
| `--help` | Human-readable command help |

Successful commands print one JSON value to stdout with no logs. Add `--pretty`
for indented JSON. `--kind theorem` (the default) or `--kind problem` selects a
catalog for every command, including `subjects` and `info`. Both `--kind` and
`--pretty` can appear before or after the command. Omitting the command still
selects a random entry, so `python lemma-lottery.pyz --kind problem` works too.
Each theorem has this structure:

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

Open problems also include `importance` (why the question matters),
`status: "open"`, and `status_note` (scope, qualifications, and partial progress).
Their IDs use a separate namespace, such as `math.NT.open.01`, to keep existing
theorem IDs stable. Pass `--kind problem` when retrieving those IDs.

`list` returns an object with `total`, `limit`, `offset`, and `items`.
The limit must be 1..100; the offset must be nonnegative. Offsets beyond the end
produce an empty `items` array. Subject codes are case-sensitive and exact; use
`math.NT` rather than a free-text topic.

Errors print a JSON object to stderr, leave stdout empty, and exit nonzero:

```json
{"error": {"code": "unknown_subject", "message": "Unknown subject 'math.XX'. Run 'subjects' for valid arXiv math codes."}}
```

Exit codes: `0` success, `2` invalid query/unknown subject/unknown entry, `1`
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

problems = Catalog(kind="problem")
problem = problems.random("math.NT")
same_problem = problems.get(problem["id"])
```

Random queries load only one small subject file. Unfiltered queries choose a
subject uniformly, then a theorem uniformly; since every subject has 20 entries,
this is uniform across all 640 category-specific theorem entries. The same
method samples uniformly from the 320 open-problem entries, since each subject
has exactly 10. Repeated results are possible because each query is independent.
Results shared by multiple subjects
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
are excluded from the theorem catalog.

The separate open-problem catalog selects 10 important unresolved questions per
subject. There is no universal ranking of the "most critical" problems; each
entry explains the editorial choice and links to relevant literature. General
Mathematics emphasizes accessible questions, and History and Overview emphasizes
historically influential ones. Cross-subject overlap is intentional: **320 is
the number of category-specific entries**, not a claim that all 320 mathematical
questions are distinct.

Problem statements specify the unresolved version of a question, and status
notes distinguish it from known special cases, counterexamples to stronger
versions, or additional assumptions. Open status reflects an editorial review
of the cited literature dated 2026-10-10 and can change as research advances.
`info --kind problem` reports that review date and the selection policy.
References are bundled for further reading and are never fetched at runtime.

The source database lives in `theorem_catalog/data/subjects.json` and
`theorem_catalog/data/theorems/math.XX.json`. Each subject has IDs `math.XX.01`
through `math.XX.20`. `validate` checks subject coverage, file counts, record
counts, unique IDs and names within a subject, subject assignments, nonempty
statements, and valid reference URL syntax. Each queried subject is also
validated when loaded. Keep existing IDs stable when revising the database.

Open-problem metadata lives in `theorem_catalog/data/open_problems.json`; the
records live in `theorem_catalog/data/open_problems/math.XX.json`, with IDs
`math.XX.open.01` through `math.XX.open.10`. `validate --kind problem` checks the
same structural invariants, the additional fields, and the `open` status value.
Structural validation does not establish the truth or current research status
of a mathematical statement.

## Development and optional installation

Everything below works with the Python standard library:

```bash
python -m unittest discover -s tests -v
python theorem.py validate
python theorem.py validate --kind problem
python scripts/build_zipapp.py
python lemma-lottery.pyz validate
python lemma-lottery.pyz validate --kind problem
```

Tests cover both catalogs' 32 categories and counts, random selection from the
correct pool, lazy loading, pagination, stable retrieval, JSON errors, and corrupt data.

Optionally install the `theorem` command in your Python environment:

```bash
python -m pip install .
theorem random --subject math.NT
```

The package includes the database and declares no runtime dependencies. Optional
lint checks use `python -m ruff check theorem_catalog theorem.py scripts tests`.
