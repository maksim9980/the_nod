"""Errors shared by the core modules: a leaf module without dependencies."""


class HarnessError(ValueError):
    """The `.nod/harness.toml` manifest does not read or does not pass the checks."""
