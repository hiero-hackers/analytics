"""Tests for the workflow security pipeline."""

from unittest.mock import Mock

import pandas as pd

from hiero_analytics.analysis.ci_health_types import CheckResult
from hiero_analytics.pipelines import ci_health


def test_main_collects_unpinned_actions_and_saves_results(
    monkeypatch,
    tmp_path,
) -> None:
    """Test that workflow security findings are collected and saved."""
    client = Mock()
    data_dir = tmp_path

    repo = Mock()
    repo.owner = "hiero-ledger"
    repo.name = "hiero-sdk-java"
    repo.full_name = "hiero-ledger/hiero-sdk-java"

    monkeypatch.setattr(
        ci_health,
        "org_context",
        lambda _: (client, data_dir, Mock()),
    )
    monkeypatch.setattr(
        ci_health,
        "fetch_org_repos",
        lambda _, __: [repo],
    )
    monkeypatch.setattr(
        ci_health,
        "fetch_repo_workflows_graphql",
        lambda _, __, ___: [
            {
                "name": "build.yml",
                "text": """name: CI

jobs:
  build:
    steps:
      - uses: actions/checkout@v4
""",
            }
        ],
    )
    monkeypatch.setattr(
        ci_health,
        "check_actions_sha_pinned",
        lambda _: CheckResult(
            check="actions_sha_pinned",
            band="actions",
            status="fail",
            evidence=(
                "Found 1 GitHub Actions reference(s) that are not pinned to a full commit SHA: actions/checkout@v4"
            ),
            location=".github/workflows/build.yml:6",
        ),
    )

    save_dataframe = Mock()
    monkeypatch.setattr(ci_health, "save_dataframe", save_dataframe)

    ci_health.main("hiero-ledger")

    save_dataframe.assert_called_once()

    saved_df = save_dataframe.call_args.kwargs["df"]

    expected = pd.DataFrame(
        [
            {
                "repo": "hiero-ledger/hiero-sdk-java",
                "check": "actions_sha_pinned",
                "band": "actions",
                "status": "fail",
                "evidence": (
                    "Found 1 GitHub Actions reference(s) that are not pinned to a full commit SHA: actions/checkout@v4"
                ),
                "location": ".github/workflows/build.yml:6",
            }
        ]
    )

    pd.testing.assert_frame_equal(saved_df, expected)


def test_main_saves_passing_result_when_all_actions_are_pinned(
    monkeypatch,
    tmp_path,
) -> None:
    """Test that a passing check still produces a result row."""
    client = Mock()
    data_dir = tmp_path

    repo = Mock()
    repo.owner = "hiero-ledger"
    repo.name = "hiero-sdk-java"
    repo.full_name = "hiero-ledger/hiero-sdk-java"

    monkeypatch.setattr(
        ci_health,
        "org_context",
        lambda _: (client, data_dir, Mock()),
    )
    monkeypatch.setattr(
        ci_health,
        "fetch_org_repos",
        lambda _, __: [repo],
    )
    monkeypatch.setattr(
        ci_health,
        "fetch_repo_workflows_graphql",
        lambda _, __, ___: [
            {
                "name": "build.yml",
                "text": ("uses: actions/checkout@0123456789abcdef0123456789abcdef01234567"),
            }
        ],
    )
    monkeypatch.setattr(
        ci_health,
        "check_actions_sha_pinned",
        lambda _: CheckResult(
            check="actions_sha_pinned",
            band="actions",
            status="pass",
            evidence="All GitHub Actions are pinned to full commit SHAs.",
            location="",
        ),
    )

    save_dataframe = Mock()
    monkeypatch.setattr(ci_health, "save_dataframe", save_dataframe)

    ci_health.main("hiero-ledger")

    save_dataframe.assert_called_once()

    saved_df = save_dataframe.call_args.kwargs["df"]

    expected = pd.DataFrame(
        [
            {
                "repo": "hiero-ledger/hiero-sdk-java",
                "check": "actions_sha_pinned",
                "band": "actions",
                "status": "pass",
                "evidence": "All GitHub Actions are pinned to full commit SHAs.",
                "location": "",
            }
        ]
    )

    pd.testing.assert_frame_equal(saved_df, expected)
