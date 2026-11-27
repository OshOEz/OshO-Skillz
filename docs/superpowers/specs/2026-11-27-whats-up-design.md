# What's up ? — les nouveautés d'une mise en prod, dans n'importe quelle app

Date : 2026-11-27 · Plugin : `osho-core` · Origine : le système `/nouveautes` d'une de nos apps (skill, hook avant main, fenêtre React), appelée « l'app d'origine » ici.

## 1. Intention

À chaque passage en prod, les utilisateurs d'une app voient une courte fenêtre « Nouveautés » (1 à 5 écrans animés : tutos du geste, avant / après). L'app d'origine le fait déjà, mais en React, avec une insertion figée dans son code et un suivi « vu » côté serveur. On veut le même service pour Horizon, Escouade, l'app d'origine… sans réécrire l'insertion par repo.

Succès : un repo neuf est branché en une session (installation), puis chaque mise en prod produit sa fiche en quelques échanges (choisir, relire), sans code spécifique à écrire.

## 2. Objectifs, non-objectifs, anti-objectifs

Objectifs
- Un seul moteur de fenêtre, framework-agnostique, réutilisé tel quel par tous les repos.
- Une fiche = des données (texte + scènes HTML/CSS), pas du code de l'app.
- Un thème proposé d'après celui de l'app, modifiable.
- Un hook qui rappelle de faire la fiche avant la prod, et une échappatoire explicite.

