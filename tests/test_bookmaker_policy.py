import pytest

from h2h.domain.bookmaker_policy import (
    SUPPORTED_BOOKMAKERS,
    UnsupportedBookmakerError,
    is_supported_bookmaker,
    normalize_bookmaker_id,
    require_supported_bookmaker,
)


def test_allowlist_contains_only_approved_bookmakers() -> None:
    assert SUPPORTED_BOOKMAKERS == frozenset({"superbet", "1xbet", "bet365"})


@pytest.mark.parametrize("bookmaker_id", ["superbet", "1xbet", "bet365", " SUPERBET ", "Bet365"])
def test_supported_bookmakers_are_case_and_whitespace_insensitive(bookmaker_id: str) -> None:
    assert is_supported_bookmaker(bookmaker_id)
    assert require_supported_bookmaker(bookmaker_id) in SUPPORTED_BOOKMAKERS


@pytest.mark.parametrize("bookmaker_id", ["pinnacle", "unibet", "", "   "])
def test_unsupported_or_empty_bookmakers_are_rejected(bookmaker_id: str) -> None:
    if not bookmaker_id.strip():
        with pytest.raises(ValueError, match="must not be empty"):
            require_supported_bookmaker(bookmaker_id)
    else:
        with pytest.raises(UnsupportedBookmakerError, match="unsupported bookmaker"):
            require_supported_bookmaker(bookmaker_id)


def test_non_string_identifier_is_rejected() -> None:
    with pytest.raises(TypeError, match="must be a string"):
        normalize_bookmaker_id(365)  # type: ignore[arg-type]
