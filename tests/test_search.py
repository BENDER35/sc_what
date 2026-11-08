from __future__ import annotations

import pytest

import group_finder
from group_finder import (
    PLATFORMS,
    SearchReport,
    build_parser,
    merge_platform_result,
    run_search,
    search_platform,
)


class FakeDDGS:
    calls = 0

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs

    def __enter__(self) -> FakeDDGS:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def text(self, *args: object, **kwargs: object) -> list[dict[str, str]]:
        FakeDDGS.calls += 1
        if FakeDDGS.calls == 1:
            raise group_finder.RatelimitException("rate limit")
        return [{"title": "ok", "href": "https://t.me/sc_what_test_only", "body": ""}]


def test_run_search_retries_after_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeDDGS.calls = 0
    monkeypatch.setattr(group_finder, "DDGS", FakeDDGS)
    monkeypatch.setattr(group_finder.time, "sleep", lambda _: None)

    args = build_parser().parse_args(["python", "--retries", "1", "--delay", "0"])
    results = run_search('site:t.me "python"', 1, args)
    assert results[0]["title"] == "ok"
    assert FakeDDGS.calls == 2


def test_search_platform_extracts_and_merges(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_run_search(query: str, page: int, args: object) -> list[dict[str, str]]:
        return [
            {
                "title": "Grupo de Python",
                "href": "https://ejemplo.com/grupos",
                "body": "Únete en https://t.me/+0000000000000000",
            },
            {
                "title": "Otro resultado",
                "href": "https://ejemplo.com/otro",
                "body": "También https://t.me/+0000000000000000",
            },
        ]

    monkeypatch.setattr(group_finder, "run_search", fake_run_search)
    args = build_parser().parse_args(["python", "-p", "telegram"])
    result = search_platform(PLATFORMS["telegram"], "python", args, None)

    assert result.error is None
    assert len(result.items) == 1
    assert result.items[0].link == "https://t.me/+0000000000000000"
    assert result.items[0].queries == ["python"]
    assert "https://ejemplo.com/grupos" in result.source_pages
    assert "https://ejemplo.com/otro" in result.source_pages


def test_merge_platform_result_deduplicates() -> None:
    from group_finder import GroupLink, PlatformResult

    report = SearchReport(results={"telegram": []})
    first = PlatformResult(
        key="telegram",
        items=[
            GroupLink(
                platform="telegram",
                title="",
                link="https://t.me/sc_what_test_only",
                queries=["python"],
            )
        ],
    )
    second = PlatformResult(
        key="telegram",
        items=[
            GroupLink(
                platform="telegram",
                title="Python",
                link="https://t.me/sc_what_test_only",
                description="Comunidad",
                queries=["gaming"],
            )
        ],
    )
    merge_platform_result(report, first)
    merge_platform_result(report, second)

    assert len(report.results["telegram"]) == 1
    item = report.results["telegram"][0]
    assert item.title == "Python"
    assert item.description == "Comunidad"
    assert item.queries == ["python", "gaming"]


def test_search_platform_reports_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> list[dict[str, str]]:
        raise RuntimeError("fallo de red")

    monkeypatch.setattr(group_finder, "run_search", boom)
    args = build_parser().parse_args(["python", "-p", "telegram"])
    result = search_platform(PLATFORMS["telegram"], "python", args, None)
    assert result.error is not None
    assert "fallo de red" in result.error
