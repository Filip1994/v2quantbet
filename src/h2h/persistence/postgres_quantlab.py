"""Compatibility shim. QuantLab persistence lives in h2h.quantlab.repository."""

from h2h.quantlab.repository import PostgreSQLQuantLabRepository

__all__ = ["PostgreSQLQuantLabRepository"]
