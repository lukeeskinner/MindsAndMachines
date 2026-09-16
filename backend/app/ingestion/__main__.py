"""Print a SERVER-ONLY processed-course JSON artifact to stdout."""
import argparse
import asyncio
import json
import sys

from . import IngestionError, process_course


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--title", default="Uploaded course")
    parser.add_argument("--mode", choices=("local", "fake", "bedrock"), default="local")
    args = parser.parse_args()
    try:
        course = asyncio.run(process_course(args.paths, title=args.title, mode=args.mode))
    except IngestionError as exc:
        print(f"Course processing failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(course.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
