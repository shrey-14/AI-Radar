"""
scrapers/talks/youtube.py — AI Radar
Source: YouTube Data API v3 + youtube-transcript-api
Auth:   YOUTUBE_API_KEY in .env

Transcript note:
  YouTube may block unauthenticated transcript requests.
  If you get IpBlocked errors, export your YouTube cookies:
    Chrome extension "Get cookies.txt LOCALLY" → open youtube.com → export → save as cookies.txt
    Then set COOKIES_PATH in .env or place cookies.txt in the project root.
"""
import os
import requests
from googleapiclient.discovery import build
from youtube_transcript_api import YouTubeTranscriptApi
from config import settings
from isodate import parse_duration

COOKIES_PATH = os.getenv("YOUTUBE_COOKIES_PATH", "cookies.txt")


def _build_ytt():
    """Build YouTubeTranscriptApi instance, loading cookies if available."""
    if os.path.exists(COOKIES_PATH):
        from http.cookiejar import MozillaCookieJar
        jar = MozillaCookieJar(COOKIES_PATH)
        jar.load(ignore_discard=True, ignore_expires=True)
        session = requests.Session()
        session.cookies = jar
        return YouTubeTranscriptApi(http_client=session)
    return YouTubeTranscriptApi()


def _fetch_transcript(ytt, video_id: str) -> tuple[bool, int, int, str, str]:
    """
    Returns (available, word_count, segment_count, preview, full_text).
    """
    try:
        transcript = ytt.fetch(video_id)
        full_text  = " ".join([t.text for t in transcript])
        words      = full_text.split()
        preview    = " ".join(words[:300])
        return True, len(words), len(transcript), preview, full_text
    except Exception:
        return False, None, None, None, None


# def scrape(channel_name: str, channel_id: str, limit: int = 2, **kwargs) -> list[dict]:
#     """
#     Fetch latest videos + transcripts from a YouTube channel.

#     Args:
#         channel_name: Display name e.g. 'Lex Fridman'
#         channel_id:   YouTube channel ID
#         limit:        Max videos to fetch
#     """
#     youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)
#     ytt     = _build_ytt()

#     # Fetch medium + long videos, deduplicate, sort by date
#     # def search(duration):
#     #     return youtube.search().list(
#     #         channelId=channel_id,
#     #         order="date",
#     #         part="snippet",
#     #         maxResults=limit * 2,
#     #         type="video",
#     #         videoDuration=duration,
#     #     ).execute().get("items", [])

#     # combined = {i["id"]["videoId"]: i for i in search("medium") + search("long")}
#     # items    = sorted(
#     #     combined.values(),
#     #     key=lambda x: x["snippet"]["publishedAt"],
#     #     reverse=True,
#     # )[:limit]

#     response = youtube.search().list(
#         channelId=channel_id,
#         order="date",
#         part="snippet",
#         maxResults=limit,
#         type="video",
#     ).execute()

#     items = response.get("items", [])

#     results = []

#     for item in items:
#         snippet  = item["snippet"]
#         video_id = item["id"]["videoId"]

#         avail, wc, sc, preview, full = _fetch_transcript(ytt, video_id)

#         results.append({
#             "id":                     video_id,
#             "channel":                channel_name,
#             "channel_id":             channel_id,
#             "video_url":              f"https://youtube.com/watch?v={video_id}",
#             "title":                  snippet["title"],
#             "description":            snippet.get("description", "")[:500],
#             "published_date":         snippet["publishedAt"][:10],
#             "transcript_available":   avail,
#             "transcript_word_count":  wc,
#             "transcript_segment_count": sc,
#             "transcript_preview":     preview,
#             "transcript_full":        full,
#         })

#     return results


def scrape(channel_name: str, channel_id: str, limit: int = 2, **kwargs) -> list[dict]:
    youtube = build("youtube", "v3", developerKey=settings.youtube_api_key)
    ytt     = _build_ytt()

    # 1. Search for latest videos
    response = youtube.search().list(
        channelId=channel_id, order="date", part="snippet",
        maxResults=limit, type="video",
    ).execute()
    items = response.get("items", [])

    # 2. Get durations via videos.list (contentDetails)
    video_ids = [item["id"]["videoId"] for item in items]
    details_resp = youtube.videos().list(
        part="contentDetails",
        id=",".join(video_ids),
    ).execute()

    duration_map = {}
    for vid in details_resp.get("items", []):
        vid_id   = vid["id"]
        iso_dur  = vid["contentDetails"]["duration"]   # e.g. "PT22M15S"
        duration_map[vid_id] = int(parse_duration(iso_dur).total_seconds())

    results = []
    for item in items:
        snippet  = item["snippet"]
        video_id = item["id"]["videoId"]
        avail, wc, sc, preview, full = _fetch_transcript(ytt, video_id)

        results.append({
            "id":                       video_id,
            "channel":                  channel_name,
            "channel_id":               channel_id,
            "video_url":                f"https://youtube.com/watch?v={video_id}",
            "title":                    snippet["title"],
            "description":              snippet.get("description", "")[:500],
            "published_date":           snippet["publishedAt"][:10],
            "duration_seconds":         duration_map.get(video_id),   # ← real duration
            "transcript_available":     avail,
            "transcript_word_count":    wc,
            "transcript_segment_count": sc,
            "transcript_preview":       preview,
            "transcript_full":          full,
        })

    return results