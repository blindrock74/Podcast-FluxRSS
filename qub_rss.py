"""Génère <balado>.xml (RSS 2.0 + iTunes) et <balado>.html pour chaque balado QUB de emissions.txt.

Source : les données embarquées dans la page QUB du balado (toutes les saisons).
Historique maison : les épisodes déjà présents dans <balado>.xml sont conservés,
même s'ils disparaissent du site.

Usage : python qub_rss.py
"""

import http.cookiejar
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import format_datetime, parsedate_to_datetime
from html import escape
from pathlib import Path
from urllib.parse import urlsplit


USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")

HERE = Path(__file__).parent
OUT = HERE / "docs"  # publié par GitHub Pages
PAUSE_HEAD = 0.2  # secondes entre deux requêtes HEAD (taille des fichiers)

SOURCE_DOMAINE = "qub.ca"  # URL de emissions.txt traitées par ce script


def emissions():
    """URL de emissions.txt appartenant à ce site (lignes vides et # ignorées)."""
    urls = []
    for ligne in (HERE / "emissions.txt").read_text("utf-8").splitlines():
        ligne = ligne.strip()
        if ligne and not ligne.startswith("#"):
            hote = urlsplit(ligne).hostname or ""
            if hote == SOURCE_DOMAINE or hote.endswith("." + SOURCE_DOMAINE):
                urls.append(ligne)
    return urls


ITUNES = "{http://www.itunes.com/dtds/podcast-1.0.dtd}"

MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
        "août", "septembre", "octobre", "novembre", "décembre"]


class LongRedirects(urllib.request.HTTPRedirectHandler):
    max_redirections = 30
    max_repeats = 10


# qub.ca fait une longue chaîne de redirections (connexion anonyme) qui pose des témoins :
# il faut garder les cookies et accepter plus de redirections que par défaut
opener = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()), LongRedirects)


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with opener.open(req) as r:
        return r.read().decode("utf-8")


def qub_show(url):
    """Lit la page QUB : infos de l'émission et tous ses épisodes (toutes saisons)."""
    html = get(url)
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.S)
    entity = json.loads(m.group(1))["props"]["pageProps"]["staticEntity"]
    show_slug = entity.get("slug") or urlsplit(url).path.rstrip("/")

    episodes = {}

    def walk(o, season=None):
        if isinstance(o, list):
            for v in o:
                walk(v, season)
            return
        if not isinstance(o, dict):
            return
        if o.get("discriminator") == "AudioSeasonEntity":
            season = o.get("seasonNumber")
        # un épisode de CETTE émission (pas une recommandation d'une autre émission)
        if o.get("fileUrl") and (o.get("slug") or "").startswith(show_slug + "/"):
            clip = re.search(r"/clips/[^/]+/[^/]+/([^/]+)/", o["fileUrl"])
            guid = clip.group(1) if clip else str(o.get("id"))
            episodes[guid] = {
                "guid": guid,
                "title": o.get("label") or "",
                "link": o.get("absoluteUrl") or o.get("canonicalUrl") or url,
                "summary": escape(o.get("description") or "", quote=False),
                "date": datetime.fromisoformat(o["activationDate"].replace("Z", "+00:00")),
                "audio": o["fileUrl"],
                "length": "0",
                "type": "audio/mpeg",
                "seconds": round((o.get("durationMillis") or 0) / 1000),
                "season": str(season) if season is not None else None,
            }
            return
        for v in o.values():
            walk(v, season)

    walk(entity.get("knownEntities"))
    show = {
        "title": entity.get("name") or "",
        "summary": entity.get("description") or "",
        "image": ((entity.get("image") or {}).get("url") or "").replace("size=large", "size=Large"),
        "link": url,
    }
    return show, episodes


def load_history(feed):
    """Relit les épisodes déjà présents dans notre propre flux."""
    if not feed.exists():
        return {}
    episodes = {}
    for item in ET.parse(feed).getroot().iter("item"):
        guid = (item.findtext("guid") or "").removeprefix("qub-")
        enc = item.find("enclosure")
        if not guid or enc is None:
            continue
        episodes[guid] = {
            "guid": guid,
            "title": item.findtext("title") or "",
            "link": item.findtext("link") or "",
            "summary": item.findtext("description") or "",
            "date": parsedate_to_datetime(item.findtext("pubDate")),
            "audio": enc.get("url"),
            "length": enc.get("length") or "0",
            "type": enc.get("type") or "audio/mpeg",
            "seconds": int(item.findtext(ITUNES + "duration") or 0),
            "season": item.findtext(ITUNES + "season"),
        }
    return episodes


