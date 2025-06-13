import pandas as pd
import streamlit as st
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from datetime import datetime, timedelta

# --- Page Config ---
st.set_page_config(page_title="YouTube Channel Analyzer")

# --- Helpers ---
@st.cache_data
def search_videos_global(keyword, max_results, region_code, duration, published_after, published_before):
    params = {
        'part': 'snippet',
        'q': keyword,
        'type': 'video',
        'maxResults': max_results,
        'regionCode': region_code,
        'videoDuration': duration
    }
    if published_after:
        params['publishedAfter'] = published_after
    if published_before:
        params['publishedBefore'] = published_before
    res = YOUTUBE.search().list(**params).execute()
    return [item['id']['videoId'] for item in res['items']]

@st.cache_data
def fetch_video_list(channel_id):
    uploads_pl = YOUTUBE.channels().list(part="contentDetails", id=channel_id).execute()["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]
    vids, token = [], None
    while True:
        resp = YOUTUBE.playlistItems().list(part="snippet", playlistId=uploads_pl, maxResults=50, pageToken=token).execute()
        vids += [(i["snippet"]["resourceId"]["videoId"], i["snippet"]["publishedAt"]) for i in resp["items"]]
        token = resp.get("nextPageToken")
        if not token:
            break
    return vids

@st.cache_data
def fetch_video_details(video_info):
    rows = []
    for i in range(0, len(video_info), 50):
        batch = video_info[i:i+50]
        ids = [v[0] for v in batch]
        pubs = {v[0]: v[1] for v in batch}
        res = YOUTUBE.videos().list(part="snippet,statistics", id=','.join(ids)).execute()
        for it in res['items']:
            vid = it['id']
            rows.append({
                'id': vid,
                'title': it['snippet']['title'],
                'thumbnail': f"https://img.youtube.com/vi/{vid}/mqdefault.jpg",
                'views': int(it['statistics'].get('viewCount', 0)),
                'channelId': it['snippet']['channelId'],
                'publishedAt': pd.to_datetime(pubs.get(vid, it['snippet']['publishedAt']))
            })
    return pd.DataFrame(rows)

@st.cache_data
def fetch_channel_subs(channel_ids):
    subs = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        res = YOUTUBE.channels().list(part='statistics', id=','.join(batch)).execute()
        for it in res['items']:
            subs[it['id']] = int(it['statistics'].get('subscriberCount', 0))
    return subs

# --- UI & Main ---
st.title("YouTube Channel Analyzer")

# 입력 옵션
key = st.text_input("🔑 YouTube API 키", type="password")
use_search = st.checkbox("🔍 키워드 검색 모드")
if use_search:
    keyword = st.text_input("🔎 검색 키워드")
else:
    channel_url = st.text_input("🔗 채널 URL")

col1, col2, col3, col4 = st.columns(4)
with col1:
    region = st.selectbox("검색 국가", ["KR","US","JP"], format_func=lambda x: {"KR":"한국","US":"미국","JP":"일본"}[x])
with col2:
    max_res = st.selectbox("검색 개수", [50,100,200,500])
with col3:
    dur = st.selectbox("영상 유형", ["any","short","long"], format_func=lambda x: {"any":"전체","short":"쇼츠","long":"롱폼"}[x])
with col4:
    period = st.selectbox("업로드 기간", ["전체","1개월 내","3개월 내","5개월 이상"])

# 기간 filter 계산
now = datetime.utcnow()
published_after = published_before = None
if period == "1개월 내":
    published_after = (now - timedelta(days=30)).isoformat('T') + 'Z'
elif period == "3개월 내":
    published_after = (now - timedelta(days=90)).isoformat('T') + 'Z'
elif period == "5개월 이상":
    published_before = (now - timedelta(days=150)).isoformat('T') + 'Z'

if key:
    YOUTUBE = build("youtube","v3",developerKey=key)

    # ID 목록 생성
    if use_search:
        if not keyword:
            st.warning("검색 키워드를 입력하세요.")
            st.stop()
        vids = search_videos_global(keyword, max_res, region, dur, published_after, published_before)
        sub_count = None
        vid_info = [(v,None) for v in vids]
    else:
        if not channel_url:
            st.warning("채널 URL을 입력하세요.")
            st.stop()
        cid = channel_url.split('?')[0].split('/')[-1]
        stats = YOUTUBE.channels().list(part='statistics', id=cid).execute()["items"][0]["statistics"]
        sub_count = int(stats.get('subscriberCount',0))
        st.write(f"**채널 구독자 수:** {sub_count:,}")
        vid_info = fetch_video_list(cid)

    df = fetch_video_details(vid_info)
    # 채널별 구독자 수 가져오기
    subs_map = fetch_channel_subs(df['channelId'].unique().tolist())
    df['channel_subs'] = df['channelId'].map(subs_map)

    # 평균 조회수
    avg_views = df['views'].mean() if not df.empty else 0
    st.write(f"**평균 조회수:** {avg_views:,.0f}")

    # 조회수 등급 함수
    def view_grade(v):
        if v==0: return '0'
        if avg_views==0: return 'BAD'
        if v>=1.5*avg_views: return 'GREAT'
        if v>=avg_views: return 'GOOD'
        return 'BAD'
    df['label'] = df['views'].apply(view_grade)

    # 정렬 옵션
    sort_option = st.selectbox("정렬 방식", [
        "조회수 내림차순","조회수 오름차순","등급별","구독자 수 내림차순","구독자 수 오름차순"
    ])
    if sort_option == "조회수 내림차순": df = df.sort_values('views',ascending=False)
    elif sort_option == "조회수 오름차순": df = df.sort_values('views',ascending=True)
    elif sort_option == "구독자 수 내림차순": df = df.sort_values('channel_subs',ascending=False)
    elif sort_option == "구독자 수 오름차순": df = df.sort_values('channel_subs',ascending=True)
    else: df = df.sort_values(by='label', key=lambda c: c.map({'GREAT':0,'GOOD':1,'BAD':2,'0':3}))

    # 결과 출력
    for idx, row in df.iterrows():
        cols = st.columns([1,4,1,1])
        cols[0].image(row['thumbnail'], width=120)
        cols[1].markdown(f"**{row['title']}**  \n조회수: {row['views']:,}")
        cols[2].markdown(f"구독자: {row['channel_subs']:,}")
        color = {'GREAT':'#CCFF00','GOOD':'#00AA00','BAD':'#DD0000','0':'#888888'}[row['label']]
        cols[3].markdown(f"<span style='color:{color};font-weight:bold'>{row['label']}</span>", unsafe_allow_html=True)
        if cols[3].button("스크립트 다운", key=idx):
            try:
                segs = YouTubeTranscriptApi.get_transcript(row['id'])
                txt = "\n".join(s['text']for s in segs)
                st.download_button("다운로드", txt, file_name=f"{row['id']}.txt")
            except Exception as e:
                st.error(f"스크립트 오류: {e}")





