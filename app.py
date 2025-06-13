```python
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
def fetch_channel_stats(channel_id):
    res = YOUTUBE.channels().list(part='statistics', id=channel_id).execute()
    stats = res['items'][0]['statistics']
    return int(stats.get('subscriberCount', 0))

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
                'thumbnail': item['snippet']['thumbnails']['medium']['url'],
                'views': int(item['statistics'].get('viewCount', 0)),
                'publishedAt': item['snippet']['publishedAt']
            })
    return pd.DataFrame(stats)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

# 사용자 API 키 입력
def main():
    key = st.text_input("🔑 YouTube API 키를 입력하세요", type="password")
    channel_url = st.text_input("🔗 분석할 YouTube 채널 URL을 입력하세요")

    if key and channel_url:
        # build client with user key
        global YOUTUBE
        YOUTUBE = build('youtube', 'v3', developerKey=key)
        channel_id = extract_channel_id(channel_url)

        if channel_id:
            sub_count = fetch_channel_stats(channel_id)
            with st.spinner("영상 목록을 불러오는 중..."):
                vids = fetch_video_list(channel_id)
                df = fetch_video_details(vids)
                df = df.sort_values('views', ascending=False).reset_index(drop=True)

            avg_views = df['views'].mean()
            df['label'] = df['views'].apply(
                lambda v: '0' if v == 0 else ('GREAT' if v >= 1.5 * avg_views else ('GOOD' if v >= avg_views else 'BAD'))
            )

            sort_opt = st.selectbox("정렬 방식", ['조회수 내림차순','조회수 오름차순','구독자 수 내림차순','구독자 수 오름차순'])
            if sort_opt == '조회수 내림차순':
                df = df.sort_values('views', ascending=False)
            elif sort_opt == '조회수 오름차순':
                df = df.sort_values('views', ascending=True)

            st.markdown(f"**채널 구독자 수:** {sub_count:,}")
            st.markdown(f"**평균 조회수:** {avg_views:,.0f}")

            for idx, row in df.iterrows():
                # 게시일 문자열 변환
                try:
                    date_obj = pd.to_datetime(row['publishedAt'])
                    date_str = date_obj.strftime('%Y-%m-%d')
                except Exception:
                    date_str = ''

                cols = st.columns([1, 3, 1, 1])
                cols[0].image(row['thumbnail'], width=120)
                cols[1].markdown(
                    f"**{row['title']}**  
                     조회수: {row['views']:,}  
                     게시일: {date_str}"
                )
                cols[2].markdown(f"구독자: {sub_count:,}")
                star = '⭐️' if row['views'] >= 1.5 * avg_views else ''
                cols[3].markdown(f"{star} **{row['label']}**")
                if cols[3].button("스크립트 다운", key=idx):
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

if __name__ == '__main__':
    main()
```









