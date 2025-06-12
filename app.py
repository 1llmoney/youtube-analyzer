import re
import requests
import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# --- Page Config ---
st.set_page_config(
    page_title="YouTube Channel Analyzer"
)

# --- Helpers ---
def extract_channel_id(url):
    url = url.split('?')[0]
    if 'channel/' in url:
        return url.split('channel/')[1]
    elif 'user/' in url:
        username = url.split('user/')[1]
        res = YOUTUBE.channels().list(part='id', forUsername=username).execute()
        return res['items'][0]['id']
    elif '/@' in url:
        handle = url.split('/@')[1]
        res = YOUTUBE.search().list(part='snippet', q=handle, type='channel', maxResults=1).execute()
        return res['items'][0]['snippet']['channelId']
    else:
        st.error("지원되지 않는 URL 형식입니다. /channel/, /user/ 또는 @handle 을 사용하세요.")
        return None

@st.cache_data
def fetch_video_list(channel_id):
    res = YOUTUBE.channels().list(part='contentDetails', id=channel_id).execute()
    uploads_pl = res['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    video_ids = []
    next_page = None
    while True:
        pl_res = YOUTUBE.playlistItems().list(
            part='snippet', playlistId=uploads_pl, maxResults=50, pageToken=next_page
        ).execute()
        # 업로드 순: API가 최신->과거 반환하므로 reverse 안 함
        video_ids += [item['snippet']['resourceId']['videoId'] for item in pl_res['items']]
        next_page = pl_res.get('nextPageToken')
        if not next_page:
            break
    return video_ids

@st.cache_data
def fetch_video_details(video_ids):
    stats = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        res = YOUTUBE.videos().list(
            part='snippet,statistics', id=','.join(batch)
        ).execute()
        for item in res['items']:
            stats.append({
                'id': item['id'],
                'title': item['snippet']['title'],
                'thumbnail': item['snippet']['thumbnails']['medium']['url'],
                'views': int(item['statistics'].get('viewCount', 0))
            })
    return pd.DataFrame(stats)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

# 사용자 API 키 입력
key = st.text_input("🔑 YouTube API 키를 입력하세요", type="password")
channel_url = st.text_input("🔗 분석할 YouTube 채널 URL을 입력하세요")

if key and channel_url:
    YOUTUBE = build('youtube', 'v3', developerKey=key)
    channel_id = extract_channel_id(channel_url)

    if channel_id:
        with st.spinner("영상 목록을 불러오는 중..."):
            vids = fetch_video_list(channel_id)
            df = fetch_video_details(vids)
        
        # 평균 조회수 및 등급 계산
        avg_views = df['views'].mean() if not df.empty else 0
        st.write(f"**채널 평균 조회수:** {avg_views:,.0f}")
        def grade(v):
            if v == 0:
                return '0'
            if avg_views == 0:
                return 'BAD'
            if v >= 1.5 * avg_views:
                return 'GREAT'
            if v >= avg_views:
                return 'GOOD'
            return 'BAD'
        df['label'] = df['views'].apply(grade)

        # 정렬 옵션
        sort_option = st.selectbox("정렬 기준 선택", ['업로드 순서', '등급별 정렬'])
        if sort_option == '등급별 정렬':
            order_map = {'GREAT': 0, 'GOOD': 1, 'BAD': 2, '0': 3}
            df = df.sort_values(by='label', key=lambda col: col.map(order_map))
        # 업로드 순서는 API 반환 순서 그대로 유지

        # 결과 출력
        for idx, row in df.iterrows():
            cols = st.columns([1, 3, 1])
            cols[0].image(row['thumbnail'], width=120)
            cols[1].markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
            # 등급 컬러 적용
            color = {
                'GREAT': '#CCFF00',
                'GOOD': '#00AA00',
                'BAD': '#DD0000',
                '0': '#888888'
            }.get(row['label'], '#000000')
            cols[2].markdown(f"<span style='color:{color}; font-weight:bold'>{row['label']}</span>", unsafe_allow_html=True)
            # 스크립트 다운로드
            if cols[2].button("스크립트 다운", key=f"txt_{idx}"):
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(row['id'])
                    text = "\n".join([seg['text'] for seg in transcript])
                    st.download_button(
                        label="TXT로 저장",
                        data=text,
                        file_name=f"{row['id']}.txt",
                        mime='text/plain'
                    )
                except Exception as e:
                    st.error(f"스크립트를 불러오는 중 오류 발생: {e}")




