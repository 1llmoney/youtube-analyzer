import re
import requests
import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# --- Config ---
API_KEY = "AIzaSyDQ3vIyF0IVWfLo9tW86C0tb-14wIRjynw"
YOUTUBE = build('youtube', 'v3', developerKey=API_KEY)

# --- Helpers ---
def extract_channel_id(url):
    if 'channel/' in url:
        return url.split('channel/')[1].split('?')[0]
    elif 'user/' in url:
        username = url.split('user/')[1].split('?')[0]
        res = YOUTUBE.channels().list(part='id', forUsername=username).execute()
        return res['items'][0]['id']
    elif '/@' in url:  # 핸들 주소 지원
        handle = url.split('/@')[1].split('?')[0]
        # search API로 채널 찾기
        res = YOUTUBE.search().list(part='snippet', q=handle, type='channel', maxResults=1).execute()
        return res['items'][0]['snippet']['channelId']
    else:
        st.error("Unsupported URL format. Use /channel/, /user/ or @handle URL.")
        return None


@st.cache
def fetch_video_list(channel_id, max_results=50):
    ch = YOUTUBE.channels().list(
        part='contentDetails', id=channel_id
    ).execute()
    uploads_id = ch['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    video_ids = []
    next_page = None
    while True:
        pl_request = YOUTUBE.playlistItems().list(
            part='contentDetails', playlistId=uploads_id,
            maxResults=50, pageToken=next_page
        )
        pl_response = pl_request.execute()
        for item in pl_response['items']:
            video_ids.append(item['contentDetails']['videoId'])
        next_page = pl_response.get('nextPageToken')
        if not next_page or len(video_ids) >= max_results:
            break
    return video_ids[:max_results]

@st.cache
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

st.title("YouTube Channel Analyzer")
channel_url = st.text_input("Enter YouTube channel URL:")
if channel_url:
    channel_id = extract_channel_id(channel_url)
    if channel_id:
        with st.spinner("Fetching videos..."):
            vids = fetch_video_list(channel_id)
            df = fetch_video_details(vids)
            df = df.sort_values('views', ascending=False).reset_index(drop=True)

        for idx, row in df.iterrows():
            cols = st.columns([1,3,1])
            cols[0].image(row['thumbnail'], width=120)
            cols[1].markdown(f"**{row['title']}**  \nViews: {row['views']:,}")
            if cols[2].button("Download Script", key=idx):
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(row['id'])
                    text = "\n".join([seg['text'] for seg in transcript])
                    st.download_button(
                        label="Download TXT",
                        data=text,
                        file_name=f"{row['id']}_script.txt",
                        mime="text/plain"
                    )
                except Exception as e:
                    st.error(f"No transcript available: {e}")
