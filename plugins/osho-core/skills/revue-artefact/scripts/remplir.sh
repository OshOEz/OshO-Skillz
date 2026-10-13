#!/usr/bin/env bash
# Builds a review page from the template: remplir.sh <contenu.json> <out.html>
# The title comes from .titre; "</" is escaped so the JSON cannot close its <script> early.
set -euo pipefail
contenu="$1"; sortie="$2"
gabarit="$(dirname "$0")/../gabarit.html"
jq -e '.titre and (.questions | type == "array")' "$contenu" >/dev/null \
  || { echo "contenu.json: .titre and .questions are required" >&2; exit 1; }
titre=$(jq -r '.titre' "$contenu" | sed 's/&/\&amp;/g; s/</\&lt;/g')
json=$(jq -c . "$contenu" | sed 's#</#<\\/#g')
TITRE="$titre" JSON="$json" python3 - "$gabarit" "$sortie" <<'PY'
import os, sys
src = open(sys.argv[1], encoding="utf-8").read()
src = src.replace("{{TITRE}}", os.environ["TITRE"]).replace("{{CONTENU}}", os.environ["JSON"])
open(sys.argv[2], "w", encoding="utf-8").write(src)
PY
echo "$sortie"
