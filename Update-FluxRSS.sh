#!/usr/bin/env bash
# Lance ohdio_rss.py et qub_rss.py puis pousse les flux mis a jour sur GitHub.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")"

erreur() {
    echo
    echo "*** ERREUR : voir les messages ci-dessus."
    exit 1
}
trap erreur ERR

PYTHON=$(command -v python3 || command -v python)

# Resume des flux modifies (fichiers deja ajoutes a l'index) :
# nombre d'episodes avant -> apres, episodes ajoutes (+) et retires (-).
resume() {
    local f
    for f in $(git diff --cached --name-only -- 'docs/*.xml'); do
        { git show "HEAD:$f" 2>/dev/null || true; } | "$PYTHON" -c "$RESUME_PY" "$f"
    done
}

# Compare l'ancien flux (entree standard) et le nouveau (fichier en argument).
RESUME_PY=$(cat <<'EOF'
import sys, html, re
from pathlib import Path

def items(xml):
    """guid -> titre de chaque episode du flux."""
    # titres echappes deux fois dans le XML (&amp;nbsp;) : on decode deux fois
    return {g: re.sub(r"<[^>]+>", "", html.unescape(html.unescape(t))).replace("\xa0", " ").strip()
            for t, g in re.findall(r"<item>\s*<title>(.*?)</title>.*?<guid[^>]*>(.*?)</guid>", xml, re.S)}

f = Path(sys.argv[1])
avant, apres = items(sys.stdin.read()), items(f.read_text("utf-8"))
ajouts = [t for g, t in apres.items() if g not in avant]
retraits = [t for g, t in avant.items() if g not in apres]
detail = "" if ajouts or retraits else "  (tailles ou details seulement)"
print(f"  {f.stem:<60} {len(avant):>5} -> {len(apres):<5} episodes{detail}")
for signe, titres in (("+", ajouts), ("-", retraits)):
    for t in titres[:5]:
        print(f"      {signe} {t}")
    if len(titres) > 5:
        print(f"      {signe} ... ({len(titres)} au total)")
EOF
)

echo "=== Recuperation de la derniere version (git pull)"
git pull --rebase --autostash

echo
echo "=== Generation des flux pour OHDIO"
"$PYTHON" ohdio_rss.py
echo "=== Generation des flux pour QUB"
"$PYTHON" qub_rss.py

echo
# TEMPORAIRE : copie des .xml a la racine pour les anciens liens
# (a retirer une fois les abonnements migres vers docs/)
cp -f docs/*.xml .
shopt -s nullglob
git add -- docs *.xml cache_audio.json emissions.txt
if git diff --cached --quiet; then
    echo "=== Aucune mise a jour : tous les flux sont a jour."
    # commits locaux pas encore envoyes (ex. modification des scripts) : on les pousse
    if [ -n "$(git log '@{u}..HEAD' --oneline)" ]; then
        echo
        echo "=== Envoi des commits locaux sur GitHub"
        git log '@{u}..HEAD' --oneline
        git push
    fi
    exit 0
fi
echo "=== Mises a jour"
resume

echo
echo "=== Envoi sur GitHub"
git commit -m "Mise a jour des flux $(date '+%Y-%m-%d %H:%M')"
git push
echo "Flux mis a jour sur GitHub."
