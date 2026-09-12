"""Public interface for the Dixon–Coles quantitative model layer."""

from .dixon_coles import DixonColesFitError, DixonColesModel, dixon_coles_tau

__all__ = ["DixonColesFitError", "DixonColesModel", "dixon_coles_tau"]
