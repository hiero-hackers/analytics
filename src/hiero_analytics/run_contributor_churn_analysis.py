import os
import random
from datetime import datetime, timedelta
import pandas as pd
from hiero_analytics.config.logging import setup_logging
from hiero_analytics.config.paths import ORG, ensure_repo_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_repo_merged_pr_difficulty_graphql
from hiero_analytics.analysis.prs import prs_to_dataframe
from hiero_analytics.analysis.contributor_churn import (
    compute_progression_stats, 
    compute_transition_metrics, 
    run_prediction_analysis
)
from hiero_analytics.domain.labels import DIFFICULTY_LEVELS
from hiero_analytics.plotting.bars import plot_bar
from hiero_analytics.plotting.lines import plot_line

setup_logging()

ORG_NAME = ORG
REPO = "hiero-sdk-python"
short_repo = REPO.split("/")[-1]

def generate_mock_data():
    """Generate mock PR data for testing when no token is present."""
    print("Generating mock data for analysis...")
    data = []
    authors = [f"author_{i}" for i in range(100)]
    
    start_date = datetime(2023, 1, 1)
    
    for author in authors:
        # Determine max level for this mock author
        r = random.random()
        if r < 0.6: # 60% stop at GFI
            max_level_idx = 0
        elif r < 0.85: # 25% reach Beginner
            max_level_idx = 1
        elif r < 0.95: # 10% reach Intermediate
            max_level_idx = 2
        else: # 5% reach Advanced
            max_level_idx = 3
            
        current_date = start_date + timedelta(days=random.randint(0, 300))
        
        # Always start with GFI
        levels_to_achieve = list(range(max_level_idx + 1))
        
        for l_idx in levels_to_achieve:
            level_name = DIFFICULTY_LEVELS[l_idx].name
            num_prs = random.randint(1, 4) if l_idx == max_level_idx else 1
            for _ in range(num_prs):
                data.append({
                    "author": author,
                    "pr_merged_at": current_date,
                    "level": level_name,
                    "issue_labels": list(DIFFICULTY_LEVELS[l_idx].labels),
                    "pr_number": random.randint(1, 10000)
                })
                current_date += timedelta(days=random.randint(1, 30))
                
    return pd.DataFrame(data)

def get_contributor_level(labels: set[str]) -> str:
    """Classify PR difficulty level based on labels."""
    for spec in reversed(DIFFICULTY_LEVELS): # advanced, intermediate, beginner, gfi
        if spec.matches(labels):
            return spec.name
    return "Unknown"

def run():
    repo_data_dir, repo_charts_dir = ensure_repo_dirs(f"{ORG_NAME}/{REPO}")

    if not os.getenv("GITHUB_TOKEN"):
        print("GITHUB_TOKEN not set. Using mock data.")
        df = generate_mock_data()
    else:
        client = GitHubClient()
        print(f"Fetching PR data for {ORG_NAME}/{REPO}...")
        prs = fetch_repo_merged_pr_difficulty_graphql(
            client,
            owner=ORG_NAME,
            repo=REPO,
            use_cache=True
        )
        
        df = prs_to_dataframe(prs)
        if df.empty:
            print("No PR data found. Using mock data.")
            df = generate_mock_data()
        else:
            df["level"] = df["issue_labels"].apply(lambda labels: get_contributor_level(set(labels or [])))
    
    df = df.dropna(subset=["author", "pr_merged_at"]).sort_values(["author", "pr_merged_at"])
    
    # Core analysis logic moved to hiero_analytics.analysis.contributor_churn
    progression = compute_progression_stats(df)
    
    # Filter to GFI starters
    gfi_starters = progression[progression["start_level"] == "Good First Issue"].copy()
    total_gfi = len(gfi_starters)
    
    if total_gfi == 0:
        print("No GFI starters found.")
        return

    # Stats Summary
    reached_beginner = len(gfi_starters[gfi_starters["max_level"].isin(["Beginner", "Intermediate", "Advanced"])])
    reached_intermediate = len(gfi_starters[gfi_starters["max_level"].isin(["Intermediate", "Advanced"])])
    reached_advanced = len(gfi_starters[gfi_starters["max_level"] == "Advanced"])
    
    funnel_df = pd.DataFrame([
        {"stage": "GFI Starters", "count": total_gfi},
        {"stage": "Progressed to Beginner+", "count": reached_beginner},
        {"stage": "Progressed to Intermediate+", "count": reached_intermediate},
        {"stage": "Progressed to Advanced", "count": reached_advanced},
    ])

    print("\n--- Contributor Churn Analysis ---")
    for _, row in funnel_df.iterrows():
        print(f"{row['stage']}: {row['count']} ({row['count']/total_gfi*100:.1f}%)")

    # Transition Metrics
    print("\n--- Level Transition Metrics ---")
    transitions = compute_transition_metrics(df)
    if not transitions.empty:
        print(transitions.to_string(index=False))
    else:
        print("No transitions detected.")

    run_prediction_analysis(gfi_starters)

    # Visualizations using project utilities
    plot_bar(
        df=funnel_df,
        x_col="stage",
        y_col="count",
        title=f"{short_repo}: Contributor Progression Funnel",
        output_path=repo_charts_dir / "contributor_churn_funnel.png"
    )
    
    # Retention Chart - extended range as requested
    max_prs = int(gfi_starters["pr_count"].max()) if not gfi_starters.empty else 10
    retention_rows = []
    for i in range(1, max_prs + 1):
        retention_rows.append({
            "min_prs": i,
            "contributors": len(gfi_starters[gfi_starters["pr_count"] >= i])
        })
    retention_df = pd.DataFrame(retention_rows)
    
    plot_line(
        df=retention_df,
        x_col="min_prs",
        y_col="contributors",
        title=f"{short_repo}: Contributor Retention by PR Count",
        output_path=repo_charts_dir / "contributor_retention.png"
    )

if __name__ == "__main__":
    run()
