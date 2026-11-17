"""Usage: python -m analyst "requirement text" [--file req.txt] [--context-dir PATH] [--format json|md] [--out FILE]"""
import argparse
import json
import sys

from analyst.analyzer import analyze, to_markdown


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m analyst", description="Turn a requirement into a structured engineering plan.")
    p.add_argument("requirement", nargs="?", help="Requirement text (or use --file / stdin)")
    p.add_argument("--file", help="Read the requirement from a file")
    p.add_argument("--context-dir", help="Existing codebase to scan (brownfield context)")
    p.add_argument("--format", choices=["json", "md"], default="md")
    p.add_argument("--out", help="Write output to this file instead of stdout")
    args = p.parse_args(argv)

    if args.file:
        text = open(args.file, encoding="utf-8").read()
    elif args.requirement:
        text = args.requirement
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        p.error("provide a requirement, --file, or pipe text on stdin")

    try:
        result = analyze(text, args.context_dir)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    rendered = json.dumps(result.to_dict(), indent=2) if args.format == "json" else to_markdown(result)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(rendered)
    else:
        sys.stdout.buffer.write(rendered.encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
