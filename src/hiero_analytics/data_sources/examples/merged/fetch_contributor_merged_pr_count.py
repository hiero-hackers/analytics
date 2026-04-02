import os
from dotenv import load_dotenv
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import (
    fetch_repo_contributor_merged_pr_count_graphql,
    fetch_org_contributor_merged_pr_count_graphql,
)
from hiero_analytics.config.logging import setup_logging

def main():
    setup_logging()
    load_dotenv()

    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("Please set GITHUB_TOKEN in your environment or .env file.")
        return

    org = os.getenv("GITHUB_ORG", "hiero-ledger")
    repo = os.getenv("GITHUB_REPO", "hiero-sdk-python")
    user = os.getenv("GITHUB_USER", "userName") # Replace with actual GitHub username

    client = GitHubClient()

    print(f"Fetching merged PR count for {user} in {org}/{repo}...")
    record = fetch_repo_contributor_merged_pr_count_graphql(
        client=client,
        owner=org,
        repo=repo,
        login=user,
        use_cache=False
    )
    
    print("\n--- Result ---")
    print(f"Repository: {record.repo}")
    print(f"Contributor: {record.login}")
    print(f"Merged PR Count: {record.merged_pr_count}")

    print("\n" + "="*40 + "\n")
    
    # --- MULTI REPO EXAMPLE ---
    repos_to_check = [repo, "hiero-sdk-js", "hiero-website", "hiero-sdk-java"]
    print(f"Fetching merged PR counts for {user} across multiple repositories in {org}...")
    
    multi_records = fetch_org_contributor_merged_pr_count_graphql(
        client=client,
        org=org,
        login=user,
        repos=repos_to_check,
        max_workers=3,
        use_cache=False
    )
    
    print("\n--- Multi-Repo Results ---")
    total_merged = 0
    for rec in multi_records:
        print(f"Repository: {rec.repo:<40} -> {rec.merged_pr_count:^4} merged PRs")
        total_merged += rec.merged_pr_count
        
    print(f"{'-'*58}")
    print(f"Total merged PRs across selected repos:  {total_merged}")

if __name__ == "__main__":
    main()
