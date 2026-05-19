#!/usr/bin/env python3
"""Render LocalPlay Supabase SQL from prefix templates.

This is intentionally local-only. It writes SQL files in the repo but does not
apply them to Supabase.
"""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "sql" / "templates" / "games-schema.template.sql"
ALLOWED_PREFIXES = {"games_", "games_gamma_"}


def render(prefix: str) -> str:
    if prefix not in ALLOWED_PREFIXES:
        allowed = ", ".join(sorted(ALLOWED_PREFIXES))
        raise SystemExit(f"Unsupported prefix {prefix!r}. Allowed: {allowed}")
    return TEMPLATE.read_text().replace("__PREFIX__", prefix)


def main() -> None:
    parser = argparse.ArgumentParser(description="Render LocalPlay Supabase SQL")
    parser.add_argument("--prefix", required=True, choices=sorted(ALLOWED_PREFIXES))
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    output = args.output if args.output.is_absolute() else ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(args.prefix))


if __name__ == "__main__":
    main()
