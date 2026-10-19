"""The preserved CornerLab runtime, with retired lab execution hard-disabled."""
from __future__ import annotations

import os


def configure_corner_only() -> None:
    for lab in ('GOAL', 'H2H', 'CARD'):
        os.environ[f'QUANTBET_QUANTLAB_{lab}_ENABLED'] = 'false'
    os.environ['QUANTBET_QUANTLAB_CORNER_ENABLED'] = 'true'
    os.environ['QUANTBET_QUANTLAB_GOAL_PICK_AUTHORITY'] = 'false'
    os.environ['QUANTBET_QUANTLAB_INLINE_GOAL_VALIDATION'] = 'false'
    os.environ['QUANTBET_QUANTLAB_INLINE_RESEARCH_AUDITS'] = 'false'


def main() -> None:
    configure_corner_only()
    from h2h.quantlab.collector_entrypoint import main as collect
    collect()


if __name__ == '__main__':
    main()
