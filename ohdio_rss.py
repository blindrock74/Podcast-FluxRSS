"""Génère <titre-du-balado>.xml (RSS 2.0 + iTunes) et episodes.html pour un balado OHdio.

Usage : python ohdio_rss.py
"""

import json
import math
import time
import urllib.request
from datetime import datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path

BASE = "https://ici.radio-canada.ca"
PROGRAM_PATH = "/ohdio/balados/9887/la-journee-est-encore-jeune"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
PAUSE = 1.0  # secondes entre deux requêtes
LIMITE = 10  # nombre max d'épisodes (pour tester) ; None = tous
MEDIA_API = ("https://services.radio-canada.ca/media/validation/v2/?appCode=medianet"
             "&connectionType=hd&deviceType=ipad&multibitrate=true&output=json"
             "&tech=progressive&idMedia={}")

HERE = Path(__file__).parent
CACHE_FILE = HERE / "cache_audio.json"
FEED_FILE = PROGRAM_PATH.rsplit("/", 1)[-1] + ".xml"  # la-journee-est-encore-jeune.xml

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8")


def page_data(number):
    """Lit l'état JSON embarqué (window._rcState_) d'une page de la liste."""
    html = get(f"{BASE}{PROGRAM_PATH}?pageNumber={number}")
    start = html.index("{", html.index("window._rcState_"))
    state, _ = json.JSONDecoder().raw_decode(html, start)
    return state["pages"]["pages"][PROGRAM_PATH]["data"]


def fetch_all():
    first = page_data(1)
    pagination = first["pagination"]
    pages = math.ceil(pagination["totalCount"] / pagination["pageSize"])
    print(f"{pagination['totalCount']} épisodes sur {pages} pages")
    episodes = first["episodes"]
    for n in range(2, pages + 1):
        if LIMITE and len(episodes) >= LIMITE:
            break
        time.sleep(PAUSE)
        print(f"page {n}/{pages}")
        episodes += page_data(n)["episodes"]
    return first["program"], episodes


def resolve_audio(episodes):
    """mediaId -> URL du fichier audio direct, avec cache sur disque."""
    cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}
    for i, ep in enumerate(episodes, 1):
        media_id = str(ep["mediaIds"][0])
        if media_id not in cache:
            print(f"audio {i}/{len(episodes)} : {ep['title']}")
            cache[media_id] = json.loads(get(MEDIA_API.format(media_id)))["url"]
            CACHE_FILE.write_text(json.dumps(cache, indent=1), "utf-8")
            time.sleep(PAUSE)
        ep["audio"] = cache[media_id]


def prepare(ep):
    ep["date"] = datetime.fromisoformat(ep["broadcastedFirstTimeAt"].replace("Z", "+00:00"))
    ep["link"] = BASE + "/ohdio" + ep["url"]
    ep["seconds"] = ep["duration"]["durationInSeconds"]


def hms(seconds):
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def write_rss(program, episodes, image):
    items = []
    for ep in episodes:
        items.append(f"""    <item>
      <title>{escape(ep['title'])}</title>
      <link>{escape(ep['link'])}</link>
      <guid isPermaLink="false">ohdio-{ep['globalId']['id']}</guid>
      <pubDate>{format_datetime(ep['date'])}</pubDate>
      <description>{escape(ep['summary'])}</description>
      <enclosure url="{escape(ep['audio'])}" length="0" type="audio/mp4"/>
      <itunes:duration>{ep['seconds']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(program['title'])}</title>
    <link>{BASE}{PROGRAM_PATH}</link>
    <description>{escape(program['summary'])}</description>
    <language>fr-ca</language>
    <copyright>Radio-Canada</copyright>
    <lastBuildDate>{format_datetime(datetime.now().astimezone())}</lastBuildDate>
    <image>
      <url>{escape(image)}</url>
      <title>{escape(program['title'])}</title>
      <link>{BASE}{PROGRAM_PATH}</link>
    </image>
    <itunes:image href="{escape(image)}"/>
    <itunes:author>Radio-Canada</itunes:author>
    <itunes:owner>
      <itunes:name>Radio-Canada</itunes:name>
      <itunes:email>{escape(program['contact']['email'])}</itunes:email>
    </itunes:owner>
    <itunes:category text="Comedy"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""
    (HERE / FEED_FILE).write_text(rss, "utf-8")


def write_html(program, episodes, image):
    blocks = []
    for ep in episodes:
        d = ep["date"]
        blocks.append(f"""<article>
  <h2><a href="{escape(ep['link'])}">{escape(ep['title'])}</a></h2>
  <p class="meta">{d.day} {MOIS[d.month - 1]} {d.year} · {hms(ep['seconds'])}</p>
  <div class="desc">{ep['summary']}</div>
  <audio controls preload="none" src="{escape(ep['audio'])}"></audio>
  <p class="dl"><a href="{escape(ep['audio'])}">Télécharger l'audio</a></p>
</article>""")

    page = f"""<!doctype html>
<html lang="fr-CA">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(program['title'])}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 46rem; margin: 0 auto; padding: 1rem;
         line-height: 1.5; color: #222; background: #fafafa; }}
  header {{ display: flex; gap: 1rem; align-items: center; margin-bottom: 2rem; }}
  header img {{ width: 120px; height: 120px; border-radius: 8px; }}
  h1 {{ margin: 0; }}
  article {{ background: #fff; border: 1px solid #ddd; border-radius: 8px; padding: 1rem; margin-bottom: 1rem; }}
  h2 {{ font-size: 1.1rem; margin: 0 0 .25rem; }}
  h2 a {{ color: inherit; }}
  .meta {{ color: #666; margin: 0 0 .5rem; font-size: .9rem; }}
  .desc p {{ margin: .25rem 0; }}
  audio {{ width: 100%; margin-top: .5rem; }}
  .dl {{ margin: .25rem 0 0; font-size: .85rem; }}
</style>
</head>
<body>
<header>
  <img src="{escape(image)}" alt="">
  <div>
    <h1>{escape(program['title'])}</h1>
    <p>{len(episodes)} épisodes · <a href="{FEED_FILE}">Flux RSS</a></p>
  </div>
</header>
{chr(10).join(blocks)}
</body>
</html>
"""
    (HERE / "episodes.html").write_text(page, "utf-8")


def main():
    program, episodes = fetch_all()
    for ep in episodes:
        prepare(ep)
    episodes.sort(key=lambda ep: ep["date"], reverse=True)
    episodes = episodes[:LIMITE]
    resolve_audio(episodes)
    image = program["picture"]["pattern"].replace("{width}", "1400").replace("{ratio}", "1x1")
    write_rss(program, episodes, image)
    write_html(program, episodes, image)
    print(f"OK : {FEED_FILE} et episodes.html ({len(episodes)} épisodes)")


if __name__ == "__main__":
    main()
