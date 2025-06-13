import re
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
                'views': int(item['statistics'].get('viewCount', 0))
            })
    return pd.DataFrame(stats)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

key = st.text_input("🔑 YouTube API 키를 입력하세요", type="password")
channel_url = st.text_input("🔗 분석할 YouTube 채널 URL을 입력하세요")
keyword = st.text_input("🔎 제목 키워드 필터 (선택)")
sort_option = st.selectbox("정렬 기준 선택", ['업로드 순서', '등급별 정렬'])

if key and channel_url:
    YOUTUBE = build('youtube', 'v3', developerKey=key)
    channel_id = extract_channel_id(channel_url)
    if channel_id:
        # 구독자 수 가져오기
        ch_info = YOUTUBE.channels().list(part='statistics', id=channel_id).execute()
        sub_count = int(ch_info['items'][0]['statistics'].get('subscriberCount', 0))
        st.write(f"**구독자 수:** {sub_count:,}")
        
        with st.spinner("영상 목록을 불러오는 중..."):
            vids = fetch_video_list(channel_id)
            df = fetch_video_details(vids)

        # 키워드 필터링
        if keyword:
            df = df[df['title'].str.contains(keyword, case=False, na=False)]

        # 평균 조회수 (채널 전체)
        full_df = fetch_video_details(fetch_video_list(channel_id))
        avg_views = full_df['views'].mean() if not full_df.empty else 0
        st.write(f"**채널 평균 조회수:** {avg_views:,.0f}")

        # 등급 부여 함수
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

        # 정렬
        if sort_option == '등급별 정렬':
            order_map = {'GREAT': 0, 'GOOD': 1, 'BAD': 2, '0': 3}
            df = df.sort_values(by='label', key=lambda col: col.map(order_map))
        # 업로드 순서는 API 반환 순

        # 결과 출력
        for idx, row in df.iterrows():
            cols = st.columns([1, 3, 1])
            cols[0].image(f"https://img.youtube.com/vi/{row['id']}/mqdefault.jpg", width=120)
            cols[1].markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
            color = {'GREAT':'#CCFF00', 'GOOD':'#00AA00', 'BAD':'#DD0000', '0':'#888888'}[row['label']]
            cols[2].markdown(f"<span style='color:{color}; font-weight:bold'>{row['label']}</span>", unsafe_allow_html=True)
            if cols[2].button("스크립트 다운", key=f"txt_{idx}"):
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(row['id'])
                    text = "\n".join([seg['text'] for seg in transcript])
                    st.download_button("TXT로 저장", text, file_name=f"{row['id']}.txt")
                except Exception as e:
                    st.error(f"스크립트를 불러오는 중 오류 발생: {e}")




