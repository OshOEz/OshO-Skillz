---
name: whats-up
description: What's up ? — la fenêtre de nouveautés d'une mise en production, dans n'importe quelle app (React, Svelte, Tauri, HTML). Installe une fois par repo le composant, le thème proposé d'après l'app et les gardes (hook git pre-push, hook Claude), puis à chaque mise en prod lit les commits, fait choisir au plus 5 nouveautés et fabrique la fiche (tutos animés, avant / après) avant la prod. Utiliser quand l'utilisateur dit « what's up », « /whats-up », « nouveautés », « fiche de nouveautés », « MEP », « mise en prod », « passage en prod », « PR vers main », « installe What's up », ou quand un garde refuse une mise en prod faute de fiche (« Pas de fiche What's up ? »).
---

# What's up ?

Une fiche = 1 à 5 écrans qui s'ouvrent une fois chez chaque utilisateur après une mise en prod. Le composant `whats-up.js`
(un fichier, sans dépendance, Shadow DOM) est copié dans l'app ; une fiche est un `.json` (texte + scène HTML) et un
`.css`, rien d'autre. Spec : `docs/superpowers/specs/2026-11-27-whats-up-design.md` du dépôt OshO-Skillz.

`<skill>` = le « Base directory » affiché au lancement du skill. Le repo n'a pas `.whatsup/config.json` → **Installer**.
Sinon → **Préparer une MEP**.

## Installer (une fois par repo)

1. **Lire le repo** : stack, dossier servi tel quel (`public/`, `static/`, dossier des assets de Tauri…), layout racine
   (là où monter la fenêtre, après la connexion s'il y en a une), thème (variables CSS de `:root` et du mode sombre,
   config Tailwind, jetons du design system), branches : `prod` et `base` lues dans le Git & CI du repo (`CLAUDE.md`,
   `docs/`, `.githooks/`), sinon demandées. Le repo pousse directement sur main → `base` = `prod`.
2. **Proposer le thème** : une valeur pour chaque clé `fond`, `texte`, `accent`, `doux`, `bord`, `rayon`, `police`, de
   préférence les variables de l'app (`var(--card)`…), pour suivre son mode clair / sombre ; `police` = la pile de
   polices de l'app (pas `inherit` : le composant isole ses styles). Montrer l'aperçu (§ Montrer, avec la fiche
   d'exemple de `<skill>/assets/exemple/`) en clair et en sombre. Plus d'un choix à faire → page `osho-core:revue-artefact`.
3. **Écrire**, sur une branche `feat/whats-up` :
   - `.whatsup/config.json` : `app`, `langue` (`fr` | `en`), `prod`, `base`, `dossier`, `url`, `theme`, et
     `apercu` si l'app se lance en local (`{ "lancer": "<commande avec {port}>", "url": "http://localhost:{port}/?whats-up=apercu" }`) ;
   - `<dossier>/whats-up.js` (copie de `<skill>/assets/whats-up.js`) et `<dossier>/index.json` = `{ "ids": [] }` ;
   - `.whatsup/garde.py` (copie de `<skill>/scripts/garde.py`) ;
   - la ligne de montage dans le layout racine, thème en style :
     ```html
     <script type="module" src="<url>whats-up.js"></script>
     <whats-up src="<url>" app="<app>" lang="<langue>" style="--wu-fond: …; --wu-texte: …; --wu-accent: …; --wu-doux: …; --wu-bord: …; --wu-rayon: …; --wu-police: …"></whats-up>
     ```
     L'app suit déjà ce que chaque compte a vu côté serveur → poser `vu="<id>"` avant d'insérer l'élément et écouter
     `whats-up:vu` (`event.detail.id`). Un menu « Nouveautés » → `document.querySelector('whats-up').ouvrir()`.
   - le hook git `pre-push`, sans jamais remplacer un hook existant. L'extrait `<skill>/assets/pre-push.sh` se place
     **juste après la ligne shebang** : il lit l'entrée de git une fois, la rend au reste du hook, ne refuse que sur le
     code 3 du garde, et laisse passer si `python3` manque.
     - `git config core.hooksPath` vaut `.githooks` (relais de repo-init-nobori) → l'insérer dans `.githooks/pre-push`,
       versionné ; sinon, sans `core.hooksPath`, dans `$(git rev-parse --git-path hooks)/pre-push` s'il existe en `sh`
       ou `bash` ;
     - aucun hook → créer `$(git rev-parse --git-path hooks)/pre-push` (`#!/bin/sh` + l'extrait), exécutable ;
     - tout autre cas (husky, lefthook, `core.hooksPath` vers un dossier généré, hook dans un autre langage) → ne rien
       modifier, donner l'extrait à l'utilisateur et dire où il va.
     Déjà là (`# >>> whats-up >>>`) → remplacer le bloc entre les deux marqueurs.
4. **Vérifier** :
   - la fenêtre : ajouter temporairement la fiche d'exemple `2026-01-01` au dossier, ouvrir l'app (ou l'aperçu) avec
     `?whats-up=apercu`, constater qu'elle s'ouvre avec le thème ; la retirer ;
   - le garde, appelé comme git l'appelle : `printf 'refs/heads/<prod> %s refs/heads/<prod> %s\n' "$(git rev-parse HEAD)" "$(git rev-parse origin/<prod>)" | python3 .whatsup/garde.py pre-push origin x; echo $?`
     → `0` : la prod n'a pas encore d'`index.json`, cette mise en prod installe le composant. Le refus (code 3,
     « Pas de fiche What's up ? ») ne peut apparaître qu'une fois une première fiche en prod ; ne pas le chercher avant.
5. **Commit** `feat(whats-up): install the release notes window` sur `feat/whats-up`. Rien de plus sans l'accord de
   l'utilisateur (PR, fusion).

Relancer l'installation sur un repo installé : comparer la ligne de version (`// whats-up v<n>`, `# whats-up garde v<n>`)
et recopier les fichiers plus récents ; ne changer la config qu'en le disant.

## Préparer une MEP

`<ce qui part>` = `origin/<base>` (ou la branche que l'utilisateur pousse, si `base` = `prod`).

1. **Lire** (sous-agent lecteur, `Agent` `general-purpose`, premier plan) avec ce prompt, complété :

   > Tu lis ce qui part en production dans `<repo>`, pour en tirer les nouveautés visibles par un utilisateur.
   > 1. `git fetch origin`, puis `git log --oneline origin/<prod>..<ce qui part>`.
   > 2. Si `gh` répond : `gh pr list --base <base> --state merged --search "merged:>=<date du dernier commit de origin/<prod>>" --limit 100 --json number,title,body`.
   > 3. Pour chaque changement : les bilans, plans et décisions du repo qui en parlent (`docs/`), et au besoin
   >    `git diff --stat origin/<prod>..<ce qui part>` pour voir l'écran touché.
   > 4. Écarte tout ce qu'un utilisateur ne voit pas : migrations, refactorisations, tests, CI, déploiement, documentation,
   >    consignes d'agent, correctifs de sécurité invisibles.
   > 5. Rends 5 à 15 changements, du plus utile au moins utile, en JSON :
   >    `{ "id": "c1", "phrase": "<une phrase simple, les mots de l'écran>", "ecran": "<écran concerné>", "forme": "tuto" | "presentation", "ref": "<PR ou commit>" }`.
   >    `tuto` = un geste nouveau à montrer pas à pas ; `presentation` = quelque chose qui a changé (avant / après).
   > Ne modifie aucun fichier. Aucun nom de vrai client ni de personne dans les phrases.

2. **Choisir** : skill `osho-core:revue-artefact`. `titre` « Nouveautés de la MEP » ; `chapo` « Coche au plus 5
   nouveautés à montrer, et leur forme. Aucune = pas de fiche. » ; une question par changement : `id` = `c1`…, `titre`
   = la phrase, `contexte` = l'écran et la ref, `choix` `tuto` (« Tuto : le geste en animation »), `presentation`
   (« Présentation : avant / après »), `non` (« Pas cette fois ») ; `reco` sur la forme du lecteur pour ses 3 premiers,
   sur `non` pour les autres. Retenus = les `cN` à `tuto` ou `presentation` ; plus de 5 → demander lesquels garder.
   **0 retenu** : pas de fiche ; donner la commande de mise en prod avec l'échappatoire « rien de choisi »
   (`--body "…\nSans nouveautés : rien de choisi"` pour une PR, `WHATSUP_SANS="rien de choisi" git push …` pour un push),
   et s'arrêter.

3. **Rédiger** :
   1. `id` = date du jour `AAAA-MM-JJ` ; déjà dans `index.json` de `<ce qui part>` → `-2`, puis `-3`…
   2. Worktree depuis `<ce qui part>`, jamais dans le dossier de l'utilisateur :
      `git worktree add ../<nom du repo>-wt/whats-up-<id> -b feat/whats-up-<id> <ce qui part>` ; si l'aperçu lance l'app,
      installer ses dépendances dans le worktree (son propre cache, jamais celui de l'utilisateur).
   3. Lancer un `Agent` (`general-purpose`, `model: opus`), nommé pour pouvoir le relancer, avec : le chemin de
      `<skill>/redacteur.md` (sa consigne, à lire en premier), le worktree, l'`id`, le `dossier`, le nom de l'app, les
      nouveautés retenues (phrase, écran, forme, ref), et les fiches précédentes du dossier à lire comme modèle.

4. **Montrer** :
   1. Aperçu, sur un port libre (`python3 -c 'import socket;s=socket.socket();s.bind(("",0));print(s.getsockname()[1])'`),
      jamais celui de l'utilisateur : `apercu` configuré → sa commande lancée depuis le worktree, `{port}` remplacé ;
      sinon `python3 -m http.server <port> --bind 127.0.0.1` dans un dossier temporaire qui contient `apercu.html`,
      `whats-up.js` et une copie du `dossier` des fiches, puis `apercu.html?src=<dossier>/&vu=<fiche précédente>&app=<app>`
      (et `&theme=<css de l'app>` si elle en a un fichier). Noter les PID.
   2. Captures à 1440 px et 390 px, avec le navigateur disponible : `capture_browser` d'Escouade, sinon Claude in Chrome,
      sinon Chrome sans interface (`--headless=new --screenshot --virtual-time-budget=4000 --window-size=1440,900`) ; il ne
      descend pas sous 500 px : pour 390 px, capturer une page qui contient l'aperçu dans une `<iframe width="390">`.
      Aucun navigateur → `open <url>` chez l'utilisateur, sans capture. Jamais de Playwright ajouté au repo.
   3. Regarder chaque image avant de la montrer : texte qui déborde, scène coupée à 390 px, écran vide → retour au
      rédacteur d'abord. Puis montrer les images (chemins complets) et l'URL de l'aperçu.
   4. Retouches : `SendMessage` au **même** rédacteur avec les mots de l'utilisateur, recapturer, remontrer, jusqu'au oui.
   5. Arrêter les serveurs par PID, jamais par motif.

5. **Livrer** (dans le worktree) :
   1. `python3 -c 'import json,sys;[json.load(open(f)) for f in sys.argv[1:]]' <dossier>/*.json` passe ; la CI locale
      du repo, s'il en a une, est verte.
   2. Commit `feat(whats-up): release note <id>` (sans captures), sur `feat/whats-up-<id>`.
   3. Sur le oui de l'utilisateur seulement : PR vers `base` (`gh pr create --base <base> --head feat/whats-up-<id>`,
      lancée depuis le worktree), ou fusion locale si le repo
      ne passe pas par des PR ; puis la mise en prod : les gardes laissent passer sans échappatoire. S'ils refusent, la
      fiche n'est pas sur ce qui part : vérifier la fusion, ne pas contourner.
   4. Retirer le worktree (`git worktree remove`).

## Règles

- Jamais d'échappatoire (`Sans nouveautés :`, `WHATSUP_SANS`) sans l'accord de l'utilisateur ; 0 coché vaut accord, avec
  la raison « rien de choisi ».
- Une fiche déjà en prod ne se réécrit pas (les utilisateurs l'ont vue) : on en fait une nouvelle.
- Aucune donnée réelle (client, personne) dans une fiche, une capture ou la page à cocher : données fictives inventées
  pour l'app (skill `osho-core:donnees-fictives` si besoin).
- Dans un repo public, rien dans une fiche qui décrive une faille de sécurité.
