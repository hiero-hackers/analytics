import os
import requests


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str | None = None):
        token = token or os.getenv("GITHUB_TOKEN")
        self.session = requests.Session()

        if token:
            self.session.headers.update(
                {"Authorization": f"Bearer {token}"}
            )

    def get_issues(self, owner: str, repo: str):
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/issues"
        response = self.session.get(url, params={"state": "all"})
        response.raise_for_status()
        return response.json()