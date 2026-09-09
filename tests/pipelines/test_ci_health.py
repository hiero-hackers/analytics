"""Tests for the workflow security pipeline."""

from unittest.mock import Mock

import pandas as pd

from hiero_analytics.analysis.ci_health_types import CheckResult
from hiero_analytics.data_sources.github_ingest.ci_health import CIHealthRecord
from hiero_analytics.pipelines import ci_health


def test_main_collects_unpinned_actions_and_missing_permissions_and_saves_results(
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

    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

jobs:
  build:
    steps:
      - uses: actions/checkout@v4
""",
        }
    ]

    record = CIHealthRecord(
        workflows=workflows,
        has_wiki_enabled=False,
        has_issues_enabled=True,
        has_discussions_enabled=False,
        has_projects_enabled=False,
        web_commit_signoff_required=False,
    )

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
        "fetch_repo_ci_health_graphql",
        lambda _, __, ___: record,
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
    monkeypatch.setattr(
        ci_health,
        "check_explicit_permissions",
        lambda _: CheckResult(
            check="explicit_permissions",
            band="permissions",
            status="fail",
            evidence=("Found 1 workflow(s) without an explicit permissions declaration: build.yml"),
            location=".github/workflows/build.yml",
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
            },
            {
                "repo": "hiero-ledger/hiero-sdk-java",
                "check": "explicit_permissions",
                "band": "permissions",
                "status": "fail",
                "evidence": ("Found 1 workflow(s) without an explicit permissions declaration: build.yml"),
                "location": ".github/workflows/build.yml",
            },
        ]
    )

    pd.testing.assert_frame_equal(saved_df, expected)


def test_main_saves_passing_results_when_all_checks_pass(
    monkeypatch,
    tmp_path,
) -> None:
    """Test that passing checks still produce result rows."""
    client = Mock()
    data_dir = tmp_path

    repo = Mock()
    repo.owner = "hiero-ledger"
    repo.name = "hiero-sdk-java"
    repo.full_name = "hiero-ledger/hiero-sdk-java"

    workflows = [
        {
            "name": "build.yml",
            "text": """name: CI

permissions:
  contents: read

jobs:
  build:
    steps:
      - uses: actions/checkout@0123456789abcdef0123456789abcdef01234567
""",
        }
    ]

    record = CIHealthRecord(
        workflows=workflows,
        has_wiki_enabled=False,
        has_issues_enabled=True,
        has_discussions_enabled=False,
        has_projects_enabled=False,
        web_commit_signoff_required=True,
    )

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
        "fetch_repo_ci_health_graphql",
        lambda _, __, ___: record,
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
    monkeypatch.setattr(
        ci_health,
        "check_explicit_permissions",
        lambda _: CheckResult(
            check="explicit_permissions",
            band="permissions",
            status="pass",
            evidence=("All 1 workflow(s) explicitly declare GitHub Actions permissions."),
            location=".github/workflows/build.yml:3",
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
            },
            {
                "repo": "hiero-ledger/hiero-sdk-java",
                "check": "explicit_permissions",
                "band": "permissions",
                "status": "pass",
                "evidence": ("All 1 workflow(s) explicitly declare GitHub Actions permissions."),
                "location": ".github/workflows/build.yml:3",
            },
        ]
    )

    pd.testing.assert_frame_equal(saved_df, expected)
