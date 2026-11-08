from __future__ import annotations

import pytest

from group_finder import (
    PLATFORMS,
    build_query,
    extract_links,
    normalize_url,
    parse_member_count,
)


@pytest.mark.parametrize(
    ("text", "platform", "expected"),
    [
        (
            "https://chat.whatsapp.com/00000000000000000000",
            "whatsapp",
            "https://chat.whatsapp.com/00000000000000000000",
        ),
        (
            "chat.whatsapp.com/00000000000000000000",
            "whatsapp",
            "https://chat.whatsapp.com/00000000000000000000",
        ),
        (
            "https://chat.whatsapp.com/invite/00000000000000000000",
            "whatsapp",
            "https://chat.whatsapp.com/00000000000000000000",
        ),
        (
            "https://signal.group/#CjQKIBabc+/def==",
            "signal",
            "https://signal.group/#CjQKIBabc+/def==",
        ),
        (
            "https://teams.microsoft.com/l/meetup-join/"
            "19%3ameeting_ABC%40thread.v2/0?context=%7b%22Tid%22%3a%22xyz%22%7d",
            "teams",
            "https://teams.microsoft.com/l/meetup-join/"
            "19%3ameeting_ABC%40thread.v2/0?context=%7b%22Tid%22%3a%22xyz%22%7d",
        ),
        (
            "https://teams.live.com/meet/1234567890?p=abc",
            "teams",
            "https://teams.live.com/meet/1234567890?p=abc",
        ),
        (
            "https://discordapp.com/invite/python",
            "discord",
            "https://discord.gg/python",
        ),
        (
            "https://discord.com/invite/python?event=1",
            "discord",
            "https://discord.gg/python",
        ),
        (
            "https://t.me/+0000000000000000",
            "telegram",
            "https://t.me/+0000000000000000",
        ),
        (
            "https://t.me/joinchat/0000000000000000",
            "telegram",
            "https://t.me/+0000000000000000",
        ),
        (
            "https://t.me/sc_what_test_only",
            "telegram",
            "https://t.me/sc_what_test_only",
        ),
        (
            "https://t.me/sc_what_test_only_2",
            "telegram",
            "https://t.me/sc_what_test_only_2",
        ),
    ],
)
def test_extract_links(text: str, platform: str, expected: str) -> None:
    assert expected in extract_links(text, PLATFORMS[platform])


@pytest.mark.parametrize(
    ("text", "platform"),
    [
        ("https://t.me/telegram", "telegram"),
        ("https://t.me/setlanguage/es", "telegram"),
        ("https://t.me/addstickers/foo", "telegram"),
        ("https://t.me/s/python", "telegram"),
        ("https://evil.com/t.me/sc_what_test_only", "telegram"),
        ("https://example.com/chat.whatsapp.com/00000000000000000000", "whatsapp"),
    ],
)
def test_extract_links_rejects_noise(text: str, platform: str) -> None:
    assert extract_links(text, PLATFORMS[platform]) == set()


def test_extract_links_unescapes_html_and_strips_punctuation() -> None:
    found = extract_links(
        "(mira https://t.me/sc_what_test_only?a=1&amp;b=2).", PLATFORMS["telegram"]
    )
    assert found == {"https://t.me/sc_what_test_only"}


def test_normalize_url_rejects_wrong_host() -> None:
    assert (
        normalize_url("https://example.com/t.me/sc_what_test_only", PLATFORMS["telegram"]) is None
    )


def test_build_query_groups_or_branches() -> None:
    query = build_query(PLATFORMS["discord"], "python", exact=True)
    assert query.startswith("((site:discord.gg)")
    assert query.endswith(') "python"')
    assert "(site:discord.com/invite)" in query
    assert "(site:discordapp.com/invite)" in query


def test_build_query_without_exact() -> None:
    query = build_query(PLATFORMS["telegram"], "machine learning", exact=False)
    assert query.endswith(" machine learning")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 234 members", 1234),
        ("12.3K members", 12300),
        ("1,2M subscribers", 1200000),
        ("sin datos", None),
    ],
)
def test_parse_member_count(raw: str, expected: int | None) -> None:
    assert parse_member_count(raw) == expected
