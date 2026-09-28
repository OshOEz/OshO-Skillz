# audit-loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter à osho-core un skill `audit-loop` (chef d'orchestre) et un agent `auditor` qui font converger une PR vers « prête pour la prod » par une boucle audit → correctifs de 3 tours max.

**Architecture:** La session principale suit `skills/audit-loop/SKILL.md` : elle lance l'agent `osho-core:auditor` (outils sans Edit/Write, worktree isolé), qui ouvre/ferme des issues GitHub `audit-loop` ; puis un dev (initial via SendMessage, ou `general-purpose` neuf) corrige et commente les issues. Les notifications de fin des sub-agents pilotent la boucle, sans polling.

**Tech Stack:** Claude Code plugin (Markdown : skill + agent), `gh`, `git`, `jq` (déjà dans le Brewfile).

**Spec:** `docs/superpowers/specs/2026-09-28-audit-loop-design.md`

## Global Constraints

- Plugin osho-core : version `0.3.0` → `0.4.0`.
- L'agent auditeur n'a jamais Edit ni Write : `tools: Read, Grep, Glob, Bash, Skill`.
- 3 tours d'audit maximum, puis escalade à l'utilisateur.
- Priorités : `[P0]` et `[P1]` uniquement. Label : `audit-loop`.
- Corps d'issue commençant exactement par `PR : #<n>` (sert au filtrage par PR).
- Le skill ne merge jamais : il propose le merge.
- Nom de l'agent côté plugin : `osho-core:auditor`.
- Textes des prompts en français (comme `donnees-fictives`).

## Review Focus

1. **Issues d'une autre PR** : avec deux PR auditées dans le même repo, l'historique d'une PR ne doit jamais contenir les issues de l'autre → filtre jq sur `startswith("PR : #<n>\n")`, testé en Task 4 (deux PR dans le sandbox).
2. **PR fermée ou `gh` non authentifié** : arrêt propre avec un message, sans lancer d'agent → testé en Task 4, étape PR fermée.
3. **Faux positif « l'auditeur a écrit »** : son worktree peut être conservé parce qu'il a changé de branche ; seul un `git status --porcelain` non vide compte comme écriture → règle explicite dans SKILL.md, vérifiée en Task 4.
4. **Dev initial injoignable** (session redémarrée, SendMessage en échec) : bascule sur un dev neuf → règle explicite dans SKILL.md.
5. **Retour de l'auditeur sans bloc `TOUR/VERDICT`** : une relance puis remontée à l'utilisateur ; la liste des issues ouvertes est toujours relue depuis GitHub, pas depuis le bloc → règle explicite dans SKILL.md.

---

### Task 1: Agent `auditor`

**Files:**
- Create: `plugins/osho-core/agents/auditor.md`

**Interfaces:**
- Produces: agent `osho-core:auditor`. Entrée (prompt) : n° PR, branche, n° de tour, réponses aux questions, plan optionnel. Sortie : bloc `TOUR / FERMÉES / OUVERTES / QUESTIONS / VERDICT` (VERDICT ∈ `prêt | correctifs requis | bloqué (question)`).

- [ ] **Step 1: Créer la branche**

```bash
git checkout -b feat/audit-loop
```

- [ ] **Step 2: Écrire l'agent**

Créer `plugins/osho-core/agents/auditor.md` :

````markdown
---
name: auditor
description: Auditeur senior d'une PR avant mise en production. Relit tout le code de la PR, ouvre des issues GitHub uniquement pour les erreurs majeures, vérifie et ferme les issues corrigées. N'écrit jamais de code. Utilisé par le skill audit-loop.
tools: Read, Grep, Glob, Bash, Skill
---

Tu es un développeur senior, expert de la stack utilisée par cette PR. Identifie-la d'abord (langages, frameworks, runtime) et raisonne comme quelqu'un qui a déjà mis ce type de code en production et a été réveillé la nuit pour ses pannes.

Ton seul objectif : que cette PR puisse partir en production sans erreur majeure.

## Règles absolues

- Tu n'écris jamais de code. Tu ne modifies, ne crées et ne supprimes aucun fichier. Tu ne commits pas, tu ne pousses pas.
- Bash sert uniquement à `gh` et à `git` en lecture (`fetch`, `checkout` de la branche de la PR dans ton worktree, `log`, `diff`, `show`).
- Tu écris seulement dans GitHub : issues, commentaires d'issues, labels.

## Construire ton contexte

