#!/usr/bin/env python3
# /// script
# dependencies = ["xlrd", "python-pptx"]
# ///
"""Outillage du skill donnees-fictives : empreinte d'une source client, contrôle des sorties, recherche de traces

Quatre commandes :
  verifier                                     dit ce qui manque pour lire tous les formats, et comment l'installer
  empreinte  <source...> -o <empreinte.json>   relève ce qui ne doit jamais réapparaître (lit les archives en mémoire)
  controle   <empreinte.json> <sortie...>      cherche l'empreinte, les copies mot pour mot, les métadonnées et images suspectes
  traces     <empreinte.json> <dossier...>     cherche les restes après purge (fichiers, historique rtk)

Formats lus : pptx, docx, xlsx (et tout fichier Office récent), xls (si xlrd est installé), pdf (si pdftotext existe),
txt, md, csv, json, zip (y compris zip dans zip). Aucun fichier n'est écrit sur disque, sauf l'empreinte

L'empreinte contient des données client : elle se range dans une zone temporaire isolée, jamais dans un projet,
et se supprime à la fin. Les commandes n'affichent que des comptes, sauf `controle`, qui montre ce qu'il trouve
dans les sorties (qui sont censées être fictives)
"""
import argparse
import hashlib
import io
import json
import os
import re
import sqlite3
import subprocess
import sys
import unicodedata
import zipfile
from collections import Counter
from pathlib import Path

TEXTE = {".txt", ".md", ".csv", ".json", ".xml", ".html", ".vtt", ".srt"}
MEDIA = {".png", ".jpg", ".jpeg", ".gif", ".emf", ".wmf", ".bmp", ".tif", ".tiff", ".svg"}
# Auteurs par défaut laissés par les bibliothèques de génération : ils trahissent l'outil, pas le client,
# mais une sortie propre ne doit porter que ce qu'on a choisi d'y mettre
AUTEURS_PAR_DEFAUT = ["python-pptx", "python-docx", "steve canny", "openpyxl", "xlsxwriter", "apache poi"]
MOTS_VIDES = set("""le la les un une des de du d l et ou en au aux a à ce ces cet cette pour par sur sous dans avec sans
qui que quoi dont où il elle ils elles on nous vous leur leurs son sa ses mon ma mes ton ta tes notre nos votre vos
est sont être avoir fait faire plus moins pas ne se si tout tous toute toutes non oui the of and to in for on with
by from at as is are be this that it""".split())
NGRAMME = 6  # six mots consécutifs identiques = copie
# Parties d'un fichier Office qui portent du texte saisi : diapositives, notes, commentaires, masques (pieds de page),
# corps et en-têtes Word, cellules Excel, propriétés du document
CONTENU = re.compile(r"^(ppt/(slides|notesSlides|comments|slideLayouts|slideMasters)/[^/]+\.xml"
                     r"|word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml"
                     r"|xl/(sharedStrings|worksheets/[^/]+|comments\d*)\.xml"
                     r"|docProps/core\.xml)$")


# --- Lecture -----------------------------------------------------------------

def _nom_zip(info):
    """Les archives Windows encodent souvent les noms en cp437 : on retente en utf-8"""
    if info.flag_bits & 0x800:
        return info.filename
    brut = info.filename.encode("cp437", errors="replace")
    for enc in ("utf-8", "cp1252"):
        try:
            return brut.decode(enc)
        except UnicodeDecodeError:
            pass
    return info.filename


# Texte que PowerPoint et Word mettent d'office dans les masques : présent partout, il ne dit rien du client
PAR_DEFAUT_OFFICE = re.compile(
    r"Click to edit Master (title|subtitle|text) styles?|Second level|Third level|Fourth level|Fifth level"
    r"|Cliquez pour modifier (le style du titre|les styles du texte du masque|le style des sous-titres du masque)"
    r"|Deuxième niveau|Troisième niveau|Quatrième niveau|Cinquième niveau|‹N°›|‹#›", re.I)


