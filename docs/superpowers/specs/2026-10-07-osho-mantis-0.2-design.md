# osho-mantis 0.2 — design

Date : 2026-10-07 · Plugin : osho-mantis (0.1.0 → 0.2.0) · Base : [2026-10-01-osho-mantis-design.md](./2026-10-01-osho-mantis-design.md)

## But

Reporter dans le plugin ce qu'un premier audit Savage réel a montré, quand il a fallu le corriger à la main :

- le dashboard omettait la plupart des données produites ;
- le contenu sensible fuyait dans les diffs ;
- les sous-agents ne pouvaient pas lancer eux-mêmes la relecture et la re-attaque que Mantis prévoit ;
- le traitement « une faille à la fois » ralentissait l'audit ;
- les refus et les changements de modèle passaient inaperçus.

Succès :

1. Un audit 0.2 produit un dashboard qui affiche tous les champs écrits par les étapes.
2. Aucun secret ni motif masqué n'apparaît dans `README.md`, `dashboard.html` ou `patches/`.
3. Les tests de `render.py` passent.
4. Un audit 0.1 en cours reprend sans erreur.

Hors périmètre :

- la règle de versionnement du dossier d'audit ne change pas, à l'exception du point 7 ci-dessous ;
- les SKILL.md de Mantis ne sont pas modifiés ;
- aucun budget en tokens ;
- aucun nouveau niveau.

## 1. `mantis-run` : déroulé

### 1.1 Dashboard en direct

Après chaque étape marquée `done`, et après chaque retour d'agent d'une étape parallèle, mantis-run lance `render.py <audit> --live`. Le mode `--live` ajoute `<meta http-equiv="refresh" content="30">`. Le dashboard est ouvert une seule fois, à la fin de « Prepare ». Le rendu final, sans `--live`, retire le rechargement automatique.

### 1.2 Relecture indépendante des exploits (étape 7 de mantis-reproduce)

Un sous-agent Claude Code ne peut pas lancer de sous-agent. C'est donc mantis-run qui lance, après reproduce et pour chaque finding `repro_status = reproduced`, un agent de relecture distinct de l'auteur de l'exploit, sur le même modèle que reproduce.

- **Ce qu'il écrit :** `repro_critic = {verdict: valid|invalid, reasoning, at}`, plus une entrée dans l'historique.
- **Si le verdict est `invalid` :** `repro_status = failed_to_reproduce`.
- **Exécution :** uniquement par la ligne docker de reproduce, avec les montages en lecture seule.
- **Ordre :** cette relecture se termine avant chain.

### 1.3 Patch et re-attaque en parallèle

La règle « une faille à la fois » disparaît. Pour chaque finding reproduit, mantis-run :

1. lance l'agent patch, qui lit la copie isolée principale propre, sans y écrire ;
2. crée une **copie isolée par faille** avec `mktemp -d` : même garde-fou que l'étape 2.4, chemin noté dans `state.json` sous `extra_shadows[]` ;
3. applique `patch_diff` dans cette copie (`git apply --check`, puis `git apply`) ;
4. lance l'agent de re-attaque sur cette copie ;
5. fixe le `patch_status` final à partir de `reattack_status`, avec la même table qu'en 0.1.

Ces chaînes tournent en parallèle, dans la limite de `parallel`. Les failles non reproduites reçoivent leur proposition de correctif en parallèle sur la copie principale, qui reste en lecture seule pour elles. Le chemin `mktemp -d` de chaque copie supplémentaire passe le garde-fou 2.4 avant d'être supprimé, à la fin de l'étape patch puis à nouveau à la fin de l'audit.

### 1.4 Diffs sensibles

Juste après l'écriture d'un `patch_diff` par l'agent, mantis-run cherche les motifs de masquage décrits en 2.3 (les motifs de secrets génériques, plus les `redact_patterns` de la campagne). Il vérifie aussi la taille : plus de 200 Ko, ou une seule ligne de plus de 20 000 caractères, ce qui correspond à un fichier JSON exporté sur une ligne.

Si l'un de ces cas se présente :

- le diff complet est déplacé vers `workspace/private_patches/<id>.diff` ;
- `patch_diff` passe à `null`, et `patch_diff_private_path` reçoit le chemin ;
- `patch_summary_safe` reçoit un résumé sans données, demandé à l'agent patch : il est désormais obligatoire dans son rapport ;
- une note est ajoutée dans `state.json`.

La re-attaque applique alors le diff depuis le fichier privé.

Les consignes envoyées à chaque agent ajoutent : « Ne recopie jamais un secret ni une donnée personnelle ; un PoC sur des données personnelles ne fait que compter. »

