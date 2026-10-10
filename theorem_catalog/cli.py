"""A small JSON command interface for local AI agents and humans."""

import argparse
import json
import sys

from theorem_catalog.catalog import Catalog, CatalogError


class JsonArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise CatalogError(message, "invalid_query")


def parser() -> argparse.ArgumentParser:
    shared = argparse.ArgumentParser(add_help=False)
    shared.add_argument(
        "--pretty", action="store_true", default=argparse.SUPPRESS, help="Indent JSON output"
    )
    shared.add_argument(
        "--kind",
        choices=("theorem", "problem"),
        default=argparse.SUPPRESS,
        help="Choose the theorem or open problem database (default: theorem)",
    )
    root = JsonArgumentParser(
        description=(
            "Get a theorem or open problem locally as JSON. "
            "No server, network, or dependencies needed."
        ),
        parents=[shared],
    )
    commands = root.add_subparsers(dest="command")
    random = commands.add_parser("random", parents=[shared], help="Get a random entry")
    random.add_argument("--subject", help="Exact arXiv code, for example math.NT")
    commands.add_parser("subjects", parents=[shared], help="List all 32 subject codes and labels")
    listing = commands.add_parser("list", parents=[shared], help="Browse entries")
    listing.add_argument("--subject", help="Filter by exact arXiv code")
    listing.add_argument("--limit", type=int, default=20, help="Page size: 1..100 (default: 20)")
    listing.add_argument("--offset", type=int, default=0, help="Nonnegative starting index")
    get = commands.add_parser("get", parents=[shared], help="Get an entry by stable ID")
    get.add_argument("id", help="For example math.NT.01 or math.NT.open.01 with --kind problem")
    commands.add_parser("info", parents=[shared], help="Database metadata and curation policy")
    commands.add_parser("validate", parents=[shared], help="Validate the selected database")
    return root


def main(argv: list[str] | None = None) -> int:
    try:
        args = parser().parse_args(argv)
        catalog = Catalog(kind=getattr(args, "kind", "theorem"))
        command = args.command or "random"
        if command == "random":
            result = catalog.random(getattr(args, "subject", None))
        elif command == "subjects":
            result = catalog.subjects()
        elif command == "list":
            result = catalog.list(args.subject, args.limit, args.offset)
        elif command == "get":
            result = catalog.get(args.id)
        elif command == "info":
            result = catalog.info()
        else:
            result = catalog.validate()
        print(
            json.dumps(
                result, ensure_ascii=True, indent=2 if getattr(args, "pretty", False) else None
            )
        )
        return 0
    except CatalogError as error:
        print(json.dumps({"error": {"code": error.code, "message": str(error)}}), file=sys.stderr)
        return 1 if error.code == "invalid_database" else 2
    except BrokenPipeError:
        # A downstream command may stop after reading its first result.
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
