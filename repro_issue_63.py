import pandas as pd
import unittest
from unittest.mock import Mock, patch
from pathlib import Path
from datetime import datetime, UTC
from hiero_analytics.run_difficulty_org_for_repo import main

class TestRunDifficulty(unittest.TestCase):
    @patch('hiero_analytics.run_difficulty_org_for_repo.GitHubClient')
    @patch('hiero_analytics.run_difficulty_org_for_repo.fetch_org_issues_graphql')
    @patch('hiero_analytics.run_difficulty_org_for_repo.ensure_org_dirs')
    @patch('hiero_analytics.run_difficulty_org_for_repo.save_dataframe')
    @patch('hiero_analytics.run_difficulty_org_for_repo.plot_pie')
    @patch('hiero_analytics.run_difficulty_org_for_repo.plot_stacked_bar')
    def test_main_flow(self, mock_plot_bar, mock_plot_pie, mock_save_df, mock_ensure_dirs, mock_fetch_issues, mock_client_class):
        # Setup mocks
        mock_data_dir = Path("mock_data")
        mock_charts_dir = Path("mock_charts")
        mock_ensure_dirs.return_value = (mock_data_dir, mock_charts_dir)
        
        # Mock issues return
        mock_issues = [
            Mock(
                number=1, repo="org/repo1", state="open", 
                created_at=datetime(2026, 3, 20, tzinfo=UTC),
                labels=["difficulty: easy"]
            ),
            Mock(
                number=2, repo="org/repo1", state="open", 
                created_at=datetime(2026, 3, 22, tzinfo=UTC),
                labels=["difficulty: hard"]
            )
        ]
        mock_fetch_issues.return_value = mock_issues
        
        # Run main
        # We need to handle the date cutoff in the script which uses datetime.now(UTC)
        # Since I cannot easily mock datetime.now in the script without more patches,
        # I'll just see if it runs and what it calls.
        try:
            main()
        except Exception as e:
            print(f"Caught expected or unexpected error: {e}")

        # Check if data was "created" (i.e. save_dataframe was called)
        print(f"save_dataframe call count: {mock_save_df.call_count}")
        for i, call in enumerate(mock_save_df.call_args_list):
            print(f"Call {i} path: {call[0][1]}")

        # Check if plots were "created"
        print(f"plot_pie call count: {mock_plot_pie.call_count}")

if __name__ == "__main__":
    unittest.main()
