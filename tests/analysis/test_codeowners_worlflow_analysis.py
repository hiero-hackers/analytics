import pandas as pd
import pytest

from hiero_analytics.data_sources.models import CodeOwnersRecord, RunnerRecord
from hiero_analytics.analysis.codeowner_workflow_analysis import (
    prepare_org_codeowners_summary,
    prepare_repo_level_codeowner_summary,
    runner_records_to_dataframe,
    prepare_stacked_runner_summary,
)



def test_prepare_org_codeowners_summary_empty():
    """Test empty list returns an empty dataframe with correct columns."""
    df = prepare_org_codeowners_summary([])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["status", "count"]
    assert df.empty


def test_prepare_org_codeowners_summary():
    """Test aggregation of present vs missing status across the org."""
    records = [
        CodeOwnersRecord(repo="repo1", status=True),
        CodeOwnersRecord(repo="repo2", status=False),
        CodeOwnersRecord(repo="repo3", status=True),
    ]
    df = prepare_org_codeowners_summary(records)
    
    # Check counts
    present = df[df["status"] == "Present"]["count"].iloc[0]
    missing = df[df["status"] == "Missing"]["count"].iloc[0]
    
    assert present == 2
    assert missing == 1


def test_prepare_repo_level_codeowner_summary():
    """Test conversion of records to a flat repo-status dataframe."""
    records = [CodeOwnersRecord(repo="hiero-sdk", status=True)]
    df = prepare_repo_level_codeowner_summary(records)
    
    assert len(df) == 1
    assert df.iloc[0]["repo"] == "hiero-sdk"
    assert df.iloc[0]["status"] == True


def test_runner_records_to_dataframe_empty():
    """Test empty runner list returns empty dataframe with standard columns."""
    df = runner_records_to_dataframe([])
    assert isinstance(df, pd.DataFrame)

    for col in ["repo", "job", "runner", "self_hosted"]:
        assert col in df.columns
    assert df.empty


def test_runner_records_to_dataframe():
    """Test mapping of RunnerRecord fields to dataframe columns."""
    records = [
        RunnerRecord(
            repo="hiero-sdk",
            workflow_file="ci.yml",
            job_name="test",
            runner="hl-sdk-py-lin-md",
            is_self_hosted=True
        )
    ]
    df = runner_records_to_dataframe(records)
    
    assert len(df) == 1
    row = df.iloc[0]
    assert row["repo"] == "hiero-sdk"
    assert row["job"] == "test"
    assert row["self_hosted"] == True


def test_prepare_stacked_runner_summary_empty():
    """Test stacked runner aggregation for empty input."""
    df = prepare_stacked_runner_summary([])
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["repo", "Self-Hosted", "Standard", "Indeterminate"]
    assert df.empty

def test_prepare_stacked_runner_summary_aggregation():
    """Test that multiple jobs in the same repo are correctly summed by type including None."""
    records = [
        RunnerRecord("repo1", "f1.yml", "j1", "hl-1", True),
        RunnerRecord("repo1", "f1.yml", "j2", "hl-1", True),
        RunnerRecord("repo1", "f2.yml", "j3", "ubuntu-latest", False),
        RunnerRecord("repo1", "f2.yml", "j4", "${{ matrix.os }}", None),
        RunnerRecord("repo2", "f3.yml", "j5", "ubuntu-latest", False),
    ]
    
    df = prepare_stacked_runner_summary(records)
    
    repo1_row = df[df["repo"] == "repo1"].iloc[0]
    assert repo1_row["Self-Hosted"] == 2
    assert repo1_row["Standard"] == 1
    assert repo1_row["Indeterminate"] == 1
    
    repo2_row = df[df["repo"] == "repo2"].iloc[0]
    assert repo2_row["Self-Hosted"] == 0
    assert repo2_row["Standard"] == 1
    assert repo2_row["Indeterminate"] == 0


def test_prepare_stacked_runner_summary_columns_exist():
    """Ensure all three infrastructure columns exist even if data only contains one type."""
    records = [RunnerRecord("repo1", "f1.yml", "j1", "ubuntu-latest", False)]
    df = prepare_stacked_runner_summary(records)

    assert "Self-Hosted" in df.columns
    assert "Standard" in df.columns
    assert "Indeterminate" in df.columns
    

    assert df.iloc[0]["Standard"] == 1
    assert df.iloc[0]["Self-Hosted"] == 0
    assert df.iloc[0]["Indeterminate"] == 0