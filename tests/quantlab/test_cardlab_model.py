from h2h.quantlab.card_lab.model import (
    MODEL_NAME,
    MODEL_VERSION,
    total_cards_probability,
)


def test_referee_poisson_over_under_are_complements_on_half_line() -> None:
    over = total_cards_probability(
        referee_card_rate=5.8,
        selection="OVER",
        line=4.5,
    )
    under = total_cards_probability(
        referee_card_rate=5.8,
        selection="UNDER",
        line=4.5,
    )

    assert MODEL_NAME == "Referee card-rate Poisson"
    assert MODEL_VERSION == "CARDLAB_REFEREE_POISSON_V1"
    assert abs((over + under) - 1.0) < 1e-12
    assert over > 0.5


def test_referee_poisson_rejects_non_half_line() -> None:
    try:
        total_cards_probability(
            referee_card_rate=5.8,
            selection="OVER",
            line=5.0,
        )
    except ValueError as exc:
        assert "half-lines" in str(exc)
    else:
        raise AssertionError("whole line must be rejected")