### 1.5 Robustesse

- **Scripts d'aide :** les consignes demandent aux agents de les écrire dans leur propre scratchpad, jamais dans `workspace/helpers/`. Des agents parallèles s'y écrasaient mutuellement.
- **Écritures concurrentes :** deux étapes qui écrivent les mêmes `findings/*.json` ne tournent jamais en même temps. Calibrate attend la fin de toutes les re-attaques. Chain peut tourner en même temps que patch, mais il n'écrit que de nouveaux fichiers.
- **Contrôle sur disque :** le contrôle de chaque étape lit le disque, pas le rapport de l'agent. Si chain a écrit de nouveaux findings avec `constituent_findings`, l'étape est `done` même si l'agent dit le contraire. Ces chaînes reçoivent `patch_status = MITIGATION_PROPOSED`, avec un `patch_summary_safe` qui renvoie aux failles qui les composent.
- **Refus et changements de modèle :** après chaque vague d'agents, mantis-run compte les `"stop_reason":"refusal"` dans le journal de chaque agent, ainsi que les modèles différents du modèle demandé. Chaque cas donne une note dans `state.json`. Un finding sans PoC à cause d'un refus reçoit `repro_status = not_attempted` et une entrée dans l'historique. Il n'est jamais relancé en boucle : mantis-run le signale une seule fois en fin d'audit.

### 1.6 Option « modèle unique »

Le triage pose une question de plus, après celle du volume :

