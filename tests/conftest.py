"""Test isolation for A-medio — prevents writes to real filesystem/keyring."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_medio(monkeypatch, tmp_path):
    """Isolate data_dir to tmp_path and mock keyring access."""
    import A_medio.data.storage as storage_module

    monkeypatch.setattr(storage_module, "_DATA_DIR", tmp_path)
    monkeypatch.setattr("A_medio.data.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr("A.core.ai.save_api_key", lambda key, **kw: True)
    monkeypatch.setattr("A.core.ai.get_api_key", lambda **kw: "mock-key")
