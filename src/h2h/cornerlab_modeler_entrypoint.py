"""Offline fitting for CornerLab only; no provider API calls."""
from h2h.cornerlab_entrypoint import configure_corner_only


def main() -> None:
    configure_corner_only()
    from h2h.quantlab.modeler_entrypoint import main as fit
    fit()


if __name__ == '__main__':
    main()
