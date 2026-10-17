#!/usr/bin/env python3
"""유튜브 쇼츠 + 인스타 릴스에서 주제별로 잘 나온 영상을 찾아 점수순으로 정리한다.

인증
  - 유튜브: 환경의 Network secret이 www.googleapis.com 요청에 X-Goog-Api-Key 헤더를 붙인다.
    없으면 환경 변수 YOUTUBE_API_KEY를 쓴다.
  - Apify: Network secret이 api.apify.com 요청에 Authorization 헤더를 붙인다.
    없으면 환경 변수 APIFY_TOKEN을 쓴다.

사용법
  python3 shorts_finder.py check
  python3 shorts_finder.py run --config keywords.json --out shorts-finder [--skip-youtube] [--skip-instagram]
"""

import argparse
import csv
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

import requests

YT_API = "https://www.googleapis.com/youtube/v3"
APIFY_API = "https://api.apify.com/v2"
SHORTS_MAX_SECONDS = 180
NOW = dt.datetime.now(dt.timezone.utc)


# ---------- 공통 ----------

def yt_get(endpoint, params):
    key = os.environ.get("YOUTUBE_API_KEY")
    if key:
        params = {**params, "key": key}
    r = requests.get(f"{YT_API}/{endpoint}", params=params, timeout=30)
    data = r.json()
    if "error" in data:
        raise RuntimeError(f"YouTube API 오류: {data['error'].get('message')}")
    return data


def apify_headers():
    token = os.environ.get("APIFY_TOKEN")
    return {"Authorization": f"Bearer {token}"} if token else {}


def apify_run(actor, payload, timeout=900):
    """Actor를 실행하고 끝날 때까지 기다린 뒤 결과 행을 돌려준다.
    동기 엔드포인트는 오래 걸리면 연결이 끊기므로 실행 → 대기 → 결과 조회로 나눈다."""
    r = requests.post(f"{APIFY_API}/acts/{actor.replace('/', '~')}/runs",
                      params={"timeout": timeout}, json=payload, headers=apify_headers(), timeout=60).json()
    if "error" in r:
        raise RuntimeError(f"Apify 오류: {r['error'].get('message')}")
    run = r["data"]
    while run["status"] in ("READY", "RUNNING"):
        run = requests.get(f"{APIFY_API}/actor-runs/{run['id']}", params={"waitForFinish": 60},
                           headers=apify_headers(), timeout=90).json()["data"]
    if run["status"] != "SUCCEEDED":
        raise RuntimeError(f"Apify 실행 실패: {run['status']} (run {run['id']})")
    print(f"  [Apify] {actor} 비용 ${run.get('usageTotalUsd') or 0:.3f}", file=sys.stderr)
    return requests.get(f"{APIFY_API}/datasets/{run['defaultDatasetId']}/items",
                        params={"clean": 1}, headers=apify_headers(), timeout=120).json()


def parse_time(s):
    return dt.datetime.fromisoformat(s.replace("Z", "+00:00"))


def days_since(ts):
    return max((NOW - parse_time(ts)).total_seconds() / 86400, 1.0)


