"""Updater and release-manifest checks with synthetic releases in temporary folders."""

from contextlib import redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release
import update
import web_app

REPO = "example/tracker"


def manifest(version, files, previous=None, removed=None, executable=()):
    previous = previous or {}
    return {"name": "coding-practice-tracker", "version": version, "repository": REPO,
            "files": {name: {"sha256": update.digest(data), "executable": name in executable,
                             "previous": sorted(update.digest(p) for p in previous.get(name, []))}
                      for name, data in files.items()},
            "removed": {name: sorted(update.digest(d) for d in datas) for name, datas in (removed or {}).items()}}


def tarball(version, files, data=None, extra=None):
    """A GitHub-style tag archive with one top-level folder."""
    data = data if data is not None else manifest(version, files)
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        entries = dict(files)
        if data is not False:
            entries[update.MANIFEST] = json.dumps(data).encode()
        entries.update(extra or {})
        for name, content in entries.items():
            info = tarfile.TarInfo("tracker-{}/{}".format(version, name))
            info.size = len(content)
            tar.addfile(info, io.BytesIO(content))
    return out.getvalue()


class FakeGitHub:
    def __init__(self, tag, archive):
        self.tag, self.archive, self.calls = tag, archive, []

    def __call__(self, url, timeout=60):
        self.calls.append(url)
        if url == "https://api.github.com/repos/{}/releases/latest".format(REPO):
            if self.tag is None:
                raise update.UpdateError("The requested URL returned error: 404")
            return json.dumps({"tag_name": self.tag, "name": self.tag, "body": "Notes",
                               "html_url": "https://github.com/{}/releases/tag/{}".format(REPO, self.tag)}).encode()
        if url == "https://codeload.github.com/{}/tar.gz/refs/tags/{}".format(REPO, self.tag):
            return self.archive
        raise update.UpdateError("unexpected URL " + url)


class Workspace(unittest.TestCase):
    V1 = {"scripts/a.py": b"a = 1\n", "scripts/b.py": b"b = 1\n", "scripts/old.py": b"old\n",
          "web.command": b"#!/bin/zsh\necho v1\n"}

    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="coding-practice-update-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        for name, data in self.V1.items():
            self.write(name, data)
        self.write("problems/leetcode/0001-two-sum/20261029.py", b"# Practice: learned\nprint(1)\n")
        self.write("plans/current-week.md", b"My plan\n")
        self.write("STYLE.md", b"My style\n")
        self.write(update.MANIFEST, json.dumps(manifest("1.0.0", self.V1)).encode())
        self.v2 = {"scripts/a.py": b"a = 2\n", "scripts/b.py": b"b = 2\n", "scripts/new.py": b"new\n",
                   "web.command": b"#!/bin/zsh\necho v2\n"}
        self.v2_manifest = manifest("1.1.0", self.v2, previous={k: [v] for k, v in self.V1.items() if k in self.v2},
                                    removed={"scripts/old.py": [self.V1["scripts/old.py"]]},
                                    executable=("web.command",))

    def write(self, name, data):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def read(self, name):
        return (self.root / name).read_bytes()

    def github(self, files=None, data=None, tag="v1.1.0"):
        return FakeGitHub(tag, tarball(tag[1:], files or self.v2, self.v2_manifest if data is None else data))


class PathAndHashTests(unittest.TestCase):
    def test_hash_ignores_line_endings(self):
        self.assertEqual(update.digest(b"a\r\nb\r\n"), update.digest(b"a\nb\n"))
        self.assertNotEqual(update.digest(b"a\n"), update.digest(b"b\n"))

    def test_user_owned_and_unsafe_paths_are_rejected(self):
        for name in ("problems/x.py", "Problems/x.py", "plans/a.md", "STYLE.md", "style.md", ".cache/x",
                     ".git/config", "../x", "/etc/passwd", "a/../b", "a\\b", "C:x", "./a", "a//b",
                     update.MANIFEST, ""):
            with self.subTest(name=name), self.assertRaises(update.UpdateError):
                update.safe_path(name)
        self.assertEqual(update.safe_path("scripts/update.py"), "scripts/update.py")

    def test_versions_compare_numerically(self):
        self.assertGreater(update.parse_version("v0.10.0"), update.parse_version("0.9.9"))
        with self.assertRaises(update.UpdateError):
            update.parse_version("latest")


