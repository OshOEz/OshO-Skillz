---
name: escouade
description: Méthode pour travailler avec Escouade (Kanban de tickets qui lance un agent Claude Code par ticket, dans un worktree sur la branche ticket/<clé>). Utiliser dès qu'une session tourne sur une branche ticket/<clé> ou commence par « Tu travailles en autonomie sur le ticket », quand l'utilisateur veut découper un travail en tickets Escouade, demande comment utiliser Escouade, ou veut fusionner, auditer ou clore un ticket.
---

# escouade

Escouade fait foi pour le suivi **et pour la fusion** : un ticket se fusionne depuis le Kanban, jamais par une PR GitHub en plus. Une PR sert seulement à l'audit.

Contexte du dépôt (sort 1 hors d'un ticket) :

```bash
bash "${CLAUDE_PLUGIN_ROOT}/skills/escouade/scripts/contexte.sh" [chemin] [base]
# ticket: KAT-4 / branche: ticket/kat-4 / base: dev / retard: 3
```

`base` vient d'`origin/HEAD` ; passe-la en argument si le projet en a une autre (kata : `dev`).

## Découper : un ticket = un lot

- **Un ticket Kanban par lot livrable** (une PR, un bilan), pas par tâche. Les tâches du lot sont des sous-tâches de la session (`TaskCreate`, une par tâche du plan) : elles s'affichent en haut de l'agent dans Escouade. C'est ce qui a marché sur les tickets V0.5-X de kata.
- **Plusieurs tickets** seulement pour des lots indépendants (fichiers disjoints, testables seuls), qui peuvent tourner en parallèle. Si un lot dépend d'un autre, crée-le **après** la fusion du premier, pour qu'il parte d'une base à jour.
- Chaque ticket porte ses critères d'acceptation vérifiables (une commande, un test, un écran).
- Le découpage se fait depuis une session classique (hors ticket), avec superpowers:brainstorming puis writing-plans si c'est complexe, puis le MCP Escouade pour créer les tickets.

## Dans un ticket (agent lancé par Escouade)

1. **Rattraper la base.** `contexte.sh` donne un `retard` supérieur à 0 → `git fetch origin && git merge origin/<base>` sur la branche du ticket. Ne jamais `reset` la branche ni travailler sur une autre : Escouade suit `ticket/<clé>` et c'est elle qu'il fusionne.
2. **Plan.** Lot complexe : superpowers (brainstorming, writing-plans, subagent-driven-development). Une décision à prendre → l'outil de question, qui est le seul canal vers l'utilisateur ; sinon tiens les décisions du plan pour acquises et note-les dans le bilan.
3. **Sous-tâches.** `TaskCreate` pour chaque tâche du plan, et `TaskUpdate` au fil de l'eau.
4. **Ports et secrets.** Utilise les ports réservés que donne le prompt (`ESCOUADE_PORT_BASE`, `ESCOUADE_PORT_END`) en variables d'environnement, jamais dans un fichier versionné. Ne commite pas les fichiers qu'Escouade copie depuis le projet (`.env`…).
5. **Commits** sur `ticket/<clé>`, avec `[<CLÉ>]` à la fin du message de commit qui clôt chaque étape.
6. **Audit.** `git push -u origin ticket/<clé>`, PR depuis cette branche (`gh pr create --base <base> --head ticket/<clé> --fill`), puis `osho-core:audit-loop`. En mode Escouade, il ne fusionne pas et ramène les correctifs sur la branche locale.
7. **Fin.** Le bilan demandé par le prompt (bloc `escouade`, critères vérifiés par une commande, `lancement`). Ne fusionne rien : la fusion se fait dans le Kanban.

## Fusionner un ticket (humain ou session principale)

1. Fusionner depuis le Kanban d'Escouade.
2. `git push origin <base>` : sinon la base locale diverge d'`origin` et les tickets suivants partent d'une base fausse.
3. Fermer la PR d'audit : `gh pr close <n> --comment "Fusionné via le Kanban d'Escouade (<sha>)."`

Ne jamais fusionner aussi la PR sur GitHub : sur kata, KAT-5 et KAT-6 ont été fusionnés deux fois (squash local par le Kanban et PR #105 et #108 sur `origin/dev`) ; le `dev` local avait alors 2 commits d'avance et 40 de retard.

## Hors Escouade

Rien ne change : branche `feat/…`, PR, `audit-loop` qui propose la fusion de la PR.
