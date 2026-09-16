"""Dependency-free command line interface for model-private-skill."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

from . import capacity, catalog, memory, output_validation
from .delivery import PlanBuildError, build_plan, read_json, render_html, write_json
from .request import InputValidationError, calculate_request, validate_request


def _read_json(path: str) -> Any:
    raw = sys.stdin.read() if path == "-" else Path(path).read_text(encoding="utf-8")
    return json.loads(raw)


def _write_json(payload: Any, path: str, pretty: bool) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2 if pretty else None,
                          separators=None if pretty else (",", ":"))
    if path == "-":
        print(rendered)
    else:
        Path(path).write_text(rendered + "\n", encoding="utf-8")


def _json_command_parser(command: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="model-private-skill " + command)
    parser.add_argument("--input", default="-", help="Input JSON file or - for stdin")
    parser.add_argument("--output", default="-", help="Output JSON file or - for stdout")
    parser.add_argument("--pretty", action="store_true")
    return parser


def _print_help() -> None:
    print(
        "model-private-skill commands:\n"
        "  calculate       Calculate from platform-neutral request JSON\n"
        "  validate-input  Validate request JSON\n"
        "  estimate-memory Run the lower-level memory CLI\n"
        "  gpu             Run GPU catalog validate/filter commands\n"
        "  validate-output Validate final schema 1.5 JSON\n"
        "  build-plan      Assemble validated plan JSON from calculation and enrichment\n"
        "  render-html     Render a validated plan JSON as standalone HTML\n"
        "  capacity-args   Run the lower-level capacity argument CLI"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        _print_help()
        return 0
    command, rest = args[0], args[1:]
    try:
        if command == "calculate":
            parsed = _json_command_parser(command).parse_args(rest)
            _write_json(calculate_request(_read_json(parsed.input)), parsed.output, parsed.pretty)
            return 0
        if command == "validate-input":
            parsed = _json_command_parser(command).parse_args(rest)
            errors = validate_request(_read_json(parsed.input))
            _write_json({"valid": not errors, "errors": errors}, parsed.output, parsed.pretty)
            return 0 if not errors else 1
        if command == "estimate-memory":
            memory.main(rest)
            return 0
        if command == "gpu":
            catalog.main(rest)
            return 0
        if command == "validate-output":
            output_validation.main(rest)
            return 0
        if command == "build-plan":
            parser = argparse.ArgumentParser(prog="model-private-skill build-plan")
            parser.add_argument("--calculation", required=True)
            parser.add_argument("--enrichment", required=True)
            parser.add_argument("--output", required=True)
            parsed = parser.parse_args(rest)
            write_json(build_plan(read_json(parsed.calculation), read_json(parsed.enrichment)), parsed.output)
            return 0
        if command == "render-html":
            parser = argparse.ArgumentParser(prog="model-private-skill render-html")
            parser.add_argument("--input", required=True)
            parser.add_argument("--output", required=True)
            parsed = parser.parse_args(rest)
            Path(parsed.output).write_text(render_html(read_json(parsed.input)), encoding="utf-8")
            return 0
        if command == "capacity-args":
            capacity.main(rest)
            return 0
        raise InputValidationError("unknown command: " + command)
    except (InputValidationError, PlanBuildError, OSError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [str(exc)]}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
