"""
clean_data.py
Indian YouTube Creator Benchmark Analysis: cleaning and quality control.

Run from the project root:
    python clean_data.py

Reads (never modifies):
    data/raw/creators_data.csv
    data/raw/videos_data.csv
    data/raw/collection_log.csv

Writes to data/processed/:
    cleaned_creators.csv
    cleaned_videos.csv
    data_quality_report.txt
"""

import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd


# =============================================================================
# SETTINGS (edit these if your files or categories change)
# =============================================================================

# Paths are relative to the project root (where you run the script from)
RAW_DIR = Path("data/raw")
PROCESSED_DIR = Path("data/processed")

CREATORS_FILE = RAW_DIR / "creators_data.csv"
VIDEOS_FILE = RAW_DIR / "videos_data.csv"
LOG_FILE = RAW_DIR / "collection_log.csv"

CLEAN_CREATORS_FILE = PROCESSED_DIR / "cleaned_creators.csv"
CLEAN_VIDEOS_FILE = PROCESSED_DIR / "cleaned_videos.csv"
REPORT_FILE = PROCESSED_DIR / "data_quality_report.txt"

MIN_VIDEOS = 10                 # creators with fewer videos are reported
HIGH_VIEWS_RATIO_PCT = 1000     # views-to-subscriber above this is flagged for review

# Encodings tried in order when reading a CSV
ENCODINGS_TO_TRY = ["utf-8-sig", "cp1252", "latin-1"]

# Text values treated as "missing" (compared in lowercase)
NA_STRINGS = {"", "na", "n/a", "null", "none", "nan", "-", "--"}

# Possible column names in the source files, mapped to a standard name.
# The first match in each list is used.
COLUMN_ALIASES = {
    "creator_id": ["creator_id", "channel_id", "creator"],
    "video_id": ["video_id", "id"],
    "subscriber_count": ["subscriber_count", "subscribers", "subs", "subscriber_cnt"],
    "views": ["views", "view_count", "viewcount"],
    "likes": ["likes", "like_count"],
    "comments": ["comments", "comment_count"],
    "upload_date": ["upload_date", "published_at", "publish_date", "uploaded_on"],
    "collected_at": ["collected_at", "collection_timestamp", "timestamp", "collected_on"],
    "niche": ["niche", "category", "genre"],
    "format": ["format", "video_format", "content_format"],
    "status": ["status", "collection_status", "result"],
    "error_message": ["error_message", "error", "error_msg", "reason"],
}

# Label standardisation. Keys are lowercase with no underscores or hyphens.
# Labels not listed here are only tidied (spacing and capitals), never guessed.
NICHE_MAP = {
    "tech": "Technology",
    "technology": "Technology",
    "finance": "Finance",
    "personal finance": "Personal Finance",
    "education": "Education",
    "edu": "Education",
    "gaming": "Gaming",
    "games": "Gaming",
    "food": "Food & Cooking",
    "cooking": "Food & Cooking",
    "beauty": "Beauty & Fashion",
    "fashion": "Beauty & Fashion",
    "fitness": "Fitness & Health",
    "health": "Fitness & Health",
    "comedy": "Comedy",
    "travel": "Travel",
    "vlog": "Vlogs",
    "vlogs": "Vlogs",
    "news": "News & Politics",
    "politics": "News & Politics",
    "music": "Music",
    "sports": "Sports",
}

FORMAT_MAP = {
    "short": "Shorts",
    "shorts": "Shorts",
    "youtube shorts": "Shorts",
    "long": "Long-form",
    "long form": "Long-form",
    "longform": "Long-form",
    "live": "Live",
    "livestream": "Live",
}

