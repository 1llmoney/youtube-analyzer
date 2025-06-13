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
def fetch_video_list(channel_id):
    uploads_pl = YOUTUBE.channels().list(
        part="contentDetails", id=channel_id
    ).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids, token = [], None
    while True:
        resp = YOUTUBE.playlistItems().list(
            part="snippet", playlistId=uploads_pl, maxResults=50, pageToken=token
        ).execute()
        vids += [i["snippet"]["resourceId"]["videoId"] for i in resp["items"]]
        token = resp.get("nextPageToken")
        if not token:
            break
    return vids

@st.cache_data
def fetch_video_details(video_ids):
    rows = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        res = YOUTUBE.videos().list(
            part="snippet,statistics",
            id=','.join(batch)
        ).execute()
        for it in res['items']:
            rows.append({
                'id': it['id'],
                'title': it['snippet']['title'],
                'thumbnail': f"https://img.youtube.com/vi/{it['id']}/mqdefault.jpg",
                'views': int(it['statistics'].get('viewCount', 0))
            })
    return pd.DataFrame(rows)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

# 입력 섹션
key = st.text_input("🔑 YouTube API 키", type="password")
use_search = st.checkbox("🔍 키워드 검색 모드")
if use_search:
    keyword = st.text_input("🔎 검색 키워드")
else:
    channel_url = st.text_input("🔗 채널 URL")

# 검색 옵션: 국가, 개수, 길이
col1, col2, col3 = st.columns(3)
with col1:
    region = st.selectbox("검색 국가", ["KR", "US", "JP"], format_func=lambda x: {"KR":"한국", "US":"미국", "JP":"일본"}[x])
with col2:
    max_res = st.selectbox("검색 개수", [50, 100, 200])
with col3:
    dur = st.selectbox("영상 유형", ["any", "short", "long"], format_func=lambda x: {"any":"전체", "short":"쇼츠", "long":"롱폼"}[x])

if key:
    YOUTUBE = build("youtube", "v3", developerKey=key)
    # 영상 ID 목록
    if use_search:
        if not keyword:
            st.warning("검색 키워드를 입력하세요.")
            st.stop()
        vids = search_videos_global(keyword, max_res, region, dur)
        sub_count = None
    else:
        if not channel_url:
            st.warning("채널 URL을 입력하세요.")
            st.stop()
        cid = channel_url.split('?')[0].split('/')[-1]
        stats = YOUTUBE.channels().list(part='statistics', id=cid).execute()["items"][0]["statistics"]
        sub_count = int(stats.get('subscriberCount', 0))
        st.write(f"**구독자 수:** {sub_count:,}")
        vids = fetch_video_list(cid)

    # 상세 정보
    df = fetch_video_details(vids)

    # 평균 조회수
    avg_views = df['views'].mean() if not df.empty else 0
    st.write(f"**평균 조회수:** {avg_views:,.0f}")

    # 조회수 등급
    def view_grade(v):
        if v == 0:
            return '0'
        if avg_views == 0:
            return 'BAD'
        if v >= 1.5 * avg_views:
            return 'GREAT'
        if v >= avg_views:
            return 'GOOD'
        return 'BAD'
    df['label'] = df['views'].apply(view_grade)

    # 정렬 옵션
    sort_option = st.selectbox("정렬 방식", [
        "조회수 내림차순", "조회수 오름차순", "등급별"
    ])
    if sort_option == "조회수 내림차순":
        df = df.sort_values('views', ascending=False)
    elif sort_option == "조회수 오름차순":
        df = df.sort_values('views', ascending=True)
    else:
        order = {'GREAT':0, 'GOOD':1, 'BAD':2, '0':3}
        df = df.sort_values(by='label', key=lambda c: c.map(order))

    # 결과 출력
    for idx, row in df.iterrows():
        cols = st.columns([1,4,1])
        cols[0].image(row['thumbnail'], width=120)
        cols[1].markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
        color = {'GREAT':'#CCFF00','GOOD':'#00AA00','BAD':'#DD0000','0':'#888888'}[row['label']]
        cols[2].markdown(
            f"<span style='color:{color};font-weight:bold'>{row['label']}</span>",
            unsafe_allow_html=True
        )
        if cols[2].button("스크립트 다운", key=idx):
            try:
                segs = YouTubeTranscriptApi.get_transcript(row['id'])
                txt = "\n".join(s['text'] for s in segs)
                st.download_button("다운로드", txt, file_name=f"{row['id']}.txt")
            except Exception as e:
                st.error(f"스크립트 오류: {e}")





