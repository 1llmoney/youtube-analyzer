import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# --- Page Config ---
st.set_page_config(page_title="YouTube Channel Analyzer")

# --- Helpers ---
@st.cache_data
def search_videos_global(keyword, max_results=50):
    res = YOUTUBE.search().list(
        part="snippet",
        q=keyword,
        type="video",
        maxResults=max_results
    ).execute()
    return [item["id"]["videoId"] for item in res["items"]]

@st.cache_data
def search_videos_in_channel(channel_id, keyword, max_results=50):
    res = YOUTUBE.search().list(
        part="snippet",
        channelId=channel_id,
        q=keyword,
        type="video",
        maxResults=max_results
    ).execute()
    return [item["id"]["videoId"] for item in res["items"]]

@st.cache_data
def fetch_video_list(channel_id):
    uploads_pl = YOUTUBE.channels().list(
        part="contentDetails", id=channel_id
    ).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    video_ids, next_page = [], None
    while True:
        pl = YOUTUBE.playlistItems().list(
            part="snippet", playlistId=uploads_pl,
            maxResults=50, pageToken=next_page
        ).execute()
        video_ids += [i["snippet"]["resourceId"]["videoId"] for i in pl["items"]]
        next_page = pl.get("nextPageToken")
        if not next_page:
            break
    return video_ids

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

key         = st.text_input("🔑 YouTube API 키를 입력하세요", type="password")
channel_url = st.text_input("🔗 (선택) 분석할 채널 URL")
keyword     = st.text_input("🔎 (선택) 검색 키워드")
use_search  = st.checkbox("키워드 기반 글로벌 검색", help="체널 분석이 아니라 YouTube 전체에서 검색")

if key:
    YOUTUBE = build("youtube", "v3", developerKey=key)

    # 구독자 수 (채널 URL이 있을 때만)
    if channel_url:
        # extract channel_id (간단히 URL 뒤부분)
        channel_id = channel_url.split("?")[0].split("/")[-1]
        sub_info = YOUTUBE.channels().list(part="statistics", id=channel_id).execute()
        sub_count = int(sub_info["items"][0]["statistics"].get("subscriberCount", 0))
        st.write(f"**구독자 수:** {sub_count:,}")

    # 영상 ID 가져오기
    with st.spinner("영상 리스트 준비 중..."):
        if use_search and keyword:
            if channel_url:
                # 채널 내 검색
                ids = search_videos_in_channel(channel_id, keyword)
            else:
                # 전체 검색
                ids = search_videos_global(keyword)
        elif channel_url:
            # 채널 전체 업로드
            ids = fetch_video_list(channel_id)
        else:
            st.info("채널 URL 또는 검색 키워드를 입력하세요.")
            st.stop()

        df = fetch_video_details(ids)

    # 평균 정의 기준
    # — 채널 분석 시엔 채널 전체 평균, 글로벌 검색 시엔 검색 결과 평균
    if channel_url and not use_search:
        full_ids = fetch_video_list(channel_id)
        avg = fetch_video_details(full_ids)["views"].mean()
    else:
        avg = df["views"].mean() if not df.empty else 0
    st.write(f"**평균 조회수 기준:** {avg:,.0f}")

    # 등급 매기기
    def grade(v):
        if v == 0:        return "0"
        if avg == 0:      return "BAD"
        if v >= 1.5*avg:  return "GREAT"
        if v >= avg:      return "GOOD"
        return "BAD"

    df["label"] = df["views"].apply(grade)

    # 정렬 옵션
    sort = st.selectbox("정렬 기준", ["조회수 내림차순", "등급별 정렬"])
    if sort == "조회수 내림차순":
        df = df.sort_values("views", ascending=False)
    else:
        order = {"GREAT":0, "GOOD":1, "BAD":2, "0":3}
        df = df.sort_values(by="label", key=lambda c: c.map(order))

    # 결과 출력
    for i, row in df.iterrows():
        c1, c2, c3 = st.columns([1,3,1])
        c1.image(row["thumbnail"], width=120)
        c2.markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
        color = {"GREAT":"#CCFF00","GOOD":"#00AA00","BAD":"#DD0000","0":"#888888"}[row["label"]]
        c3.markdown(f"<span style='color:{color}; font-weight:bold'>{row['label']}</span>",
                    unsafe_allow_html=True)
        if c3.button("스크립트 다운", key=f"t{i}"):
            try:
                segs = YouTubeTranscriptApi.get_transcript(row["id"])
                text = "\n".join(s["text"] for s in segs)
                st.download_button("TXT 저장", text, file_name=f"{row['id']}.txt")
            except Exception as e:
                st.error(f"스크립트 오류: {e}")