# Collection log status values mapped to three standard states
STATUS_MAP = {
    "success": "success",
    "successful": "success",
    "ok": "success",
    "completed": "success",
    "failed": "failed",
    "fail": "failed",
    "failure": "failed",
    "error": "failed",
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def log_issue(issues, section, message):
    """Store a message for the quality report. Nothing is discarded silently."""
    issues[section].append(message)


def read_csv_with_fallback(path):
    """Read a CSV as text (no automatic type guessing), trying several encodings."""
    if not path.exists():
        sys.exit(f"ERROR: File not found: {path}\nRun this script from the project root.")

    for encoding in ENCODINGS_TO_TRY:
        try:
            # dtype=str keeps every value as typed. keep_default_na=False stops
            # pandas from silently turning values like "NA" into missing values.
            table = pd.read_csv(path, dtype=str, keep_default_na=False, encoding=encoding)
            return table, encoding
        except UnicodeDecodeError:
            continue

    sys.exit(f"ERROR: Could not decode {path} using: {ENCODINGS_TO_TRY}")


def standardise_columns(table, must_have, expected, label, issues):
    """Rename column variants to standard names and check required columns."""
    # Make headers consistent: "Video ID " -> "video_id"
    table.columns = [str(c).strip().lower().replace(" ", "_") for c in table.columns]

    rename_map = {}
    for standard_name, options in COLUMN_ALIASES.items():
        for option in options:
            if option in table.columns and standard_name not in table.columns:
                if option != standard_name:
                    rename_map[option] = standard_name
                break
    table = table.rename(columns=rename_map)

    for col in must_have:
        if col not in table.columns:
            sys.exit(
                f"ERROR in {label}: required column '{col}' not found.\n"
                f"Columns found: {list(table.columns)}"
            )

    for col in expected:
        if col not in table.columns:
            table[col] = np.nan
            log_issue(issues, label,
                      f"Column '{col}' not found in file. Treated as entirely missing (no values invented).")
    return table


def clean_text_columns(table):
    """Trim whitespace, fix non-breaking spaces, and turn NA-like text into real missing values."""
    table = table.copy()
    for col in table.columns:
        text = table[col].astype(str)
        text = text.str.replace("\u00a0", " ", regex=False)        # non-breaking space
        text = text.str.replace(r"\s+", " ", regex=True).str.strip()  # collapse spaces
        is_missing = text.str.lower().isin(NA_STRINGS)
        table[col] = text.mask(is_missing)                          # blank -> NaN
    return table


def drop_repeated_ids(table, key, label, issues):
    """Keep the first row for each repeated ID. Every removal is logged."""
    repeated = table[key].notna() & table.duplicated(subset=[key], keep="first")
    if repeated.any():
        ids = table.loc[repeated, key].astype(str).tolist()
        log_issue(issues, label,
                  f"Repeated {key}: {len(ids)} extra row(s) removed (first kept). IDs: {', '.join(ids)}")
    else:
        log_issue(issues, label, f"OK: no repeated {key} values.")
    return table.loc[~repeated].reset_index(drop=True), int(repeated.sum())


def to_number(series, column_name, label, issues):
    """Convert text to numbers. Values that cannot be read become missing (NaN), never guessed."""
    cleaned = (series.str.replace(",", "", regex=False)
                     .str.replace("\u20b9", "", regex=False)   # rupee sign
                     .str.strip())
    numbers = pd.to_numeric(cleaned, errors="coerce")

    unreadable = series.notna() & numbers.isna()
    blanks = series.isna().sum()
    if unreadable.any():
        examples = series[unreadable].unique()[:5].tolist()
        log_issue(issues, label,
                  f"{column_name}: {int(unreadable.sum())} non-numeric value(s) left as missing. "
                  f"Examples: {examples}")
    log_issue(issues, label, f"{column_name}: {int(blanks)} blank value(s) left as missing (not filled).")
    return numbers


def to_datetime_safe(series, column_name, label, issues):
    """Parse dates. Unreadable dates become missing (NaT) and are reported."""
    parsed = pd.to_datetime(series, errors="coerce", dayfirst=True)
    if parsed.dt.tz is not None:
        parsed = parsed.dt.tz_localize(None)   # keep plain local times for comparisons

    unreadable = series.notna() & parsed.isna()
    if unreadable.any():
        examples = series[unreadable].unique()[:5].tolist()
        log_issue(issues, label,
                  f"{column_name}: {int(unreadable.sum())} unreadable date(s) left as missing. "
                  f"Examples: {examples}")
    else:
        log_issue(issues, label, f"OK: all non-blank values in {column_name} parsed as dates.")
    return parsed


def standardise_labels(series, mapping, unmapped_values):
    """Tidy category labels and map known variants to one standard name."""
    def convert(value):
        if pd.isna(value):
            return np.nan
        text = " ".join(str(value).split())
        key = text.lower().replace("_", " ").replace("-", " ")
        key = " ".join(key.split())
        if key in mapping:
            return mapping[key]
        unmapped_values.add(text)      # remember it so the report can list it
        return text.title()
    return series.map(convert)


def flag_rows(flags, mask, label, table, id_col, issues, section):
    """Mark rows matching a condition with a flag label and log the result."""
    mask = mask.fillna(False).astype(bool)
    count = int(mask.sum())
    if count:
        flags.loc[mask] = flags.loc[mask] + label + "; "
        ids = table.loc[mask, id_col].fillna("(blank ID)").astype(str).tolist()
        log_issue(issues, section, f"FLAG {label}: {count} row(s). IDs: {', '.join(ids)}")
    else:
        log_issue(issues, section, f"OK: no rows flagged as {label}.")
    return count


def safe_percent(numerator, denominator):
    """Return numerator / denominator * 100. Zero or missing denominators give NaN."""
    result = pd.Series(np.nan, index=numerator.index, dtype=float)
    valid = numerator.notna() & denominator.notna() & (denominator > 0)
    result.loc[valid] = numerator[valid] / denominator[valid] * 100
    return result.round(4)


def flag_summary(table):
    """Count how often each flag appears across all rows."""
    flags = table["quality_flags"].replace("", np.nan).dropna()
    if flags.empty:
        return pd.Series(dtype=int)
    return flags.str.split("; ").explode().value_counts()


# =============================================================================
# MAIN PIPELINE
# =============================================================================

def main():
    print("=" * 60)
    print("YouTube Creator Benchmark: clean_data.py")
    print("=" * 60)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    issues = defaultdict(list)   # section name -> list of messages for the report

    # -------------------------------------------------------------------------
    # STEP 1: Load all three CSVs (raw files are only read, never written)
    # -------------------------------------------------------------------------
    print("\n[1/6] Loading raw files...")

    creators, creators_enc = read_csv_with_fallback(CREATORS_FILE)
    creators = standardise_columns(creators, ["creator_id"],
                                   ["creator_id", "subscriber_count", "niche"],
                                   "Creators", issues)
    creators = clean_text_columns(creators)
    creators_rows_loaded = len(creators)

    videos, videos_enc = read_csv_with_fallback(VIDEOS_FILE)
    videos = standardise_columns(videos, ["video_id", "creator_id"],
                                 ["video_id", "creator_id", "views", "likes", "comments",
                                  "upload_date", "niche", "format"],
                                 "Videos", issues)
    videos = clean_text_columns(videos)
    videos_rows_loaded = len(videos)

    log, log_enc = read_csv_with_fallback(LOG_FILE)
    log = standardise_columns(log, ["creator_id", "status"],
                              ["creator_id", "status", "collected_at", "error_message"],
                              "Collection log", issues)
    log = clean_text_columns(log)
    log_rows_loaded = len(log)

    print(f"  Creators: {creators_rows_loaded} rows | Videos: {videos_rows_loaded} rows "
          f"| Collection log: {log_rows_loaded} rows")

    # -------------------------------------------------------------------------
    # STEP 2: Clean the data
    # -------------------------------------------------------------------------
    print("\n[2/6] Cleaning data...")

    # Duplicate IDs
    creators, creator_dupes = drop_repeated_ids(creators, "creator_id", "Creators", issues)
    videos, video_dupes = drop_repeated_ids(videos, "video_id", "Videos", issues)

    exact_log_dupes = int(log.duplicated().sum())
    if exact_log_dupes:
        log_issue(issues, "Collection log",
                  f"{exact_log_dupes} exact duplicate row(s) found. Kept (log records are not removed).")
    else:
        log_issue(issues, "Collection log", "OK: no exact duplicate log rows.")

    # Numeric columns
    creators["subscriber_count"] = to_number(creators["subscriber_count"], "subscriber_count",
                                             "Creators", issues)
    for col in ["views", "likes", "comments"]:
        videos[col] = to_number(videos[col], col, "Videos", issues)

    # Dates and timestamps
    videos["upload_date"] = to_datetime_safe(videos["upload_date"], "upload_date", "Videos", issues)
    log["collected_at"] = to_datetime_safe(log["collected_at"], "collected_at",
                                           "Collection log", issues)

    # Standardise labels
    unmapped_niche, unmapped_format = set(), set()
    creators["niche"] = standardise_labels(creators["niche"], NICHE_MAP, unmapped_niche)
    videos["niche"] = standardise_labels(videos["niche"], NICHE_MAP, unmapped_niche)
    videos["format"] = standardise_labels(videos["format"], FORMAT_MAP, unmapped_format)

    if unmapped_niche:
        log_issue(issues, "Cleaning",
                  f"Niche labels not in NICHE_MAP (tidied only, kept): {sorted(unmapped_niche)}")
    if unmapped_format:
        log_issue(issues, "Cleaning",
                  f"Format labels not in FORMAT_MAP (tidied only, kept): {sorted(unmapped_format)}")

    # Standardise collection status
    raw_status = log["status"]
    status_clean = raw_status.str.lower().map(STATUS_MAP).fillna("unrecognised")
    status_clean[raw_status.isna()] = "missing"
    log["status_clean"] = status_clean
    unrecognised = log.loc[log["status_clean"] == "unrecognised", "status"].unique().tolist()
    if unrecognised:
        log_issue(issues, "Collection log", f"Unrecognised status values (kept as 'unrecognised'): {unrecognised}")

    # -------------------------------------------------------------------------
    # STEP 3: Creator flags, then merge subscriber counts into videos
    # -------------------------------------------------------------------------
    print("\n[3/6] Merging creator subscriber counts into videos...")

    creator_flags = pd.Series("", index=creators.index, dtype=object)
    subs_c = creators["subscriber_count"]
    flag_rows(creator_flags, subs_c.isna(), "missing_subscriber_count", creators,
              "creator_id", issues, "Creator checks")
    flag_rows(creator_flags, subs_c == 0, "zero_subscribers", creators,
              "creator_id", issues, "Creator checks")
    flag_rows(creator_flags, subs_c < 0, "negative_subscribers", creators,
              "creator_id", issues, "Creator checks")
    creators["quality_flags"] = creator_flags.str.rstrip("; ")

    # Merge: keep every video (left join). Validate that creator_id is unique in creators.
    lookup = (creators.loc[creators["creator_id"].notna(), ["creator_id", "subscriber_count"]]
                      .rename(columns={"subscriber_count": "creator_subscriber_count"}))
    videos = videos.merge(lookup, on="creator_id", how="left",
                          validate="many_to_one", indicator="_merge")
    videos["creator_in_creators_file"] = videos["_merge"].eq("both")
    videos = videos.drop(columns="_merge")

    # -------------------------------------------------------------------------
    # STEP 4: Calculate metrics (zero and missing denominators give NaN)
    # -------------------------------------------------------------------------
    print("\n[4/6] Calculating engagement and views-to-subscriber ratios...")

    views = videos["views"]
    likes = videos["likes"]
    comments = videos["comments"]
    subs = videos["creator_subscriber_count"]

    # Engagement rate = (likes + comments) / views * 100
    interactions = likes + comments          # NaN if either is missing
    videos["engagement_rate_pct"] = safe_percent(interactions, views)

    # Views-to-subscriber ratio = views / subscriber_count * 100
    videos["views_to_subscriber_pct"] = safe_percent(views, subs)

    # -------------------------------------------------------------------------
    # STEP 5: Row-level quality flags for videos
    # -------------------------------------------------------------------------
    video_flags = pd.Series("", index=videos.index, dtype=object)
    section = "Video checks"

    flag_rows(video_flags, views.isna(), "missing_views", videos, "video_id", issues, section)
    flag_rows(video_flags, likes.isna(), "missing_likes", videos, "video_id", issues, section)
    flag_rows(video_flags, comments.isna(), "missing_comments", videos, "video_id", issues, section)
    flag_rows(video_flags, views == 0, "zero_views", videos, "video_id", issues, section)
    flag_rows(video_flags, (views < 0) | (likes < 0) | (comments < 0),
              "negative_value", videos, "video_id", issues, section)
    flag_rows(video_flags, likes > views, "likes_exceed_views", videos, "video_id", issues, section)
    flag_rows(video_flags, comments > views, "comments_exceed_views", videos, "video_id", issues, section)
    flag_rows(video_flags, videos["upload_date"].isna(), "missing_or_invalid_upload_date",
              videos, "video_id", issues, section)
    flag_rows(video_flags, videos["upload_date"] > pd.Timestamp.now(), "future_upload_date",
              videos, "video_id", issues, section)
    flag_rows(video_flags, ~videos["creator_in_creators_file"], "creator_not_in_creators_file",
              videos, "video_id", issues, section)
    flag_rows(video_flags, subs.isna() & videos["creator_in_creators_file"],
              "missing_creator_subscribers", videos, "video_id", issues, section)
    flag_rows(video_flags, subs == 0, "zero_creator_subscribers", videos, "video_id", issues, section)
    flag_rows(video_flags, videos["engagement_rate_pct"] > 100, "engagement_over_100pct",
              videos, "video_id", issues, section)
    flag_rows(video_flags, videos["views_to_subscriber_pct"] > HIGH_VIEWS_RATIO_PCT,
              f"views_to_subscriber_over_{HIGH_VIEWS_RATIO_PCT}pct_review",
              videos, "video_id", issues, section)

    videos["quality_flags"] = video_flags.str.rstrip("; ")

    # -------------------------------------------------------------------------
    # STEP 6: Coverage checks and collection log analysis
    # -------------------------------------------------------------------------
    print("\n[5/6] Running quality control checks...")

    # Video counts per creator (creators with no videos get 0)
    video_counts = videos.dropna(subset=["creator_id"]).groupby("creator_id").size()
    creators["video_count"] = creators["creator_id"].map(video_counts).fillna(0).astype(int)
    creators["in_collection_log"] = creators["creator_id"].isin(set(log["creator_id"].dropna()))

    creator_ids = set(creators["creator_id"].dropna())
    video_creator_ids = set(videos["creator_id"].dropna())
    log_ids = set(log["creator_id"].dropna())

    missing_from_creators_file = sorted((video_creator_ids | log_ids) - creator_ids)
    creators_without_videos = sorted(creator_ids - video_creator_ids)
    low_video_creators = (creators.loc[creators["video_count"] < MIN_VIDEOS, ["creator_id", "video_count"]]
                                  .sort_values(["video_count", "creator_id"]))
    creators_not_in_log = sorted(creator_ids - log_ids)

    # Collection log analysis
    status_counts = log["status_clean"].value_counts()
    failed_rows = log[log["status_clean"] == "failed"]
    success_ids = set(log.loc[log["status_clean"] == "success", "creator_id"].dropna())
    failed_creators = set(failed_rows["creator_id"].dropna())
    failed_only_creators = sorted(failed_creators - success_ids)
    log_not_in_creators = sorted(log_ids - creator_ids)

    # Missing creators are part of the reported gaps (nothing is dropped)
    if missing_from_creators_file:
        log_issue(issues, "Coverage gaps",
                  f"{len(missing_from_creators_file)} creator ID(s) appear in video or log data "
                  f"but not in creators_data.csv: {', '.join(missing_from_creators_file)}")

    # -------------------------------------------------------------------------
    # STEP 7: Build output tables
    # -------------------------------------------------------------------------
    creators_out = creators.copy()
    videos_out = videos.copy()
    videos_out["upload_date"] = videos_out["upload_date"].dt.strftime("%Y-%m-%d")

    # Keep only a clear, ordered set of columns in cleaned_videos.csv
    video_column_order = [
        "video_id", "creator_id", "niche", "format", "upload_date",
        "views", "likes", "comments",
        "creator_in_creators_file", "creator_subscriber_count",
        "engagement_rate_pct", "views_to_subscriber_pct", "quality_flags",
    ]
    other_video_cols = [c for c in videos_out.columns if c not in video_column_order]
    videos_out = videos_out[video_column_order + other_video_cols]

    creators_out = creators_out.drop(columns=["in_collection_log"], errors="ignore").join(
        creators_out[["in_collection_log"]])

    creators_out.to_csv(CLEAN_CREATORS_FILE, index=False, encoding="utf-8")
    videos_out.to_csv(CLEAN_VIDEOS_FILE, index=False, encoding="utf-8")

    # -------------------------------------------------------------------------
    # STEP 8: Write the data quality report
    # -------------------------------------------------------------------------
    print("\n[6/6] Writing data quality report...")

    report = []

    def add(line=""):
        report.append(line)

    add("=" * 72)
    add("YOUTUBE CREATOR BENCHMARK: DATA QUALITY REPORT")
    add("=" * 72)
    add(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    add("")
    add("SOURCE FILES (raw, read-only)")
    add(f"  {CREATORS_FILE.name}: {creators_rows_loaded} rows loaded (encoding: {creators_enc})")
    add(f"  {VIDEOS_FILE.name}: {videos_rows_loaded} rows loaded (encoding: {videos_enc})")
    add(f"  {LOG_FILE.name}: {log_rows_loaded} rows loaded (encoding: {log_enc})")
    add("")
    add("OUTPUT FILES")
    add(f"  {CLEAN_CREATORS_FILE.name}: {len(creators_out)} rows")
    add(f"  {CLEAN_VIDEOS_FILE.name}: {len(videos_out)} rows")
    add("")

    add("1. ROW COUNTS")
    add(f"  Creators: {creators_rows_loaded} loaded, {creator_dupes} repeated ID row(s) removed, "
        f"{len(creators_out)} kept")
    add(f"  Videos: {videos_rows_loaded} loaded, {video_dupes} repeated ID row(s) removed, "
        f"{len(videos_out)} kept")
    add(f"  Collection log: {log_rows_loaded} loaded, all kept")
    add("")

    add("2. CLEANING AND CHECK LOG")
    for section_name, messages in issues.items():
        add(f"  [{section_name}]")
        for message in messages:
            add(f"    - {message}")
    add("")

    add("3. CREATOR AND VIDEO COVERAGE")
    add(f"  3a. Creators missing from creators_data.csv ({len(missing_from_creators_file)}):")
    for cid in missing_from_creators_file:
        add(f"    - {cid}")
    if not missing_from_creators_file:
        add("    None")
    add(f"  3b. Creators without videos ({len(creators_without_videos)}):")
    for cid in creators_without_videos:
        add(f"    - {cid}")
    if not creators_without_videos:
        add("    None")
    add(f"  3c. Creators with fewer than {MIN_VIDEOS} videos ({len(low_video_creators)}):")
    for _, row in low_video_creators.iterrows():
        add(f"    - {row['creator_id']}: {row['video_count']} video(s)")
    if low_video_creators.empty:
        add("    None")
    median_videos = creators["video_count"].median() if len(creators) else float("nan")
    add(f"  Videos per creator (creators file): median {median_videos}, "
        f"min {creators['video_count'].min() if len(creators) else 'n/a'}, "
        f"max {creators['video_count'].max() if len(creators) else 'n/a'}")
    add("")

    add("4. COLLECTION LOG ANALYSIS")
    add(f"  Total records: {log_rows_loaded}")
    for status_name, count in status_counts.items():
        add(f"  {status_name}: {count}")
    add(f"  4a. Failed records ({len(failed_rows)}):")
    for _, row in failed_rows.iterrows():
        when = (row["collected_at"].strftime("%Y-%m-%d %H:%M")
                if pd.notna(row["collected_at"]) else "timestamp missing")
        error = row["error_message"] if pd.notna(row.get("error_message", np.nan)) else "no error message"
        add(f"    - creator {row['creator_id']} | {when} | {error}")
    if failed_rows.empty:
        add("    None")
    add(f"  4b. Creators with failed records and no successful record ({len(failed_only_creators)}):")
    for cid in failed_only_creators:
        add(f"    - {cid}")
    if not failed_only_creators:
        add("    None")
    add(f"  4c. Creators in creators file with no collection log entry ({len(creators_not_in_log)}):")
    for cid in creators_not_in_log:
        add(f"    - {cid}")
    if not creators_not_in_log:
        add("    None")
    add(f"  4d. Creators in collection log but not in creators file ({len(log_not_in_creators)}):")
    for cid in log_not_in_creators:
        add(f"    - {cid}")
    if not log_not_in_creators:
        add("    None")
    add("")

    add("5. ROW-LEVEL FLAG SUMMARY: VIDEOS")
    video_flagged_rows = int((videos_out["quality_flags"] != "").sum())
    add(f"  Videos with at least one flag: {video_flagged_rows} of {len(videos_out)}")
    video_flag_counts = flag_summary(videos_out)
    for flag_name, count in video_flag_counts.items():
        add(f"    {flag_name}: {count}")
    if video_flag_counts.empty:
        add("    No flags raised")
    add("")

    add("6. ROW-LEVEL FLAG SUMMARY: CREATORS")
    creator_flagged_rows = int((creators_out["quality_flags"] != "").sum())
    add(f"  Creators with at least one flag: {creator_flagged_rows} of {len(creators_out)}")
    creator_flag_counts = flag_summary(creators_out)
    for flag_name, count in creator_flag_counts.items():
        add(f"    {flag_name}: {count}")
    if creator_flag_counts.empty:
        add("    No flags raised")
    add("")

    add("7. NOTES")
    add("  - Flagged rows are kept in the cleaned outputs. Filter on quality_flags to exclude them.")
    add("  - Missing values were left blank. No values were estimated or filled.")
    add("  - Raw CSV files were not modified.")
    add("=" * 72)

    REPORT_FILE.write_text("\n".join(report), encoding="utf-8")

    # -------------------------------------------------------------------------
    # EXECUTION SUMMARY (printed to the terminal)
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("EXECUTION SUMMARY")
    print("=" * 60)
    print(f"Creators:            {creators_rows_loaded} loaded -> {len(creators_out)} saved")
    print(f"Videos:              {videos_rows_loaded} loaded -> {len(videos_out)} saved")
    print(f"Videos matched to creators file: {int(videos_out['creator_in_creators_file'].sum())}"
          f" of {len(videos_out)}")
    print(f"Collection log:      {log_rows_loaded} records | success {status_counts.get('success', 0)}"
          f" | failed {status_counts.get('failed', 0)}")
    print(f"Creators missing from creators file: {len(missing_from_creators_file)}")
    print(f"Creators without videos:             {len(creators_without_videos)}")
    print(f"Creators with < {MIN_VIDEOS} videos:              {len(low_video_creators)}")
    print(f"Videos with quality flags:           {video_flagged_rows}")
    print("-" * 60)
    print(f"Saved: {CLEAN_CREATORS_FILE}")
    print(f"Saved: {CLEAN_VIDEOS_FILE}")
    print(f"Saved: {REPORT_FILE}")
    print("=" * 60)
    print("Done.")


if __name__ == "__main__":
    main()