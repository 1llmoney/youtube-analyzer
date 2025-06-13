import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta

# --- Page Config ---
st.set_page_config(page_title="YouTube Channel Analyzer", layout="wide")

# --- Helpers ---
@st.cache_data
def search_videos_global(keyword, max_results, region_code, duration, published_after, published_before):
    all_ids = []
    next_token = None
    while len(all_ids) < max_results:
        batch_size = min(500, max_results - len(all_ids))
        params = {
            'part': 'snippet',
            'q': keyword,
            'type': 'video',
            'maxResults': batch_size,
            'regionCode': region_code,
            'videoDuration': duration,
            'pageToken': next_token
        }
        if published_after:
            params['publishedAfter'] = published_after
        if published_before:
            params['publishedBefore'] = published_before

        res = YOUTUBE.search().list(**params).execute()
        all_ids += [item['id']['videoId'] for item in res['items']]
        next_token = res.get('nextPageToken')
        if not next_token:
            break

    return all_ids[:max_results]

@st.cache_data
def fetch_video_list(channel_id):
    uploads_pl = YOUTUBE.channels().list(
        part="contentDetails", id=channel_id
    ).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids, token = [], None
    while True:
        resp = YOUTUBE.playlistItems().list(
            part="snippet", playlistId=uploads_pl,
            maxResults=50, pageToken=token
        ).execute()
        for i in resp["items"]:
            vids.append((i["snippet"]["resourceId"]["videoId"], i["snippet"]["publishedAt"]))
        token = resp.get("nextPageToken")
        if not token:
            break
    return vids

@st.cache_data
def fetch_video_details(video_info):
    rows = []
    for i in range(0, len(video_info), 50):
        batch = video_info[i:i+50]
        ids = [v[0] for v in batch]
        pubs = {v[0]: v[1] for v in batch}
        res = YOUTUBE.videos().list(
            part="snippet,statistics", id=",".join(ids)
        ).execute()
        for it in res["items"]:
            vid = it["id"]
            pub = pubs.get(vid) or it["snippet"]["publishedAt"]
            stats = it.get('statistics', {})
            rows.append({
                "id": vid,
                "title": it["snippet"]["title"],
                "thumbnail": f"https://img.youtube.com/vi/{vid}/mqdefault.jpg",
                "views": int(stats.get("viewCount", 0)),
                "likes": int(stats.get("likeCount", 0)),
                "comments": int(stats.get("commentCount", 0)),
                "channelId": it["snippet"]["channelId"],
                "channelTitle": it["snippet"]["channelTitle"],
                "publishedAt": pd.to_datetime(pub)
            })
    return pd.DataFrame(rows)

@st.cache_data
def fetch_channel_subs(channel_ids):
    subs = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        res = YOUTUBE.channels().list(
            part="statistics", id=",".join(batch)
        ).execute()
        for it in res["items"]:
            subs[it["id"]] = int(it["statistics"].get("subscriberCount", 0))
    return subs

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

key = st.text_input("🔑 YouTube API 키", type="password")
use_search = st.checkbox("🔍 키워드 검색 모드")
if use_search:
    keyword = st.text_input("🔎 검색 키워드")
else:
    channel_url = st.text_input("🔗 채널 URL")

col1, col2, col3, col4 = st.columns(4)
with col1:
    region = st.selectbox("검색 국가", ["KR","US","JP"],
        format_func=lambda x: {"KR":"한국","US":"미국","JP":"일본"}[x]
    )
with col2:
    max_res = st.selectbox("검색 개수", [50,100,200,500,1000])
with col3:
    dur = st.selectbox("영상 유형", ["any","short","long"],
        format_func=lambda x: {"any":"전체","short":"쇼츠","long":"롱폼"}[x]
    )
with col4:
    period = st.selectbox("업로드 기간", ["전체","1개월 내","3개월 내","5개월 이상"] )

now = datetime.utcnow()
published_after = published_before = None
if period == "1개월 내": published_after = (now - timedelta(days=30)).isoformat('T')+'Z'
elif period == "3개월 내": published_after = (now - timedelta(days=90)).isoformat('T')+'Z'
elif period == "5개월 이상": published_before = (now - timedelta(days=150)).isoformat('T')+'Z'

if key:
    YOUTUBE = build("youtube","v3",developerKey=key)

    if use_search:
        if not keyword: st.warning("검색 키워드를 입력하세요."); st.stop()
        vids = search_videos_global(keyword, max_res, region, dur, published_after, published_before)
        vid_info = [(v,None) for v in vids]
        sub_count = None
    else:
        if not channel_url: st.warning("채널 URL을 입력하세요."); st.stop()
        cid = channel_url.split('?')[0].split('/')[-1]
        stats = YOUTUBE.channels().list(part="statistics", id=cid).execute()["items"][0]["statistics"]
        sub_count = int(stats.get("subscriberCount",0))
        st.markdown(f"**채널 구독자 수: {sub_count:,}명**")
        vid_info = fetch_video_list(cid)

    df = fetch_video_details(vid_info)
    subs_map = fetch_channel_subs(df["channelId"].unique().tolist())
    df["channel_subs"] = df["channelId"].map(subs_map)

    avg_views = df["views"].mean() if not df.empty else 0
    st.metric("평균 조회수", f"{avg_views:,.0f}")

    def view_grade(v):
        if v==0: return "0"
        if avg_views==0: return "BAD"
        if v>=1.5*avg_views: return "GREAT"
        if v>=avg_views:     return "GOOD"
        return "BAD"
    df["label"] = df["views"].apply(view_grade)

    sort_option = st.selectbox("정렬 방식",[
        "조회수 내림차순","조회수 오름차순",
        "구독자 수 내림차순","구독자 수 오름차순",
        "등급별"
    ])
    if   sort_option=="조회수 내림차순": df=df.sort_values("views",ascending=False)
    elif sort_option=="조회수 오름차순": df=df.sort_values("views",ascending=True)
    elif sort_option=="구독자 수 내림차순": df=df.sort_values("channel_subs",ascending=False)
    elif sort_option=="구독자 수 오름차순": df=df.sort_values("channel_subs",ascending=True)
    else: df=df.sort_values(by="label",key=lambda c:c.map({"GREAT":0,"GOOD":1,"BAD":2,"0":3}))

    color_map={"GREAT":"#CCFF00","GOOD":"#00AA00","BAD":"#DD0000","0":"#888888"}

    for idx,row in df.iterrows():
        star = "⭐️" if (row["channel_subs"]>0 and row["views"]>=1.5*row["channel_subs"]) else ""
        cols = st.columns([1,4,1,1,1])
        cols[0].image(row["thumbnail"],width=120)
        url = f"https://www.youtube.com/watch?v={row['id']}"
        # Channel title in bold, strong font
        cols[1].markdown(
            f"**{row['channelTitle']}**  \n"
            f"{star} [{row['title']}]({url})  \n"
            f"조회수: {row['views']:,}  |  좋아요: {row['likes']:,}  |  댓글: {row['comments']:,}"  
        , unsafe_allow_html=True)
        date_str = row["publishedAt"].strftime("%Y-%m-%d") if pd.notnull(row["publishedAt"]) else "N/A"
        cols[2].markdown(f"게시일: {date_str}")
        cols[3].markdown(f"구독자: {row['channel_subs']:,}")
        lbl=row['label']
        html = f"<span style='color:{color_map[lbl]};font-weight:bold'>{lbl}</span>"
        cols[4].markdown(html,unsafe_allow_html=True)




















