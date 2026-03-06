from pathlib import Path
import pandas as pd


def save_dataframe(
    df: pd.DataFrame,
    path: Path,
) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)