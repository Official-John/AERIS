"""AERIS core: health monitoring, diagnosis and recovery.

Rule: nothing in this package may import aeris.sim or read fault ground truth.
AERIS sees only what a real aircraft would give it (tests/test_architecture.py checks this).
"""
from .config import AerisConfig
from .monitor import AerisCore

__all__ = ["AerisConfig", "AerisCore"]
