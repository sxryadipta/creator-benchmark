-- =============================================================================
-- sql/analysis.sql
-- YouTube Creator Benchmark: SQLite analysis
--
-- Tables are created with IF NOT EXISTS, so this file does NOT fix a table
-- that already exists with the wrong columns. Use the reset steps in the
-- instructions to drop and recreate the tables first.
-- Column order matches the cleaned CSVs exactly (.import maps by position).
-- =============================================================================

CREATE TABLE IF NOT EXISTS creators (
    creator_id           TEXT,
    channel_name         TEXT,
    channel_url          TEXT,
    niche                TEXT,
    subscriber_count     TEXT,
    total_channel_views  TEXT,
    data_collected_on    TEXT,
    channel_id           TEXT,
    quality_flags        TEXT,
    video_count          TEXT,
    in_collection_log    TEXT
);

CREATE TABLE IF NOT EXISTS videos (
    video_id                    TEXT,
    creator_id                  TEXT,
    niche                       TEXT,
    format                      TEXT,
    upload_date                 TEXT,
    views                       TEXT,
    likes                       TEXT,
    comments                    TEXT,
    creator_in_creators_file    TEXT,
    creator_subscriber_count    TEXT,
    engagement_rate_pct         TEXT,
    views_to_subscriber_pct     TEXT,
    quality_flags               TEXT,
    channel_name                TEXT,
    video_title                 TEXT,
    video_url                   TEXT,
    duration_seconds            TEXT,
    format_estimate             TEXT,
    data_collected_on           TEXT,
    source_url                  TEXT
);

-- ---------------------------------------------------------------------------
-- VIEWS: trim text, empty -> NULL, cast to REAL once.
-- Videos need positive views and a valid engagement rate to be analysed.
-- ---------------------------------------------------------------------------
DROP VIEW IF EXISTS v_creators;
CREATE VIEW v_creators AS
SELECT TRIM(creator_id)                              AS creator_id,
       TRIM(niche)                                   AS niche,
       CAST(NULLIF(TRIM(subscriber_count), '') AS REAL) AS subscriber_count
FROM creators;

DROP VIEW IF EXISTS v_videos;
CREATE VIEW v_videos AS
SELECT TRIM(video_id)                                    AS video_id,
       TRIM(creator_id)                                  AS creator_id,
       TRIM(niche)                                       AS niche,
       TRIM(format)                                      AS format,
       CAST(NULLIF(TRIM(views), '') AS REAL)             AS views,
       CAST(NULLIF(TRIM(engagement_rate_pct), '') AS REAL)     AS engagement_rate_pct,
       CAST(NULLIF(TRIM(views_to_subscriber_pct), '') AS REAL) AS views_to_subscriber_pct
FROM videos
WHERE CAST(NULLIF(TRIM(views), '') AS REAL) > 0
  AND CAST(NULLIF(TRIM(engagement_rate_pct), '') AS REAL) IS NOT NULL;

-- Per-creator averages. A creator is "eligible" with 5+ valid videos.
DROP VIEW IF EXISTS v_creator_avg;
CREATE VIEW v_creator_avg AS
SELECT v.creator_id,
       COUNT(*)                       AS n_videos,
       AVG(v.views)                   AS avg_views,
       AVG(v.engagement_rate_pct)     AS avg_engagement,
       AVG(v.views_to_subscriber_pct) AS avg_views_to_subscriber,
       c.subscriber_count             AS subscriber_count
FROM v_videos v
LEFT JOIN v_creators c ON c.creator_id = v.creator_id
GROUP BY v.creator_id, c.subscriber_count;

-- ---------------------------------------------------------------------------
-- Q1: Which niche has the highest MEDIAN engagement rate? (5+ videos)
-- ---------------------------------------------------------------------------
WITH ranked AS (
    SELECT niche,
           engagement_rate_pct AS v,
           ROW_NUMBER() OVER (PARTITION BY niche ORDER BY engagement_rate_pct) AS rn,
           COUNT(*)     OVER (PARTITION BY niche) AS n
    FROM v_videos
    WHERE niche IN ('Technology', 'Gaming', 'Entertainment')
)
SELECT niche,
       n                AS videos,
       ROUND(AVG(v), 2) AS median_engagement_pct
FROM ranked
WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
GROUP BY niche, n
HAVING n >= 5
ORDER BY median_engagement_pct DESC;

-- ---------------------------------------------------------------------------
-- Q2: Which niche has the highest AVERAGE views per video? (5+ videos)
-- ---------------------------------------------------------------------------
SELECT niche,
       COUNT(*)          AS videos,
       ROUND(AVG(views)) AS avg_views_per_video
FROM v_videos
WHERE niche IN ('Technology', 'Gaming', 'Entertainment')
GROUP BY niche
HAVING COUNT(*) >= 5
ORDER BY avg_views_per_video DESC;

-- ---------------------------------------------------------------------------
-- Q3: Which duration-based format estimate performs better in each niche?
-- IMPORTANT: format_estimate is a DURATION-BASED ESTIMATE (<=60s vs >60s),
-- NOT a verified YouTube Shorts classification.
-- Groups with fewer than 3 videos are hidden to avoid misleading averages.
-- ---------------------------------------------------------------------------
SELECT TRIM(niche)                               AS niche,
       TRIM(format_estimate)                     AS duration_estimate_unverified,
       COUNT(*)                                  AS videos,
       ROUND(AVG(CAST(NULLIF(TRIM(views), '') AS REAL)))                 AS avg_views,
       ROUND(AVG(CAST(NULLIF(TRIM(engagement_rate_pct), '') AS REAL)), 2) AS avg_engagement_pct