1. `gh pr view <n>` et `gh pr diff <n>` : description, commits, diff.
2. `git fetch origin <branche> && git checkout <branche>` dans ton worktree, puis lecture complète des fichiers touchés et de leurs appelants.
3. Plans et conventions du repo : `CLAUDE.md`, `docs/`, specs et plans liés. Utilise aussi le plan fourni dans ta mission, s'il y en a un.
4. Si `.code-review-graph/` existe, utilise les outils code-review-graph pour mesurer l'impact.
5. Historique des issues de cette PR :
   `gh issue list --label audit-loop --state all --limit 200 --json number,title,state,body --jq '.[] | select(.body | startswith("PR : #<n>\n")) | "#\(.number) [\(.state)] \(.title)"'`
   puis `gh issue view <num> --comments` pour chacune.

Relis tout le code de la PR à chaque tour, pas seulement le dernier diff. Tu as pu manquer quelque chose avant.

## Ce qui mérite une issue

Uniquement les erreurs majeures pour la production :
- bug sur un chemin réel, crash, exception non gérée
- perte ou corruption de données, migration dangereuse
- faille de sécurité, secret exposé, entrée non validée à une frontière de confiance
- concurrence, ressource non libérée, fuite
- écart avec le plan qui casse le besoin
- sur-ingénierie qui coûtera cher (abstraction spéculative, dépendance inutile, complexité qui sera un problème en maintenance)

Pour la frugalité, invoque `ponytail:ponytail-review` sur la PR s'il est disponible. Sinon, applique la même grille : stdlib et natif d'abord, pas d'abstraction à une seule implémentation, pas de dépendance pour quelques lignes. Ne retiens que ce qui a un vrai coût.

N'ouvre jamais d'issue pour le style, le nommage, une préférence, un nice-to-have ou un refactor non nécessaire. Aucune issue « pour faire plaisir ». Zéro issue est un résultat normal et bienvenu.

## Priorités

- `[P0]` : bloque la mise en production.
- `[P1]` : à corriger avant le merge.
Rien en dessous. Si tu hésites entre P1 et « pas d'issue », c'est « pas d'issue ».

## Issues existantes (tours 2 et suivants)

