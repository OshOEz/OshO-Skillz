#!/usr/bin/env bash
# Auto-test de remplir.sh et du rendu du gabarit
#   bash test_remplir.sh
set -eu
ici="$(cd "$(dirname "$0")" && pwd)"
script="$ici/remplir.sh"; gabarit="$ici/../gabarit.html"
t=$(mktemp -d)
trap 'rm -rf "$t"' EXIT
fail() { echo "FAIL: $1"; echo "${out:-}"; exit 1; }

# Renders the page's inline script against a tiny fake DOM; prints what the tests look at.
rendre() {
  node - "$1" <<'JS'
const html = require('fs').readFileSync(process.argv[2], 'utf8');
const json = html.match(/<script type="application\/json" id="contenu">([\s\S]*?)<\/script>/)[1];
const code = html.match(/<script>\n([\s\S]*?)<\/script>/)[1];
const noeud = tag => ({ tag, className: '', textContent: '', hidden: false, attrs: {}, enfants: [],
  setAttribute(k, v) { this.attrs[k] = v; }, append(...e) { this.enfants.push(...e); }, addEventListener() {} });
const racine = noeud('div');
const tous = n => [n, ...n.enfants.flatMap(tous)];
globalThis.window = {};
globalThis.document = {
  createElement: noeud,
  getElementById: id => id === 'contenu' ? { textContent: json } : id === 'page' ? racine : null,
};
new Function(code)();
const n = tous(racine);
const titre = n.find(x => x.textContent === 'En 30 secondes');
const bref = titre ? n.find(x => x.enfants.includes(titre)) : null;
const details = n.filter(x => x.tag === 'details' && x.enfants.some(e => e.tag === 'summary' && e.textContent === 'Détail technique'));
console.log(JSON.stringify({
  bref: bref ? tous(bref).filter(x => x.tag === 'li').map(x => x.textContent) : null,
  details: details.map(d => tous(d).filter(x => x.tag === 'p').map(x => x.textContent).join('')),
  vides: n.filter(x => x.tag === 'details' || x.className === 'bref').length - details.length - (bref ? 1 : 0),
}));
JS
}

# contenu.json d'avant : la page se construit, sans bloc nouveau
printf '%s' '{"titre":"Revue simple","sections":[{"titre":"S","items":["x"]}],"questions":[{"id":"q","titre":"Q ?"}]}' > "$t/avant.json"
out=$(bash "$script" "$t/avant.json" "$t/avant.html" 2>&1) || fail "contenu d'avant refusé"
grep -q "<title>Revue simple</title>" "$t/avant.html" || fail "titre absent"

# enBref et technique : les chaînes sont dans la page
printf '%s' '{"titre":"Revue riche","enBref":["a1","b2","c3","d4"],"sections":[{"titre":"S","items":["x"],"technique":"détail-section"}],"questions":[{"id":"q","titre":"Q ?","technique":"détail-question"}]}' > "$t/riche.json"
out=$(bash "$script" "$t/riche.json" "$t/riche.html" 2>&1) || fail "contenu riche refusé"
for s in a1 b2 détail-section détail-question; do grep -q "$s" "$t/riche.html" || fail "$s absent"; done

# Le gabarit porte le bloc et le repli
grep -q "En 30 secondes" "$gabarit" || fail "« En 30 secondes » absent du gabarit"
grep -q "<details" "$gabarit" || grep -q "'details'" "$gabarit" || fail "details absent du gabarit"

# Sans titre : code 1
printf '%s' '{"questions":[]}' > "$t/sans.json"
if bash "$script" "$t/sans.json" "$t/sans.html" 2>/dev/null; then fail "sans titre accepté"; else [ $? -eq 1 ] || fail "code attendu 1"; fi

# Rendu dans un faux DOM : 3 lignes au plus, un repli par champ technique, rien sans ces champs
if command -v node >/dev/null 2>&1; then
  out=$(rendre "$t/riche.html") || fail "rendu riche"
  [ "$out" = '{"bref":["a1","b2","c3"],"details":["détail-section","détail-question"],"vides":0}' ] || fail "rendu riche"
  out=$(rendre "$t/avant.html") || fail "rendu d'avant"
  [ "$out" = '{"bref":null,"details":[],"vides":0}' ] || fail "rendu d'avant"
else
  echo "SKIP (node absent)"
fi

echo "OK test_remplir"
