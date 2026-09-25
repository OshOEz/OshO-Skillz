#!/usr/bin/env python3
"""Test inverse de l'outil, sur une source inventée : une sortie propre passe, chaque fuite injectée échoue
  python3 test_donnees_fictives.py
"""
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

OUTIL = [sys.executable, str(Path(__file__).with_name("donnees_fictives.py"))]
PHRASE = "Le comité de pilotage valide chaque trimestre la feuille de route des ateliers."
IMAGE = b"\x89PNG image de la source"
PROPRE = "Une boulangerie artisanale planifie ses fournées et suit les commandes des restaurants voisins."


def pptx(chemin, texte, auteur="Équipe test", image=None, description=""):
    """Paquet Office minimal : seules les parties lues par l'outil"""
    with zipfile.ZipFile(chemin, "w") as z:
        z.writestr("ppt/slides/slide1.xml", f"<p:sld><a:p><a:t>Revue du processus</a:t></a:p><a:p><a:t>{texte}</a:t></a:p></p:sld>")
        z.writestr("docProps/core.xml", f"<cp:coreProperties><dc:creator>{auteur}</dc:creator><dc:description>{description}"
                   f"</dc:description><cp:revision>1</cp:revision><dcterms:created>2013-01-27T09:14:16Z</dcterms:created>"
                   f"</cp:coreProperties>")
        if image:
            z.writestr("ppt/media/image1.png", image)


def controle(dossier, fichier):
    return subprocess.run(OUTIL + ["controle", str(dossier / "empreinte.json"), str(fichier)],
                          capture_output=True, text=True)


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        src = d / "source"
        src.mkdir()
        pptx(src / "Moulinsart_Processus.pptx", "Réunion avec Zorglub Industries, budget 12 500 €. "
             "Écrire à bertrand.tournesol@groupe-hexa.fr. " + PHRASE, auteur="Bertrand Tournesol", image=IMAGE)
        (src / "transcription.txt").write_text("La réunion animée par Castafiore a duré longtemps.")
        subprocess.run(OUTIL + ["empreinte", str(src), "-o", str(d / "empreinte.json")], check=True, capture_output=True)

        propre = d / "propre.pptx"
        pptx(propre, PROPRE)
        r = controle(d, propre)
        assert r.returncode == 0, "sortie propre refusée :\n" + r.stdout

        fuites = {
            "terme": dict(texte=PROPRE + " Merci à Zorglub Industries."),
            "phrase": dict(texte=PROPRE + " " + PHRASE.lower()),
            "image": dict(texte=PROPRE, image=IMAGE),
            "auteur": dict(texte=PROPRE, description="generated using python-pptx"),
            "personne": dict(texte=PROPRE + " Document préparé par Bertrand Tournesol."),
            "courriel": dict(texte=PROPRE + " Contact : bertrand.tournesol@groupe-hexa.fr pour tout."),
            "domaine": dict(texte=PROPRE + " Voir groupe-hexa.fr"),
        }
        for nom, kw in fuites.items():
            f = d / f"fuite_{nom}.pptx"
            pptx(f, **kw)
            r = controle(d, f)
            assert r.returncode == 1, f"fuite « {nom} » non détectée :\n{r.stdout}"
    print(f"ok : sortie propre acceptée, {len(fuites)}/{len(fuites)} fuites détectées")


if __name__ == "__main__":
    main()
