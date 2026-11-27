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
- `index.json` : `<id>` ajouté à la fin de `ids` (du plus ancien au plus récent).

Modèles à lire d'abord : `assets/exemple/2026-01-01.*` du skill (cadre, proportions, animation), puis les fiches
précédentes du dossier, pour ne pas répéter leurs scènes.

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

- **Tuto** : le geste montré pas à pas en animation (le curseur ou la main qui fait, l'élément qui réagit), en 2 à
  4 temps enchaînés par `animation-delay`.
- **Présentation** : avant / après côte à côte (ou l'un qui se transforme en l'autre), l'avant estompé.
- HTML + CSS seulement : pas d'image, de canvas, de script, de lien, d'iframe, d'URL externe. Un SVG en ligne simple
  (une flèche, un trait : `svg`, `path`, `line`, `circle`, `rect`, `polyline`, `polygon`, `g`) est permis. Balises
  permises : `div span p b i strong em ul ol li br` ; attributs : `class`, `style`, `aria-hidden` et la géométrie SVG.
  Le reste est retiré à l'affichage.
- Une maquette dessinée de l'écran, simplifiée : les formes et les mots qu'il faut, pas une copie de toute la page.
- Couleurs : seulement `var(--wu-fond)`, `var(--wu-texte)`, `var(--wu-accent)`, `var(--wu-doux)`, `var(--wu-bord)`,
  et des mélanges `color-mix(in srgb, var(--wu-…) <n>%, transparent)`. Aucune couleur en dur : la fiche doit rester
  lisible dans les thèmes clair et sombre de l'app.
- Toutes les classes et keyframes préfixées `wu-<id sans tirets>-` (ex. `wu-20261127-carte`).
- `prefers-reduced-motion` : le composant coupe les animations ; ajoute une règle qui pose l'état final de chaque
  élément animé, pour que la scène figée montre le résultat.
- La scène tient dans 340 px de haut, et dans environ 310 px de large à 390 px d'écran : pas de largeur fixe sans
  `max-width: 100%`, `min-width: 0` sur les colonnes flex, `flex-wrap` ou une `@media (max-width: 480px)` qui resserre.
  Aucun texte ne déborde de sa boîte. Une animation qui dépend de la largeur se calcule en `%`, pas en px.
- L'état final de l'animation est atteint en 1,5 s au plus (les captures sont prises après), puis tient.
- Données fictives seulement, cohérentes avec l'app ; aucun vrai client, aucune vraie personne.

## Les retouches

L'utilisateur relit les captures et demande des changements : tu les reçois par message. Corrige seulement ce qu'il
demande, garde le reste, et dis en une ligne par point ce que tu as changé.
