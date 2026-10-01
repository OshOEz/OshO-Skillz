# osho-mantis — design

Date : 2026-10-01 · Plugin : osho-mantis (nouveau, 0.1.0)

## But

Lancer les skills de sécurité [google/mantis](https://github.com/google/mantis) depuis Claude Code, sans clé Google ni clé API : l'abonnement Claude Code suffit (une `ANTHROPIC_API_KEY` marche aussi, sans code en plus, puisque tout passe par l'auth de Claude Code).
Deux temps : un triage court qui mesure le repo et recommande un volume, puis une campagne au volume choisi, qui produit un rapport, des corrections suggérées et un dashboard.

Succès : sur `~/dev/mantis/reference/test_targets/`, un audit Light va jusqu'au dashboard et trouve au moins une vulnérabilité connue, sans modifier un fichier de la cible hors `osho-mantis/`.

Hors périmètre : le harness ADK Python de Mantis (`reference/`) n'est ni utilisé ni modifié. Pas de suivi de budget en tokens, pas de `knowledge.db`, pas de synthèse de graphe (`--objective`).

## Composants

```
plugins/osho-mantis/
├── .claude-plugin/plugin.json
└── skills/
    ├── mantis-triage/
    │   ├── SKILL.md
    │   └── scripts/
    │       ├── inventory.py           # inventaire du repo, zéro token
    │       ├── test_inventory.py
    │       ├── check-visibility.sh    # repo public / privé / local / unknown
    │       └── test_check_visibility.sh
    └── mantis-run/
        ├── SKILL.md                   # chef d'orchestre de la campagne
        └── scripts/
            ├── render.py              # findings → README.md, patches/, dashboard.html (zéro token)
            └── test_render.py
```

- **Mantis est référencé, jamais copié** (règle `docs/decisions.md` ; Mantis est Apache-2.0, ce repo est MIT). Les skills clonent `google/mantis` dans `~/.local/share/mantis` au premier lancement, puis `git pull --ff-only` à chaque audit. Le hash utilisé est noté dans `campaign.json`.
- Les 19 `SKILL.md` de Mantis ne sont pas installés comme skills : chaque sous-agent reçoit le chemin du `SKILL.md` de son étape et le lit. Leurs descriptions ne coûtent donc rien dans les autres sessions.
- Plugin séparé d'`osho-core` : lourd, exécute du code généré. Installé par le bootstrap comme osho-core (`osho-mantis@osho-skillz`).

## Dossier d'audit

Chaque audit écrit dans le repo cible :

```
<repo>/osho-mantis/audit-2026-10-01_14h32/
├── README.md          # rapport, affiché par GitHub quand on ouvre le dossier
├── dashboard.html     # dashboard autonome, lien depuis README.md
├── patches/<id>.diff  # un diff par correction, applicable avec git apply
├── inventory.json
├── triage.md
├── campaign.json      # niveau, étapes, hypothèses, parallélisme, versionnement, hash Mantis
├── state.json         # étapes terminées, pour la reprise
└── workspace/         # contrat Mantis : plan.json, findings/*.json, learnings.jsonl, kb/…
```

La copie isolée du code utilisée pour les patchs (`workspace/shadow/`) est supprimée en fin d'audit ; seuls les diffs restent.

### Versionnement

Versionné par défaut. `check-visibility.sh` est injecté au chargement de chaque skill (syntaxe !`…` des skills Claude Code : exécution déterministe avant que Claude lise le skill, sans hook global actif dans les autres sessions). Si la sortie manque ou si la cible n'est pas le dossier courant, le skill relance le script avec Bash.

| Cas | Sortie | Comportement |
|---|---|---|
| Pas de remote | `local` | Versionné, sans avertissement |
| `gh repo view --json visibility` → `PRIVATE` / `INTERNAL` | `private` | Versionné, sans avertissement |
| → `PUBLIC` | `public` | ⚠️ Avertissement « le dossier contient des exploits » ; question : Non versionné (Recommandé) / Versionné quand même |
| `gh` absent, non connecté, ou remote hors GitHub | `unknown` | Question : Versionné / Non versionné |

Non versionné → `osho-mantis/` ajouté à `.git/info/exclude`. Le choix est écrit dans `campaign.json` ; `/mantis-run` ne repose pas la question pour le même audit. Les skills ne commitent jamais : ils finissent sur la commande `git add osho-mantis/audit-… && git commit`.

## Niveaux

| Niveau | Étapes Mantis | Hypothèses | Parallélisme |
|---|---|---|---|
| **Light** | architecture → threat-model → plan → researcher → review → patch (diff écrit, sans vérification ni re-attaque) → report. Statique seulement | 5 | 2 |
| **Sharp** | Light + structural-index, dedupe, critic, reproduce (findings High+), patch vérifié par re-attaque, calibrate | 10 | 3 |
| **Savage** | Sharp + history, reproduce sur tous les findings viables, chain, reflect | 20 | 4 |
| **Overkill** | Savage + researcher sur chaque fichier source + 2 tours reflect → replan | tous | 6 |

La question de volume (AskUserQuestion) est posée à la fin de `/mantis-triage`, et au début de `/mantis-run` si aucun `campaign.json` n'existe pour l'audit en cours. Chaque option a un sous-titre calculé à partir du triage, indiquant le coût estimé par abonnement, par exemple « Pro : 1 à 2 fenêtres · Max 5x : 1 fenêtre ». « (Recommandé) » est placé sur le niveau que le triage juge adapté à la taille et à la surface d'attaque.
Les estimations sont des ordres de grandeur (nombre d'appels d'agents × coût moyen par étape) et sont présentées comme tels.

## `/mantis-triage <repo>`

1. `check-visibility.sh` (voir Versionnement).
2. Crée `osho-mantis/audit-<date>_<heure>/`.
3. `inventory.py` (stdlib) → `inventory.json` :
   - fichiers et lignes par langage (`git ls-files`) ;
   - manifestes détectés (`package.json`, `pyproject.toml`, `go.mod`, `pom.xml`, `Dockerfile`…) ;
   - motifs de surface d'attaque (routes HTTP, `exec`/`subprocess`, SQL brut, désérialisation, upload, auth), avec le nombre d'occurrences et les fichiers ;
   - historique : nombre de commits, commits avec mots-clés sécurité (CVE, XSS, injection, sanitize, auth…) ;
   - faisabilité de reproduction : tests présents, Dockerfile, `docker info` OK, runtime `runsc` présent.
4. Un sous-agent Sonnet lit `inventory.json`, le README et 20 fichiers clés au plus, puis écrit :
   - `triage.md` : stack, top 5 des zones à risque, hors périmètre, niveau recommandé, estimation par niveau ;
   - `campaign.json` : brouillon éditable (niveau, étapes, hypothèses prioritaires, parallélisme).
5. Question de volume → niveau écrit dans `campaign.json`.
6. Propose de lancer `/mantis-run`.

Coût visé : 2 à 5 % d'une fenêtre Max 5x, 1 à 3 minutes.

## `/mantis-run [dossier d'audit]`

1. Sans argument : reprend le dernier audit non terminé du repo (`state.json`). Sans audit : lance d'abord `/mantis-triage`.
2. `check-visibility.sh` si le versionnement n'est pas encore fixé dans `campaign.json`.
3. Met à jour `~/.local/share/mantis`, note le hash.
4. **Une étape = un sous-agent** `general-purpose`. Modèle de prompt :
   « Lis `~/.local/share/mantis/<skill>/SKILL.md` et applique-le en mode standalone. Workspace : `<audit>/workspace`. Code cible : `<repo>`, en lecture seule. N'écris que dans le workspace. »
   Modèle par étape : Haiku pour history, structural-index et dedupe ; Opus pour critic, reproduce, chain et patch ; Sonnet pour le reste.
5. **Chaînage** (repris de `reference/workflow.json`), filtré par le niveau :
   `history → structural-index → architecture → threat-model → plan → researcher (×N en parallèle) → dedupe → review → critic → reproduce → chain → patch → calibrate → reflect`, puis `render.py` (zéro token, remplace l'étape mantis-report).
   Par finding : review « confirmed » → critic ; critic « viable » → reproduce ; reproduce « success » → chain → patch. Sinon le finding va directement à calibrate/report avec le motif du rejet.
   Les researchers, les reviews et les critics tournent en parallèle, dans la limite du niveau.
6. **Reprise** : chaque étape terminée est notée dans `state.json`. Un sous-agent en échec (quota, erreur) laisse l'étape « pending ». Relancer `/mantis-run` repart de là.
7. **Sécurité**
   - Reproduce : uniquement via `docker run --network=none` (avec `--runtime=runsc` s'il est présent), code monté en lecture seule. Docker absent → reproduce sauté, noté dans le rapport.
   - Patch : appliqué dans `workspace/shadow/`, jamais dans le repo. Les patchs passent un par un (copie remise à zéro avant chacun), pour éviter que deux patchs se mélangent.
   - Fin d'audit : `git status --porcelain` ne doit lister que `osho-mantis/`. Sinon, arrêt et alerte avec la liste des fichiers.
8. **Sorties** : `render.py` écrit `README.md`, `patches/<id>.diff` et `dashboard.html`, ouvert avec `open`.

## Rapport `README.md`

En français, affiché par GitHub à l'ouverture du dossier d'audit.

- En-tête : repo, date, niveau, hash Mantis, lien vers `dashboard.html`. Note : GitHub affiche le HTML en source ; il faut l'ouvrir en local.
- Tableau récapitulatif : sévérité, titre, `fichier:ligne`, reproduit, patch vérifié.
- Une section par finding, de Critical à Low : résumé, problème, cas testé (commande et sortie), diff suggéré, statut (vérifié ou non), commande `git apply patches/<id>.diff`.
- Section « Écartés » : titre et motif du rejet, une ligne par finding.
- Limites de l'audit : étapes sautées (niveau, Docker absent) ; rappel que tout finding doit être vérifié par un humain avant d'être signalé.

## Dashboard `dashboard.html`

Généré par `render.py` (stdlib) à partir de `workspace/findings/*.json`. Fichier unique : CSS, JS et données JSON inline, aucune ressource externe (s'ouvre hors ligne, rien ne sort de la machine). Clair et sombre via `prefers-color-scheme`.

1. **En-tête** : repo, date et heure, niveau, hash Mantis, durée.
2. **Stats globales** : findings par sévérité, entonnoir confirmés → reproduits → patchés, nombre d'écartés, étapes exécutées.
3. **Points critiques** : une carte par Critical ou High (`executive_summary`, `fichier:ligne`).
4. **Kanban** : colonnes Critical | High | Medium | Low | Écartés (repliée par défaut). Dans chaque colonne, les cartes sont triées par `mantis_risk_score` décroissant (absent en Light, faute de calibrate : tri par titre). Une carte affiche le titre, la CWE et les badges « reproduit » / « patch vérifié ».
5. **Panneau de détail** (clic sur une carte), 4 onglets :
   - Résumé : `executive_summary`, `impact`, `attacker_position`, `privileges_required`, `user_interaction` ;
   - Problème : `description`, `code_paths`, `reasoning`, `critic_reasoning` ;
   - Cas testé : `repro_status`, `run_command`, `repro_output`, `repro_file_path` ;
   - Correction : `patch_diff` coloré, `reattack_status`, commande `git apply`.

Un champ absent (étape non exécutée au niveau choisi) affiche « non évalué à ce niveau ».

## Tests

- `test_inventory.py` : repo git temporaire avec 2 langages, 1 route HTTP et 1 commit « fix XSS » → les compteurs attendus apparaissent dans `inventory.json`.
- `test_render.py` : 3 findings factices (Critical, Low, écarté) → le HTML contient les 3 cartes dans les bonnes colonnes, avec les données inline.
- `test_check_visibility.sh` : faux `gh` dans le PATH → `local`, `public`, `private` (y compris `INTERNAL`), remote SSH, remote hors GitHub et `gh` absent → `unknown`.
- Bout en bout : audit Light sur `~/dev/mantis/reference/test_targets/` → au moins une vulnérabilité connue trouvée, `git status` propre hors `osho-mantis/`, dashboard ouvert.

## Documentation

- `.claude-plugin/marketplace.json` : entrée `osho-mantis`.
- `docs/skills.md` : section osho-mantis (2 skills, 3 scripts).
- `README.md` : ligne dans « What you get » et commande d'installation.
- `docs/decisions.md` : « Mantis référencé dans `~/.local/share/mantis`, pas installé comme skills » et « dossiers d'audit versionnés par défaut, garde-fou sur les repos publics ».
