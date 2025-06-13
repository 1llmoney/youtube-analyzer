import re
import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi

# --- Page config ---
st.set_page_config(page_title="YouTube Channel Analyzer")

# --- Helpers ---
def extract_channel_id(url):
    url = url.split('?')[0]
    if 'channel/' in url:
        return url.split('channel/')[1]
    if 'user/' in url:
        name = url.split('user/')[1]
        res = youtube.channels().list(part='id', forUsername=name).execute()
        return res['items'][0]['id']
    if '/@' in url:
        handle = url.split('/@')[1]
        res = youtube.search().list(
            part='snippet', q=handle, type='channel', maxResults=1
        ).execute()
        return res['items'][0]['snippet']['channelId']
    st.error("지원되지 않는 URL 형식입니다.")
    return None

@st.cache_data
def fetch_channel_videos(cid):
    pl = youtube.channels().list(part='contentDetails', id=cid).execute()
    upl = pl['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    vids, token = [], None
    while True:
        r = youtube.playlistItems().list(
            part='snippet', playlistId=upl, maxResults=50, pageToken=token
        ).execute()
        vids += [i['snippet']['resourceId']['videoId'] for i in r['items']]
        token = r.get('nextPageToken')
        if not token:
            break
    return vids

@st.cache_data
def fetch_video_details(vids):
    rows = []
    for i in range(0, len(vids), 50):
        batch = vids[i:i+50]
        r = youtube.videos().list(
            part='snippet,statistics', id=','.join(batch)
        ).execute()
        for it in r.get('items', []):
            rows.append({
                'id': it['id'],
                'title': it['snippet']['title'],
                'thumb': it['snippet']['thumbnails']['medium']['url'],
                'views': int(it['statistics'].get('viewCount', 0)),
                'pub': it['snippet']['publishedAt'][:10],  # YYYY-MM-DD
            })
    return pd.DataFrame(rows)

@st.cache_data
def fetch_sub_count(cid):
    r = youtube.channels().list(part='statistics', id=cid).execute()
    return int(r['items'][0]['statistics'].get('subscriberCount', 0))

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

key = st.text_input("🔑 YouTube API 키", type="password")
url = st.text_input("🔗 분석할 YouTube 채널 URL")

if key and url:
    youtube = build('youtube', 'v3', developerKey=key)
    cid = extract_channel_id(url)
    if cid:
        subs = fetch_sub_count(cid)
        st.metric("구독자 수", f"{subs:,}")
        vids = fetch_channel_videos(cid)
        df = fetch_video_details(vids)
        df = df.sort_values('views', ascending=False).reset_index(drop=True)

        avg = df['views'].mean()
        df['grade'] = df['views'].apply(
            lambda v: '0' if v == 0 else ('GREAT' if v >= 1.5*avg else ('GOOD' if v >= avg else 'BAD'))
        )

        # 정렬 옵션
        order = st.selectbox("정렬 방식", ["조회수 내림차순", "조회수 오름차순", "등급순"])
        if order == "조회수 내림차순":
            df = df.sort_values('views', ascending=False)
        elif order == "조회수 오름차순":
            df = df.sort_values('views', ascending=True)
        else:
            rank = {'GREAT':0, 'GOOD':1, 'BAD':2, '0':3}
            df['r'] = df['grade'].map(rank)
            df = df.sort_values('r').drop(columns='r')

        # 결과 출력
        for idx, row in df.iterrows():
            c1, c2, c3 = st.columns([1, 4, 1])
            c1.image(row['thumb'], width=120)
            # 제목, 조회수, 게시일, 등급
            c2.markdown(
                f"**{row['title']}**  \n"
                f"조회수: {row['views']:,}  \n"
                f"게시일: {row['pub']}  \n"
                f"등급: {row['grade']}"
            )
            if c3.button("스크립트 다운", key=idx):
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(row['id'])
                    text = "\n".join([seg['text'] for seg in transcript])
                    st.download_button(
                        label="TXT로 저장",
                        data=text,
                        file_name=f"{row['id']}.txt",
                        mime='text/plain',
                        key=f"dl{idx}"
                    )
                except Exception as e:
                    st.error(f"스크립트 불러오기 오류: {e}")












