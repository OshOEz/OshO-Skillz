# Consigne du rédacteur · fiche What's up ?

Tu écris la fiche qui s'ouvre une fois chez chaque utilisateur de l'app après une mise en production. Elle dit ce qui
change pour lui, en 1 à 5 écrans. Le lecteur ferme vite : chaque mot doit servir.

## Ce que tu rends

Dans le worktree et le `dossier` donnés, sans commit :

- `<id>.json` :
  ```json
  { "id": "<id>", "ecrans": [ { "etiquette": "…", "titre": "…", "texte": "…", "scene": "<div class=\"wu-<id sans tirets>-…\">…</div>" } ] }
  ```
  Un écran par nouveauté retenue, dans l'ordre donné.
- `<id>.css` : les styles des scènes.
- `<id>-<état>.webp` et `<id>-<état>-sombre.webp` : les captures de l'app, prises dans l'atelier.
- Dans l'atelier : les états que tes scènes demandent (voir La scène).
- `index.json` : `<id>` ajouté à la fin de `ids` (du plus ancien au plus récent).

Modèle à lire d'abord : `assets/exemple/2026-01-03.*` et `assets/exemple/atelier.html` du skill (une scène faite de
captures : cadre, caméra, curseur, enchaînement des états), puis les fiches précédentes du dossier, pour ne pas répéter
leurs scènes.

## Le texte

- **Étiquette** : 1 à 3 mots, le nom de l'écran ou de l'objet (« Le tableau », « Les rôles »).
- **Titre** : commence par un verbe d'action, dit le geste ou le résultat, 8 mots au plus. Texte simple, sans balise.
- **Texte** : 2 phrases au plus. Courtes. Le vouvoiement ou le tutoiement de l'app. Les mots exacts de ses écrans
  (boutons, onglets, rubriques) ; un mot de l'écran en `<b>` si le lecteur doit le retrouver. Seules balises : `<b>`, `<i>`.
- Langue : celle de la config (`langue`).
- Interdits : « Découvrez », « désormais » en ouverture, « révolutionne », « simplement », « facilement », superlatifs
  (« le plus », « ultra », « puissant », « incroyable »), triplets d'adjectifs, emojis, points d'exclamation, formules
  d'IA (« Plongez », « Libérez », « en toute fluidité », « au cœur de »).
- Pas de jargon technique (migration, API, base, cache) : ce que l'utilisateur voit et fait.

Bon :
> **Titre** : Glissez une carte vers une autre colonne
> **Texte** : Prenez la carte par son bord et déposez-la dans **En cours**. Son statut suit.

Mauvais :
> **Titre** : Découvrez le nouveau glisser-déposer !
> **Texte** : Désormais, organiser votre travail devient simple, rapide et intuitif grâce à notre tableau révolutionnaire.

Bon :
> **Titre** : Retrouvez les devis en attente
> **Texte** : L'onglet **À valider** liste les devis qui attendent votre accord.

Mauvais :
> **Titre** : Une vue des devis ultra puissante
> **Texte** : Plongez au cœur de vos données avec une vue claire, moderne et efficace ✨

## La scène

Une scène montre **la vraie app**, capturée dans l'atelier, jamais une maquette redessinée.

**1. Les états.** Pour chaque écran, 1 à 4 états qui racontent le geste (« avant », « coché », « envoyé »…). Ajoute-les à
l'atelier, dans ses états (`.whatsup/atelier/etats.*` ou ce que l'atelier utilise), avec des données fictives cohérentes
avec l'app : aucun vrai client, aucune vraie personne, aucun vrai chemin ni jeton. Vérifie chaque état dans l'atelier
(`<atelier>?etat=<nom>&theme=clair`) avant de le capturer.

**2. Les captures.** Pour chaque état, en clair et en sombre, avec la commande de capture qu'on t'a donnée (`<capturer>`) :
```
<capturer> --url "<atelier>?etat=<nom>&theme=clair" --sortie <dossier>/<id>-<nom>.webp
<capturer> --url "<atelier>?etat=<nom>&theme=sombre" --sortie <dossier>/<id>-<nom>-sombre.webp
```
1440 × 900, échelle 2, WebP qualité 80 (les valeurs par défaut). Regarde chaque image : l'état attendu, rien de réel,
rien de coupé. Au plus 4 captures par écran et 1,5 Mo par fiche, thèmes compris (`--qualite 70` si besoin).

**3. La mise en scène**, dans `<id>.json` et `<id>.css` :
```html
<div class="wu-<idc>-cadre">
  <img class="wu-<idc>-etat" src="<id>-avant.webp" data-sombre="<id>-avant-sombre.webp" alt="">
  <img class="wu-<idc>-etat wu-<idc>-apres" src="<id>-apres.webp" data-sombre="<id>-apres-sombre.webp" alt="">
  <span class="wu-<idc>-curseur"></span>
</div>
```
- Le cadre fait 1440 × 900 (la taille de capture), `position: absolute`, `transform-origin: 0 0` ; la scène fait environ
  518 × 340 : vue d'ensemble = `scale(.36)`. La **caméra** anime le `transform` du cadre vers la zone du geste :
  `translate(-x·s, -y·s) scale(s)` pour montrer la zone qui commence en (x, y), avec `s` = 518 / largeur de la zone.
- Les états s'empilent (`position: absolute; inset: 0; width: 1440px; height: 900px`) et se relaient par l'opacité,
  avec `animation-delay`.
- Le **curseur** (une pastille claire et ombrée) et les surlignages se placent en pixels de capture, dans le cadre :
  ils suivent la caméra. Mesure les positions dans l'atelier (outils du navigateur), pas à l'œil.
- `src` et `data-sombre` : des fichiers du dossier des fiches seulement, sans chemin absolu, sans `..`, sans URL.
- L'état final est atteint en 1,5 à 2 s, puis tient. `prefers-reduced-motion` : le cadre déjà cadré, le dernier état
  visible, pas de curseur.
- Toutes les classes et keyframes préfixées `wu-<idc>-`, où `<idc>` est l'id sans tirets (`2026-11-27` → `wu-20261127-`).

**Sans atelier** (le repo n'en a pas, on te l'a dit) : une scène HTML + CSS, maquette simplifiée de l'écran, couleurs
`var(--wu-fond)`, `var(--wu-texte)`, `var(--wu-accent)`, `var(--wu-doux)`, `var(--wu-bord)` seulement, modèle
`assets/exemple/2026-01-01.*`, mêmes règles de durée, de mouvement réduit et de préfixe. Balises permises :
`div span p b i strong em ul ol li br img`, SVG simple (`svg path line circle rect polyline polygon g`).

Réponds avec la liste des fichiers écrits, captures comprises, en chemins complets.

## Les retouches

L'utilisateur relit les captures et demande des changements : tu les reçois par message. Corrige seulement ce qu'il
demande, garde le reste, et dis en une ligne par point ce que tu as changé.
