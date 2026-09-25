---
name: donnees-fictives
description: Utiliser dès qu'il est question de fausses données, jeu de test, fixtures, données synthétiques, données de démonstration, d'anonymiser ou de « rendre anonymes » des fichiers, ou de travailler à partir de documents client confidentiels (pptx, docx, xlsx, xls, pdf, transcriptions, archives zip) pour développer ou tester un outil, même si le mot « fictif » n'est pas prononcé.
---

# Données fictives d'après un patron client

Transformer des documents client confidentiels en un **jeu de test entièrement inventé** qui garde ce qui sert au développement (structure, mise en page, pièges) et rien de ce qui appartient au client

## Le principe : synthétiser, jamais anonymiser

Anonymiser, c'est partir du document client et remplacer ce qui se voit. Un terme oublié, une tournure, un seuil reconnaissable suffisent alors à réidentifier le client. **Ce skill ne fait pas ça**

On relève seulement **le patron** : les champs, la mise en page, les habitudes de rédaction, les défauts qui rendent l'outil difficile à construire. Puis on écrit **de zéro** un contenu inventé qui reproduit ce patron. Rien du texte client n'est recopié, aucun fichier client ne sert de modèle de fichier (un modèle peut porter logo, masque, auteur, propriétés)

Si la personne demande vraiment d'anonymiser un document pour le réutiliser tel quel, dire que c'est une décision humaine au cas par cas, hors de ce skill, et proposer la synthèse à la place

## Outil

`scripts/donnees_fictives.py`, quatre commandes. Il tourne avec **`uv run`**, qui installe ses dépendances (déclarées en tête du script) dans un environnement isolé et mis en cache : rien dans le Python du système, rien dans le projet du client. Dans la suite, `OUTIL` désigne :

```bash
uv run <dossier du skill>/scripts/donnees_fictives.py
```

| Commande | Rôle |
| --- | --- |
| `verifier` | Dit ce qui manque pour lire tous les formats, et donne la commande d'installation |
| `empreinte <source...> -o <fichier>` | Lit la source **en mémoire** (y compris les archives dans les archives) et relève ce qui ne doit jamais réapparaître : noms propres, sigles, courriels, domaines, montants, nombres longs, mots des noms de fichiers, suites de six mots, empreintes des images |
| `controle <empreinte> <sorties...>` | Cherche tout cela dans les sorties, plus les métadonnées laissées par un outil. Code retour 1 s'il y a un échec |
| `traces <empreinte> <dossiers...> --motifs …` | Même recherche dans les endroits où des copies ont pu rester, plus l'historique de l'outil `rtk` |

Options utiles de `empreinte` : `--reference <dossiers>` (documents **neutres** de même langue et même métier, jamais du client : leurs mots écrits en minuscules comptent comme courants, ce qui évite les faux positifs) · `--autoriser <fichier>` (un terme générique par ligne)

## La procédure

Suivre les étapes dans l'ordre. Annoncer chaque étape en une ligne

### 0. Préparer l'environnement

En début de procédure (10 secondes) :

```bash
OUTIL verifier
python3 <dossier du skill>/scripts/test_donnees_fictives.py
```

- `verifier` dit ce qui manque. Si `uv` est absent : `brew install uv`
- Le test rejoue le test inverse sur une source inventée : il doit afficher `ok`. Sinon l'outil est cassé, ne pas continuer
- **xlrd** lit les `.xls` · **python-pptx** sert aux générateurs de PowerPoint. Ajouter `--with python-docx` ou `--with openpyxl` le jour où un jeu de test Word ou Excel est à produire, pas avant

Pour les PDF, il faut `pdftotext` (paquet poppler), installé au niveau du système. **Demander avant de l'installer**, puis :
- macOS : `brew install poppler`
- Debian, Ubuntu : `sudo apt install poppler-utils`

Si une dépendance reste absente, la procédure peut continuer : le script **signale nommément** chaque fichier qu'il n'a pas pu lire. Dire alors à la personne que ces fichiers ne sont pas couverts par l'empreinte, donc pas protégés par le contrôle

### 1. Cadrer

- Quelle source, pour produire quoi, pour tester quoi
- **L'accord de la personne qui porte le client** : se servir de ses documents comme patron, même sans en garder le contenu, doit être couvert. Le demander si ce n'est pas dit
- Où iront les sorties (dans le projet, dossier de jeux de test) et **la zone isolée** : un sous-dossier `isole/` du dossier temporaire de session, jamais le projet, jamais un dossier synchronisé

### 2. Lire en local, dans la zone isolée

