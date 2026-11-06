@echo off
rem Lance ohdio_rss.py puis pousse les flux mis a jour sur GitHub.
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo === Recuperation de la derniere version (git pull)
git pull --rebase --autostash || goto :erreur

echo.
echo === Generation des flux pour OHDIO
python ohdio_rss.py || goto :erreur
echo === Generation des flux pour QUB
python qub_rss.py || goto :erreur

echo.
echo === Envoi sur GitHub
git add docs cache_audio.json
git diff --cached --quiet && (
    echo Aucun changement a envoyer.
    goto :fin
)
git commit -m "Mise a jour des flux %date% %time:~0,5%" || goto :erreur
git push || goto :erreur
echo Flux mis a jour sur GitHub.
goto :fin

:erreur
echo.
echo *** ERREUR : voir les messages ci-dessus.

:fin
echo.