def _texte_xml(octets):
    x = octets.decode("utf-8", errors="ignore")
    x = re.sub(r"</(a:p|w:p|row|si|p)>", "\n", x)
    x = re.sub(r"<[^>]+>", " ", x)
    for a, b in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"), ("&quot;", '"'), ("&apos;", "'")):
        x = x.replace(a, b)
    x = PAR_DEFAUT_OFFICE.sub(" ", x)
    x = re.sub(r"\d{4}-\d\d-\d\dT[\d:.]+Z?", " ", x)  # dates des propriétés : l'outil les écrit, pas le client
    return re.sub(r"[ \t]+", " ", x)


def lire(nom, octets, avertir):
    """Rend une liste de (nom, texte, empreintes des médias). Descend dans les archives"""
    ext = Path(nom).suffix.lower()
    if ext == ".zip" or (ext in {".pptx", ".docx", ".xlsx", ".pptm", ".docm", ".xlsm", ".potx", ".dotx", ".xltx"}):
        try:
            z = zipfile.ZipFile(io.BytesIO(octets))
        except zipfile.BadZipFile:
            avertir(f"archive illisible : {nom}")
            return []
        if ext == ".zip":
            out = []
            for i in z.infolist():
                if not i.is_dir():
                    out += lire(f"{nom}/{_nom_zip(i)}", z.read(i), avertir)
            return out
        textes, medias, meta = [], [], ""
        for part in z.namelist():
            if CONTENU.search(part):  # le texte écrit par les gens, pas les thèmes ni les polices
                textes.append(_texte_xml(z.read(part)))
                if part == "docProps/core.xml":
                    meta += textes[-1]
            elif part == "docProps/app.xml":  # seuls les champs saisis, pas la liste des polices
                x = z.read(part).decode("utf-8", errors="ignore")
                champs = re.findall(r"<(?:Company|Manager)>([^<]*)<", x)
                textes += champs
                meta += " ".join(champs)
            elif part.endswith(".rels"):  # liens externes : révèlent des sites et des dossiers partagés
                x = z.read(part).decode("utf-8", errors="ignore")
                textes += re.findall(r'Target="(https?://[^"]+)"', x)
            elif Path(part).suffix.lower() in MEDIA:
                medias.append(hashlib.sha256(z.read(part)).hexdigest())
        return [(nom, "\n".join(textes), medias, meta)]
    if ext == ".xls":
        try:
            import xlrd
        except ImportError:
            avertir(f"xlrd absent, .xls non lu : {nom}")
            return [(nom, "", [], "")]
        b = xlrd.open_workbook(file_contents=octets)
        lignes = [" | ".join(str(v) for v in sh.row_values(r)) for sh in b.sheets() for r in range(sh.nrows)]
        return [(nom, "\n".join(lignes), [], "")]
    if ext == ".pdf":
        try:
            r = subprocess.run(["pdftotext", "-q", "-", "-"], input=octets, capture_output=True, check=True)
            return [(nom, r.stdout.decode("utf-8", errors="ignore"), [], "")]
        except (FileNotFoundError, subprocess.CalledProcessError):
            avertir(f"pdftotext absent ou en échec, PDF non lu : {nom}")
            return [(nom, "", [], "")]
    if ext in MEDIA:
        return [(nom, "", [hashlib.sha256(octets).hexdigest()], "")]
    if ext in {".xml", ".html", ".rels"}:  # balises retirées : seul le texte compte, pas les noms de styles
        return [(nom, _texte_xml(octets), [], "")]
    if ext in TEXTE or ext == "":
        return [(nom, octets.decode("utf-8", errors="ignore"), [], "")]
    avertir(f"format non lu : {nom}")
    return [(nom, "", [], "")]


def lire_chemins(chemins, avertir, exclure=()):
    out = []
    for c in chemins:
        p = Path(c)
        fichiers = [p] if p.is_file() else [f for f in p.rglob("*") if f.is_file()]
        for f in sorted(fichiers):
            if any(part in exclure for part in f.parts) or f.name.startswith("."):
                continue
            out += lire(str(f), f.read_bytes(), avertir)
    return out


# --- Empreinte ---------------------------------------------------------------

def norm(t):
    t = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in t if not unicodedata.combining(c))


