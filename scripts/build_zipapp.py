"""Build the single-file application using only the Python standard library."""

import shutil
import tempfile
import zipapp
from pathlib import Path

root = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory() as temporary:
    staging = Path(temporary)
    shutil.copytree(
        root / "theorem_catalog",
        staging / "theorem_catalog",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (staging / "__main__.py").write_text(
        "from theorem_catalog.cli import main\nraise SystemExit(main())\n",
        encoding="utf-8",
    )
    zipapp.create_archive(
        staging,
        target=root / "lemma-lottery.pyz",
        interpreter="/usr/bin/env python3",
        compressed=True,
    )
