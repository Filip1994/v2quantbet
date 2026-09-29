"""One-shot Railway entrypoint for QuantLab collection and scoring."""

from __future__ import annotations

import os

from h2h.quantlab.entrypoint import main as quantlab_main


def main() -> None:
    os.environ.setdefault("QUANTBET_QUANTLAB_COLLECTOR_ONLY", "true")
    os.environ.setdefault("QUANTBET_QUANTLAB_ONE_SHOT", "true")
    quantlab_main()


if __name__ == "__main__":
    main()