def head_length(url):
    """Taille du fichier audio en octets (Content-Length d'une requête HEAD), "0" en cas d'échec."""
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.headers.get("Content-Length", "0")
    except Exception as e:  # length="0" : on réessaiera au prochain lancement
        print(f"   taille introuvable : {e}")
        return "0"


def resolve_lengths(episodes, history):
    """Ajoute ep["length"] : reprise de l'historique, sinon requête HEAD."""
    for i, ep in enumerate(episodes, 1):
        connu = history.get(ep["guid"])
        if connu and connu["audio"] == ep["audio"] and connu["length"] != "0":
            ep["length"] = connu["length"]
        else:
            print(f"taille {i}/{len(episodes)} : {ep['title']}")
            ep["length"] = head_length(ep["audio"])
            time.sleep(PAUSE_HEAD)


def hms(seconds):
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def write_rss(slug, show, episodes):
    items = []
    for ep in episodes:
        season = f"\n      <itunes:season>{ep['season']}</itunes:season>" if ep["season"] else ""
        items.append(f"""    <item>
      <title>{escape(ep['title'])}</title>
      <link>{escape(ep['link'])}</link>
      <guid isPermaLink="false">qub-{escape(ep['guid'])}</guid>
      <pubDate>{format_datetime(ep['date'])}</pubDate>
      <description>{escape(ep['summary'])}</description>
      <enclosure url="{escape(ep['audio'])}" length="{escape(ep['length'])}" type="{escape(ep['type'])}"/>
      <itunes:duration>{ep['seconds']}</itunes:duration>{season}
      <itunes:explicit>false</itunes:explicit>
    </item>""")

    rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{escape(show['title'])}</title>
    <link>{escape(show['link'])}</link>
    <description>{escape(show['summary'])}</description>
    <language>fr-ca</language>
    <copyright>QUB radio</copyright>
    <lastBuildDate>{format_datetime(datetime.now().astimezone())}</lastBuildDate>
    <image>
      <url>{escape(show['image'])}</url>
      <title>{escape(show['title'])}</title>
      <link>{escape(show['link'])}</link>
    </image>
    <itunes:image href="{escape(show['image'])}"/>
    <itunes:author>QUB radio</itunes:author>
    <itunes:owner>
      <itunes:name>QUB radio</itunes:name>
    </itunes:owner>
    <itunes:category text="Society &amp; Culture"/>
    <itunes:explicit>false</itunes:explicit>
    <itunes:type>episodic</itunes:type>
{chr(10).join(items)}
  </channel>
</rss>
"""
    (OUT / f"{slug}.xml").write_text(rss, "utf-8")


def write_html(slug, show, episodes):
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
<title>{escape(show['title'])}</title>
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
  <img src="{escape(show['image'])}" alt="">
  <div>
    <h1>{escape(show['title'])}</h1>
    <p>{len(episodes)} épisodes · <a href="{slug}.xml">Flux RSS</a></p>
  </div>
</header>
{chr(10).join(blocks)}
</body>
</html>
"""
    (OUT / f"{slug}.html").write_text(page, "utf-8")


def traiter(url):
    slug = urlsplit(url).path.rstrip("/").rsplit("/", 1)[-1]
    print(f"== {slug}")
    feed = OUT / f"{slug}.xml"
    show, site = qub_show(url)
    history = load_history(feed)
    nouveaux = site.keys() - history.keys()
    print(f"{len(site)} épisodes sur QUB, {len(history)} dans l'historique, {len(nouveaux)} nouveau(x)")
    if history and not nouveaux and all(ep["length"] != "0" for ep in history.values()):
        print("Déjà à jour")
        return
    episodes = sorted({**history, **site}.values(), key=lambda ep: ep["date"], reverse=True)
    if not episodes:
        print("Aucun épisode trouvé")
        return
    resolve_lengths(episodes, history)
    write_rss(slug, show, episodes)
    write_html(slug, show, episodes)
    print(f"OK : {slug}.xml et {slug}.html ({len(episodes)} épisodes)")


def main():
    for url in emissions():
        traiter(url)


if __name__ == "__main__":
    main()
