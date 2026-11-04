"""Génère <balado>.xml (RSS 2.0 + iTunes) et <balado>.html pour chaque balado OHdio de EMISSIONS.

Usage : python ohdio_rss.py
"""
import re
import json
import math
import time
import urllib.request
from datetime import datetime
from email.utils import format_datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

# Émissions à traiter : URL de la page du balado (copier-coller du navigateur)
EMISSIONS = [
    "https://ici.radio-canada.ca/ohdio/balados/9887/la-journee-est-encore-jeune",
    "https://ici.radio-canada.ca/ohdio/balados/14021/lhistoire-est-encore-jeune",
    "https://ici.radio-canada.ca/ohdio/balados/7135/pires-moments-histoire-charles-beauchesne-humoriste",
    "https://ici.radio-canada.ca/ohdio/premiere/emissions/3855/aujourd-hui-l-histoire",
    "https://ici.radio-canada.ca/ohdio/premiere/emissions/6056/moteur-de-recherche",
    "https://ici.radio-canada.ca/ohdio/balados/13247/louis-blouin-aux-etats-unis-de-trump",
    "https://ici.radio-canada.ca/ohdio/balados/11099/decrypteurs",
    "https://ici.radio-canada.ca/ohdio/balados/6108/ca-sexplique-balado-info-alexis-de-lancer",
    "https://ici.radio-canada.ca/ohdio/balados/5548/histoires-enquete-reportage-proces-affaire-judiciaire/saison-9",
    "https://ici.radio-canada.ca/ohdio/balados/12185/enquete-de-crime-une-histoire-presque-vraie",
    "https://ici.radio-canada.ca/ohdio/balados/12949/ecotherapie-journal-dun-cataclysme",
    "https://ici.radio-canada.ca/ohdio/balados/12165/chiens-ecrases-nouvelles-insolites-sous-la-loupe",
]

BASE = "https://ici.radio-canada.ca"
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
PAUSE = 1.0  # secondes entre deux requêtes
MEDIA_API = ("https://services.radio-canada.ca/media/validation/v2/?appCode=medianet"
             "&connectionType=hd&deviceType=ipad&multibitrate=true&output=json"
             "&tech=progressive&idMedia={}")

HERE = Path(__file__).parent
CACHE_FILE = HERE / "cache_audio.json"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req) as r:
        return r.read().decode("utf-8")


def page_data(path, number):
    """Lit l'état JSON embarqué (window._rcState_) d'une page de la liste."""
    html = get(f"{BASE}{path}?pageNumber={number}")
    start = html.index("{", html.index("window._rcState_"))
    state, _ = json.JSONDecoder().raw_decode(html, start)
    return state["pages"]["pages"][path]["data"]


def fetch_all(path, first):
    pagination = first["pagination"]
    pages = math.ceil(pagination["totalCount"] / pagination["pageSize"])
    print(f"{pagination['totalCount']} épisodes sur {pages} pages")
    episodes = first["episodes"]
    for n in range(2, pages + 1):
        time.sleep(PAUSE)
        print(f"page {n}/{pages}")
        episodes += page_data(path, n)["episodes"]
    return first["program"], episodes


def resolve_audio(episodes):
    """mediaId -> URL du fichier audio direct, avec cache sur disque.

    Retourne seulement les épisodes qui ont un audio (les autres sont sautés).
    """
    cache = json.loads(CACHE_FILE.read_text("utf-8")) if CACHE_FILE.exists() else {}
    gardes = []
    for i, ep in enumerate(episodes, 1):
        if not ep.get("mediaIds"):
            print(f"audio {i}/{len(episodes)} : SAUTÉ, pas d'audio : {ep['title']}")
            continue
        media_id = str(ep["mediaIds"][0])
        if media_id not in cache:
            print(f"audio {i}/{len(episodes)} : {ep['title']}")
            try:
                url = json.loads(get(MEDIA_API.format(media_id))).get("url")
            except Exception as e:
                url = None
                print(f"   erreur : {e}")
            time.sleep(PAUSE)
            if not url:  # pas mis en cache : on réessaiera au prochain lancement
                print("   SAUTÉ, audio introuvable")
                continue
            cache[media_id] = url
            CACHE_FILE.write_text(json.dumps(cache, indent=1), "utf-8")
        ep["audio"] = cache[media_id]
        gardes.append(ep)
    return gardes


