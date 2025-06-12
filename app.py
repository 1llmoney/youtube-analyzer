import re
import requests
import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

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
        st.error("Unsupported URL format. Use /channel/, /user/ or @handle URL.")
        return None

@st.cache_data
def fetch_video_list(channel_id):
    # fetch video IDs from uploads playlist
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
                'views': int(item['statistics'].get('viewCount', 0))
            })
    return pd.DataFrame(stats)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")
key = st.text_input("🔑 YouTube API 키를 입력하세요", type="password")
channel_url = st.text_input("🔗 분석할 YouTube 채널 URL을 입력하세요")

if key and channel_url:
    # build client with user key
    YOUTUBE = build('youtube', 'v3', developerKey=key)
    channel_id = extract_channel_id(channel_url)
    if channel_id:
        with st.spinner("Fetching videos..."):
            vids = fetch_video_list(channel_id)
            df = fetch_video_details(vids)
            df = df.sort_values('views', ascending=False).reset_index(drop=True)
        for idx, row in df.iterrows():
            cols = st.columns([1, 3, 1])
            cols[0].image(row['thumbnail'], width=120)
            cols[1].markdown(f"**{row['title']}**  \nViews: {row['views']:,}")
            if cols[2].button("Download Script", key=idx):
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(row['id'])
                    text = "\n".join([seg['text'] for seg in transcript])
                    st.download_button(label="Download TXT",
                                       data=text,
                                       file_name=f"{row['id']}.txt",
                                       mime='text/plain')
                except Exception as e:
                    st.error(f"No transcript available: {e}")

