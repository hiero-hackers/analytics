import os
import pandas as pd
from hiero_analytics.config.logging import setup_logging
from hiero_analytics.config.paths import ORG, ensure_repo_dirs
from hiero_analytics.data_sources.github_client import GitHubClient
from hiero_analytics.data_sources.github_ingest import fetch_repo_merged_pr_difficulty_graphql
from hiero_analytics.analysis.prs import prs_to_dataframe, first_time_contributors
from hiero_analytics.domain.labels import DIFFICULTY_LEVELS
from hiero_analytics.plotting.bars import plot_bar
from hiero_analytics.plotting.lines import plot_line

setup_logging()

ORG_NAME = ORG
REPO = "hiero-sdk-python"
short_repo = REPO.split("/")[-1]

def get_contributor_level(labels: set[str]) -> str:
    """Classify PR difficulty level based on labels."""
    for spec in reversed(DIFFICULTY_LEVELS): # advanced, intermediate, beginner, gfi
        if spec.matches(labels):
            return spec.name
    return "Unknown"

def run_prediction_analysis(df):
    """Simple prediction analysis using 80/20 split as requested."""
    print("\n--- ML Prediction Analysis (80/20 Split) ---")
    
    # Feature engineering: characteristics of contributors
    # target: reached advanced
    df["is_advanced"] = (df["max_level"] == "Advanced").astype(int)
    
    # Shuffle and split
    df = df.sample(frac=1, random_state=42).reset_index(drop=True)
    split_idx = int(len(df) * 0.8)
    train_df = df.iloc[:split_idx]
    test_df = df.iloc[split_idx:].copy()
    
    # Simple characteristic-based prediction: 
    # If they have high PR count and stay active for > 60 days, predict Advanced
    def predict(row):
        return 1 if row["pr_count"] > 3 and row["tenure_days"] > 60 else 0
    
    test_df["prediction"] = test_df.apply(predict, axis=1)
    
    accuracy = (test_df["prediction"] == test_df["is_advanced"]).mean()
    print(f"Training set size: {len(train_df)}")
    print(f"Test set size: {len(test_df)}")
    print(f"Prediction Accuracy (based on early characteristics): {accuracy:.2f}")

def run():
    repo_data_dir, repo_charts_dir = ensure_repo_dirs(f"{ORG_NAME}/{REPO}")

    if not os.getenv("GITHUB_TOKEN"):
        raise RuntimeError("no github token, exiting data fetch as it will exceed api limits")

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
        print("No PR data found.")
        return

    df["level"] = df["issue_labels"].apply(lambda labels: get_contributor_level(set(labels or [])))
    df = df.dropna(subset=["author", "pr_merged_at"]).sort_values(["author", "pr_merged_at"])
    
    # Progression Analysis
    progression = df.groupby("author").agg({
        "level": list,
        "pr_merged_at": ["min", "max", "count"]
    })
    progression.columns = ["levels", "first_seen", "last_seen", "pr_count"]
    
    level_order = {spec.name: i for i, spec in enumerate(DIFFICULTY_LEVELS)}
    level_order["Unknown"] = -1
    
    progression["max_level"] = progression["levels"].apply(lambda lvls: max(lvls, key=lambda l: level_order.get(l, -1)))
    progression["start_level"] = progression["levels"].apply(lambda lvls: lvls[0])
    progression["tenure_days"] = (progression["last_seen"] - progression["first_seen"]).dt.days
    
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

    run_prediction_analysis(gfi_starters)

    # Visualizations using project utilities
    plot_bar(
        df=funnel_df,
        x_col="stage",
        y_col="count",
        title=f"{short_repo}: Contributor Progression Funnel",
        output_path=repo_charts_dir / "contributor_churn_funnel.png"
    )
    
    # Retention Chart
    retention_rows = []
    for i in range(1, 11):
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
