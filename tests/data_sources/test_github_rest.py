from unittest.mock import Mock

import hiero_analytics.data_sources.github_rest as github_rest


def test_fetch_org_repos(monkeypatch):

    client = Mock()

    fake_data = [
        {"full_name": "org/repo1"},
        {"full_name": "org/repo2"},
        {"name": "ignored"},
    ]

    client.get.return_value = fake_data

    monkeypatch.setattr(
        github_rest,
        "paginate_page_number",
        lambda f: f(1),
    )

    repos = github_rest.fetch_org_repos(client, "org")

    assert repos == ["org/repo1", "org/repo2"]


def test_fetch_repo_issues_without_label(monkeypatch):

    client = Mock()

    fake_data = [
        {"id": 1},
        {"id": 2},
        "invalid",
    ]

    client.get.return_value = fake_data

    monkeypatch.setattr(
        github_rest,
        "paginate_page_number",
        lambda f: f(1),
    )

    issues = github_rest.fetch_repo_issues(
        client,
        "org/repo",
    )

    assert issues == [{"id": 1}, {"id": 2}]


def test_fetch_repo_issues_with_label(monkeypatch):

    client = Mock()

    fake_data = [{"id": 10}]
    client.get.return_value = fake_data

    monkeypatch.setattr(
        github_rest,
        "paginate_page_number",
        lambda f: f(1),
    )

    github_rest.fetch_repo_issues(
        client,
        "org/repo",
        label="bug",
    )

    called_url = client.get.call_args[0][0]

    assert "labels=bug" in called_url


def test_fetch_repo_issues_filters_invalid(monkeypatch):

    client = Mock()

    fake_data = [
        {"id": 1},
        {"id": 2},
        None,
        "bad",
    ]

    client.get.return_value = fake_data

    monkeypatch.setattr(
        github_rest,
        "paginate_page_number",
        lambda f: f(1),
    )

    issues = github_rest.fetch_repo_issues(client, "org/repo")

    assert issues == [{"id": 1}, {"id": 2}]