class PythonVersionTests(unittest.TestCase):
    def test_release_requiring_newer_python_is_refused(self):
        data = manifest("2.0.0", {"scripts/a.py": b"a\n"})
        data["requires_python"] = "3.11"
        update.check_python(update.validate_manifest(data), (3, 11))
        with self.assertRaisesRegex(update.UpdateError, "needs Python 3.11 or newer, but this is Python 3.9"):
            update.check_python(data, (3, 9))
        data["requires_python"] = "three"
        with self.assertRaises(update.UpdateError):
            update.validate_manifest(data)

    def test_tools_stop_on_old_python(self):
        import common
        from unittest.mock import patch
        with patch.object(common.sys, "version_info", (3, 9, 6, "final", 0)):
            with self.assertRaisesRegex(SystemExit, "needs Python 3.11 or newer; this is Python 3.9"):
                common.require_python()
        common.require_python()

    def test_shipped_requirement_matches_the_tools(self):
        import common
        self.assertEqual(release.REQUIRES_PYTHON, "{}.{}".format(*common.MIN_PYTHON))


class InstallTests(Workspace):
    def install(self, fetch):
        prepared = update.prepare(self.root, fetch=fetch)
        return prepared, update.install(self.root, prepared["manifest"], prepared["raw"], prepared["files"])

    def test_updates_pristine_files_and_keeps_user_files_and_edits(self):
        self.write("scripts/b.py", b"b = 'my edit'\n")
        prepared, result = self.install(self.github())
        self.assertEqual(prepared["summary"]["kept"], ["scripts/b.py"])
        self.assertEqual(result["counts"], {"add": 1, "update": 2, "delete": 1, "keep": 1})
        self.assertEqual(self.read("scripts/a.py"), b"a = 2\n")
        self.assertEqual(self.read("scripts/new.py"), b"new\n")
        self.assertFalse((self.root / "scripts/old.py").exists())
        self.assertEqual(self.read("scripts/b.py"), b"b = 'my edit'\n")
        self.assertEqual(self.read(".cache/update/1.1.0/scripts/b.py"), b"b = 2\n")
        self.assertEqual(self.read("problems/leetcode/0001-two-sum/20261029.py"), b"# Practice: learned\nprint(1)\n")
        self.assertEqual(self.read("plans/current-week.md"), b"My plan\n")
        self.assertEqual(self.read("STYLE.md"), b"My style\n")
        self.assertEqual(update.current_version(self.root), "1.1.0")
        if os.name != "nt":
            self.assertTrue(os.access(str(self.root / "web.command"), os.X_OK))
        # A second run finds nothing left to do except the kept edit.
        self.assertEqual([a["action"] for a in update.plan(self.root, self.v2_manifest, update.local_manifest(self.root))],
                         ["keep"])

    def test_locally_modified_file_removed_upstream_is_kept(self):
        self.write("scripts/old.py", b"I changed this\n")
        _, result = self.install(self.github())
        self.assertIn("scripts/old.py", result["kept"])
        self.assertEqual(self.read("scripts/old.py"), b"I changed this\n")

    def test_copy_without_manifest_is_adopted_using_previous_hashes(self):
        (self.root / update.MANIFEST).unlink()
        self.write("scripts/b.py", b"unknown version\n")
        self.assertIsNone(update.current_version(self.root))
        self.assertEqual(update.repository_of(self.root), update.DEFAULT_REPOSITORY)
        actions = {a["path"]: a["action"] for a in update.plan(self.root, self.v2_manifest)}
        self.assertEqual(actions, {"scripts/a.py": "update", "scripts/b.py": "keep", "scripts/new.py": "add",
                                   "scripts/old.py": "delete", "web.command": "update"})

    def test_crlf_checkout_counts_as_unmodified(self):
        self.write("scripts/a.py", b"a = 1\r\n")
        actions = {a["path"]: a["action"] for a in update.plan(self.root, self.v2_manifest, update.local_manifest(self.root))}
        self.assertEqual(actions["scripts/a.py"], "update")

    def test_bad_releases_change_nothing(self):
        before = {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        bad = {
            "checksum": self.github(files=dict(self.v2, **{"scripts/a.py": b"tampered\n"})),
            "no manifest": self.github(data=False),
            "protected path": self.github(files=dict(self.v2, **{"problems/x.py": b"x\n"}),
                                          data=manifest("1.1.0", dict(self.v2, **{"problems/x.py": b"x\n"}))),
            "version mismatch": self.github(data=manifest("9.9.9", self.v2)),
            "not an archive": FakeGitHub("v1.1.0", b"not a tarball"),
        }
        for label, fetch in bad.items():
            with self.subTest(label), self.assertRaises(update.UpdateError):
                update.prepare(self.root, fetch=fetch)
        self.assertEqual(before, {p: p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


class CheckTests(Workspace):
    def test_check_is_cached_for_a_day_and_force_refreshes(self):
        fetch = self.github()
        info = update.check(self.root, fetch=fetch, now=1000)
        self.assertTrue(info["available"])
        self.assertEqual((info["current"], info["latest"]["version"]), ("1.0.0", "1.1.0"))
        update.check(self.root, fetch=fetch, now=1000 + 3600)
        self.assertEqual(len(fetch.calls), 1)
        update.check(self.root, fetch=fetch, now=1000 + 3600, force=True)
        update.check(self.root, fetch=fetch, now=1000 + 90000)
        self.assertEqual(len(fetch.calls), 3)
        self.assertTrue(update.cached_status(self.root)["available"])

    def test_failures_are_reported_and_retried_sooner(self):
        fetch = FakeGitHub(None, b"")
        info = update.check(self.root, fetch=fetch, now=1000)
        self.assertFalse(info["available"])
        self.assertIn("has not published a release", info["error"])
        update.check(self.root, fetch=fetch, now=1000 + 1800)
        update.check(self.root, fetch=fetch, now=1000 + 3700)
        self.assertEqual(len(fetch.calls), 2)

    def test_same_or_older_release_is_not_offered(self):
        self.assertFalse(update.check(self.root, fetch=self.github(tag="v1.0.0"), force=True)["available"])

    def test_command_line_install(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(update.main(["--check"], root=self.root, fetch=self.github()), 0)
        self.assertIn("1.1.0 is available", output.getvalue())
        self.assertEqual(update.current_version(self.root), "1.0.0")
        with redirect_stdout(output):
            self.assertEqual(update.main(["--yes"], root=self.root, fetch=self.github()), 0)
        self.assertIn("Installed 1.1.0", output.getvalue())
        self.assertEqual(update.current_version(self.root), "1.1.0")
        with redirect_stdout(output):
            update.main([], root=self.root, fetch=self.github())
        self.assertIn("is up to date", output.getvalue())


class WebUpdateTests(Workspace):
    def setUp(self):
        super().setUp()
        self.app = web_app.PracticeApp(self.root, model="test-model", fetch=self.github())
        self.addCleanup(self.app.close)

    def test_status_check_install_and_restart_guard(self):
        info = self.app.update_status()
        self.assertEqual((info["current"], info["available"], info["migration"]), ("1.0.0", False, []))
        self.assertTrue(self.app.check_updates()["available"])
        with self.assertRaises(web_app.WebError) as raised:
            self.app.request_restart()
        self.assertEqual(raised.exception.status, 409)
        info = self.app.install_update()
        self.assertEqual(info["installed"]["version"], "1.1.0")
        self.assertFalse(info["available"])
        self.assertEqual(update.current_version(self.root), "1.1.0")
        with self.assertRaises(web_app.WebError):
            self.app.install_update()
        with self.assertRaises(web_app.WebError):
            self.app.apply_migration()
        restarted = []
        self.app.restart = lambda: restarted.append(True)
        self.assertTrue(self.app.request_restart()["restarting"])

    def test_install_waits_for_active_archives(self):
        self.app.check_updates()
        self.app.jobs["busy"] = {"id": "busy", "state": "generating", "fingerprint": ""}
        with self.assertRaises(web_app.WebError) as raised:
            self.app.install_update()
        self.assertEqual(raised.exception.status, 409)
        self.assertEqual(update.current_version(self.root), "1.0.0")

    def test_auto_check_can_be_disabled(self):
        self.assertFalse(web_app.auto_check_enabled(True))
        os.environ["PRACTICE_NO_UPDATE_CHECK"] = "1"
        self.addCleanup(os.environ.pop, "PRACTICE_NO_UPDATE_CHECK", None)
        self.assertFalse(web_app.auto_check_enabled(False))
        os.environ["PRACTICE_NO_UPDATE_CHECK"] = ""
        self.assertTrue(web_app.auto_check_enabled(False))


@unittest.skipUnless(shutil.which("git"), "git is required for release manifests")
class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="coding-practice-release-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.git("init", "-q")
        for name, text in {"scripts/a.py": "a1\n", "scripts/gone.py": "g\n", "problems/.gitkeep": "",
                           "plans/p.md": "plan\n", "STYLE.md": "style\n"}.items():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        self.git("add", "-A")

    def git(self, *args):
        subprocess.run(["git", *args], cwd=str(self.root), check=True, capture_output=True)

    def build(self, *args):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(release.main(list(args), root=self.root), 0)
        return json.loads((self.root / update.MANIFEST).read_text(encoding="utf-8"))

    def test_versions_keep_previous_hashes_and_removed_files(self):
        first = self.build("--version", "0.1.0")
        self.assertEqual(sorted(first["files"]), ["scripts/a.py", "scripts/gone.py"])
        (self.root / "scripts/a.py").write_text("a2\n", encoding="utf-8")
        (self.root / "scripts/gone.py").unlink()
        self.git("add", "-A")
        dev = self.build()
        self.assertEqual(dev["version"], "0.1.0")
        self.assertEqual(dev["files"]["scripts/a.py"]["previous"], [update.digest(b"a1\n")])
        second = self.build("--version", "0.2.0")
        self.assertEqual(second["files"]["scripts/a.py"]["previous"], [update.digest(b"a1\n")])
        self.assertEqual(second["removed"], {"scripts/gone.py": [update.digest(b"g\n")]})
        with redirect_stdout(io.StringIO()):
            self.assertEqual(release.main(["--check"], root=self.root), 0)
        (self.root / "scripts/a.py").write_text("a3\n", encoding="utf-8")
        with redirect_stdout(io.StringIO()):
            self.assertEqual(release.main(["--check"], root=self.root), 1)


@unittest.skipUnless(shutil.which("git") and (ROOT / ".git").exists(), "needs a Git checkout")
class ShippedManifestTests(unittest.TestCase):
    def test_repository_manifest_is_current(self):
        with redirect_stdout(io.StringIO()):
            self.assertEqual(release.main(["--check"], root=ROOT), 0,
                             "Run python3 scripts/release.py after changing shipped files.")
        data = update.local_manifest(ROOT)
        self.assertTrue(all(not name.startswith(("problems/", "plans/")) for name in data["files"]))
        self.assertIn("scripts/update.py", data["files"])


if __name__ == "__main__":
    unittest.main()
