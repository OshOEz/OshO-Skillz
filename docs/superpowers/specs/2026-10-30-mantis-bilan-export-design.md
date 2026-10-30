# osho-mantis : bilan, exports, vue Cycle, pilotage sans console et robustesse (lot 3), design

Date : 2026-10-30 · Plugin : osho-mantis (0.3.0 vers 0.4.0) · Branche : `feat/mantis-dashboard-bilan`
Bases : [dashboard live (lot 1)](./2026-10-22-mantis-dashboard-live-design.md), [Corriger depuis le kanban (lot 2)](./2026-10-22-mantis-fix-from-kanban-design.md), tous deux fusionnés.
Cas d'essai : l'audit Overkill `Ezymob-Global/osho-mantis/audit-2026-10-29_12h07` (248 findings, 3 tours, 66 patchs), **en lecture seule** : les scripts tournent sur une copie (`mktemp -d`).
Modèles visuels : la synthèse Kata (`synthese-kata.html`, pièce jointe) pour le bilan ; le SIPOC de Kata (`web/app/liens/VueSipoc.tsx`, `liens.css`, `encart.ts` sur la branche `dev`) pour la vue Cycle.

## Intention

Le premier audit Overkill réel a tenu jusqu'au bout, mais il a révélé quatre manques :

1. **Rien à remettre aux développeurs.** Le `README.md` fait 629 Ko et liste 248 findings ; le dossier d'audit contient des fichiers de session (`server.json` avec la clé du dashboard, `commands*.jsonl`), des chemins de l'hôte et, dans un finding, une vraie clé Google du dépôt. L'équipe qui reçoit l'audit a besoin d'une **synthèse lisible** et d'un **paquet réutilisable**, sans rien de sensible.
2. **Le déroulé est illisible.** Trois tours d'Overkill rejouent plan → reflect ; le pipeline actuel ne montre que le tour en cours.
3. **Le terminal reste indispensable** pour lancer l'audit après le triage et pour tout ce qui arrive quand aucune session n'écoute.
4. **L'orchestrateur est fragile** : coupures de quota, un helper `jq` qui a vidé 10 findings, des reproductions impossibles hors ligne, des patchs vérifiés un par un sur un seul shadow.

Le coût de l'audit (environ 294 $ en équivalent API, 2 h 46 de travail actif pour près de 20 h d'horloge à cause des pauses de quota) n'apparaît nulle part.

## Objectifs

1. **Bilan** : un onglet « Bilan » du dashboard, aussi produit en `bilan.html` autonome, sur le modèle de la synthèse Kata (structure et ton ; style du dashboard), **sans** note ni plafond.
2. **Exports depuis le dashboard**, sans console :
   - **léger** : `bilan.html` + `dashboard.html` (zip de deux fichiers) ;
   - **complet** : zip de tout ce que l'audit a créé, nettoyé (voir §3).
   Tous deux contiennent une section « Pour l'équipe de développement » (§2.4).
3. **Vue Cycle** du pipeline : des cartes d'étapes reliées par des flèches animées (dessin SIPOC), une rangée par tour, la rangée suivante apparaît quand un tour commence.
4. **Pilotage sans console** : lancer l'audit, répondre, mettre en pause, reprendre, arrêter, relancer, corriger, exporter, saisir le coût, tout depuis la page. Ce qui exige une session Claude passe par la file de commandes existante ; quand aucune session n'écoute, la page le dit et dit quoi faire (§4.3).
5. **Coût et durées** : coût estimé calculé automatiquement depuis les transcripts Claude Code, remplaçable par une saisie ; temps actif et temps d'horloge.
6. **Robustesse** de mantis-run (§6) : reprise après coupure, `force_repro` qui force vraiment, sauvegarde des findings avant chaque étape parallèle, volume Docker de dépendances, doublures d'amont, un shadow par finding pour paralléliser patch + re-attaque, re-vérification des patchs du tour 1 devenus reproductibles, réfection des patchs contournés.

