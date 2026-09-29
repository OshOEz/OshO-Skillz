# audit-loop — design

Date : 2026-09-28 · Plugin : osho-core (0.3.0 → 0.4.0)

## But

Faire converger une PR vers « prête pour la prod » par une boucle audit → correctifs, pilotée par la session principale via les callbacks des sub-agents (plus de `/loop` en polling).
Succès : la PR sort de la boucle sans issue ouverte (ou avec les issues restantes remontées à l'utilisateur), et chaque issue créée concernait une erreur majeure, pas un nice-to-have.

## Composants

```
plugins/osho-core/
├── agents/auditor.md          # dev senior strict, n'écrit jamais de code
└── skills/audit-loop/SKILL.md # chef d'orchestre : la boucle
```

- **Chef d'orchestre** = la session principale qui suit `audit-loop/SKILL.md`. Seule à parler à l'utilisateur.
- **auditor** = sub-agent. Outils : `Read, Grep, Glob, Bash, Skill`. Pas d'Edit/Write. Bash réservé à `gh` et `git` en lecture.
- **dev** = pas d'agent dédié. Le dev initial de l'utilisateur, ou un `general-purpose` lancé avec le modèle de prompt fourni par le skill.

## Boucle

1. **Entrée** (prérequis unique : une PR existe)
   - PR fournie (n° ou URL) → étape 2.
   - Sub-agent de dev en cours → attendre son callback. Fini sans PR → ouvrir la PR ou demander à l'utilisateur.
2. **Audit tour N (N ≤ 3)** : lancer `auditor` en arrière-plan, sans isolation (il lit le code de la PR via `git fetch pull/<n>/head` + `git show`/`git grep`, sans checkout), avec : chemin du repo, n° PR, n° de tour, réponses aux questions précédentes, plan de la session s'il n'existe pas dans le repo/la PR.
3. **Question bloquante** → pause, poser la question (AskUserQuestion), relancer l'auditeur avec la réponse.
4. **0 issue `audit-loop` ouverte** sur la PR → étape 7.
5. **Correctifs**
   - Dev initial disponible et premier tour de correctifs → le reprendre via `SendMessage`.
   - Sinon, ou si une issue survit à un tour de correctifs → nouveau dev dans un worktree créé par le chef d'orchestre (`git worktree add --detach`), supprimé après son passage.
   - Le dev pousse sur la branche de la PR et commente chaque issue traitée avec ses commits. Il ne ferme pas les issues.
6. Tour N+1 → étape 2. **Après l'audit du tour 3 avec des issues encore ouvertes** : arrêt, liste des issues restantes à l'utilisateur, qui décide (tour supplémentaire, merge, abandon).
7. **Sortie** : résumé en 3 à 5 lignes (tours, issues ouvertes/fermées), questions non bloquantes, puis « Merger la PR #X ? ». Ne merge jamais seul.

## Contrat de l'auditeur (`agents/auditor.md`)

**Posture**
- Identifie la stack de la PR et agit en dev senior de cette techno, visant la mise en prod.
- N'écrit jamais de code, ne pousse rien, ne modifie aucun fichier. Écrit uniquement dans GitHub (issues, commentaires).
- Se fait son propre contexte : diff et description de la PR, commits, code complet des fichiers touchés et de leurs appelants, plans du repo (`docs/`, `CLAUDE.md`), issues `audit-loop` existantes. Graphe code-review-graph s'il existe.
- Relit **tout** le code de la PR à chaque tour : il peut trouver ce qu'il a manqué avant.

**Ce qui mérite une issue** : erreurs majeures pour la prod — bugs, perte ou corruption de données, sécurité, gestion d'erreur absente sur un chemin réel, concurrence, écart avec le plan qui casse le besoin, sur-ingénierie coûteuse (complexité qui sera un problème en maintenance).
**Ce qui n'en mérite pas** : style, nommage, préférences, nice-to-have, refactors non nécessaires. Pas d'issue « pour faire plaisir ». Zéro issue est un résultat normal.

**Frugalité** : invoque `ponytail:ponytail-review` sur la PR s'il est installé, sinon applique la même grille (stdlib d'abord, pas d'abstraction spéculative, pas de dépendance inutile). Ne retient que ce qui a un vrai coût.

**Priorités** : préfixe de titre `[P0]` (bloque la mise en prod) ou `[P1]` (à corriger avant merge). Rien en dessous.

**Hygiène des issues**
- Label `audit-loop` (créé s'il manque). Corps : lien PR, `fichier:ligne`, problème, impact en prod, piste de correction, critère de validation. Autonome : un dev neuf doit pouvoir la traiter sans autre contexte.
- Avant de créer : liste les issues `audit-loop` de la PR, pas de doublon, pas de réouverture d'une issue fermée sans élément nouveau.
- Issues commentées par le dev : vérifie la correction dans le code, ferme avec un commentaire si validée, sinon commente ce qui manque et la laisse ouverte.

**Retour au chef d'orchestre** (bloc court, rien d'autre) :
```
TOUR: N
FERMÉES: #a, #b
OUVERTES: #c [P0], #d [P1]
QUESTIONS:
- [bloquante] ...
- [non bloquante] ...
VERDICT: prêt | correctifs requis | bloqué (question)
```
Une question est **bloquante** si sa réponse change ce qu'est un code correct ; sinon non bloquante.

## Modèle de prompt dev (dans le skill)

Branche et PR, liste des issues à traiter, consigne : lire chaque issue, corriger au plus juste, pousser sur la branche de la PR, commenter chaque issue avec les SHA des commits, ne pas fermer les issues, contester une issue jugée erronée en commentaire (sans la corriger) — l'auditeur tranche au tour suivant. Retour : `TRAITÉES / CONTESTÉES / BLOQUÉ`.

## Erreurs

- `gh` non authentifié → arrêt, proposer `! gh auth login`.
- PR introuvable / fermée → arrêt, le dire.
- Sub-agent en échec ou sans bloc de retour → une relance, puis remonter à l'utilisateur.
- Session hors du dépôt → trouver le repo parmi les sous-dossiers (remote `origin`), sinon demander le chemin.

## Validation

Repo de test avec une PR contenant 1 vrai bug (ex. exception non gérée sur une entrée réelle), 1 point de style, 1 abstraction inutile. Attendu : issue P0/P1 pour le bug, issue ou non pour l'abstraction selon son coût, **aucune** pour le style ; le dev corrige ; l'auditeur ferme au tour 2 ; sortie avec proposition de merge. Vérifier aussi : aucune écriture de l'auditeur hors GitHub, arrêt après 3 tours sur un bug volontairement non corrigé.

## Hors périmètre (v1)

Merge automatique, hook de verrouillage dur de l'auditeur, lancement du dev depuis un plan (superpowers:subagent-driven-development le couvre).
