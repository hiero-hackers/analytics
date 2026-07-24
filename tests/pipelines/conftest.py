"""Shared fixtures for pipeline orchestration tests.

Pipeline tests are integration-style: they stub the fetch layer at the pipeline
module's namespace and assert the output files. The one dependency seam *every*
org/repo pipeline shares is its preamble — ``_shared.org_context`` /
``repo_context`` (GitHub client + ensured output dirs). ``stub_pipeline_context``
centralizes that seam so a rename of it changes this fixture, not every test;
each test still stubs its own pipeline-specific fetches, which legitimately differ.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_pipeline_context(monkeypatch, tmp_path):
    """Redirect a pipeline's preamble to tmp_path with a mock client.

    Returns a callable ``stub(module, *, repo_scoped=False)`` that patches the
    module's ``org_context`` (or ``repo_context``) to hand back a mock client and
    tmp output dirs, and returns ``(client, data_dir, charts_dir)`` for assertions.
    """
    client = MagicMock()
    data_dir = tmp_path / "data"
    charts_dir = tmp_path / "charts"

    def stub(module, *, repo_scoped: bool = False):
        data_dir.mkdir(parents=True, exist_ok=True)
        charts_dir.mkdir(parents=True, exist_ok=True)
        if repo_scoped:
            monkeypatch.setattr(module, "repo_context", lambda _org, _repo: (client, data_dir, charts_dir))
        else:
            monkeypatch.setattr(module, "org_context", lambda _org: (client, data_dir, charts_dir))
        return client, data_dir, charts_dir

    return stub