- Ne rien envoyer à un service en ligne : pas de lecture web, pas de page publiée, pas d'agent d'un autre outil
- Lire en mémoire quand c'est possible. Si une extraction sur disque est nécessaire, **uniquement dans la zone isolée**
- Les noms de fichiers des archives Windows sont souvent mal encodés : le script les corrige, une extraction `unzip` classique peut échouer
- Afficher des comptes et des structures, pas des pages de contenu client dans la conversation

### 3. Relever le patron

Écrire, pour soi, une liste **sans aucune donnée client** :
- les champs et sections du document type
- la mise en page (où sont les titres, les acteurs, les entrées et sorties, les légendes)
- **les pièges** : ce qui rendra l'import difficile. Exemple réel : dans des schémas PowerPoint dessinés à la main, 95 % des flèches n'étaient pas rattachées aux boîtes, donc le déroulé ne se lisait que sur l'image
- les volumes typiques (nombre d'éléments par document)

### 4. Construire l'empreinte

```bash
OUTIL empreinte <source> -o <isole>/empreinte.json --reference <docs neutres>
```

L'empreinte **contient des données client** : elle reste dans la zone isolée et se supprime à l'étape 10, en dernier

### 5. Générer de zéro

Écrire un **générateur** propre à ce jeu, rangé avec les sorties (par exemple `fixtures/<jeu>/generer.py`), et le lancer avec `uv run --with python-pptx generer.py`. Il doit :
- inventer une entreprise, des rôles (jamais des noms de personnes), un vocabulaire de son secteur, **sans ressemblance** avec le client (autre métier, autres intitulés)
- reproduire les **pièges** relevés à l'étape 3, volontairement
- produire pour chaque fichier **sa vérité attendue** (ce qu'un import doit retrouver, et rien de plus), dans un fichier à côté
- fixer une **graine** pour que la génération soit reproductible
- régler des **métadonnées neutres** (auteur, dernier auteur, titre, commentaires, dates) : les bibliothèques de génération laissent leur propre nom par défaut, python-pptx écrit par exemple « generated using python-pptx » dans les commentaires
- **se vérifier lui-même** en relisant ce qu'il a produit, et échouer si la vérité n'y est pas. Prouver une fois que cette vérification échoue bien en cassant volontairement une valeur
- porter une mention « document fictif » dans un pied de page, pour qu'un fichier égaré ne passe jamais pour un vrai

Produire un **aperçu visuel dès la première génération** et le regarder : les défauts de mise en page (textes qui se chevauchent, flèches qui traversent le texte) se voient tout de suite et coûtent cher à découvrir tard

Ajouter un `README.md` : ce que chaque fichier teste, la liste des pièges, comment mesurer un import contre la vérité, et la règle « aucun fichier client dans ce dossier »

### 6. Contrôler

```bash
OUTIL controle <isole>/empreinte.json <dossier des sorties>
```

- **ÉCHEC** : à corriger dans le générateur, puis régénérer. Jamais en retouchant le fichier produit à la main
- Un ÉCHEC sur un **mot générique** (un verbe, un nom de logiciel grand public) : l'ajouter à la liste `--autoriser`, reconstruire l'empreinte, relancer. **Jamais un nom de personne, d'entreprise, de lieu ou de produit du client**
- **SIGNAL** : à regarder, ne bloque pas
- Terminer à **0 échec**

Faire aussi le **test inverse** une fois par nouvelle source : injecter dans une copie d'une sortie, en zone isolée, un terme de l'empreinte, une suite de mots de la source, une image de la source et un auteur par défaut. Le contrôle doit échouer sur les quatre. Sinon, l'empreinte est trop pauvre pour ce format

### 7. Purger les copies

Supprimer, sur accord de la personne si ce n'est pas déjà demandé, **tout sauf l'empreinte**, qui sert encore aux étapes 8 à 10 :
- dans la zone isolée : copies extraites, liste d'autorisation, copies piégées du test inverse
- les fichiers texte, captures ou scripts de lecture créés pendant l'étape 2

Puis chercher les restes :

```bash
OUTIL traces <isole>/empreinte.json <dossier temporaire> <projet> --motifs <nom du client> <nom de l'archive>
```

- Une trace dans un fichier du projet : vérifier si c'est un vrai reste (à supprimer) ou un homonyme, un mot générique
- L'historique de `rtk` ne garde que des lignes de commande (des noms de fichiers, pas de contenu). Ne pas le modifier soi-même : donner à la personne la commande `sqlite3` pour l'effacer si elle le souhaite
- Les sorties d'outils conservées par l'agent dans son dossier de projet (`tool-results`) peuvent contenir du contenu lu : les vérifier avec la même commande, supprimer celles qui en contiennent

### 8. Bilan

Présenter ce bilan. **Tous les chiffres viennent des sorties des commandes** (`empreinte` donne la source par type et les fichiers non lus, `controle` donne les sorties par type et les fichiers en échec, `traces` donne les restes). Ne rien estimer : un chiffre qu'on n'a pas mesuré s'écrit « non mesuré »

Le vocabulaire compte : on a **analysé** des fichiers client et **produit** des fichiers fictifs. On n'a anonymisé aucun fichier client, le bilan le dit dans ces termes

```markdown
## Bilan · données fictives <nom du jeu>

**Résultat : ✅ succès**  (ou ⚠️ succès partiel · ❌ échec, avec la raison en une ligne)

| | Nombre | Par type |
| --- | --- | --- |
| Fichiers client analysés | <n> | <.pptx n · .xls n · …> |
| dont non lus (non couverts par le contrôle) | <n> | <liste et raison, ex. PDF sans pdftotext> |
| Fichiers fictifs produits | <n> | <.pptx n · .json n · …> |

| Contrôle | Résultat |
| --- | --- |
| Références au client dans les sorties | ✅ 0 échec sur <n> fichiers · ou ❌ <n> fichiers en échec |
| Test inverse (4 fuites injectées) | ✅ 4/4 détectées · ou ❌ <n>/4 |
| Auto-vérification du générateur | ✅ passe, et échoue bien si on casse une valeur |
| Aperçu visuel relu | ✅ · ou ❌ |
| Traces après purge | ✅ aucune · ou ⚠️ <n>, avec ce qu'elles sont (homonymes, historique rtk) |

**Purgé** : <liste>
**Reste** : <données client d'origine : <chemin>> · <historique rtk, commande fournie> · <empreinte, supprimée à l'étape 10>
**À faire par la personne** : <ex. ouvrir un fichier dans son logiciel pour valider le rendu réel>
```

**Succès** veut dire : 0 échec au contrôle, 4/4 au test inverse, auto-vérification qui passe, aucun fichier source non lu. S'il reste des fichiers non lus, c'est un **succès partiel** : ces fichiers n'ont pas été protégés par le contrôle, le dire

### 9. Demander ce qu'on fait des données d'origine

Juste après le bilan, poser **une question avec l'outil de question** (pas en texte libre), pour que la réponse soit un choix explicite :

- Question : « Que fait-on des données client d'origine (<chemin>, <n> fichiers) ? »
- Option 1 · **Les conserver** : elles restent où elles sont, rien ne change
- Option 2 · **Les mettre à la corbeille** : récupérables tant que la corbeille n'est pas vidée

Ne jamais supprimer l'original sans cette réponse, même si la personne a demandé plus tôt de « tout nettoyer » : l'original n'est pas une copie de travail, il appartient à son propriétaire

Si la réponse est **les mettre à la corbeille** :
- macOS 15 et plus : `/usr/bin/trash "<chemin>"` (commande native, instantanée, sans autorisation)
- macOS plus ancien : `mv "<chemin>" ~/.Trash/` (récupérable depuis la corbeille, sans « Remettre »). **Ne pas passer par Finder avec `osascript`** : la commande attend une autorisation d'automatisation et reste bloquée deux minutes avant d'échouer
- Linux : `gio trash "<chemin>"`
- Vérifier que le chemin d'origine n'existe plus, puis relancer `traces` sur son dossier parent
- **Ne jamais faire de suppression définitive** (`rm`, vider la corbeille) : c'est un geste irréversible, il revient à la personne. Le lui dire en une ligne

### 10. Supprimer l'empreinte

En dernier, une fois la question posée : supprimer la zone isolée entière, empreinte comprise. Confirmer en une ligne que c'est fait

## Pièges déjà rencontrés

| Piège | Parade |
| --- | --- |
| Noms de fichiers mal encodés dans une archive | Lecture en mémoire par le script |
| Auteur par défaut de la bibliothèque dans les métadonnées | Régler auteur et dernier auteur, le contrôle le détecte |
| Faux positifs en masse (mots en majuscules, verbes en tête de titre, texte par défaut des masques Office) | `--reference` avec des documents neutres, puis `--autoriser` pour les mots génériques restants |
| Nom de personne écrit aussi dans une adresse (`prenom.nom@…`), donc vu comme un mot courant | Corrigé dans le script : les adresses ne comptent pas comme vocabulaire courant |
| Liste de termes à chercher faite de mémoire | L'empreinte automatique remplace la mémoire |
| Aperçu regardé trop tard | Aperçu dès la première génération |
| Caches d'outils oubliés | Étape 7, commande `traces` |
| Original supprimé par excès de zèle | Étape 9 : question explicite, corbeille seulement |
