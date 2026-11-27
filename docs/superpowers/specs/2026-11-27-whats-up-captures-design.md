# What's up ? v2 — des scènes faites de captures de la vraie app

Date : 2026-11-27 · Plugin : `osho-whats-up` · Suite de `2026-11-27-whats-up-design.md`.

## 1. Pourquoi

Dans la v1, les scènes sont des maquettes redessinées en HTML/CSS : elles reprennent les couleurs de l'app, pas ses
écrans. Le premier essai réel (une app Svelte + Tauri) a donné des boîtes génériques. Deux pistes ont été essayées sur
le même écran, avec la même histoire :

- **A · instantané vectoriel** (DOM rendu + règles CSS qui s'y appliquent) : fidèle de près, mais la vue d'ensemble
  s'écarte de l'app (hauteur, sections repliées, éléments manquants) et chaque app demanderait ses correctifs ;
- **B · captures animées** (la vraie app dans un navigateur, avec des données fictives, capturée par états, puis
  animée : caméra, curseur, enchaînement des états) : exacte, sans correctif par app.

Choix de l'utilisateur : **B**. La méthode (garde, lecteur, page à cocher, livraison) ne change pas.

## 2. Objectifs, non-objectifs, anti-objectifs

Objectifs
- Une scène montre la vraie app, à l'identique, dans le thème de l'utilisateur (clair ou sombre).
- Le geste reste animé : caméra qui zoome, curseur, coche, enchaînement « avant → pendant → après ».
- Rien de propre à une app dans le plugin : ce qui l'est (l'atelier) vit dans le repo de l'app.

Non-objectifs
- Vidéo, GIF, Lottie.
- Les scènes HTML/CSS de la v1 restent permises (petits schémas), mais ne sont plus la forme par défaut.

Anti-objectifs
- Une donnée réelle (client, personne, chemin, jeton) sur une capture.
- Des captures prises dans l'app de travail de l'utilisateur (son compte, ses projets).
- Une dépendance ajoutée au repo de l'app (Playwright, Puppeteer…).

## 3. L'atelier (par repo, construit à l'installation)

La vraie app, lancée dans un navigateur avec des données fictives, mise dans un état nommé par son adresse.
Versionné dans `.whatsup/atelier/`, jamais dans le build de l'app.

Contrat :
- adresse : `<url de l'atelier>?etat=<nom>&theme=clair|sombre` ;
- quand l'écran est prêt, l'atelier pose `window.__whatsupPret = true` ;
- les états vivent dans l'atelier (par exemple `.whatsup/atelier/etats.ts`) ; le rédacteur en ajoute pour chaque fiche ;
- données fictives seulement, inventées pour l'app.

Façons de le construire, dans l'ordre de préférence (l'installation choisit et le dit) :
1. l'app a un faux backend pour ses tests (IPC simulé, MSW, fixtures) → une page qui monte l'app réelle sur ce faux
   backend (cas de l'essai : `mockIPC` de Tauri, environ 40 lignes) ;
2. l'app tourne en local avec une base de démo → l'atelier est l'app locale sur une base fictive à elle (jamais la base
   de travail), avec un compte de démo ;
3. ni l'un ni l'autre → le dire, proposer de construire l'un des deux, et en attendant garder les scènes HTML de la v1.

Config : `"atelier": { "lancer": "<commande avec {port}>", "url": "http://localhost:{port}/<chemin>" }` dans
`.whatsup/config.json`.

## 4. Le capteur `capturer.mjs` (dans le plugin)

Node ≥ 22 et Chrome, sans dépendance : il lance Chrome sans interface avec le protocole DevTools (WebSocket natif de
Node), ouvre l'adresse, attend `window.__whatsupPret === true` (puis deux images), et écrit une capture WebP.

```
node <skill>/scripts/capturer.mjs --url <adresse> --sortie <fichier.webp>
     [--largeur 1440] [--hauteur 900] [--echelle 2] [--qualite 80] [--clip x,y,l,h] [--attendre 20000]
```

- Chrome : `$CHROME`, sinon l'app macOS, sinon `google-chrome`, `chromium`, `chromium-browser` sur le PATH ; absent →
  message clair, code 2.
- Pas prêt dans le délai → code 3, rien d'écrit ; toute autre erreur → code 1. Profil Chrome temporaire, supprimé.
- `--clip` en pixels CSS de la page ; l'image fait `l × échelle` sur `h × échelle`.

## 5. La fenêtre `whats-up.js` (v2)

- Une scène peut contenir `<img src="…" data-sombre="…" alt="">` : chemins relatifs au dossier des fiches seulement
  (ni schéma, ni `//`, ni `data:`), résolus contre `src`.
- Thème : attribut `theme-sombre="<sélecteur>"` sur l'élément ; si `document.documentElement.matches(sélecteur)`
  à l'ouverture d'un écran, une image prend son `data-sombre`. Sans l'attribut : `prefers-color-scheme: dark`.
- La scène n'a plus de marge intérieure (le cadrage est celui de la fiche) ; elle est `inert`.
- Fonction pure exportée `imageSure(chemin) → boolean`, testée sous node.

## 6. La fiche avec captures

Une scène = un cadre 1440 × 900 (la taille de capture) mis à l'échelle de la scène (environ 518 × 340), et dedans :
- 1 à 4 captures d'états, empilées, qui s'enchaînent par opacité (`animation-delay`) ;
- une caméra : `transform: translate() scale()` sur le cadre, de la vue d'ensemble à la zone du geste ;
- un curseur (pastille) et au besoin un surlignage, positionnés en pixels de capture ;
- état final en 1,5 s à 2 s ; `prefers-reduced-motion` → la dernière capture, cadrée, sans mouvement.

Captures en clair et en sombre (`<id>-<état>.webp`, `<id>-<état>-sombre.webp`), WebP qualité 80, échelle 2.
Au plus 4 captures par écran et 1,5 Mo par fiche, thèmes compris.

## 7. Ce qui change dans le skill

- Installer : nouvelle étape « construire l'atelier » (§3), `theme-sombre` posé sur l'élément d'après l'app, config
  `atelier`. Vérification : une capture de l'état par défaut, regardée.
- Préparer une MEP, Rédiger : le rédacteur ajoute les états à l'atelier, lance l'atelier, capture avec `capturer.mjs`,
  regarde chaque image (aucune donnée réelle, l'état attendu), puis écrit la mise en scène. Sa consigne est réécrite.
- Montrer : inchangé (captures de la fenêtre à 1440 et 390 px).

## 8. Tests

- `test_capturer.sh` : page statique servie en local qui pose `__whatsupPret` après 300 ms → un WebP valide aux
  bonnes dimensions (échelle, `--clip`) ; page jamais prête → code 3 et pas de fichier. Sauté si Chrome ou node ≥ 22
  manque.
- `test_whats_up.sh` : `imageSure` (relatif accepté ; `http:`, `//`, `data:`, `javascript:` refusés).
- Vérification dans Chrome sans interface de la fiche d'exemple avec images (thème clair et sombre).

## 9. Laissé au constructeur

La détection du chemin de Chrome selon l'OS, le texte des messages, le découpage interne de `capturer.mjs`.
