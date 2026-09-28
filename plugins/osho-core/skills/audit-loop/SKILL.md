---
name: audit-loop
description: Boucle audit → correctifs sur une PR jusqu'à ce qu'elle soit prête pour la prod. Un auditeur senior (agent osho-core:auditor, n'écrit jamais de code) ouvre des issues GitHub pour les erreurs majeures, un dev les corrige, l'auditeur vérifie et ferme ; 3 tours maximum. Utiliser quand l'utilisateur dit « audit loop », « audite la PR », « boucle d'audit », donne une PR à auditer avant merge, ou demande d'auditer le travail d'un sub-agent de dev en cours ou terminé.
---

# audit-loop

Tu es le chef d'orchestre. Tu ne relis pas le code et tu ne corriges rien toi-même : tu lances l'auditeur et le dev, tu lis leurs retours, tu parles à l'utilisateur. Les sub-agents te réveillent quand ils ont fini : pas de `/loop`, pas de polling.

## 0. Prérequis

1. `gh auth status`. Échec → arrêt, proposer `! gh auth login`.
2. Trouver la PR :
   - n° ou URL fourni → `gh pr view <n> --json number,headRefName,state,url`. PR introuvable ou `state` différent de `OPEN` → arrêt, le dire.
   - sub-agent de dev en cours → attendre sa notification de fin, puis `gh pr list --head <branche> --state all --json number,state`. PR trouvée mais pas `OPEN` → arrêt, le dire.
   - aucune PR : si le dev a fini et poussé sa branche, ouvrir la PR (`gh pr create --base dev --head <branche> --fill` ; si `dev` n'existe pas sur le remote, demander la branche cible). Sinon demander à l'utilisateur.
3. Retenir : n° PR, branche, identifiant du dev initial s'il existe, plan de référence **seulement** s'il n'existe que dans cette session (sinon l'auditeur le trouve seul).

Commande « issues ouvertes de la PR », source de vérité à chaque étape :

```bash
gh issue list --label audit-loop --state open --limit 200 --json number,title,body \
  --jq '.[] | select((.body // "") | test("^PR ?: ?#<n>(\\D|$)")) | "#\(.number) \(.title)"'
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
- Relire les issues ouvertes avec la commande du §0 : c'est elle qui fait foi, pas le bloc. Si `OUVERTES` cite une issue que la commande ne renvoie pas → prévenir l'utilisateur (corps d'issue mal formé), ne pas conclure à 0 issue.

## 2. Décider

- Question `[bloquante]` ou `VERDICT: bloqué` → poser chaque question bloquante (AskUserQuestion), puis relancer l'audit **du même tour** avec les réponses. Ce n'est pas un nouveau tour.
- Questions `[non bloquante]` → les garder pour la sortie.
- 0 issue ouverte → §5.
- N ≥ 3 et des issues ouvertes → §4.
- Sinon → §3.

## 3. Correctifs

Choisir le dev :
- dev initial connu **et** premier tour de correctifs → `SendMessage` vers lui avec le prompt ci-dessous. Si SendMessage échoue → dev neuf.
- sinon, ou si une issue ouverte l'était déjà au tour précédent → dev neuf : agent `general-purpose`, `isolation: "worktree"`, description `Correctifs PR #<n> tour <N>`.

Prompt dev :

```
Tu corriges la PR #<n> (branche `<branche>`) suite à l'audit du tour <N>.

Issues à traiter : <#12 [P0], #14 [P1]>

[dev neuf uniquement] Tu travailles dans ton worktree : `git fetch origin <branche> && git switch --detach origin/<branche>` (la branche peut être prise par un autre worktree).

Pour chaque issue, par ordre de priorité (P0 d'abord) :
1. `gh issue view <num>` : lis le problème, l'impact et le critère de validation.
2. Corrige à la racine, au plus juste. Ne touche pas au reste de la PR, pas de refactor opportuniste.
3. Vérifie le critère de validation (tests, commande, exécution). Ajoute un test si la correction porte sur de la logique non triviale.
4. Commite avec un message qui référence l'issue (`Refs #<num>`).

Puis :
- pousse sur la branche de la PR : `git push origin HEAD:<branche>` ;
- commente chaque issue traitée : `gh issue comment <num> --body "Corrigé dans <sha> : <une ligne>. Vérifié par : <test/commande>."`
- ne ferme aucune issue : c'est l'auditeur qui valide ;
- si tu juges une issue erronée, dis-le en commentaire avec tes arguments, et ne la corrige pas.

Réponds uniquement avec :
    TRAITÉES: #12 (<sha>), #14 (<sha>) | aucune
    CONTESTÉES: #n (raison) | aucune
    BLOQUÉ: <raison> | non
```

À la notification :
- Agent en échec ou pas de bloc `TRAITÉES / CONTESTÉES / BLOQUÉ` → relancer une fois. Second échec → remonter à l'utilisateur, arrêt.
- `BLOQUÉ` différent de `non` → remonter à l'utilisateur et attendre sa décision.
- Sinon N = N + 1 → §1.

## 4. Escalade (après l'audit du tour 3)

Afficher les issues encore ouvertes (n°, priorité, titre) et dire que les 3 tours sont épuisés. Demander (AskUserQuestion) : un tour de plus / merger quand même / s'arrêter là. « Un tour de plus » → §3 puis §1 avec N = 4, et redemander à la fin.

## 5. Sortie

En 3 à 5 lignes : nombre de tours, issues fermées, issues restantes, commits de correctifs. Puis les questions non bloquantes. Terminer par : « Merger la PR #<n> ? ». Ne jamais merger sans un oui explicite de l'utilisateur.
