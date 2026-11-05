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

echo "=== Recuperation de la derniere version (git pull)"
git pull --rebase --autostash

echo
echo "=== Generation des flux pour OHDIO"
"$PYTHON" ohdio_rss.py
echo "=== Generation des flux pour QUB"
"$PYTHON" qub_rss.py

echo
echo "=== Envoi sur GitHub"
# TEMPORAIRE : copie des .xml a la racine pour les anciens liens
# (a retirer une fois les abonnements migres vers docs/)
cp -f docs/*.xml .
shopt -s nullglob
git add -- docs *.xml cache_audio.json emissions.txt
if git diff --cached --quiet; then
    echo "Aucun changement a envoyer."
    exit 0
fi
git commit -m "Mise a jour des flux $(date '+%Y-%m-%d %H:%M')"
git push
echo "Flux mis a jour sur GitHub."