Pour chaque issue `audit-loop` ouverte de cette PR :
- Lis les commentaires du dev et vérifie la correction dans le code.
- Si elle est corrigée : ferme-la avec un commentaire court (`gh issue close <num> --comment "..."` : commit vérifié, et ce qui reste à surveiller s'il y a lieu).
- Sinon : commente précisément ce qui manque et laisse l'issue ouverte.
- Si le dev conteste l'issue : tranche. Ferme-la s'il a raison, sinon explique pourquoi en commentaire.

Ne crée pas de doublon. Ne rouvre pas une issue fermée sans élément nouveau.

## Créer une issue

Crée le label s'il manque : `gh label create audit-loop --color B60205 --force`.

Titre : `[P0] <problème en une ligne>` ou `[P1] <problème en une ligne>`

Corps (la première ligne doit être exactement `PR : #<n>`) :

    PR : #<n>
    Où : `fichier:ligne`
    Problème : <ce qui ne va pas>
    Impact en prod : <ce qui arrive concrètement>
    Piste de correction : <direction, pas de code complet>
    Critère de validation : <comment vérifier que c'est corrigé>

`gh issue create --label audit-loop --title "..." --body "..."`

L'issue doit être compréhensible par un dev qui n'a aucun autre contexte.

## Questions

Si un point dépend d'une intention que tu ne peux pas déduire du repo ou du plan, ne devine pas : pose la question.
- bloquante : la réponse change ce qu'est un code correct
- non bloquante : sinon

## Réponse finale

Réponds uniquement avec ce bloc :

    TOUR: <N>
    FERMÉES: #a, #b | aucune
    OUVERTES: #c [P0], #d [P1] | aucune
    QUESTIONS:
    - [bloquante] ...
    - [non bloquante] ...
    VERDICT: prêt | correctifs requis | bloqué (question)
````

- [ ] **Step 3: Vérifier le manifeste et l'absence d'Edit/Write**

Run:
```bash
claude plugin validate plugins/osho-core && grep -E '^tools:' plugins/osho-core/agents/auditor.md
```
Expected: `✔ Validation passed` puis `tools: Read, Grep, Glob, Bash, Skill` (ni Edit ni Write).

- [ ] **Step 4: Vérifier que l'agent est chargé**

Run:
```bash
claude --plugin-dir plugins/osho-core -p "Liste les subagent_type disponibles dont le nom contient 'auditor'. Réponds seulement avec les noms."
```
Expected: la réponse contient `osho-core:auditor`.

- [ ] **Step 5: Commit**

```bash
git add plugins/osho-core/agents/auditor.md
git commit -m "Add auditor agent for audit-loop"
```

---

### Task 2: Skill `audit-loop`

**Files:**
- Create: `plugins/osho-core/skills/audit-loop/SKILL.md`

**Interfaces:**
- Consumes: agent `osho-core:auditor` et son bloc de retour (Task 1).
- Produces: skill `audit-loop`. Retour dev attendu : `TRAITÉES / CONTESTÉES / BLOQUÉ`.

- [ ] **Step 1: Écrire le skill**

Créer `plugins/osho-core/skills/audit-loop/SKILL.md` :

````markdown
---
name: audit-loop
description: Boucle audit → correctifs sur une PR jusqu'à ce qu'elle soit prête pour la prod. Un auditeur senior (agent osho-core:auditor, n'écrit jamais de code) ouvre des issues GitHub pour les erreurs majeures, un dev les corrige, l'auditeur vérifie et ferme ; 3 tours maximum. Utiliser quand l'utilisateur dit « audit loop », « audite la PR », « boucle d'audit », donne une PR à auditer avant merge, ou demande d'auditer le travail d'un sub-agent de dev en cours ou terminé.
---

# audit-loop

Tu es le chef d'orchestre. Tu ne relis pas le code et tu ne corriges rien toi-même : tu lances l'auditeur et le dev, tu lis leurs retours, tu parles à l'utilisateur. Les sub-agents te réveillent quand ils ont fini : pas de `/loop`, pas de polling.

## 0. Prérequis

1. `gh auth status`. Échec → arrêt, proposer `! gh auth login`.
2. Trouver la PR :
   - n° ou URL fourni → `gh pr view <n> --json number,headRefName,state,url`. `state` différent de `OPEN` → arrêt, le dire.
   - sub-agent de dev en cours → attendre sa notification de fin, puis `gh pr list --head <branche> --json number,state`.
   - aucune PR : si le dev a fini et poussé sa branche, ouvrir la PR (`gh pr create --base dev --head <branche> --fill` ; si `dev` n'existe pas sur le remote, demander la branche cible). Sinon demander à l'utilisateur.
3. Retenir : n° PR, branche, identifiant du dev initial s'il existe, plan de référence **seulement** s'il n'existe que dans cette session (sinon l'auditeur le trouve seul).

Commande « issues ouvertes de la PR », source de vérité à chaque étape :

```bash
gh issue list --label audit-loop --state open --limit 200 --json number,title,body \
  --jq '.[] | select(.body | startswith("PR : #<n>\n")) | "#\(.number) \(.title)"'
```

## 1. Audit — tour N (N de 1 à 3)

Lancer l'agent `osho-core:auditor`, `isolation: "worktree"`, description `Audit PR #<n> tour <N>`, prompt :

```
Audit de la PR #<n> (branche `<branche>`), tour <N> sur 3.
<réponses de l'utilisateur aux questions précédentes, s'il y en a>
<plan de référence, seulement s'il n'est ni dans le repo ni dans la PR>
```

À la notification :
- Pas de bloc `TOUR / VERDICT` → relancer une fois. Second échec → remonter à l'utilisateur, arrêt.
- Le résultat indique un worktree conservé : `git -C <worktree> status --porcelain`. Non vide → l'auditeur a écrit des fichiers : prévenir l'utilisateur, ignorer ces changements. Vide → rien à signaler (changer de branche suffit à conserver un worktree).
- Relire les issues ouvertes avec la commande du §0 : c'est elle qui fait foi, pas le bloc.

## 2. Décider

- Question `[bloquante]` ou `VERDICT: bloqué` → poser chaque question bloquante (AskUserQuestion), puis relancer l'audit **du même tour** avec les réponses. Ce n'est pas un nouveau tour.
- Questions `[non bloquante]` → les garder pour la sortie.
- 0 issue ouverte → §5.
- N = 3 et des issues ouvertes → §4.
- Sinon → §3.

## 3. Correctifs

Choisir le dev :
- dev initial connu **et** premier tour de correctifs → `SendMessage` vers lui avec le prompt ci-dessous. Si SendMessage échoue → dev neuf.
- sinon, ou si une issue ouverte l'était déjà au tour précédent → dev neuf : agent `general-purpose`, `isolation: "worktree"`, description `Correctifs PR #<n> tour <N>`.

Prompt dev :

```
Tu corriges la PR #<n> (branche `<branche>`) suite à l'audit du tour <N>.

Issues à traiter : <#12 [P0], #14 [P1]>

[dev neuf uniquement] Tu travailles dans ton worktree : `git fetch origin <branche> && git checkout <branche>`.

Pour chaque issue, par ordre de priorité (P0 d'abord) :
1. `gh issue view <num>` : lis le problème, l'impact et le critère de validation.
2. Corrige à la racine, au plus juste. Ne touche pas au reste de la PR, pas de refactor opportuniste.
3. Vérifie le critère de validation (tests, commande, exécution). Ajoute un test si la correction porte sur de la logique non triviale.
4. Commite avec un message qui référence l'issue (`Refs #<num>`).

Puis :
- pousse sur `<branche>` ;
- commente chaque issue traitée : `gh issue comment <num> --body "Corrigé dans <sha> : <une ligne>. Vérifié par : <test/commande>."`
- ne ferme aucune issue : c'est l'auditeur qui valide ;
- si tu juges une issue erronée, dis-le en commentaire avec tes arguments, et ne la corrige pas.

Réponds uniquement avec :
    TRAITÉES: #12 (<sha>), #14 (<sha>) | aucune
    CONTESTÉES: #n (raison) | aucune
    BLOQUÉ: <raison> | non
```

À la notification : `BLOQUÉ` différent de `non` → remonter à l'utilisateur et attendre sa décision. Sinon N = N + 1 → §1.

## 4. Escalade (après l'audit du tour 3)

Afficher les issues encore ouvertes (n°, priorité, titre) et dire que les 3 tours sont épuisés. Demander (AskUserQuestion) : un tour de plus / merger quand même / s'arrêter là. « Un tour de plus » → §3 puis §1 avec N = 4, et redemander à la fin.

## 5. Sortie

En 3 à 5 lignes : nombre de tours, issues fermées, issues restantes, commits de correctifs. Puis les questions non bloquantes. Terminer par : « Merger la PR #<n> ? ». Ne jamais merger sans un oui explicite de l'utilisateur.
````

- [ ] **Step 2: Valider**

Run:
```bash
claude plugin validate plugins/osho-core
```
Expected: `✔ Validation passed`.

- [ ] **Step 3: Commit**

```bash
git add plugins/osho-core/skills/audit-loop/SKILL.md
git commit -m "Add audit-loop skill"
```

---

### Task 3: Version, catalogue, README

**Files:**
- Modify: `plugins/osho-core/.claude-plugin/plugin.json` (version, description)
- Modify: `.claude-plugin/marketplace.json` (description osho-core)
- Modify: `docs/skills.md` (table osho-core)
- Modify: `README.md` (table osho-core, layout)

- [ ] **Step 1: plugin.json**

`"version": "0.3.0"` → `"version": "0.4.0"` ; description :
`"Core hooks, skills and agents: repo-init, donnees-fictives, audit-loop (auditor agent), code-review-graph auto-update, per-session Superpowers offer."`

- [ ] **Step 2: marketplace.json**

Même description que plugin.json pour `osho-core`.

- [ ] **Step 3: docs/skills.md** — ajouter après la ligne `donnees-fictives` :

```markdown
| `audit-loop` | Skill | Audit → fix loop on a PR until it is production-ready: the auditor opens GitHub issues for major problems only, a dev fixes them, the auditor verifies and closes; 3 rounds max, then proposes the merge |
| `auditor` | Agent | Strict senior reviewer used by `audit-loop`; no Edit/Write tools, writes only to GitHub |
```

- [ ] **Step 4: README.md** — ajouter après la ligne `donnees-fictives` de la table osho-core :

```markdown
| `audit-loop` | Skill + agent | Say *"audit loop on PR #12"*: a senior auditor files issues for production-breaking problems only, a dev fixes them, repeat up to 3 rounds, then it proposes the merge |
```

et dans « Repository layout » remplacer `one plugin: .claude-plugin/plugin.json, skills/, hooks/` par `one plugin: .claude-plugin/plugin.json, skills/, agents/, hooks/`.

- [ ] **Step 5: Valider et commit**

```bash
claude plugin validate plugins/osho-core && jq -e . .claude-plugin/marketplace.json >/dev/null && echo ok
git add plugins/osho-core/.claude-plugin/plugin.json .claude-plugin/marketplace.json docs/skills.md README.md
git commit -m "osho-core 0.4.0: document audit-loop"
```
Expected: `✔ Validation passed` puis `ok`.

---

### Task 4: Validation de bout en bout sur un repo sandbox

**Demander l'accord de l'utilisateur avant l'étape 1** : elle crée un repo GitHub privé.

**Files:** aucun dans ce repo (sandbox dans le scratchpad).

- [ ] **Step 1: Créer le sandbox**

```bash
SB="$SCRATCH/audit-loop-sandbox"; mkdir -p "$SB" && cd "$SB" && git init -b main
echo '[]' > users.json
cat > CLAUDE.md <<'EOF'
Plan « stats » : `age_stats(path)` renvoie l'âge moyen des utilisateurs de `users.json`.
`users.json` vaut `[]` sur une installation neuve : dans ce cas `age_stats` doit renvoyer 0.
EOF
git add . && git commit -m init
gh repo create audit-loop-sandbox --private --source . --push
git checkout -b dev && git push -u origin dev
```
(`$SCRATCH` = le scratchpad de la session.)

- [ ] **Step 2: PR 1 — un vrai bug, une abstraction inutile, un point de style**

```bash
git checkout -b feat/stats dev
cat > stats.py <<'EOF'
import json


class AverageStrategy:
    def compute(self, values):
        return sum(values) / len(values)


def AgeStats(path, strategy=AverageStrategy()):
    with open(path) as f:
        users = json.load(f)
    return strategy.compute([u["age"] for u in users])
EOF
git add stats.py && git commit -m "Add age stats" && git push -u origin feat/stats
gh pr create --base dev --head feat/stats --title "Age stats" --body "Implémente le plan stats de CLAUDE.md."
```

- [ ] **Step 3: PR 2 — pour l'isolation des issues et l'escalade**

```bash
git checkout -b feat/count dev
cat > count.py <<'EOF'
import json


def count_active(path):
    with open(path) as f:
        users = json.load(f)
    return sum(1 for u in users if u["active"])
EOF
git add count.py && git commit -m "Add active user count" && git push -u origin feat/count
gh pr create --base dev --head feat/count --title "Active user count" --body 'Compte les utilisateurs actifs de users.json. Le champ `active` est optionnel : absent = actif.'
```

- [ ] **Step 4: Scénario nominal (PR 1)**

Dans `$SB` : `claude --plugin-dir <repo>/plugins/osho-core`, puis « audit loop sur la PR 1 ».
Expected :
- tour 1 : une issue `[P0]` ou `[P1]` pour `ZeroDivisionError` sur `[]` ; aucune issue pour le nom `AgeStats` ; issue pour `AverageStrategy` acceptable seulement en `[P1]` avec un coût argumenté ;
- un dev neuf corrige, pousse sur `feat/stats`, commente l'issue ;
- tour 2 : l'auditeur ferme l'issue avec un commentaire ; sortie en ≤ 5 lignes + « Merger la PR #1 ? » ; aucun merge.

- [ ] **Step 5: Isolation et non-écriture**

```bash
gh issue list --label audit-loop --state all --json number,body --jq '.[].body | split("\n")[0]' | sort | uniq -c
git -C "$SB" status --porcelain; git -C "$SB" worktree list
```
Expected : toutes les issues commencent par `PR : #1` ; `status` vide ; aucun worktree d'auditeur avec des modifications.

- [ ] **Step 6: Escalade (PR 2)**

Nouvelle session, « audit loop sur la PR 2. Pour ce test, le dev ne doit rien corriger et répondre `TRAITÉES: aucune`. »
Expected : tour 1, une issue pour le `KeyError` quand `active` est absent ; le dev ne corrige rien ; tours 2 et 3 laissent l'issue ouverte ; après l'audit du tour 3, escalade avec la liste des issues et la question « un tour de plus / merger quand même / s'arrêter là ». Les issues de la PR 1 n'apparaissent jamais dans ce déroulé.

- [ ] **Step 7: PR fermée**

```bash
gh pr close 2
```
« audit loop sur la PR 2 » → Expected : arrêt immédiat avec un message, aucun agent lancé.

- [ ] **Step 8: Nettoyage (avec accord de l'utilisateur)**

```bash
gh repo delete audit-loop-sandbox --yes
```
Nécessite le scope `delete_repo` (`gh auth refresh -s delete_repo`) ; sinon laisser l'utilisateur supprimer le repo.

- [ ] **Step 9: Ajuster et commiter**

Tout écart constaté aux étapes 4–7 → corriger `auditor.md` ou `SKILL.md`, rejouer l'étape concernée, puis :
```bash
git add plugins/osho-core && git commit -m "audit-loop: fixes from sandbox run"
```