FROM videos
WHERE TRIM(niche) IN ('Technology', 'Gaming', 'Entertainment')
  AND TRIM(format_estimate) <> ''
  AND CAST(NULLIF(TRIM(views), '') AS REAL) > 0
  AND CAST(NULLIF(TRIM(engagement_rate_pct), '') AS REAL) IS NOT NULL
GROUP BY TRIM(niche), TRIM(format_estimate)
HAVING COUNT(*) >= 3
ORDER BY niche, avg_engagement_pct DESC;

-- ---------------------------------------------------------------------------
-- Q4: Top 10 creators by MEDIAN engagement rate (5+ videos).
-- ---------------------------------------------------------------------------
WITH ranked AS (
    SELECT creator_id,
           engagement_rate_pct AS v,
           ROW_NUMBER() OVER (PARTITION BY creator_id ORDER BY engagement_rate_pct) AS rn,
           COUNT(*)     OVER (PARTITION BY creator_id) AS n
    FROM v_videos
),
medians AS (
    SELECT creator_id,
           n,
           AVG(v) AS median_engagement
    FROM ranked
    WHERE rn IN ((n + 1) / 2, (n + 2) / 2)
    GROUP BY creator_id, n
    HAVING n >= 5
)
SELECT m.creator_id,
       c.niche,
       m.n                           AS videos,
       ROUND(m.median_engagement, 2) AS median_engagement_pct
FROM medians m
LEFT JOIN v_creators c ON c.creator_id = m.creator_id
ORDER BY m.median_engagement DESC
LIMIT 10;

-- ---------------------------------------------------------------------------
-- Q5: Highest average views-to-subscriber ratio (5+ videos, subscribers > 0).
-- Ratio = views / subscribers * 100, averaged per creator.
-- ---------------------------------------------------------------------------
SELECT creator_id,
       n_videos                          AS videos,
       subscriber_count,
       ROUND(avg_views_to_subscriber, 2) AS avg_views_to_subscriber_pct
FROM v_creator_avg
WHERE n_videos >= 5
  AND subscriber_count > 0
  AND avg_views_to_subscriber IS NOT NULL
ORDER BY avg_views_to_subscriber DESC
LIMIT 10;

-- ---------------------------------------------------------------------------
-- Q6a: Pearson correlation of subscriber count vs average views.
-- Uses ALL eligible creators (5+ videos, subscribers > 0, avg views present).
-- Also reports the number of creators used, so you can confirm it is not 1.
-- ---------------------------------------------------------------------------
WITH pts AS (
    SELECT subscriber_count AS x,
           avg_views        AS y
    FROM v_creator_avg
    WHERE n_videos >= 5
      AND subscriber_count > 0
      AND avg_views IS NOT NULL
),
sums AS (
    SELECT COUNT(*)   AS n,
           SUM(x)     AS sx,
           SUM(y)     AS sy,
           SUM(x * y) AS sxy,
           SUM(x * x) AS sxx,
           SUM(y * y) AS syy
    FROM pts
)
SELECT n AS creators_used,
       ROUND((n * sxy - sx * sy)
             / SQRT(NULLIF((n * sxx - sx * sx) * (n * syy - sy * sy), 0)), 3) AS pearson_r
FROM sums;

-- ---------------------------------------------------------------------------
-- Q6b: Average views per video by subscriber tier (same eligible creators).
-- ---------------------------------------------------------------------------
SELECT CASE
         WHEN subscriber_count < 100000   THEN '1. under 100K'
         WHEN subscriber_count < 1000000  THEN '2. 100K to 1M'
         WHEN subscriber_count < 10000000 THEN '3. 1M to 10M'
         ELSE '4. 10M and above'
       END                   AS subscriber_tier,
       COUNT(*)              AS creators,
       ROUND(AVG(avg_views)) AS avg_views_per_video
FROM v_creator_avg
WHERE n_videos >= 5
  AND subscriber_count > 0
GROUP BY subscriber_tier
HAVING COUNT(*) >= 3
ORDER BY subscriber_tier;

-- ---------------------------------------------------------------------------
-- Q7: Creators with unusually high or low engagement (|z| >= 2).
-- z-score of each creator's average engagement against all eligible creators.
-- ---------------------------------------------------------------------------
WITH stats AS (
    SELECT AVG(avg_engagement) AS mu,
           AVG(avg_engagement * avg_engagement) - AVG(avg_engagement) * AVG(avg_engagement) AS var
    FROM v_creator_avg
    WHERE n_videos >= 5
),
scored AS (
    SELECT a.creator_id,
           a.n_videos,
           a.avg_engagement,
           (a.avg_engagement - s.mu) / SQRT(NULLIF(s.var, 0)) AS z
    FROM v_creator_avg a
    CROSS JOIN stats s
    WHERE a.n_videos >= 5
)
SELECT creator_id,
       n_videos                 AS videos,
       ROUND(avg_engagement, 2) AS avg_engagement_pct,
       ROUND(z, 2)              AS z_score,
       CASE WHEN z >= 0 THEN 'HIGH' ELSE 'LOW' END AS flag
FROM scored
WHERE ABS(z) >= 2
ORDER BY z DESC;