def iso_duration_seconds(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return None
    days, h, mi, s = (int(x or 0) for x in m.groups())
    return days * 86400 + h * 3600 + mi * 60 + s


def relevant(text, words):
    text = (text or "").lower()
    return any(w.lower() in text for w in words)


def add_scores(row):
    views, fans = row["views"] or 0, row["followers"] or 0
    row["viral_ratio"] = round(views / fans, 2) if fans else None
    row["views_per_day"] = round(views / days_since(row["published"]))
    eng = (row["likes"] or 0) + (row["comments"] or 0)
    row["engagement"] = round(eng / views * 100, 2) if views else None
    return row


# ---------- 유튜브 ----------

def collect_youtube(cfg):
    after = (NOW - dt.timedelta(days=cfg.get("days", 90))).strftime("%Y-%m-%dT%H:%M:%SZ")
    hits = {}
    for theme, keywords in cfg["themes"].items():
        for kw in keywords.get("youtube", []):
            data = yt_get("search", {
                "part": "id", "q": kw, "type": "video", "videoDuration": "short",
                "order": "viewCount", "publishedAfter": after, "regionCode": "KR",
                "relevanceLanguage": "ko", "maxResults": cfg.get("youtube_per_keyword", 50),
            })
            for item in data.get("items", []):
                hits.setdefault(item["id"]["videoId"], (theme, kw))
            print(f"  [YT] {theme} / {kw}: {len(data.get('items', []))}개", file=sys.stderr)

    ids = list(hits)
    videos = []
    for i in range(0, len(ids), 50):
        data = yt_get("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids[i:i + 50])})
        videos += data.get("items", [])

    channel_ids = list({v["snippet"]["channelId"] for v in videos})
    subs = {}
    for i in range(0, len(channel_ids), 50):
        data = yt_get("channels", {"part": "statistics", "id": ",".join(channel_ids[i:i + 50])})
        for c in data.get("items", []):
            st = c["statistics"]
            subs[c["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))

    rows = []
    for v in videos:
        sec = iso_duration_seconds(v["contentDetails"].get("duration"))
        if sec is None or sec > SHORTS_MAX_SECONDS:
            continue
        sn, st = v["snippet"], v["statistics"]
        theme, kw = hits[v["id"]]
        rows.append(add_scores({
            "platform": "YouTube", "theme": theme, "keyword": kw,
            "title": sn["title"], "account": sn["channelTitle"],
            "url": f"https://www.youtube.com/shorts/{v['id']}",
            "published": sn["publishedAt"], "seconds": sec,
            "views": int(st.get("viewCount", 0)), "likes": int(st.get("likeCount", 0)),
            "comments": int(st.get("commentCount", 0)), "followers": subs.get(sn["channelId"]),
        }))
    return rows


# ---------- 인스타 ----------

def collect_instagram(cfg):
    # 인스타 해시태그 페이지는 최근 글이 아니라 인기 글 위주라, 날짜는 받은 뒤에 거른다.
    cutoff = NOW - dt.timedelta(days=cfg.get("instagram_days", 365))
    tag_theme = {}
    for theme, keywords in cfg["themes"].items():
        for tag in keywords.get("instagram", []):
            tag_theme[tag] = theme
    if not tag_theme:
        return []

    urls = [f"https://www.instagram.com/explore/tags/{urllib.parse.quote(t)}/" for t in tag_theme]
    items = apify_run("apify/instagram-scraper", {
        "directUrls": urls, "resultsType": "reels",
        "resultsLimit": cfg.get("instagram_per_hashtag", 30), "addParentData": True,
    })

    reels, seen = [], set()
    for x in items:
        if x.get("error") or not x.get("timestamp") or x.get("url") in seen:
            continue
        if parse_time(x["timestamp"]) < cutoff:
            continue
        seen.add(x["url"])
        tag = urllib.parse.unquote(x.get("inputUrl", "")).rstrip("/").split("/")[-1]
        reels.append((tag_theme.get(tag, "기타"), tag, x))
    print(f"  [IG] 릴스 {len(items)}개 중 기간 안 {len(reels)}개", file=sys.stderr)

    owners = sorted({x["ownerUsername"] for _, _, x in reels if x.get("ownerUsername")})
    followers = {}
    if owners and cfg.get("instagram_followers", True):
        profiles = apify_run("apify/instagram-scraper", {
            "directUrls": [f"https://www.instagram.com/{u}/" for u in owners],
            "resultsType": "details", "resultsLimit": 1,
        })
        for p in profiles:
            if p.get("username"):
                followers[p["username"]] = p.get("followersCount")
        print(f"  [IG] 계정 {len(followers)}/{len(owners)}개 팔로워 조회", file=sys.stderr)

    rows = []
    for theme, tag, x in reels:
        caption = x.get("caption") or ""
        rows.append(add_scores({
            "platform": "Instagram", "theme": theme, "keyword": f"#{tag}",
            "title": caption.split("\n")[0][:80], "account": x.get("ownerUsername"),
            "url": x["url"], "published": x["timestamp"],
            "seconds": round(x["videoDuration"]) if x.get("videoDuration") else None,
            "views": x.get("videoPlayCount") or x.get("videoViewCount") or 0,
            "likes": max(x.get("likesCount") or 0, 0), "comments": x.get("commentsCount") or 0,
            "followers": followers.get(x.get("ownerUsername")),
            "_caption": caption,
        }))
    return rows


# ---------- 출력 ----------

FIELDS = ["platform", "theme", "keyword", "relevant", "title", "account", "url", "published",
          "seconds", "views", "followers", "viral_ratio", "views_per_day", "likes", "comments", "engagement"]


def fmt(n):
    if n is None:
        return "-"
    if n >= 10000:
        return f"{n / 10000:.1f}만"
    return f"{n:,}"


def write_report(rows, out, cfg):
    os.makedirs(out, exist_ok=True)
    words = cfg.get("relevance_words", [])
    for r in rows:
        if "relevant" not in r:
            r["relevant"] = relevant(r.get("_caption") or r["title"], words) if words else True
    rows.sort(key=lambda r: (r["viral_ratio"] or 0, r["views_per_day"]), reverse=True)
    # 구독자 몇 명짜리 채널이 수천 회로 1위가 되는 걸 막는다. CSV/JSON에는 전부 남긴다.
    min_views = cfg.get("min_views", 10000)

    stamp = NOW.strftime("%Y%m%d")
    with open(os.path.join(out, f"results_{stamp}.csv"), "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    with open(os.path.join(out, f"results_{stamp}.json"), "w", encoding="utf-8") as f:
        json.dump([{k: r.get(k) for k in FIELDS} for r in rows], f, ensure_ascii=False, indent=1)

    top_n = cfg.get("report_top", 10)
    lines = [f"# 숏폼 벤치마킹 리포트 ({NOW:%Y-%m-%d})", "",
             f"유튜브 최근 {cfg.get('days', 90)}일 · 인스타 최근 {cfg.get('instagram_days', 365)}일 · "
             f"조회 {fmt(min_views)} 이상 · 떡상 지수(조회수 ÷ 구독자/팔로워) 순 · 주제 무관 영상 제외", ""]
    for platform in ("YouTube", "Instagram"):
        prows = [r for r in rows if r["platform"] == platform and r["relevant"] and r["views"] >= min_views]
        if not prows:
            continue
        lines += [f"## {platform}", ""]
        for theme in cfg["themes"]:
            trows = [r for r in prows if r["theme"] == theme][:top_n]
            if not trows:
                continue
            lines += [f"### {theme}", "",
                      "| # | 제목 | 계정 | 조회 | 구독/팔로워 | 떡상 지수 | 일평균 |",
                      "|---|---|---|---|---|---|---|"]
            for i, r in enumerate(trows, 1):
                title = r["title"].replace("|", "/")[:40] or "(캡션 없음)"
                ratio = f"{r['viral_ratio']}배" if r["viral_ratio"] is not None else "-"
                lines.append(f"| {i} | [{title}]({r['url']}) | {r['account']} | {fmt(r['views'])} | "
                             f"{fmt(r['followers'])} | {ratio} | {fmt(r['views_per_day'])} |")
            lines.append("")
    path = os.path.join(out, f"report_{stamp}.md")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return path


# ---------- 명령 ----------

def cmd_check(_):
    ok = True
    try:
        yt_get("search", {"part": "id", "q": "test", "type": "video", "maxResults": 1})
        print("YouTube: OK")
    except Exception as e:
        ok = False
        print(f"YouTube: 실패 - {e}")
    r = requests.get(f"{APIFY_API}/users/me", headers=apify_headers(), timeout=30).json()
    if "data" in r:
        print(f"Apify: OK ({r['data']['plan']['id']} 플랜)")
    else:
        ok = False
        print(f"Apify: 실패 - {r.get('error', {}).get('message')}")
    sys.exit(0 if ok else 1)


def cmd_run(a):
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    rows = []
    if not a.skip_youtube:
        print("유튜브 수집 중...", file=sys.stderr)
        rows += collect_youtube(cfg)
    if not a.skip_instagram:
        print("인스타 수집 중...", file=sys.stderr)
        rows += collect_instagram(cfg)
    path = write_report(rows, a.out, cfg)
    print(f"완료: {len(rows)}개 영상 → {path}")


def cmd_report(a):
    """이미 모은 results_*.json으로 리포트만 다시 만든다 (API 비용 없음)."""
    with open(a.config, encoding="utf-8") as f:
        cfg = json.load(f)
    with open(a.data, encoding="utf-8") as f:
        rows = json.load(f)
    path = write_report(rows, a.out, cfg)
    print(f"완료: {len(rows)}개 영상 → {path}")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(func=cmd_check)
    r = sub.add_parser("run")
    r.add_argument("--config", required=True)
    r.add_argument("--out", default="shorts-finder")
    r.add_argument("--skip-youtube", action="store_true")
    r.add_argument("--skip-instagram", action="store_true")
    r.set_defaults(func=cmd_run)
    rp = sub.add_parser("report")
    rp.add_argument("--config", required=True)
    rp.add_argument("--data", required=True, help="results_YYYYMMDD.json")
    rp.add_argument("--out", default="shorts-finder")
    rp.set_defaults(func=cmd_report)
    a = p.parse_args()
    a.func(a)


if __name__ == "__main__":
    main()
