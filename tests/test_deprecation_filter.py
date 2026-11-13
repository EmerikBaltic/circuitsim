import warnings

import pytest


def test_deprecation_warning_in_circuitsim_raises_error() -> None:
    """Verify pyproject.toml turns circuitsim.* DeprecationWarnings into errors."""
    with pytest.raises(DeprecationWarning, match="test deprecated"):
        warnings.warn_explicit(
            "test deprecated",
            DeprecationWarning,
            "dummy.py",
            1,
            module="circuitsim.x",
        )