## Non-objectifs

- Pas de note globale, de lettre, ni de plafonnement des scores par les constats (explicitement écarté par l'utilisateur).
- Jamais de lancement de Claude par le serveur (décision 3).
- Pas de dépendance nouvelle : Python 3 stdlib, HTML/CSS/JS sans build. Pas de PDF.
- Pas de modification des SKILL.md de Mantis amont ni du repo kata.
- Pas de masquage dans les exports (décision 4) : le contenu part brut. La détection de secrets ne sert qu'à prévenir et à lister ce qu'il faut révoquer ; elle se fait par motifs, sans garantie d'exhaustivité.

## Anti-objectifs (échec même si « ça marche »)

- Un export contient `server.json`, la clé de session ou une commande du dashboard.
- Un export qui contient des secrets part sans avertissement visible ni liste des secrets à révoquer.
- Le bilan affirme plus que les findings : un constat non reproduit présenté comme prouvé, un patch `MITIGATION_PROPOSED` présenté comme vérifié.
- Un chiffre de coût présenté comme une facture : c'est une estimation au tarif public de l'API, à dire comme telle.
- Une animation qui tourne alors que rien ne tourne (étape `done`, audit en pause ou sans session).
- Les gardes existantes (symlinks, shadow guard, clé de session, `Origin`) affaiblies.

## 1. Architecture

```
render.py ── build_snapshot ──► README.md, patches/, dashboard.html (existant)
          └─ bilan.py ─────────► bilan.html               (nouveau, HTML statique, sans JS)
dashboard.py serve : GET /bilan  (bilan.html à la volée, mode live : « audit en cours »)
                     GET /export?kind=light|full  (zip en flux, export.py)
                     POST /command  (+ launch, set_cost)
cost.py      transcripts ~/.claude/projects → cost.json (jetons par modèle, $, temps actif)
guard.py     backup | check | restore des findings ; resume → RESUME.md
```

Nouveaux fichiers du dossier d'audit : `bilan.html`, `cost.json`, `RESUME.md`, `workspace/backups/<étape>-r<tour>-<horodatage>/` (3 derniers gardés).

## 2. Bilan

### 2.1 Forme

- Un seul générateur Python (`bilan.py`, fonction `bilan(snapshot, extras) -> str`), qui échappe tout texte issu des findings avec `html.escape` (repo potentiellement hostile). Pas de JS dans le bilan.
- Le fichier autonome `bilan.html` est écrit par `render.py` à côté de `dashboard.html`. L'onglet « Bilan » du dashboard l'affiche dans une `iframe sandbox` : `src="/bilan"` en live, `src="bilan.html"` dans le `dashboard.html` final. Les liens d'un constat pointent vers `dashboard.html#<id>` (le bilan ne recopie pas les 248 fiches).
- Style : celui du dashboard (décision 6), jetons Horizon recopiés de `dashboard.html` (fonds, cartes, accent bleu, couleurs de sévérité, Source Sans 3 / Geist Mono), clair et sombre, `max-width: 1040px`, impression propre (`@media print`). La synthèse Kata ne sert que de modèle de structure et de ton.

### 2.2 Plan (repris de Kata, adapté)

1. **Bandeau et titre** : « <repo> : bilan de l'audit de sécurité », moteur (Mantis `<commit>`, niveau, nombre de tours), limites en une phrase (statique pour Light ; reproduction en Docker hors ligne sinon).
2. **Paragraphe d'ouverture** : dépôt et commit audités (`base_commit`), verdict en une phrase, coût estimé et durées.
   Verdict, règle simple, sans note : constats `CRITICAL`/`HIGH` non écartés dont le patch n'est pas `VERIFIED_SECURE` → « N failles critiques ou hautes restent ouvertes : à corriger avant d'exposer l'application » ; sinon « Aucune faille critique ou haute ouverte » avec les réserves.
3. **Sommaire**.
4. **Le dépôt audité** : pile et zones à risque (extraits de `triage.md`).
5. **En bref** : tuiles (constats valides par gravité, reproduits, patchs vérifiés / contournés / proposés), « Le plus grave » (5 constats max, une phrase chacun), « Réserves » (risques résiduels, prérequis de déploiement, rotations de secrets, tirés des `notes`).
6. **Ce que veulent dire gravité, reproduction et statut de patch** : échelles en langage simple.
7. **Les constats** : tableau par gravité (id court, titre, `fichier:ligne`, reproduction, patch, score), écartés repliés.
8. **Pour l'équipe de développement** (§2.4).
9. **Déroulé de l'audit** : tours, étapes, durées, coût par modèle, temps actif / d'horloge, incidents (notes contenant « INCIDENT », « arrêt », « reprise »).
10. **Comment ces résultats ont été vérifiés** : critic, reproduction `--network=none`, re-attaque par un agent distinct ; limites de couverture (notes « non lus », « partiel »).
11. **Lexique** (finding, PoC, re-attaque, shadow, `MITIGATION_PROPOSED`…).

Notes d'un constat : une note de `state.json` qui contient l'id court (8 premiers caractères) ou le stem d'un finding est rattachée à ce finding (prérequis, résiduel, conflit).

### 2.3 Pendant l'audit

`GET /bilan` produit le bilan à partir du snapshot courant, avec un bandeau « Audit en cours, tour N : bilan provisoire ».

### 2.4 Pour l'équipe de développement

Section commune au bilan et au `LISEZMOI-DEV.md` de l'export complet :

- **Lire l'audit** : bilan d'abord, puis `dashboard.html` (filtre, fiche d'un constat), puis `workspace/findings/<stem>.json` pour le détail brut.
- **Appliquer un patch** : `git checkout <base_commit>` (ou une branche à partir de lui), `git apply --check patches/<id>.diff && git apply patches/<id>.diff`. Ordre conseillé : gravité décroissante, patchs `VERIFIED_SECURE` d'abord.
- **Prérequis par patch** : tableau patch → prérequis de déploiement et risques résiduels (champ `deploy_prerequisites` du finding s'il existe, sinon les notes rattachées).
- **Patchs en conflit** : calculés par `export.py` en lisant les diffs : deux patchs qui touchent le même fichier avec des plages de lignes qui se chevauchent sont « en conflit probable » ; même fichier sans chevauchement : « à appliquer dans l'ordre ». Plus les conflits cités dans les notes.
- **Rejouer une reproduction** : commande `docker run` du PoC (`workspace/reproducers/`), volume de dépendances à recréer (§6.4).
- **Secrets à révoquer** (§3.3) : findings et patchs qui contiennent une valeur de secret, listés, avec la consigne de révoquer ces secrets et de transmettre l'archive par un canal privé.

## 3. Exports

### 3.1 Déclenchement

- Onglet Bilan, deux boutons : « Exporter le bilan (HTML) » et « Exporter tout l'audit (zip) ». Liens `GET /export?kind=light|full`, protégés par la clé de session (cookie), réponse `application/zip` en flux, nom `mantis-<repo>-<audit>-<léger|complet>.zip`. Rien n'est écrit dans le dossier d'audit (zip dans un fichier temporaire supprimé après envoi).
- N'exige pas de session Claude : le serveur suffit. Dans le `dashboard.html` final hors ligne, les boutons sont remplacés par « Exports disponibles avec le dashboard en direct ».
- CLI identique pour les tests et le terminal : `python3 export.py light|full <AUDIT> <sortie.zip>`.

### 3.2 Contenu

- **Léger** : `bilan.html`, `dashboard.html`, régénérés.
- **Complet** : tout le dossier d'audit, sauf : `server.json`, `server.log`, `waiting.json`, `commands.jsonl`, `commands-done.jsonl`, `workspace/backups/`, fichiers `*.tmp`, et **tout lien symbolique** (jamais suivi). Ajout de `LISEZMOI-DEV.md` (§2.4) et `MANIFESTE.json` (liste des fichiers, exclusions, secrets repérés).
- Garde : le dossier d'audit passe le contrôle « hostile » existant avant l'export ; chaque chemin ajouté au zip est résolu et doit rester sous `AUDIT`.

### 3.3 Contenu brut, secrets signalés (décision 4)

- Rien n'est masqué ni réécrit : les fichiers partent tels quels (seules les exclusions du §3.2 s'appliquent).
- `export.py` repère les valeurs de secret par motifs (clé Google `AIza…`, AWS `AKIA…`, clé privée PEM, jetons `ghp_`/`github_pat_`, `xox[bp]-`, `sk-…`, URL avec identifiants `://user:pass@`) dans les fichiers texte, et rattache chaque fichier touché à son finding ou à son patch.
- Avertissement, avant l'export dans la page (boîte de confirmation des deux boutons), en tête de `LISEZMOI-DEV.md` et dans le bilan : « Cette archive contient des secrets en clair et le détail d'exploits : à transmettre par un canal privé uniquement. Secrets à révoquer : … ». La liste donne le finding ou le patch, le type de secret et le fichier, pas la valeur.
- `MANIFESTE.json` : fichiers inclus, exclusions, secrets repérés (fichier, type, finding).

## 4. Pilotage sans console

### 4.1 Lancer l'audit

Aujourd'hui le triage finit par « Lancer `/mantis-run` ? ». Désormais (décision 2) la question Volume du triage devient « Lancer l'audit » : chaque option est « Lancer en <niveau> » (description et coût inchangés), plus « Plus tard ». Une réponse de niveau enchaîne **dans la même session** sur mantis-run avec ce dossier ; « Plus tard » écrit le niveau et termine, et le dashboard affiche alors le bouton « Lancer l'audit » (commande `launch`, §4.2).

### 4.2 Nouvelles commandes

| action | Quand | Qui l'applique |
|---|---|---|
| `launch` | niveau choisi, `state.json` absent ou audit arrêté | la prochaine session mantis-run (la reprend au §1) |
| `set_cost` | toujours ; `{usd: nombre ≥ 0 ou null, note?: texte ≤ 200}` | **le serveur** directement (comme `merge_fix`) : écrit `cost.json.manual` ; `null` revient au calcul auto |

### 4.3 Aucune session à l'écoute

Contrainte : Claude n'exécute rien hors d'une session ouverte. Aujourd'hui le serveur refuse (409) tout POST sans session. Désormais (décision 3) :

- `launch`, `resume`, `retry`, `fix`, `false_positive`, `prioritize_repro` sont **acceptées et mises en file** : la page les montre « en file, en attente d'une session Claude ».
- Un bandeau dit quoi faire, avec un bouton « Copier » : « Aucune session Claude n'écoute. Ouvre Claude Code dans `<repo>` et tape `/mantis-run "<AUDIT>"` : la file sera reprise. »
- mantis-run, à l'ouverture (§1), traite toute la file en attente avant de reprendre : `launch` vaut accord de lancement, `resume`/`retry` sont appliquées, `pause`/`stop` restées en file sont refusées « plus d'actualité ».
- `pause`, `stop`, `answer`, `end_fixes` restent refusées (409) sans session : elles n'ont de sens que pour une session vivante.
- `merge_fix`, `set_cost` et les exports marchent toujours (serveur seul).

### 4.4 Durée de vie du serveur

Le serveur ne s'arrête plus 30 min après la fin **tant qu'une page est connectée** (exports et correctifs restent possibles). Il s'arrête 30 min après la fin sans page connectée, ou après 4 h sans changement ni page (inchangé), ou 24 h quoi qu'il arrive (inchangé). Relancer le serveur reste une commande terminal (`dashboard.py serve`), indiquée sur la page hors ligne.

## 5. Coût et durées

### 5.1 Calcul automatique (`cost.py`)

- Sources : les transcripts Claude Code `$CLAUDE_CONFIG_DIR` (défaut `~/.claude`) `/projects/*/<session>.jsonl` modifiés après le début de l'audit **et** qui contiennent le chemin du dossier d'audit, plus leurs sous-agents `<session>/subagents/*.jsonl`.
- Fenêtre : du début du triage (`inventory.json`) à `finished_at` (ou maintenant). Les messages hors fenêtre sont ignorés (la même session sert souvent après l'audit).
- Jetons : une fois par `message.id` (les lignes de streaming répètent l'usage), par modèle : entrée, sortie, lecture de cache, écriture de cache 5 min et 1 h.
- Prix : table en tête de `cost.py`, datée, tarif public de l'API (par Mtok : Opus 5.5 4 / 20, Opus 4.8 5 / 25, Sonnet 5.5 2 / 10, Haiku 5.5 0,10 / 0,50 ; lecture de cache 0,1×, écriture 5 min 1,25×, 1 h 2×). Un modèle absent de la table : ses jetons sont comptés, son coût n'est pas, et la page le dit.
- **Temps actif** : sur la session principale seule, somme des écarts entre messages consécutifs inférieurs à 120 s. **Temps d'horloge** : `started_at` → `finished_at`.
- Vérifié sur le cas d'essai : 300,6 $ (référence 294 $, écart 2 %) et 2 h 46 min actives (référence 2 h 46) pour 19 h 57 d'horloge.
- Résultat dans `cost.json` : `{auto: {usd, by_model, active_s, sessions, computed_at}, manual: {usd, note, at} | null}`. Calculé par `render.py` et à la demande depuis la page (bouton « Recalculer », serveur seul). Jamais de contenu de transcript copié, seulement des nombres.

### 5.2 Affichage

Bannière : « ≈ 301 $ (équivalent API) · 2 h 46 actives · 19 h 57 au total ». Clic → panneau détail par modèle + champ de saisie (`set_cost`). Une saisie manuelle prime et s'affiche « saisi ». Bilan : même chiffres, avec la mention « estimation au tarif public de l'API Claude, pas une facture ; sur abonnement, l'audit consomme du quota ».

## 6. Robustesse de mantis-run (SKILL.md + `guard.py`)

Tirée des `notes` et des `trajectory_insight` du cas d'essai.

1. **Reprise après coupure.** `python3 guard.py resume <AUDIT>` (zéro jeton) écrit `RESUME.md` depuis `state.json` : tour, étapes, étape interrompue, `force_repro`, périmètres en cours, règles (volume Docker, Docker seul), commandes de vérification (conteneurs `mantis-<audit>-*` orphelins, `*.tmp`). Appelé à chaque passage d'étape à `running` et à l'arrêt. À la reprise : contrôle d'intégrité (`guard.py check`), nettoyage des conteneurs orphelins **de cet audit seulement** (noms préfixés), puis reprise.
2. **`force_repro` force vraiment.** Un finding listé est reproduit même s'il a déjà un `repro_status`, sauf s'il a `repro_round` égal au tour courant (écrit par l'agent de reproduction). Il sort de `force_repro` une fois fait.
3. **Sauvegarde et validation des findings.** Avant toute étape qui écrit des findings en parallèle (dedupe, review, critic, reproduce, patch, calibrate) : `guard.py backup <AUDIT> <étape>`. Après chaque lot : `guard.py check` (chaque JSON lisible, non vide, garde son `id` et au moins ses champs d'avant). Un fichier en défaut est restauré depuis la sauvegarde, avec une note. Règle ajoutée au prompt d'agent : « écrire dans un nouveau fichier, le valider, puis le renommer ; jamais `jq … > même_fichier` ; fichiers temporaires seulement sous `workspace/tmp/` ».
4. **Volume Docker de dépendances** (Sharp+, décision 5, automatique, sans question ; le journal et la page disent « remplissage du volume de dépendances, avec réseau ») : pour les piles Maven, Gradle, npm, pip repérées par l'inventaire, un conteneur **avec réseau** remplit une fois `mantis-<repo>-deps` (`--ignore-scripts` pour npm, dépôt monté en lecture seule), puis toute reproduction monte ce volume en **lecture seule**, `--network=none`. Noté dans `state.json` (`deps_volume`).
5. **Doublures d'amont.** Ligne ajoutée au prompt de reproduction : AWS Secrets Manager, Google, etc. sont remplacés par des doublures dans le conteneur ou sur un réseau `docker network create --internal` ; jamais de vrai point d'accès. Les doublures écrites vont dans `workspace/reproducers/` pour être réutilisées.
6. **Un shadow par finding.** Patch + re-attaque (Sharp+) : chaque finding a son propre `mktemp -d` (liste `shadows` dans `state.json`, même garde que le shadow principal), lots de `parallel` findings en parallèle au lieu d'un à la fois. Le contrôle `git apply` et le statut final restent faits par mantis-run.
7. **Re-vérifier les patchs du tour 1.** Un finding devenu `reproduced` dont le patch est `MITIGATION_PROPOSED` entre dans patch + re-attaque.
8. **Refaire les patchs contournés** (Overkill, tours 2 et 3) : `VERIFICATION_FAILED` rentre dans le périmètre de patch ; l'ancien diff et le résultat de re-attaque vont dans `previous_patches`, et le prompt demande de traiter les « voies voisines » (autres routes, loggers, appelants du même défaut). Les LOW notés ≥ 5,0 par calibrate entrent aussi au tour suivant.
9. Règle « rien sur l'hôte » répétée dans chaque prompt d'étape ; refus du filtre de l'API : statut noté, finding laissé `statically_confirmed`, pas de nouvelle tentative automatique.

## 7. Vue Cycle

- Remplace les vues Réseau et Matrice (décision 1).
- **Cartes** : une par étape (code, nom, état en mot, durée, lot `k/n` et workers pour l'étape active), sur fond pointillé (`radial-gradient`, comme `.sp-zone`). Rangée « Préparation » (triage, history, structural-index, architecture, threat-model), puis une rangée par tour (plan → reflect). Overkill : la rangée du tour 2 (puis 3) apparaît, en fondu, quand `round` passe à 2.
- **Flèches** : courbes de Bézier SVG `M x1 y1 C mx y1, mx y2, x2 y2` entre cartes (calcul repris de `encart.ts`), bouts ronds en HTML, et une flèche de retour reflect (tour N) → plan (tour N+1). Flèche entrante de l'étape `running` : trait animé (`stroke-dasharray` + `stroke-dashoffset` en boucle) ; étapes faites : trait plein ; à venir : pointillé gris. Rien n'est animé en pause, sans session ou avec `prefers-reduced-motion`.
- Tours passés : statut et durées par tour déduits d'`activity.jsonl` (k-ième passage de `plan` = tour k) ; les nouveaux événements d'étape portent `round`.
- Clic sur une carte : le panneau d'étape existant (notes, Relancer).
- Accessibilité : cartes focusables, état en texte, `aria-live` inchangé.

## 7 bis. Fil de Claude (demande de l'utilisateur, 2026-10-30)

« En bas à droite ajoute un tab qui ouvre une fenêtre en bas en mode chat qui donne la sortie de Claude pendant tout le process. Pas d'écriture, que de l'affichage (comme des logs). »

- Un onglet « Fil de Claude » ancré en bas à droite ouvre un panneau en bas de page (tiroir, hauteur réglable, refermable), présenté comme une conversation : une bulle par message, avec l'heure et l'auteur (« Claude » pour l'orchestrateur, la `description` de l'agent pour un sous-agent, par exemple « R2 critic groupe 02 »).
- **Lecture seule** : pas de champ de saisie, pas d'envoi. Le défilement suit le bas tant que l'utilisateur n'est pas remonté.
- Source : les transcripts Claude Code de l'audit, trouvés comme dans `cost.py` (`find_sessions`, même fenêtre). On affiche : texte des messages de l'assistant (session principale et sous-agents), et une ligne par lancement et fin de sous-agent (nom, modèle). Pas les résultats d'outils ni les entrées utilisateur (trop volumineux, et ils peuvent contenir des secrets ou des fichiers entiers). Texte coupé à 2 000 caractères par bulle.
- Serveur : `GET /feed?after=<curseur>` (clé exigée) renvoie au plus 200 éléments `{at, who, text, kind}` et le curseur suivant (position par fichier) ; la page interroge toutes les 2 s quand le panneau est ouvert, toutes les 10 s sinon (pastille « nouveaux messages »). Lecture incrémentale des fichiers, jamais d'écriture.
- Triage, audit, correctifs : couverts tant que la session qui les mène mentionne le dossier d'audit (c'est le cas dès le triage, qui le crée).
- `dashboard.html` final et exports : l'onglet est masqué ; le contenu des transcripts n'est jamais copié dans un fichier de l'audit.
- Affichage par `textContent` uniquement (sortie de Claude potentiellement issue d'un repo hostile).
- Tests : extraction (texte assistant gardé, résultats d'outils exclus, doublons de streaming fusionnés par `message.id`), curseur incrémental, route sans clé = 403.

## 8. Onglets

Barre d'onglets sous la bannière (l'onglet « Fil de Claude » du §7 bis est à part, en bas à droite) : **Suivi** (pipeline + kanban + colonne de droite, l'existant) et **Bilan** (iframe + boutons d'export + coût). Onglet mémorisé dans `localStorage`, lien `#bilan`.

## 9. Tests (auto-tests exécutables, comme les existants)

- `test_bilan.py` : bilan sur un audit fictif (Light, Overkill 3 tours, en cours, aucun finding) ; XSS dans titre et notes ; verdict ; rattachement des notes ; pas de plafond ni de note.
- `test_export.py` : exclusions (`server.json`, `commands*.jsonl`…), symlink ignoré, chemin hors `AUDIT` refusé, contenu identique à la source, secrets repérés et listés avec leur finding, conflits de patchs (chevauchement, même fichier sans chevauchement), zip lisible.
- `test_cost.py` : transcripts fictifs (doublons de `message.id`, fenêtre, modèle inconnu, sous-agents), temps actif, saisie manuelle prioritaire.
- `test_guard.py` : backup / check / restore (fichier vidé, JSON tronqué), `RESUME.md`.
- `test_commands.py`, `test_dashboard.py` : `launch`, `set_cost`, file sans session (acceptées / 409), `GET /export` sans clé = 403, `GET /bilan`, durée de vie du serveur.
- `test_snapshot.py` : statut par tour et `round` dans les événements.
- Vérification manuelle : rendu et exports sur une copie du cas d'essai ; ouverture de `bilan.html` et du zip.

## 10. Laissé au constructeur

Découpage du JS, noms internes, formulation exacte des textes (français, sans tiret cadratin), forme exacte de `cost.json` et du manifeste, liste exacte des motifs de secrets, mise en page des cartes dans la largeur.

## Décisions de l'utilisateur (2026-10-30)

1. Vue Cycle : remplace Réseau et Matrice.
2. La réponse à la question Volume lance l'audit (« Lancer en <niveau> » / « Plus tard ») ; bouton « Lancer l'audit » seulement après « Plus tard ».
3. Sans session : file + commande `/mantis-run` à taper ; le serveur ne lance jamais `claude -p`.
4. Exports bruts, sans masquage ; avertissement clair (page, `LISEZMOI-DEV.md`, bilan) et liste des findings et patchs qui contiennent des secrets, à révoquer.
5. Volume Docker de dépendances créé et rempli automatiquement en Sharp+, le remplissage avec réseau est signalé.
6. Bilan au style du dashboard (Horizon) ; la synthèse Kata reste le modèle de structure et de contenu, sans plafond.