- **en-tête :** `Modèles` ;
- **choix :** « Par défaut (haiku, sonnet, opus selon l'étape) » ou « Opus partout ».

La réponse est enregistrée dans `campaign.json` sous `model_override` (`null` ou `"opus"`). On peut aussi la passer en argument à `/mantis-run`. Quand elle vaut `"opus"`, la colonne Model du tableau des étapes est ignorée. La question précise que le coût est nettement plus élevé que l'estimation du niveau.

### 1.7 Commande de commit en fin d'audit

Quand `versioning = versioned`, la commande proposée n'ajoute plus tout le dossier d'audit. Elle ajoute seulement `README.md`, `dashboard.html`, `patches/`, `campaign.json`, `state.json`, `triage.md` et `inventory.json`, **jamais `workspace/`**, qui peut contenir des secrets, des données personnelles et les diffs privés. En plus, mantis-run ajoute `osho-mantis/*/workspace/` au fichier `info/exclude` du repo (même méthode que l'étape 2 du triage).

## 2. `render.py` : dashboard

### 2.1 Un seul script

`render.py` continue d'écrire `README.md` et `patches/<id>.diff`, uniquement pour les findings non écartés qui ont un `patch_diff` non nul. Son modèle de dashboard est remplacé. Il n'y a pas de deuxième script.

### 2.2 Contenu

- **En-tête :** repo, niveau, dates et durée, commit Mantis, `model_override`.
- **Pipeline des étapes :** l'état de chacune, avec les notes de `state.json` rattachées. Les refus et changements de modèle sont mis en évidence.
- **Chiffres clés,** groupés en Gravité, Preuve (reproduites, confirmées par lecture, non tentées), Correctifs (vérifiés, contournés, proposés) et Écartés.
- **Liste des findings :** triée par `mantis_risk_score`, avec des filtres (sévérité, statut, reproduction, issue du correctif, chaînes, écartés) et une recherche.
- **Panneau de détail :**
  - score décomposé ;
  - reasoning et checklist du review ;
  - verdict du critic ;
  - reproduction (commande, sortie, nom du fichier d'exploit, `repro_hints`) ;
  - `repro_critic` ;
  - re-attaque (statut, sortie, variantes) ;
  - correctif (`patch_diff` ou `patch_summary_safe`, avec la mention « diff complet gardé privé », `patch_notes`) ;
  - `remediation_steps` à cocher ;
  - historique daté ;
  - `code_paths` ;
  - chaînes, avec liens vers leurs composantes et liens retour ;
  - doublons fusionnés (lus dans `findings/.trash/`).
- **Actions humaines :** agrégées depuis `remediation_steps` et `patch_notes`, à cocher. L'état coché est gardé dans `localStorage`, dans un try/catch.
- **Section repliée** des faux positifs (avec leur reasoning) et des doublons.
- **Sections repliables :** triage, `THREAT_MODEL.md`, architecture, learnings, glossaire.

### 2.3 Sécurité et confidentialité

- **Injection des données :** JSON embarqué avec échappement de `<`, `>`, `&`, U+2028 et U+2029. Le DOM est construit uniquement avec `textContent` et `createElement`, jamais avec `innerHTML` sur des données.
- **Masquage :** chaque chaîne est filtrée avant l'embarquement.
  - **Motifs de secrets génériques :** `ghp_`, `gho_`, `github_pat_`, `sk-`, `sk-ant-`, `xox[abpr]-`, `AKIA[0-9A-Z]{16}`, clés privées PEM, JWT `eyJ…\.eyJ…`, `apify_api_`.
  - **Motifs propres à l'audit :** `campaign.json` peut contenir `redact_patterns : [{"pattern": "<regex>", "label": "<texte>"}]`. Le triage peut le remplir, et mantis-run peut le compléter quand une étape signale un nouveau motif.
- **Contrôle final :** si l'un des motifs subsiste dans `dashboard.html`, `README.md` ou `patches/`, le rendu échoue avec un code non nul et supprime le fichier fautif.
- **`workspace/private_patches/` n'est jamais lu.**
- **Hors ligne :** aucun script, police ou image externe.

### 2.4 Thèmes

- **Couleurs :** jetons définis sur `:root`. Le thème sombre est appliqué sous `@media (prefers-color-scheme: dark)` avec `:root:not([data-theme="light"])`, puis à nouveau sous `:root[data-theme="dark"]`.
- **Bouton :** dans l'en-tête, il bascule `data-theme` et mémorise le choix dans `localStorage` (clé `mantis-theme`, dans un try/catch). Un petit script dans `<head>` applique le choix avant l'affichage.
- **Accessibilité :** contraste AA dans les deux thèmes. Mise en page lisible à 375 px, sans défilement horizontal de la page. `prefers-reduced-motion` est respecté.
- **Rechargement en direct :** la balise `<head>` reste écrite littéralement, et le mode `--live` y insère la balise de rechargement.

## 3. Compatibilité

- **Lecture des champs :** `render.py` lit les champs avec des valeurs par défaut. Un audit 0.1, qui n'a ni `repro_critic`, ni `patch_summary_safe`, ni `model_override`, ni `extra_shadows`, s'affiche quand même.
- **Reprise :** un audit 0.1 en cours reprend avec 0.2. Les nouvelles étapes internes (relecture des exploits, copies par faille) s'appliquent seulement aux étapes qui restent à faire.

## 4. Tests

`test_render.py`, avec la bibliothèque standard seulement, sur des audits fictifs générés dans un dossier temporaire :

1. Le JSON embarqué ne casse pas une balise `</script>`, et le modèle ne contient aucun `innerHTML`.
2. Le bouton de thème et les deux jeux de jetons sont présents.
3. Un secret générique, ou un motif de `redact_patterns`, placé dans un finding est masqué. Un secret injecté après le masquage fait échouer le rendu.
4. Un fichier dans `private_patches/` n'est jamais lu : son contenu n'apparaît nulle part.
5. Un `patch_diff` nul avec un `patch_summary_safe` affiche le résumé, et n'écrit aucun `patches/<id>.diff`.
6. Les champs `mantis_risk_score`, `reattack_status`, `repro_critic`, `constituent_findings` et les doublons de `.trash/` sont bien dans les données embarquées.
7. `--live` ajoute la balise de rechargement, et le mode normal ne l'ajoute pas.
8. Un audit au format 0.1 s'affiche sans erreur.
9. Les tests 0.1 existants qui portent sur `README.md` et `patches/` restent verts.

`test_inventory.py` et `test_check_visibility.sh` restent inchangés et doivent passer.

## 5. Documentation et version

- **Version :** `plugins/osho-mantis/.claude-plugin/plugin.json` passe en `0.2.0`.
- **`README.md`, section osho-mantis :** dashboard en direct, thèmes, `private_patches/`, option « Opus partout », commande de commit sans `workspace/`.
- **`docs/decisions.md` :** deux lignes, l'une sur l'orchestrateur qui lance la relecture et la re-attaque, l'autre sur les diffs sensibles gardés privés et le masquage.
- **Spec 0.1 :** un renvoi en tête vers ce document.

## 6. Livraison

- **Branche et PR :** branche `feat/osho-mantis-0.2`, commits par thème (`run`, `triage`, `render`, `docs`), puis PR sur `OshOEz/OshO-Skillz`.
- **Réinstallation, après le merge :** `claude plugin marketplace update osho-skillz`, puis `claude plugin update osho-mantis@osho-skillz`. On vérifie que `~/.claude/plugins/cache/osho-skillz/osho-mantis/0.2.0/` existe.
