import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))
import fix


STAMP = "2026-10-21T12:00:00+00:00"


def write_skill(path, name):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {name} description\n---\nbody\n", encoding="utf-8")
    return path


def write_session(path, skill_name=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    content = []
    if skill_name:
        content.append({"type": "tool_use", "id": "skill-call", "name": "Skill",
                        "input": {"skill": skill_name}})
    event = {"type": "assistant", "timestamp": STAMP, "message": {
        "id": path.stem, "model": "claude-sonnet-4", "usage": {
            "input_tokens": 100, "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0, "output_tokens": 10,
        }, "content": content,
    }}
    path.write_text(json.dumps(event) + "\n", encoding="utf-8")


def make_sessions(config_dir, count=10, skill_name=None):
    for index in range(count):
        used = skill_name if index == 0 else None
        write_session(config_dir / "projects" / "demo" / f"session-{index}.jsonl", used)


def visible_tree(root):
    entries = {}
    for path in sorted(root.rglob("*")):
        if "tokenmaxxing-archive" in path.relative_to(root).parts:
            continue
        relative = str(path.relative_to(root))
        if path.is_symlink():
            entries[relative] = ("symlink", os.readlink(path))
        elif path.is_dir():
            entries[relative] = ("directory",)
        else:
            entries[relative] = ("file", path.read_bytes())
    return entries


class TestFix(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.home = self.base / "home"
        self.home.mkdir()
        self.config = self.base / "claude-config"
        self.config.mkdir()
        self.settings = self.config / "settings.json"
        self.settings_bytes = b'{\n  "enabledPlugins": {}\n}\n'
        self.settings.write_bytes(self.settings_bytes)

    def tearDown(self):
        self.temp.cleanup()

    def args(self, **overrides):
        values = {"config_dir": self.config, "since": "30d", "keep": [],
                  "apply": False, "json": True, "undo": None, "list": False}
        values.update(overrides)
        return SimpleNamespace(**values)

    def run_json(self, args):
        output = io.StringIO()
        with patch.object(fix.doctor, "_home", return_value=self.home):
            with contextlib.redirect_stdout(output):
                code = fix.run(args)
        return code, json.loads(output.getvalue())

    def test_dry_run_changes_nothing_and_preserves_settings_bytes(self):
        make_sessions(self.config)
        write_skill(self.config / "skills" / "unused" / "SKILL.md", "unused")
        before = visible_tree(self.config)

        code, result = self.run_json(self.args())

        self.assertEqual(code, 0)
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(result["moves"]), 1)
        self.assertFalse((self.config / "tokenmaxxing-archive").exists())
        self.assertEqual(visible_tree(self.config), before)
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_fix_is_wired_into_top_level_cli(self):
        result = subprocess.run([sys.executable, str(ROOT / "tokenmaxxing.py"), "fix", "--help"],
                                text=True, capture_output=True)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--undo [RUN_ID]", result.stdout)
        self.assertIn("--apply", result.stdout)

        env = os.environ.copy()
        env["HOME"] = str(self.home)
        result = subprocess.run([sys.executable, str(ROOT / "tokenmaxxing.py"), "fix",
                                 "--config-dir", str(self.config), "--json"],
                                text=True, capture_output=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(json.loads(result.stdout)["dry_run"])
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_apply_writes_manifest_before_move_and_undo_round_trips(self):
        make_sessions(self.config, skill_name="used")
        write_skill(self.config / "skills" / "used" / "SKILL.md", "used")
        write_skill(self.config / "skills" / "unused" / "SKILL.md", "unused")
        before = visible_tree(self.config)
        move = fix._move_path

        def inspect_manifest(src, dst):
            manifest = dst.parents[1] / "manifest.json"
            data = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertFalse(data["moves"][0]["done"])
            return move(src, dst)

        with patch.object(fix, "_move_path", side_effect=inspect_manifest):
            code, applied = self.run_json(self.args(apply=True))

        self.assertEqual(code, 0)
        self.assertFalse((self.config / "skills" / "unused").exists())
        self.assertTrue((self.config / "skills" / "used").is_dir())
        self.assertTrue((self.config / "tokenmaxxing-archive" / applied["run_id"]
                         / "skills" / "unused").is_dir())
        self.assertIn("fix --undo", applied["undo_command"])
        self.assertIn("Restart Claude Code sessions", applied["restart_message"])
        manifest = json.loads((self.config / "tokenmaxxing-archive" / applied["run_id"]
                               / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["moves"][0]["done"])
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

        _, listed = self.run_json(self.args(list=True))
        self.assertEqual(listed["runs"][0]["run_id"], applied["run_id"])
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

        code, undone = self.run_json(self.args(undo=""))
        self.assertEqual(code, 0)
        self.assertEqual(undone["status"], "undone")
        self.assertEqual(visible_tree(self.config), before)
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

        _, repeated = self.run_json(self.args(undo=applied["run_id"]))
        self.assertEqual(repeated["status"], "already_undone")
        self.assertEqual(visible_tree(self.config), before)
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_keep_is_honoured_and_fewer_than_ten_sessions_skips(self):
        make_sessions(self.config)
        write_skill(self.config / "skills" / "kept" / "SKILL.md", "kept")
        write_skill(self.config / "skills" / "unused" / "SKILL.md", "unused")

        _, applied = self.run_json(self.args(apply=True, keep=[["kept"]]))

        self.assertTrue((self.config / "skills" / "kept").is_dir())
        self.assertFalse((self.config / "skills" / "unused").exists())
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

        fewer = self.base / "few-sessions"
        fewer.mkdir()
        fewer_settings = fewer / "settings.json"
        fewer_settings.write_bytes(self.settings_bytes)
        make_sessions(fewer, count=9)
        write_skill(fewer / "skills" / "unused" / "SKILL.md", "unused")
        output = io.StringIO()
        args = self.args(config_dir=fewer, apply=True)
        with patch.object(fix.doctor, "_home", return_value=self.home):
            with contextlib.redirect_stdout(output):
                code = fix.run(args)
        skipped = json.loads(output.getvalue())

        self.assertEqual(code, 0)
        self.assertEqual(skipped["moves"], [])
        self.assertIn("at least 10 Claude sessions", json.dumps(skipped["actions"]))
        self.assertTrue((fewer / "skills" / "unused").is_dir())
        self.assertEqual(fewer_settings.read_bytes(), self.settings_bytes)
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)
        self.assertIsNotNone(applied["run_id"])

    def test_ambiguous_same_scope_duplicates_are_suggested_not_moved(self):
        make_sessions(self.config, skill_name="shared")
        write_skill(self.config / "skills" / "copy-one" / "SKILL.md", "shared")
        write_skill(self.config / "skills" / "copy-two" / "SKILL.md", "shared")

        _, result = self.run_json(self.args(apply=True))

        self.assertEqual(result["moves"], [])
        self.assertTrue((self.config / "skills" / "copy-one").is_dir())
        self.assertTrue((self.config / "skills" / "copy-two").is_dir())
        self.assertTrue(any(item["type"] == "duplicate_skill" and item["status"] == "suggest"
                            for item in result["actions"]))
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_stacked_optimizer_suggestion_reuses_doctor_profiles(self):
        make_sessions(self.config)
        self.settings_bytes = (b'{"enabledPlugins":{"occam@official":true,'
                               b'"whittle@official":true}}\n')
        self.settings.write_bytes(self.settings_bytes)

        _, result = self.run_json(self.args())

        action = next(item for item in result["actions"] if item["type"] == "stacked_optimizers")
        self.assertIn("/plugin disable whittle", action["message"])
        self.assertIn("balanced=ponytail", action["message"])
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_oversized_instruction_suggestion_lists_heading_estimates_only(self):
        make_sessions(self.config)
        project = self.base / "workspace"
        project.mkdir()
        (project / "CLAUDE.md").write_text("# Overview\nshort\n## Rare steps\n" + "z" * 5000,
                                             encoding="utf-8")

        with patch.object(fix.Path, "cwd", return_value=project):
            _, result = self.run_json(self.args())

        action = next(item for item in result["actions"] if item["type"] == "oversized_instructions")
        self.assertIn("Rare steps", action["message"])
        self.assertIn("tokens estimate", action["message"])
        self.assertNotIn("z" * 100, action["message"])
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_symlink_skill_moves_as_link_and_undo_restores_link(self):
        make_sessions(self.config)
        target = self.base / "skill-target"
        write_skill(target / "SKILL.md", "external-skill")
        skills = self.config / "skills"
        skills.mkdir()
        link = skills / "linked"
        link.symlink_to(target, target_is_directory=True)

        _, applied = self.run_json(self.args(apply=True))
        archived_link = (self.config / "tokenmaxxing-archive" / applied["run_id"]
                         / "skills" / "linked")
        self.assertTrue(archived_link.is_symlink())
        self.assertEqual(os.readlink(archived_link), str(target))
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

        self.run_json(self.args(undo=applied["run_id"]))
        self.assertTrue(link.is_symlink())
        self.assertEqual(os.readlink(link), str(target))
        self.assertTrue((target / "SKILL.md").is_file())
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

    def test_undo_refuses_existing_source_and_can_retry(self):
        make_sessions(self.config)
        write_skill(self.config / "skills" / "unused" / "SKILL.md", "unused")
        _, applied = self.run_json(self.args(apply=True))
        original = self.config / "skills" / "unused"
        write_skill(original / "SKILL.md", "user-recreated")

        code, refused = self.run_json(self.args(undo=applied["run_id"]))

        self.assertEqual(code, 1)
        self.assertEqual(refused["status"], "conflict")
        self.assertEqual((original / "SKILL.md").read_text(encoding="utf-8"),
                         "---\nname: user-recreated\ndescription: user-recreated description\n---\nbody\n")
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)

        import shutil
        shutil.rmtree(original)
        code, retried = self.run_json(self.args(undo=applied["run_id"]))
        self.assertEqual(code, 0)
        self.assertEqual(retried["status"], "undone")
        self.assertEqual(self.settings.read_bytes(), self.settings_bytes)


if __name__ == "__main__":
    unittest.main()
