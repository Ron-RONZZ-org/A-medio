"""Test isolation for A-medio — prevents writes to real filesystem/keyring."""

from __future__ import annotations

import pytest
from A.core.testing import patch_paths


@pytest.fixture(autouse=True)
def isolate_medio(monkeypatch, tmp_path):
    """Isolate data_dir to tmp_path and mock keyring access."""
    import A_medio.data.storage as storage_module
    import A_medio.services.youtube._strategy as strategy_module

    # Redirect all A-core paths via A_DIR env var
    patch_paths(monkeypatch, tmp_path)

    # _strategy.py does `from A.core.paths import data_dir` → local ref
    monkeypatch.setattr(strategy_module, "data_dir", lambda: tmp_path)
    monkeypatch.setattr("A.core.ai.save_api_key", lambda key, **kw: True)
    monkeypatch.setattr("A.core.ai.get_api_key", lambda **kw: "mock-key")
