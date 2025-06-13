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
def search_videos(channel_id, keyword, max_results=50):
    # 유튜브 검색 API로 채널 + 키워드 영상 검색
    res = YOUTUBE.search().list(
        part='snippet', channelId=channel_id,
        q=keyword, type='video', maxResults=max_results
    ).execute()
    return [item['id']['videoId'] for item in res['items']]

@st.cache_data
def fetch_video_list(channel_id):
    # 기본: 채널 업로드 목록
    uploads_pl = YOUTUBE.channels().list(
        part='contentDetails', id=channel_id
    ).execute()['items'][0]['contentDetails']['relatedPlaylists']['uploads']
    video_ids, next_page = [], None
    while True:
        pl = YOUTUBE.playlistItems().list(
            part='snippet', playlistId=uploads_pl,
            maxResults=50, pageToken=next_page
        ).execute()
        video_ids += [i['snippet']['resourceId']['videoId'] for i in pl['items']]
        next_page = pl.get('nextPageToken')
        if not next_page:
            break
    return video_ids

@st.cache_data
def fetch_video_details(video_ids):
    df = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i+50]
        res = YOUTUBE.videos().list(
            part='snippet,statistics', id=','.join(batch)
        ).execute()
        for item in res['items']:
            df.append({
                'id': item['id'],
                'title': item['snippet']['title'],
                'thumbnail': f"https://img.youtube.com/vi/{item['id']}/mqdefault.jpg",
                'views': int(item['statistics'].get('viewCount', 0))
            })
    return pd.DataFrame(df)

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

key = st.text_input("🔑 YouTube API 키를 입력하세요", type="password")
channel_url = st.text_input("🔗 분석할 YouTube 채널 URL을 입력하세요")
keyword = st.text_input("🔎 검색 키워드 (선택)")
is_search = st.checkbox("키워드 기반 검색 사용")

if key and channel_url:
    YOUTUBE = build('youtube', 'v3', developerKey=key)
    channel_id = extract_channel_id(channel_url)
    if channel_id:
        # 구독자 수
        info = YOUTUBE.channels().list(part='statistics', id=channel_id).execute()['items'][0]['statistics']
        sub_count = int(info.get('subscriberCount', 0))
        st.write(f"**구독자 수:** {sub_count:,}")
        # 영상 ID 리스트
        with st.spinner("영상 목록 준비 중..."):
            if is_search and keyword:
                vids = search_videos(channel_id, keyword)
            else:
                vids = fetch_video_list(channel_id)
            df = fetch_video_details(vids)
        # 채널 전체 평균
        full = fetch_video_details(fetch_video_list(channel_id))
        avg = full['views'].mean() if not full.empty else 0
        st.write(f"**채널 평균 조회수:** {avg:,.0f}")
        # 등급 함수
        def grade(v):
            if v == 0: return '0'
            if avg == 0: return 'BAD'
            if v >= 1.5*avg: return 'GREAT'
            if v >= avg: return 'GOOD'
            return 'BAD'
        df['label'] = df['views'].apply(grade)
        # 정렬
        sort = st.selectbox("정렬 기준", ['업로드 순서', '등급별'])
        if sort=='등급별': df = df.sort_values(by='label', key=lambda c: c.map({'GREAT':0,'GOOD':1,'BAD':2,'0':3}))
        # 출력
        for i,row in df.iterrows():
            c1,c2,c3=st.columns([1,3,1])
            c1.image(row['thumbnail'],width=120)
            c2.markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
            color={'GREAT':'#CCFF00','GOOD':'#00AA00','BAD':'#DD0000','0':'#888888'}[row['label']]
            c3.markdown(f"<span style='color:{color};font-weight:bold'>{row['label']}</span>",unsafe_allow_html=True)
            if c3.button("스크립트",key=f"t{i}"):
                txt=YouTubeTranscriptApi.get_transcript(row['id'])
                text="\n".join(x['text'] for x in txt)
                st.download_button("다운", text, file_name=f"{row['id']}.txt")




