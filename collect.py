#!/usr/bin/env python3
"""
Collect channel statistics and the 10 newest video metadata for creators.csv.
Install: python -m pip install yt-dlp pandas
Run: python collect.py
"""
import pandas as pd, subprocess, json, sys, datetime, re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
TODAY=datetime.date.today().isoformat()
creators=pd.read_csv(ROOT/"creators.csv",dtype=str).fillna("NA")
videos=[]
def extract(url):
    cmd=["yt-dlp","--dump-single-json","--no-warnings","--skip-download",url]
    p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
    if p.returncode: return None
    try: return json.loads(p.stdout.splitlines()[-1])
    except: return None
for _,c in creators.iterrows():
    print("Channel:",c.channel_name,flush=True)
    channel=extract(c.channel_url)
    if not channel:
        print("  channel extraction failed")
        continue
    creators.loc[creators.creator_id==c.creator_id,"subscriber_count"]=channel.get("channel_follower_count","NA") or "NA"
    creators.loc[creators.creator_id==c.creator_id,"total_channel_views"]=channel.get("view_count","NA") or "NA"
    # Use playlist entries, then fetch each video separately for metrics
    entries=channel.get("entries") or []
    if len(entries)<10:
        playlist=extract(c.channel_url.rstrip("/")+"/videos")
        entries=(playlist or {}).get("entries") or entries
    for e in entries[:10]:
        vid=e.get("id")
        if not vid: continue
        url=e.get("url") or ("https://www.youtube.com/watch?v="+vid)
        info=extract(url)
        if not info:
            info=e
        duration=info.get("duration")
        webpage=info.get("webpage_url") or url
        fmt="Short" if "/shorts/" in webpage or (duration is not None and duration<=180) else "Long-form"
        def val(x): return "NA" if x is None else x
        videos.append({
            "creator_id":c.creator_id,"channel_name":c.channel_name,
            "video_title":val(info.get("title")),"video_url":webpage,
            "upload_date":val(info.get("upload_date")),
            "views":val(info.get("view_count")),"likes":val(info.get("like_count")),
            "comments":val(info.get("comment_count")),"format":fmt,
            "data_collected_on":TODAY,"source_url":webpage
        })
creators["data_collected_on"]=TODAY
creators.to_csv(ROOT/"creators.csv",index=False)
pd.DataFrame(videos,columns=["creator_id","channel_name","video_title","video_url","upload_date","views","likes","comments","format","data_collected_on","source_url"]).to_csv(ROOT/"videos.csv",index=False)
print(f"Saved {len(creators)} creators and {len(videos)} videos.")
