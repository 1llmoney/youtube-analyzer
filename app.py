import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# --- Page Config ---
st.set_page_config(page_title="YouTube Channel Analyzer")

# --- Helpers ---
@st.cache_data
def search_videos_global(keyword, max_results, region_code, duration):
    res = YOUTUBE.search().list(
        part="snippet",
        q=keyword,
        type="video",
        maxResults=max_results,
        regionCode=region_code,
        videoDuration=duration
    ).execute()
    return [item["id"]["videoId"] for item in res["items"]]

@st.cache_data
def search_videos_in_channel(channel_id, keyword, max_results, region_code, duration):
    res = YOUTUBE.search().list(
        part="snippet",
        channelId=channel_id,
        q=keyword,
        type="video",
        maxResults=max_results,
        regionCode=region_code,
        videoDuration=duration
    ).execute()
    return [item["id"]["videoId"] for item in res["items"]]

@st.cache_data
def fetch_video_list(channel_id):
    uploads_pl = YOUTUBE.channels().list(
        part="contentDetails", id=channel_id
    ).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids, next_page = [], None
    while True:
        pl = YOUTUBE.playlistItems().list(
            part="snippet", playlistId=uploads_pl,
            maxResults=50, pageToken=next_page
        ).execute()
        vids += [i["snippet"]["resourceId"]["videoId"] for i in pl["items"]]
        next_page = pl.get("nextPageToken")
        if not next_page:
            break
    return vids

@st.cache_data
def fetch_video_details(video_ids):
    rows = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        res = YOUTUBE.videos().list(
            part="snippet,statistics",
            id=",".join(batch)
        ).execute()
        for item in res["items"]:
            rows.append({
                "id": item["id"],
                "title": item["snippet"]["title"],
                "thumbnail": f"https://img.youtube.com/vi/{item['id']}/mqdefault.jpg",
                "views": int(item["statistics"].get("viewCount", 0))
            })
    return pd.DataFrame(rows)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

# 입력
key = st.text_input("🔑 YouTube API 키", type="password")
channel_url = st.text_input("🔗 채널 URL (선택)")
keyword = st.text_input("🔎 검색 키워드 (선택)")
use_search = st.checkbox("🔍 키워드 검색 모드")

# 검색 옵션
col1, col2, col3 = st.columns(3)
with col1:
    region = st.selectbox("검색 국가", ["KR", "US", "JP"], format_func=lambda x: {"KR":"한국", "US":"미국", "JP":"일본"}[x])
with col2:
    max_res = st.selectbox("검색 개수", [50, 100, 200])
with col3:
    dur = st.selectbox("영상 유형", ["any", "short", "long"], format_func=lambda x: {"any":"전체", "short":"쇼츠", "long":"롱폼"}[x])

if key:
    YOUTUBE = build("youtube", "v3", developerKey=key)
    channel_id = None
    # 채널 ID 추출
    if channel_url:
        channel_id = channel_url.split("?")[0].split("/")[-1]
        info = YOUTUBE.channels().list(part="statistics", id=channel_id).execute()["items"][0]["statistics"]
        st.write(f"**구독자 수:** {int(info.get('subscriberCount',0)):,}")

    # 영상 ID 취합
    if use_search and keyword:
        if channel_id:
            vids = search_videos_in_channel(channel_id, keyword, max_res, region, dur)
        else:
            vids = search_videos_global(keyword, max_res, region, dur)
    elif channel_id:
        vids = fetch_video_list(channel_id)
    else:
        st.info("채널 URL이나 키워드 검색 모드를 사용하세요.")
        st.stop()

    # 세부 정보 조회
    df = fetch_video_details(vids)

    # 평균 조회수 기준
    if channel_id and not (use_search and keyword):
        avg = fetch_video_details(fetch_video_list(channel_id))["views"].mean()
    else:
        avg = df["views"].mean() if not df.empty else 0
    st.write(f"**평균 조회수:** {avg:,.0f}")

    # 등급
    def grade(v):
        if v==0: return "0"
        if avg==0: return "BAD"
        if v>=1.5*avg: return "GREAT"
        if v>=avg: return "GOOD"
        return "BAD"
    df["label"] = df["views"].apply(grade)

    # 정렬
    order_map = {"GREAT":0, "GOOD":1, "BAD":2, "0":3}
    sort = st.selectbox("정렬", ["조회수 내림차순", "등급별"])
    if sort=="조회수 내림차순": df=df.sort_values("views", ascending=False)
    else: df=df.sort_values(by="label", key=lambda c: c.map(order_map))

    # 출력
    for i,row in df.iterrows():
        c1,c2,c3=st.columns([1,3,1])
        c1.image(row["thumbnail"], width=120)
        c2.markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
        color={'GREAT':'#CCFF00','GOOD':'#00AA00','BAD':'#DD0000','0':'#888888'}[row['label']]
        c3.markdown(f"<span style='color:{color}; font-weight:bold'>{row['label']}</span>", unsafe_allow_html=True)
        if c3.button("스크립트 다운", key=f"t{i}"):
            try:
                segs = YouTubeTranscriptApi.get_transcript(row['id'])
                txt = "\n".join(s['text'] for s in segs)
                st.download_button("다운로드", txt, file_name=f"{row['id']}.txt")
            except Exception as e:
                st.error(f"스크립트 오류: {e}")




