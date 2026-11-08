from __future__ import annotations

import argparse
from argparse import Namespace
from pathlib import Path

import pytest

from group_finder import (
    PLATFORMS,
    build_parser,
    main,
    positive_int,
    resolve_platforms,
    resolve_queries,
    validate_args,
)


def test_parser_defaults() -> None:
    args = build_parser().parse_args(["python"])
    assert args.query == "python"
    assert args.platforms == "all"
    assert args.max_results == 50
    assert args.format == "both"
    assert args.exact is True


def test_positive_int_rejects_zero() -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int("0")


def test_resolve_platforms_all() -> None:
    parser = build_parser()
    args = parser.parse_args(["python"])
    platforms = resolve_platforms(args, parser)
    assert [platform.key for platform in platforms] == list(PLATFORMS)


def test_resolve_platforms_deduplicates_and_rejects_invalid() -> None:
    parser = build_parser()
    args = parser.parse_args(["python", "-p", "telegram,telegram,Discord"])
    platforms = resolve_platforms(args, parser)
    assert [platform.key for platform in platforms] == ["telegram", "discord"]

    bad = parser.parse_args(["python", "-p", "telegram,matrix"])
    with pytest.raises(SystemExit):
        resolve_platforms(bad, parser)


def test_resolve_queries_from_file(tmp_path: Path) -> None:
    path = tmp_path / "queries.txt"
    path.write_text("python\n\n# comentario\ngaming\npython\n", encoding="utf-8")
    parser = build_parser()
    args = parser.parse_args(["--query-file", str(path)])
    assert resolve_queries(args, parser) == ["python", "gaming"]


def test_resolve_queries_requires_query() -> None:
    parser = build_parser()
    args = parser.parse_args([])
    with pytest.raises(SystemExit):
        resolve_queries(args, parser)


def test_validate_args_min_members_requires_validation() -> None:
    parser = build_parser()
    args = parser.parse_args(["python", "--min-members", "10"])
    with pytest.raises(SystemExit):
        validate_args(args, parser)


def test_validate_args_append_and_force_conflict() -> None:
    parser = build_parser()
    args = parser.parse_args(["python", "--append", "--force"])
    with pytest.raises(SystemExit):
        validate_args(args, parser)


def test_dry_run_does_not_touch_network(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--dry-run", "python", "-p", "telegram", "--no-color"])
    assert code == 0
    output = capsys.readouterr().out
    assert "python" in output
    assert "Telegram" in output
    assert "site:t.me" in output


def test_dry_run_without_exact(capsys: pytest.CaptureFixture[str]) -> None:
    code = main(["--dry-run", "--no-exact", "machine learning", "-p", "discord", "--no-color"])
    assert code == 0
    output = capsys.readouterr().out
    assert "machine learning" in output
    assert '"machine learning"' not in output


def test_main_rejects_invalid_platform(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(["python", "-p", "matrix", "--no-color"])


def test_namespace_defaults_for_search() -> None:
    args = build_parser().parse_args(["python"])
    assert isinstance(args, Namespace)
    assert args.pages == 1
    assert args.retries == 3
    assert args.workers == 1