def mots(t):
    # l'apostrophe sépare : « l'architecture » donne « l » et « architecture »
    return re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ][A-Za-zÀ-ÖØ-öø-ÿ\-]*", t)


def ngrammes(t):
    m = [norm(x) for x in mots(t)]
    return {" ".join(m[i:i + NGRAMME]) for i in range(len(m) - NGRAMME + 1)}


def relever(textes, noms, reference=""):
    """Termes forts : bloquent un contrôle. Termes faibles : signalés, à juger"""
    tout = "\n".join(textes)
    fort = set()
    courriels = set(re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", tout))
    fort |= courriels | {norm(c.split("@")[1]) for c in courriels}                 # courriels et leurs domaines
    fort |= {norm(d) for d in re.findall(r"(?:https?://|www\.)([\w.-]+)", tout)}     # domaines
    fort |= set(re.findall(r"\b[A-Z][A-Z0-9]{1,}(?:[_-][A-Z0-9]+)*\b", tout))        # sigles
    # noms propres : suites de mots capitalisés, hors début de phrase isolé
    for m in re.finditer(r"(?<![.!?]\s)(?<!^)\b([A-ZÀ-Ý][a-zà-ÿ]+(?:[ -][A-ZÀ-Ý][A-Za-zà-ÿ]+)+)", tout, re.M):
        fort.add(m.group(1))
    # nom propre isolé en milieu de phrase : « avec Zorglub », « par Durand »
    fort |= set(re.findall(r"(?<=[a-zà-ÿ,:] )([A-ZÀ-Ý][A-Za-zà-ÿ]{2,})\b", tout)) - {w.capitalize() for w in MOTS_VIDES}
    fort |= set(re.findall(r"\b\d[\d  .]{3,}\d\b", tout))                           # nombres longs, téléphones
    fort |= set(re.findall(r"\b\d+(?:[.,]\d+)?\s?k?€", tout))                        # montants
    for n in noms:                                                                   # mots des noms de fichiers
        fort |= {w for w in mots(Path(n).stem) if len(w) >= 5 and norm(w) not in MOTS_VIDES}
    fort = {f.strip() for f in fort if len(f.strip()) >= 2}
    # Un mot qui existe aussi en minuscules dans la source est un mot courant (« CLIENT », « Cahier »),
    # pas un nom propre. Un nom de personne, d'outil ou de lieu n'apparaît jamais en minuscules
    # référence : seuls ses mots écrits en minuscules comptent, un nom propre y reste un nom propre
    ref = {norm(w) for w in mots(reference) if w.islower()}
    # courriels et adresses web retirés : « bertrand.tournesol@… » ne fait pas de « Tournesol » un mot courant
    sans_adresses = re.sub(r"\S+@\S+|(?:https?://|www\.)\S+", " ", tout)
    minuscules = {norm(w) for w in mots(sans_adresses) if w.islower()} | ref
    singulier = lambda w: re.sub(r"(s|x)$", "", w)
    minuscules |= {singulier(w) for w in minuscules}
    courant = lambda t: all(norm(w) in minuscules or singulier(norm(w)) in minuscules for w in mots(t))
    generiques = {t for t in fort if "@" not in t and not re.search(r"\d", t) and courant(t)}
    fort -= generiques
    fort = {t for t in fort if not re.fullmatch(r"[A-Za-z]\d{1,2}", t)}  # repères de schéma (A1, B2), pas des données
    deux_lettres = {t for t in fort if re.fullmatch(r"[A-Z]{2}", t)}  # ID, NB, RH : trop ambigus pour bloquer
    fort -= deux_lettres
    # mots capitalisés isolés et mots longs rares : faibles, car souvent génériques (Processus, Validation)
    compte = Counter(w for w in mots(tout) if len(w) >= 4)
    faible = {w for w, n in compte.items() if w[0].isupper() and norm(w) not in MOTS_VIDES}
    faible |= {w for w, n in compte.items() if len(w) >= 9 and n <= 2}
    faible = {w for w in faible if norm(w) not in ref} | deux_lettres
    return sorted(fort), sorted(faible - fort)


def cmd_empreinte(a):
    avert = []
    lus = lire_chemins(a.source, avert.append)
    ref = "\n".join(t for _, t, *_ in lire_chemins(a.reference, avert.append)) if a.reference else ""
    fort, faible = relever([t for _, t, *_ in lus], [n for n, *_ in lus], ref)
    autorises = {norm(x) for x in (Path(a.autoriser).read_text().split("\n") if a.autoriser else []) if x.strip()}
    fort = [t for t in fort if norm(t) not in autorises]
    faible = [t for t in faible if norm(t) not in autorises]
    ngr = set()
    for _, t, *_ in lus:
        ngr |= ngrammes(t)
    medias = sorted({h for _, _, ms, _ in lus for h in ms})
    types = Counter(Path(n).suffix.lower() or "(sans extension)" for n, *_ in lus)
    non_lus = [x for x in avert if "non lu" in x or "illisible" in x]
    Path(a.sortie).write_text(json.dumps({"fort": fort, "faible": faible, "ngrammes": sorted(ngr),
                                          "medias": medias, "fichiers": len(lus), "types": dict(types),
                                          "non_lus": len(non_lus)}, ensure_ascii=False))
    os.chmod(a.sortie, 0o600)
    print(f"empreinte : {len(lus)} fichiers lus · {len(fort)} termes forts · {len(faible)} termes faibles · "
          f"{len(ngr)} séquences de {NGRAMME} mots · {len(medias)} images")
    print("source par type : " + " · ".join(f"{t} {n}" for t, n in types.most_common()))
    print(f"source non lue : {len(non_lus)} fichier(s)" + (" (détail ci-dessous)" if non_lus else ""))
    for x in avert:
        print("attention :", x)
    print(f"rangée dans {a.sortie} (droits 600). Elle contient des données client : à supprimer en fin de procédure")


# --- Contrôle ----------------------------------------------------------------

def _present(terme, texte_norm):
    t = norm(terme)
    return re.search(r"(?<!\w)" + re.escape(t) + r"(?!\w)", texte_norm) is not None


def cmd_controle(a):
    e = json.loads(Path(a.empreinte).read_text())
    avert = []
    lus = lire_chemins(a.sorties, avert.append, exclure={"__pycache__"})
    echecs, signaux = [], []
    ngr = set(e["ngrammes"])
    medias = set(e["medias"])
    for nom, texte, ms, meta in lus:
        tn = norm(texte)
        for t in e["fort"]:
            if _present(t, tn):
                echecs.append(f"{nom} : terme de la source « {t} »")
        for t in e["faible"]:
            if _present(t, tn):
                signaux.append(f"{nom} : mot présent aussi dans la source « {t} »")
        copies = ngrammes(texte) & ngr
        for c in sorted(copies)[:5]:
            echecs.append(f"{nom} : suite de {NGRAMME} mots identique à la source « {c} »")
        if len(copies) > 5:
            echecs.append(f"{nom} : {len(copies) - 5} autres copies mot pour mot")
        for h in ms:
            if h in medias:
                echecs.append(f"{nom} : image identique à une image de la source ({h[:12]}…)")
        for d in AUTEURS_PAR_DEFAUT:  # dans les propriétés du fichier seulement, pas dans son texte
            if d in norm(meta):
                echecs.append(f"{nom} : métadonnée laissée par défaut par un outil « {d} »")
        if ms:
            signaux.append(f"{nom} : {len(ms)} image(s) embarquée(s), à vérifier à l'œil")
    for x in avert:
        print("attention :", x)
    types = Counter(Path(n).suffix.lower() or "(sans extension)" for n, *_ in lus)
    print(f"contrôle : {len(lus)} fichiers · {len(echecs)} échec(s) · {len(signaux)} signal(aux)")
    print("sorties par type : " + " · ".join(f"{t} {n}" for t, n in types.most_common()))
    print("fichiers en échec : " + str(len({x.split(' : ')[0] for x in echecs})))
    par_fichier = Counter()
    for x in echecs:
        f = x.split(" : ")[0]
        par_fichier[f] += 1
        if par_fichier[f] <= 15:
            print("ÉCHEC   ", x)
    for f, n in par_fichier.items():
        if n > 15:
            print(f"ÉCHEC    {f} : … {n - 15} autres")
    for x in signaux[: a.max_signaux]:
        print("SIGNAL  ", x)
    if len(signaux) > a.max_signaux:
        print(f"SIGNAL   … {len(signaux) - a.max_signaux} autres (option --max-signaux)")
    sys.exit(1 if echecs else 0)


# --- Traces ------------------------------------------------------------------

def cmd_traces(a):
    """Même lecture et même recherche que le contrôle, appliquées aux endroits où des copies ont pu rester"""
    e = json.loads(Path(a.empreinte).read_text())
    medias = set(e["medias"])
    trouve = 0
    avert = []
    lus = lire_chemins(a.dossiers, avert.append)
    for nom, texte, ms, _ in lus:
        if Path(nom).resolve() == Path(a.empreinte).resolve():
            continue
        tn = norm(texte)
        n = sum(1 for t in e["fort"] if _present(t, tn)) + len(ngrammes(texte) & set(e["ngrammes"]))
        n += sum(1 for h in ms if h in medias)
        if n:
            trouve += 1
            print(f"TRACE    {nom} : {n} élément(s) de la source")
    rtk = Path.home() / "Library/Application Support/rtk/history.db"
    if rtk.exists() and a.motifs:
        con = sqlite3.connect(f"file:{rtk}?mode=ro", uri=True)
        for m in a.motifs:
            n = con.execute("select count(*) from commands where original_cmd like ?", (f"%{m}%",)).fetchone()[0]
            if n:
                trouve += 1
                print(f"TRACE    historique rtk : {n} commande(s) contenant « {m} » (noms de fichiers, pas de contenu)")
    print(f"traces : {trouve} emplacement(s) à nettoyer" if trouve else "traces : aucune")
    sys.exit(1 if trouve else 0)


def cmd_verifier(a):
    """Contrôle les dépendances. Ne lit rien, n'installe rien"""
    manque = []
    for module, usage in (("xlrd", "lire les .xls"), ("pptx", "générer des PowerPoint (paquet python-pptx)")):
        try:
            __import__(module)
            print(f"ok       {module} · {usage}")
        except ImportError:
            print(f"MANQUE   {module} · {usage}")
            manque.append(module)
    pdf = subprocess.run(["which", "pdftotext"], capture_output=True).returncode == 0
    print(("ok       " if pdf else "MANQUE   ") + "pdftotext · lire les PDF (paquet poppler)")
    print(f"python   {sys.executable}")
    if manque:
        print(f"\nLancer le script avec uv, qui installe ses dépendances :\n  uv run {Path(__file__).resolve()} verifier")
    if not pdf:
        print("\nPDF : brew install poppler (macOS) · sudo apt install poppler-utils (Debian, Ubuntu)")
    sys.exit(1 if manque or not pdf else 0)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    s = p.add_subparsers(dest="cmd", required=True)
    s.add_parser("verifier")
    e = s.add_parser("empreinte")
    e.add_argument("source", nargs="+")
    e.add_argument("-o", "--sortie", required=True)
    e.add_argument("--autoriser", help="fichier, un terme générique par ligne, à ne pas compter dans l'empreinte")
    e.add_argument("--reference", nargs="*", help="documents neutres de même langue et même métier (jamais du client) : "
                                                   "leurs mots sont considérés comme courants")
    c = s.add_parser("controle")
    c.add_argument("empreinte")
    c.add_argument("sorties", nargs="+")
    c.add_argument("--max-signaux", type=int, default=30)
    t = s.add_parser("traces")
    t.add_argument("empreinte")
    t.add_argument("dossiers", nargs="+")
    t.add_argument("--motifs", nargs="*", default=[], help="mots à chercher dans l'historique rtk (nom du client…)")
    a = p.parse_args()
    {"verifier": cmd_verifier, "empreinte": cmd_empreinte, "controle": cmd_controle, "traces": cmd_traces}[a.cmd](a)


if __name__ == "__main__":
    main()
