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
    st.error("URL 형식 오류 (→ /channel/, /user/, 또는 @handle)")
    return None

@st.cache_data
def fetch_channel_videos(cid):
    # 채널 업로드 플레이리스트에서 전부 가져오기
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
def fetch_search_videos(q, country, count, vtype, period):
    # 유튜브 Search API
    params = dict(part='snippet', q=q, maxResults=count, type='video', regionCode=country)
    if vtype != '전체': params['videoDuration'] = 'short' if vtype=='쇼츠' else 'long'
    if period!='전체':
        # 1개월 내 → 'month' etc
        mp = {'1개월내':'month','3개월내':'quarter','5개월 이상':'year'}[period]
        params['publishedAfter'] = pd.Timestamp.now() - pd.DateOffset(**{'months':1 if mp=='month' else 3 if mp=='quarter' else 6})
    res = youtube.search().list(**params).execute()
    return [i['id']['videoId'] for i in res['items']]

@st.cache_data
def fetch_video_details(vids):
    rows=[]
    for i in range(0, len(vids), 50):
        b=vids[i:i+50]
        r=youtube.videos().list(part='snippet,statistics', id=','.join(b)).execute()
        for it in r.get('items', []):
            rows.append({
                'id': it['id'],
                'title': it['snippet']['title'],
                'thumb': it['snippet']['thumbnails']['medium']['url'],
                'views': int(it['statistics'].get('viewCount',0)),
                'pub': it['snippet']['publishedAt'],
            })
    return pd.DataFrame(rows)

@st.cache_data
def fetch_sub_count(cid):
    r=youtube.channels().list(part='statistics', id=cid).execute()
    return int(r['items'][0]['statistics'].get('subscriberCount',0))

# --- UI ---
st.title("YouTube Channel Analyzer")

key = st.text_input("🔑 YouTube API 키", type="password")
use_search = st.checkbox("🔍 키워드 검색 모드")
if use_search:
    kw = st.text_input("🔎 검색 키워드")
    country = st.selectbox("검색 국가", ["KR","US","JP"], format_func=lambda x:{"KR":"한국","US":"미국","JP":"일본"}[x])
    cnt = st.selectbox("검색 개수", [50,100,200,500])
    vtype= st.selectbox("영상 유형", ["전체","쇼츠","롱폼"])
    period=st.selectbox("업로드 기간", ["전체","1개월내","3개월내","5개월 이상"])
else:
    url=st.text_input("🔗 채널 URL")

if key and ( (use_search and kw) or (not use_search and url) ):
    youtube = build('youtube','v3',developerKey=key)

    if use_search:
        vids = fetch_search_videos(kw, country, cnt, vtype, period)
        cid = None
    else:
        cid = extract_channel_id(url)
        vids = fetch_channel_videos(cid) if cid else []

    if vids:
        df = fetch_video_details(vids)
        avg = df['views'].mean()
        if cid:
            subs = fetch_sub_count(cid)
        else:
            subs = None

        # 등급 및 구독자 초과 영상 표시
        df['grade'] = df['views'].apply(
            lambda v: '0' if v==0 else ('GREAT' if v>=1.5*avg else ('GOOD' if v>=avg else 'BAD'))
        )
        df['star'] = df['views'] >= 1.5*(subs if subs else avg)

        # 정렬
        order = st.selectbox("정렬 기준", ["조회수↓","조회수↑","등급","구독자수↓","구독자수↑"])
        if order=="조회수↓": df=df.sort_values('views',ascending=False)
        elif order=="조회수↑": df=df.sort_values('views',ascending=True)
        elif order=="등급":
            ordm={'GREAT':0,'GOOD':1,'BAD':2,'0':3}
            df['o']=df['grade'].map(ordm); df=df.sort_values('o').drop(columns='o')
        elif order=="구독자수↓": df=df.sort_values('star',ascending=False)
        else: df=df.sort_values('star',ascending=True)

        # 테이블 표시
        for i,row in df.iterrows():
            c1,c2,c3=st.columns([1,4,1])
            c1.image(row['thumb'],width=120)
            txt = f"**{row['title']}**\n조회수: {row['views']:,}"
            if subs:
                txt += f"\n구독자: {subs:,}"
            txt += f"\n게시일: {row['pub'][:10]}"
            txt += f"\n등급: {'⭐ '+row['grade'] if row['star'] else row['grade']}"
            c2.markdown(txt)
            if c3.button("스크립트 다운",key=i):
                try:
                    t = YouTubeTranscriptApi.get_transcript(row['id'])
                    txt="\n".join([s['text'] for s in t])
                    st.download_button("TXT로 저장",txt,f"{row['id']}.txt","text/plain",key=f"dl{i}")
                except Exception as e:
                    st.error(f"스크립트 오류: {e}")











