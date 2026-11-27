#!/usr/bin/env python3
"""Auto-test de garde.py sur des dépôts jetables
  python3 test_garde.py
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Un GIT_DIR hérité (hook pre-push d'un worktree lié) ferait écrire les dépôts de test dans le vrai dépôt.
for _k in subprocess.run(["git", "rev-parse", "--local-env-vars"], capture_output=True, text=True).stdout.split():
    os.environ.pop(_k, None)

from garde import cle, decider, derniere, echappe, poussees, pr_vers_prod  # noqa: E402

GARDE = Path(__file__).with_name("garde.py")
Z = "0" * 40


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


def ecrire_index(repo, ids):
    d = Path(repo) / "public" / "whats-up"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.json").write_text(json.dumps({"ids": ids}))


def depot(tmp, ids=("2026-11-20",), config=True):
    """A repo whose main holds `ids` and is pushed to a bare origin; returns its path."""
    origin = Path(tmp) / "origin.git"
    git(tmp, "init", "-q", "--bare", "-b", "main", str(origin))
    repo = Path(tmp) / "app"
    git(tmp, "init", "-q", "-b", "main", str(repo))
    git(repo, "config", "user.email", "t@t")
    git(repo, "config", "user.name", "t")
    if config:
        (repo / ".whatsup").mkdir()
        (repo / ".whatsup" / "config.json").write_text(json.dumps({"prod": "main", "base": "dev", "dossier": "public/whats-up"}))
    if ids is not None:
        ecrire_index(repo, list(ids))
    (repo / "a.txt").write_text("a")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "remote", "add", "origin", str(origin))
    git(repo, "push", "-q", "origin", "main")
    return repo


def commit(repo, nom="b.txt"):
    (Path(repo) / nom).write_text(nom)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", nom)
    return git(repo, "rev-parse", "HEAD")


def pre_push(repo, local_sha, remote_sha, env=None):
    ligne = f"refs/heads/main {local_sha} refs/heads/main {remote_sha}\n"
    return subprocess.run([sys.executable, str(GARDE), "pre-push", "origin", "x"], cwd=repo, input=ligne,
                          capture_output=True, text=True, env={**os.environ, **(env or {})})


def claude(repo, commande):
    entree = json.dumps({"tool_input": {"command": commande}})
    return subprocess.run([sys.executable, str(GARDE), "claude"], cwd=repo, input=entree, capture_output=True, text=True)


class Fonctions(unittest.TestCase):
    def test_cle_orders_suffixes(self):
        self.assertEqual(derniere(["2026-11-27", "2026-11-27-9", "2026-11-27-10"]), "2026-11-27-10")
        self.assertEqual(derniere([]), "")
        self.assertLess(cle("2026-11-27"), cle("2026-11-27-2"))

    def test_decider(self):
        self.assertTrue(decider(["2026-11-27"], None))
        self.assertTrue(decider(["2026-11-20", "2026-11-27"], ["2026-11-20"]))
        self.assertFalse(decider(["2026-11-20"], ["2026-11-20"]))
        self.assertFalse(decider(None, ["2026-11-20"]))

    def test_pr_vers_prod(self):
        self.assertEqual(pr_vers_prod('gh pr create --base main --head dev --title x', "main"), "dev")
        self.assertEqual(pr_vers_prod('gh pr create -B main --body "see --base dev"', "main"), "")
        self.assertIsNone(pr_vers_prod('gh pr create --base dev --body "--base main"', "main"))
        self.assertIsNone(pr_vers_prod('git status', "main"))

    def test_echappe(self):
        self.assertTrue(echappe('gh pr create --base main --body "x\nSans nouveautés : correctif"'))
        self.assertFalse(echappe('gh pr create --base main --body "Sans nouveautés :"'))
        self.assertTrue(echappe('gh pr create --base main --body-file f', "Sans nouveautés : rien"))

    def test_poussees(self):
        lignes = (f"refs/heads/main aaa refs/heads/main bbb\nrefs/heads/x ccc refs/heads/x ddd\n"
                  f"(delete) {Z} refs/heads/main eee\nrefs/tags/v1 fff refs/tags/v1 {Z}\n")
        self.assertEqual(poussees(lignes, "main"), [("aaa", "bbb")])


class PrePush(unittest.TestCase):
    def test_refuses_without_newer_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            avant = git(repo, "rev-parse", "HEAD")
            r = pre_push(repo, commit(repo), avant)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertIn("Pas de fiche What's up ?", r.stderr)

    def test_escape_variable(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            avant = git(repo, "rev-parse", "HEAD")
            r = pre_push(repo, commit(repo), avant, {"WHATSUP_SANS": "correctif de sécurité"})
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_passes_with_newer_note(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            avant = git(repo, "rev-parse", "HEAD")
            ecrire_index(repo, ["2026-11-20", "2026-11-28"])
            r = pre_push(repo, commit(repo), avant)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_new_remote_branch_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            r = pre_push(repo, commit(repo), Z)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_lost_index_refuses(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            avant = git(repo, "rev-parse", "HEAD")
            git(repo, "rm", "-q", "public/whats-up/index.json")
            r = pre_push(repo, commit(repo), avant)
            self.assertEqual(r.returncode, 1, r.stderr)

    def test_malformed_index_refuses_without_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            avant = git(repo, "rev-parse", "HEAD")
            (repo / "public" / "whats-up" / "index.json").write_text("{pas du json")
            r = pre_push(repo, commit(repo), avant)
            self.assertEqual(r.returncode, 1, r.stderr)
            self.assertNotIn("Traceback", r.stderr)

    def test_first_release_after_install_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp, ids=None)
            avant = git(repo, "rev-parse", "HEAD")
            ecrire_index(repo, [])
            r = pre_push(repo, commit(repo), avant)
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_repo_without_config_passes_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp, config=False)
            avant = git(repo, "rev-parse", "HEAD")
            r = pre_push(repo, commit(repo), avant)
            self.assertEqual((r.returncode, r.stderr), (0, ""))

    def test_unknown_sha_passes_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            r = pre_push(repo, commit(repo), "1" * 40)
            self.assertEqual(r.returncode, 0)
            self.assertIn("vérification impossible", r.stderr)


class Claude(unittest.TestCase):
    def test_pr_to_prod_without_newer_note_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            git(repo, "switch", "-q", "-c", "dev")
            commit(repo)
            git(repo, "push", "-q", "origin", "dev")
            r = claude(repo, 'gh pr create --base main --head dev --title "MEP"')
            self.assertEqual(r.returncode, 2, r.stderr)
            self.assertIn("Pas de fiche What's up ?", r.stderr)

    def test_pr_to_prod_with_newer_note_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            git(repo, "switch", "-q", "-c", "dev")
            ecrire_index(repo, ["2026-11-20", "2026-11-28"])
            commit(repo)
            git(repo, "push", "-q", "origin", "dev")
            r = claude(repo, 'gh pr create --base main --title "MEP"')
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_pr_escape_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            r = claude(repo, 'gh pr create --base main --head dev --body "Sans nouveautés : rien de visible"')
            self.assertEqual(r.returncode, 0, r.stderr)

    def test_other_commands_and_bad_input_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            self.assertEqual(claude(repo, "git status").returncode, 0)
            r = subprocess.run([sys.executable, str(GARDE), "claude"], cwd=repo, input="pas du json",
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0)

    def test_no_origin_passes_with_warning(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = depot(tmp)
            git(repo, "remote", "remove", "origin")
            r = claude(repo, 'gh pr create --base main --head dev')
            self.assertEqual(r.returncode, 0)
            self.assertIn("vérification impossible", r.stderr)


if __name__ == "__main__":
    unittest.main()