Non-objectifs (pour cette version)
- Migrer l'app d'origine : elle garde son système ; elle pourra adopter What's up ? plus tard.
- Un suivi « vu » côté serveur fourni par le skill (l'app peut le brancher, voir §5.4).
- Statistiques de lecture, images, vidéos, Lottie.

Anti-objectifs (échec même si « ça marche »)
- Un ton marketing (« Découvrez », superlatifs, emojis) : la consigne du rédacteur de l'app d'origine s'applique.
- Bloquer une mise en prod parce que l'outillage échoue (git, réseau) : le hook laisse passer et le dit.
- Des données réelles (clients, personnes) dans une fiche, une capture ou la page à cocher.
- Un code d'insertion différent par repo à maintenir à chaque évolution.

## 3. Approches considérées

| | Approche | Gain | Coût |
|---|---|---|---|
| **A (retenue)** | Composant web universel `<whats-up>` (un fichier JS sans dépendance, Shadow DOM), fiches en JSON + CSS | Un seul moteur ; marche en React, Svelte, Tauri, HTML | La fenêtre imite le style de l'app au lieu d'utiliser ses composants |
| B | Adaptateur généré par repo dans sa techno | Rendu natif | Un code par repo à faire évoluer : le problème actuel |
| C | Page hors de l'app + lien | Rien à intégrer | Ne met pas les nouveautés dans le produit |

Choix de l'utilisateur : A.

## 4. Organisation dans le plugin

```
plugins/osho-core/
  skills/whats-up/
    SKILL.md            deux procédures : Installer (repo sans .whatsup/) et Préparer une MEP
    redacteur.md        consigne du rédacteur (reprise de l'app d'origine, rendue générique)
    assets/whats-up.js  le composant, copié dans chaque repo
    assets/apercu.html  page d'aperçu autonome (composant + thème + une fiche)
    scripts/garde.py    décision des gardes (stdlib), copiée dans chaque repo ; + test_garde.py
    scripts/test_whats_up.sh  auto-test du composant (node, sans dépendance)
  hooks/whats-up.sh     relais PreToolUse Bash (gh pr create) → .whatsup/garde.py du repo
```

Le hook est déclaré dans `hooks/hooks.json` (`PreToolUse`, matcher `Bash`). Il ne fait rien hors d'un repo qui contient `.whatsup/config.json` (opt-in, comme code-review-graph).

## 5. Ce qui vit dans le repo de l'app

### 5.1 `.whatsup/config.json` (écrit à l'installation)

```json
{
  "app": "Horizon",
  "langue": "fr",
  "prod": "main",
  "base": "dev",
  "dossier": "public/whats-up",
  "url": "/whats-up/",
  "theme": { "fond": "var(--card)", "texte": "var(--foreground)", "accent": "var(--accent)",
             "doux": "var(--muted-foreground)", "bord": "var(--border)", "rayon": "12px", "police": "inherit" },
  "apercu": { "lancer": "npm run dev -- --port {port} --strictPort", "url": "http://localhost:{port}/?whats-up=apercu" }
}
```

- `prod` : la branche de production ; `base` : la branche où la fiche est commitée avant la prod (égale à `prod` si le repo pousse directement sur main, cas de l'action `merge` d'Escouade).
- `dossier` : dossier servi tel quel par l'app (public/, static/…) ; `url` : son adresse dans l'app.
- `theme` : chaque valeur est une couleur CSS ou une variable de l'app ; elle suit donc le thème clair / sombre de l'app.
- `apercu` : facultatif ; `{port}` est remplacé par un port libre, jamais celui du serveur de l'utilisateur, et la commande tourne dans le worktree du rédacteur (ses propres dépendances et son propre cache). Sans `apercu`, l'aperçu passe par `apercu.html`, servi par `python3 -m http.server` sur un port libre.

### 5.2 `<dossier>/` (servi par l'app)

```
whats-up.js            copie du composant (ligne 1 : // whats-up v<version>)
index.json             { "ids": ["2026-11-27", ...] }  du plus ancien au plus récent
2026-11-27.json        la fiche
2026-11-27.css         ses scènes
```

Fiche :

```json
{ "id": "2026-11-27",
  "ecrans": [ { "etiquette": "La carte", "titre": "Glissez une activité vers une autre étape",
                "texte": "Prenez la boîte par son bord… <b>Étapes</b>.",
                "scene": "<div class=\"wu-20261127-boite\">…</div>" } ] }
```

`texte` accepte seulement `<b>` et `<i>` ; `scene` est du HTML statique (pas de `<script>`, pas d'attribut `on*`, pas d'URL externe). Les fiches sont écrites par notre rédacteur et relues, commitées dans le repo : le nettoyage est un filet, pas une frontière de sécurité. Le composant parse avec `<template>` dans le navigateur et garde une liste blanche de balises et d'attributs ; le `.css` perd ses `@import` et ses `url()` externes.

### 5.3 Le montage (une ligne, posée à l'installation)

```html
<script type="module" src="/whats-up/whats-up.js"></script>
<whats-up src="/whats-up/" app="Horizon" lang="fr"></whats-up>
```

Dans le layout racine de l'app (index.html, layout Svelte/React…), visible seulement quand un utilisateur est dans l'app (pas sur l'écran de connexion, si l'app en a un). Le thème est posé en style sur l'élément (`style="--wu-fond: var(--card); …"`), à partir de `theme`.

### 5.4 Le composant `whats-up.js`

- Charge `index.json`, compare au dernier id vu, charge les fiches non vues (dans l'ordre, enchaînées), sinon ne rend rien.
- Vu : `localStorage["whats-up:<app>"]` = dernier id vu. Premier passage (rien en mémoire) : seulement la fiche la plus récente. L'app peut prendre la main : attribut `vu="<id>"` (lu avant `localStorage`) et événement `whats-up:vu` (`detail.id`) émis à la fermeture, pour stocker côté serveur.
- `?whats-up=apercu` : montre la dernière fiche sans rien écrire ; `?whats-up=revoir` ou `element.ouvrir()` : la rouvre (pour un menu « Nouveautés »).
- Fenêtre : `role="dialog"`, `aria-modal`, focus piégé et rendu, Échap, flèches gauche/droite, points d'écran, Précédent / Suivant / « C'est parti ». Libellés fr et en.
- Shadow DOM : le CSS des fiches n'atteint pas l'app ; les variables `--wu-*` traversent.
- `prefers-reduced-motion` : animations coupées, état final affiché.
- Échec de chargement (réseau, JSON invalide) : rien n'est affiché, l'app n'est pas touchée.

## 6. Les gardes (avant la prod)

Une seule logique de décision, `garde.py` (stdlib), copiée dans le repo à l'installation (`.whatsup/garde.py`, version en ligne 2) : un hook git ne peut pas pointer vers le cache du plugin, dont le chemin change à chaque version. Deux portes l'appellent :

- **Hook git `pre-push`** (posé à l'installation) : tout push vers `prod`, depuis Claude ou depuis un terminal. Git lui donne sur stdin `<ref locale> <sha local> <ref distante> <sha distant>` ; seules les lignes dont la ref distante est `refs/heads/<prod>` comptent, et ce qui part est le `<sha local>`. Si le repo a déjà un `pre-push` (relais versionné `.githooks/pre-push` de repo-init-nobori, ou un hook à lui), l'installation y ajoute un appel au lieu de le remplacer ; un hook qu'elle ne sait pas modifier sans risque → elle donne la ligne à ajouter à la main.
- **Hook Claude `PreToolUse` Bash** (dans le plugin, opt-in par `.whatsup/config.json`) : seulement `gh pr create` dont `--base`/`-B` vaut `prod`, qu'un hook git ne voit pas. Ce qui part : la branche `--head`/`-H` (à défaut la branche courante), lue sur `origin/<head>` puis en local. Le cas `base == prod` est couvert : la PR qui apporte la fiche est elle-même la mise en prod. Il appelle `.whatsup/garde.py` du repo.

Décision : refus (message « Pas de fiche What's up ? pour cette mise en prod : lance /whats-up, ou écris la raison ») quand la fiche la plus récente de `index.json` sur ce qui part n'est pas plus récente que celle de `origin/<prod>`. `index.json` absent de `origin/<prod>` (première mise en prod après l'installation) → laisse passer : cette mise en prod installe le composant.

Échappatoires : une ligne `Sans nouveautés : <raison>` dans le corps de la PR (`--body`, `--body-file`) ; pour un push, la variable `WHATSUP_SANS="<raison>"` (`WHATSUP_SANS="correctif de sécurité" git push`). Toute erreur d'outillage (pas de remote, git en échec, config illisible, python absent) → laisse passer avec un avertissement.

## 7. Procédure « Installer » (repo sans `.whatsup/`)

1. Lire le repo : stack, dossier statique servi, layout racine, fichiers de thème (variables CSS `:root`, config Tailwind, jetons du design system), branches (`prod`, `base`, lues dans le Git & CI du repo ou demandées).
2. Proposer le thème : une correspondance `theme` vers les variables de l'app, plus un aperçu (`apercu.html` avec une fiche d'exemple, clair et sombre). L'utilisateur valide ou change des couleurs (page `osho-core:revue-artefact` si plusieurs choix).
3. Écrire `.whatsup/config.json`, copier `whats-up.js` et `.whatsup/garde.py`, poser le hook git `pre-push` (§6), créer `index.json` vide, poser la ligne de montage.
4. Lancer l'app (ou `apercu.html`), vérifier que la fiche d'exemple s'ouvre, puis la retirer.
5. Commit sur une branche `feat/whats-up`, et rien de plus sans l'accord de l'utilisateur.

Relancer l'installation sur un repo déjà installé met à jour `whats-up.js` et `garde.py` (version en tête) et ne touche pas à la config sans le dire.

## 8. Procédure « Préparer une MEP » (le run)

Déclenchée par le hook, par `/whats-up`, ou par « nouveautés », « mise en prod », « MEP ». Reprise de l'app d'origine, sans ce qui lui est propre (base Postgres, ports, scripts de capture) :

1. **Lire** (sous-agent lecteur) : `git log origin/<prod>..<ce qui part>`, PR fusionnées si `gh` est là, bilans et plans du repo ; écarter l'invisible (migrations, refactor, tests, CI, docs, sécurité invisible) ; rendre 5 à 15 changements `{id, phrase, ecran, forme: tuto|presentation, ref}`.
2. **Choisir** : page `osho-core:revue-artefact`, au plus 5 retenus et leur forme. 0 retenu → pas de fiche, donner la commande de prod avec l'échappatoire « rien de choisi », s'arrêter.
3. **Rédiger** (sous-agent rédacteur, `redacteur.md`) dans un worktree depuis `base` : `<id>.json`, `<id>.css`, ajout à `index.json`. Id = date du jour, `-2`, `-3` si déjà pris.
4. **Montrer** : captures 1440 px et 390 px de l'aperçu (app si `apercu` est configuré, sinon `apercu.html`), avec le navigateur disponible : `capture_browser` d'Escouade, sinon Claude in Chrome ; aucun des deux → ouvrir l'aperçu chez l'utilisateur (`open <url>`) sans capture. Jamais de Playwright ajouté au repo. Captures regardées avant de les montrer ; retouches par le même rédacteur jusqu'au oui ; serveurs arrêtés par PID.
5. **Livrer** : commit `feat(whats-up): release note <id>` sur `feat/whats-up-<id>`, puis, sur oui : PR vers `base` (ou fusion locale si le repo n'a pas de PR) ; le hook laisse alors passer la prod.

Règles : jamais l'échappatoire sans l'accord de l'utilisateur ; une fiche déjà en prod ne se réécrit pas ; aucune donnée réelle.

## 9. Consigne du rédacteur

Celle de l'app d'origine, généralisée : ton, longueurs, interdits, exemples bons / mauvais ; scènes HTML + CSS seulement, maquettes simplifiées de l'écran, 340 px de haut, lisibles à 390 px, état final en 1,5 s ; couleurs uniquement `var(--wu-*)` ; classes et keyframes préfixées `wu-<id sans tirets>-` ; mots exacts des écrans de l'app ; données fictives inventées pour l'app (skill `osho-core:donnees-fictives` si besoin).

## 10. Tests

- `test_garde.py` : mode PR (avec et sans fiche plus récente, `--head` lu, `base == prod`, commande qui cite « --base main » dans le corps, ligne `Sans nouveautés`) et mode pre-push (lignes stdin vers prod et ailleurs, suppression de branche, `WHATSUP_SANS`), première mise en prod (pas d'`index.json` sur prod), erreur git → passe ; sur des dépôts jetables.
- `test_whats_up.sh` : sous node sans navigateur, le choix des fiches dues (rien vu, vu ancien, vu à jour, `vu=` prioritaire) et le filtre CSS, exportés comme fonctions pures. Le nettoyage HTML (dépend du DOM) se vérifie dans `apercu.html` avec une fiche piégée d'exemple.
- CI du repo (`make ci`) : les deux s'y ajoutent d'eux-mêmes (`test_*.py`, `test_*.sh`). Ce repo est public : aucun nom d'app privée ni chemin personnel dans les fichiers suivis (étape 7 de la CI).

## 11. Choix validés le 27 novembre 2026

Par l'utilisateur : la spec, une seule skill, la fiche la plus récente au premier passage, un hook git `pre-push` en plus du hook Claude.

### Choix faits par Claude

- Premier passage d'un utilisateur : seulement la fiche la plus récente (§5.4).
- Nettoyage HTML = filet, pas frontière (§5.2).
- Une seule skill à deux procédures plutôt que deux skills (§4).

## 12. Laissé au constructeur

Le découpage interne de `whats-up.js` (garder un seul fichier), le style exact de la fenêtre (sobre, proche de la fenêtre de l'app d'origine), la détection du layout et du thème selon la stack, le texte des messages.
