
import sqlite3
import pandas as pd
from pathlib import Path

DB_PATH = "data/processed/benchmark.db"
OUTPUT_DIR = Path("outputs")
OUTPUT_DIR.mkdir(exist_ok=True)

conn = sqlite3.connect(DB_PATH)

queries = {
    "niche_performance": """
        SELECT
            c.niche,
            COUNT(v.video_id) AS video_count,
            ROUND(AVG(v.views), 0) AS avg_views,
            ROUND(AVG(v.engagement_rate_pct), 2) AS avg_engagement_pct
        FROM creators c
        JOIN videos v ON c.creator_id = v.creator_id
        GROUP BY c.niche
    """,

    "top_creators": """
        SELECT
            c.creator_id,
            c.channel_name,
            c.niche,
            c.subscriber_count,
            COUNT(v.video_id) AS video_count,
            ROUND(AVG(v.engagement_rate_pct), 2) AS avg_engagement_pct,
            ROUND(AVG(v.views), 0) AS avg_views
        FROM creators c
        JOIN videos v ON c.creator_id = v.creator_id
        GROUP BY c.creator_id
        ORDER BY avg_engagement_pct DESC
        LIMIT 10
    """,

    "format_distribution": """
        SELECT
            format_estimate,
            COUNT(*) AS video_count
        FROM videos
        GROUP BY format_estimate
    """
}

for name, query in queries.items():
    df = pd.read_sql_query(query, conn)
    df.to_csv(OUTPUT_DIR / f"{name}.csv", index=False)
    print(f"Exported {name}: {len(df)} rows")

conn.close()

