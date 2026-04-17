import pandas as pd
from typing import List, Dict, Any
from hiero_analytics.domain.labels import DIFFICULTY_LEVELS

def compute_progression_stats(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute contributor-level progression statistics from PR records.
    Deduplicates PRs to avoid inflation from multiple linked issues.
    Highest difficulty level is chosen if a PR closes multiple issues.
    """
    if df.empty:
        return pd.DataFrame()

    level_order = {spec.name: i for i, spec in enumerate(DIFFICULTY_LEVELS)}
    level_order["Unknown"] = -1

    # One level per PR: highest difficulty across its closing issues.
    # This ensures start_level and levels list are deterministic and not inflated.
    pr_level = (
        df.assign(_rank=df["level"].map(lambda l: level_order.get(l, -1)))
          .sort_values(["author", "pr_merged_at", "_rank"])
          .drop_duplicates(subset=["author", "pr_number"], keep="last")
          .drop(columns="_rank")
    )

    # Progression Analysis
    progression = pr_level.groupby("author").agg({
        "level": list,
        "pr_merged_at": ["min", "max"],
        "pr_number": "nunique"
    })
    progression.columns = ["levels", "first_seen", "last_seen", "pr_count"]
    
    progression["max_level"] = progression["levels"].apply(
        lambda lvls: max(lvls, key=lambda l: level_order.get(l, -1))
    )
    progression["start_level"] = progression["levels"].apply(lambda lvls: lvls[0])
    progression["tenure_days"] = (progression["last_seen"] - progression["first_seen"]).dt.days
    
    # Calculate early activity (first 30 days) to avoid data leakage in predictions
    early_window = pd.Timedelta(days=30)
    
    # Join first_seen back to deduplicated pr_level
    df_with_start = pr_level.merge(progression[["first_seen"]], on="author")
    early_prs = df_with_start[df_with_start["pr_merged_at"] <= df_with_start["first_seen"] + early_window]
    
    early_stats = early_prs.groupby("author").agg({"pr_number": "nunique"}).rename(columns={"pr_number": "early_pr_count"})
    progression = progression.join(early_stats).fillna({"early_pr_count": 0})
    
    return progression

def compute_transition_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute transition metrics between difficulty levels.
    Deduplicates PRs to avoid spurious intra-PR transitions.
    """
    if df.empty:
        return pd.DataFrame()

    level_order = {spec.name: i for i, spec in enumerate(DIFFICULTY_LEVELS)}
    level_order["Unknown"] = -1

    # Deduplicate to one level per PR (highest difficulty) before walking transitions
    df_sorted = (
        df.assign(_rank=df["level"].map(lambda l: level_order.get(l, -1)))
          .sort_values(["author", "pr_merged_at", "_rank"])
          .drop_duplicates(subset=["author", "pr_number"], keep="last")
          .sort_values(["author", "pr_merged_at"])
    )
    
    transitions = []
    for author, group in df_sorted.groupby("author"):
        levels = group["level"].tolist()
        last_level = None
        
        for level in levels:
            if level != last_level:
                if last_level is not None:
                    transitions.append({"from": last_level, "to": level})
                last_level = level
                
    if not transitions:
        return pd.DataFrame(columns=["from", "to", "count"])
        
    trans_df = pd.DataFrame(transitions)
    counts = trans_df.groupby(["from", "to"]).size().reset_index(name="count")
    return counts

def run_prediction_analysis(df: pd.DataFrame):
    """
    Prediction analysis using features from early behavior to avoid leakage.
    Target: reached 'Advanced' level.
    """
    print("\n--- ML Prediction Analysis (80/20 Split) ---")
    
    if df.empty:
        print("No data for prediction.")
        return

    # target: reached advanced
    df["is_advanced"] = (df["max_level"] == "Advanced").astype(int)
    
    # Shuffle and split
    df_split = df.sample(frac=1, random_state=42).reset_index(drop=True)
    split_idx = int(len(df_split) * 0.8)
    train_df = df_split.iloc[:split_idx]
    test_df = df_split.iloc[split_idx:].copy()
    
    # Simple characteristic-based prediction using EARLY behaviors:
    # If they did more than 1 PR in their first 30 days, predict progression to Advanced
    # This avoids using total tenure or total PR count which leaks the outcome.
    def predict(row):
        return 1 if row["early_pr_count"] > 1 else 0
    
    test_df["prediction"] = test_df.apply(predict, axis=1)
    
    accuracy = (test_df["prediction"] == test_df["is_advanced"]).mean()
    print(f"Training set size: {len(train_df)}")
    print(f"Test set size: {len(test_df)}")
    print(f"Prediction Accuracy (using features from first 30 days): {accuracy:.2f}")
