
import pandas as pd
from pathlib import Path

files = {
    "Creators": "data/raw/creators_data.csv",
    "Videos": "data/raw/videos_data.csv",
    "Collection Log": "data/raw/collection_log.csv"
}

for name, path in files.items():
    df = pd.read_csv(path, encoding="utf-8-sig")

    print(f"\n{'='*40}")
    print(name)
    print("Rows:", len(df))
    print("Columns:", list(df.columns))
    print("\nMissing values:")
    print(df.isna().sum())
    print("\nDuplicate rows:", df.duplicated().sum())

    if "creator_id" in df.columns:
        print("Unique creators:", df["creator_id"].nunique())

    if name == "Collection Log":
        print("\nCollection status:")
        print(df["status"].value_counts())

    if name == "Videos":
        print("\nVideos per creator:")
        print(df.groupby("creator_id").size().describe())

    print("\nFirst 3 records:")
    print(df.head(3).to_string(index=False))
