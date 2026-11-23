# YouTube Creator Benchmark Analysis

I wanted to explore how creators across different YouTube niches perform and whether there are any noticeable differences in views, engagement and audience size.

So I put together a small dataset of Indian creators from three categories; Technology, Gaming and Entertainment; and analysed it using Python and SQL.

## What this project looks at

- How engagement differs across niches
- Average views per video across categories
- Creators with high engagement rates
- Views in relation to subscriber count
- Whether larger channels necessarily get more views
- Differences between long-form and short-form video estimates

## Dataset

The dataset contains:

- 47 creators
- 442 videos
- 3 niches: Technology, Gaming and Entertainment

The data was collected from publicly available YouTube information. Some collection attempts were unsuccessful, and a few creators have incomplete video data.

Video format is estimated using duration (above or below 60 seconds). It is not a verified classification of YouTube Shorts.

## Tools used

- Python
- Pandas
- SQLite
- SQL
- Excel

## Project structure

```text
creator-benchmark/
│
├── data/
│   ├── raw/
│   └── processed/
│
├── notebooks/
├── outputs/
├── reports/
├── research/
├── sql/
│
├── collect.py
├── clean_data.py
├── audit.py
├── requirements.txt
└── README.md
```

## Some observations

- Entertainment had the highest average views per video in this dataset.
- Technology had the lowest average engagement rate among the three categories.
- Subscriber count and average video views showed a moderate positive correlation.
- A few creators stood out with unusually high engagement rates.

These are observations from this particular sample, not conclusions about the entire Indian YouTube ecosystem.

## Limitations

This isn't a complete representation of YouTube. The dataset is relatively small, collection wasn't successful for every creator, and individual viral videos can significantly affect averages.

The idea was to practise the complete process of collecting, cleaning, analysing and presenting data rather than build a perfect industry-wide benchmark.

## Running the project

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the cleaning and analysis scripts as needed. SQL queries are available in the `sql/` directory.
