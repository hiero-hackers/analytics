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
    # Define start_level as the first non-Unknown level to avoid missing GFI starters
    progression["start_level"] = progression["levels"].apply(
        lambda lvls: next((l for l in lvls if l != "Unknown"), lvls[0])
    )
    progression["tenure_days"] = (progression["last_seen"] - progression["first_seen"]).dt.days
    
    return progression

def compute_transition_metrics(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute progression-only transition metrics between difficulty levels.
    Deduplicates PRs to avoid spurious intra-PR transitions.
    """
    if df.empty:
        return pd.DataFrame()

    level_order = {spec.name: i for i, spec in enumerate(DIFFICULTY_LEVELS)}
    level_order["Unknown"] = -1

    # Deduplicate to one level per PR (highest difficulty) before walking transitions
    # Filter out 'Unknown' to avoid noise in transitions
    df_sorted = (
        df[df["level"] != "Unknown"]
          .assign(_rank=df["level"].map(lambda l: level_order.get(l, -1)))
          .sort_values(["author", "pr_merged_at", "_rank"])
          .drop_duplicates(subset=["author", "pr_number"], keep="last")
          .sort_values(["author", "pr_merged_at"])
    )
    
    transitions = []
    for author, group in df_sorted.groupby("author"):
        levels = group["level"].tolist()
        max_rank_so_far = -1
        
        for level in levels:
            current_rank = level_order.get(level, -1)
            if current_rank > max_rank_so_far:
                if max_rank_so_far != -1:
                    from_level = next((name for name, rank in level_order.items() if rank == max_rank_so_far), "Unknown")
                    transitions.append({"from": from_level, "to": level})
                max_rank_so_far = current_rank
                
    if not transitions:
        return pd.DataFrame(columns=["from", "to", "count"])
        
    trans_df = pd.DataFrame(transitions)
    counts = trans_df.groupby(["from", "to"]).size().reset_index(name="count")
    return counts