def prepare(ep):
    ep["date"] = datetime.fromisoformat(ep["broadcastedFirstTimeAt"].replace("Z", "+00:00"))
    ep["link"] = BASE + "/ohdio" + ep["url"]
    ep["seconds"] = ep["duration"]["durationInSeconds"]


def hms(seconds):
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def write_rss(path, slug, program, episodes, image):
    items = []
    for ep in episodes:
        items.append(f"""    <item>
      <title>{escape(re.sub(r'<[^>]+>', '', ep['title']))}</title>
      <link>{escape(ep['link'])}</link>
      <guid isPermaLink="false">ohdio-{ep['globalId']['id']}</guid>
      <pubDate>{format_datetime(ep['date'])}</pubDate>
      <description>{escape(ep['summary'] or '')}</description>
      <enclosure url="{escape(ep['audio'])}" length="0" type="audio/mp4"/>
      <itunes:duration>{ep['seconds']}</itunes:duration>
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    email = (program.get("contact") or {}).get("email")
    email_xml = f"\n      <itunes:email>{escape(email)}</itunes:email>" if email else ""

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(program['title'])}</title>
    <link>{BASE}{path}</link>
    <description>{escape(program['summary'] or '')}</description>
    <language>fr-ca</language>
    <copyright>Radio-Canada</copyright>
    <lastBuildDate>{format_datetime(datetime.now().astimezone())}</lastBuildDate>
    <image>
      <url>{escape(image)}</url>
      <title>{escape(program['title'])}</title>
      <link>{BASE}{path}</link>
    </image>
    <itunes:image href="{escape(image)}"/>
    <itunes:author>Radio-Canada</itunes:author>
    <itunes:owner>
      <itunes:name>Radio-Canada</itunes:name>{email_xml}
    </itunes:owner>
    <itunes:category text="Comedy"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""
    (HERE / f"{slug}.xml").write_text(rss, "utf-8")


def write_html(slug, program, episodes, image):
    blocks = []
    for ep in episodes:
        d = ep["date"]
        blocks.append(f"""<article>
  <h2><a href="{escape(ep['link'])}">{escape(ep['title'])}</a></h2>
  <p class="meta">{d.day} {MOIS[d.month - 1]} {d.year} · {hms(ep['seconds'])}</p>
  <div class="desc">{ep['summary'] or ''}</div>
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
    <p>{len(episodes)} épisodes · <a href="{slug}.xml">Flux RSS</a></p>
  </div>
</header>
{chr(10).join(blocks)}
</body>
</html>
"""
    (HERE / f"{slug}.html").write_text(page, "utf-8")


def traiter(url):
    path = urlsplit(url).path.rstrip("/")  # /ohdio/balados/9887/la-journee-est-encore-jeune
    parts = path.split("/")
    slug = parts[-1]  # la-journee-est-encore-jeune
    if re.fullmatch(r"saison-\d+", slug):  # .../histoires-enquete-.../saison-9
        slug = f"{parts[-2]}-{slug}"
    print(f"== {slug}")
    first = page_data(path, 1)
    feed = HERE / f"{slug}.xml"
    avec_audio = [ep for ep in first["episodes"] if ep.get("mediaIds")]
    if avec_audio and feed.exists():
        newest = max(avec_audio, key=lambda ep: ep["broadcastedFirstTimeAt"])
        if f"<guid isPermaLink=\"false\">ohdio-{newest['globalId']['id']}</guid>" in feed.read_text("utf-8"):
            print(f"Déjà à jour (dernier épisode : {newest['title']})")
            return
    program, episodes = fetch_all(path, first)
    for ep in episodes:
        prepare(ep)
    episodes.sort(key=lambda ep: ep["date"], reverse=True)
    episodes = resolve_audio(episodes)
    image = program["picture"]["pattern"].replace("{width}", "1400").replace("{ratio}", "1x1")
    write_rss(path, slug, program, episodes, image)
    write_html(slug, program, episodes, image)
    print(f"OK : {slug}.xml et {slug}.html ({len(episodes)} épisodes)")


def main():
    for url in EMISSIONS:
        traiter(url)


if __name__ == "__main__":
    main()
