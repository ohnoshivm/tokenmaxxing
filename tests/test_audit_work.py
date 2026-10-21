import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("tokenmaxxing_audit_work", ROOT / "scripts" / "audit.py")
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def write_jsonl(path, events):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
    return path


def claude_tool(mid, call_id, name, tool_input, at):
    return {
        "type": "assistant",
        "timestamp": at,
        "message": {
            "id": mid,
            "model": "gpt-test-unknown",
            "usage": {"input_tokens": 10, "cache_read_input_tokens": 0,
                       "cache_creation_input_tokens": 0, "output_tokens": 2},
            "content": [{"type": "tool_use", "id": call_id, "name": name, "input": tool_input}],
        },
    }


def result(call_id, *, is_error=None, exit_code=None):
    value = {"type": "user", "message": {"content": [{
        "type": "tool_result", "tool_use_id": call_id, "content": "ok",
    }]}}
    if is_error is not None:
        value["message"]["content"][0]["is_error"] = is_error
    if exit_code is not None:
        value["message"]["content"][0]["exit_code"] = exit_code
    return value


class TestAuditWork(unittest.TestCase):
    def test_claude_work_skills_and_verified_edit_order(self):
        now = "2026-10-21T12:00:00+00:00"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = [
                claude_tool("m1", "edit-1", "Edit", {"file_path": "a.py"}, now),
                result("edit-1", is_error=False),
                claude_tool("m2", "test-1", "Bash", {"command": "python -m unittest discover -s tests"}, now),
                result("test-1", is_error=False),
                claude_tool("m3", "test-2", "Bash", {"command": "python -m unittest discover -s tests"}, now),
                result("test-2", is_error=False),
                claude_tool("m3b", "test-unknown", "Bash", {"command": "ruff check ."}, now),
                result("test-unknown"),
                claude_tool("m4", "noise", "Bash", {"command": "echo pytest"}, now),
                result("noise", is_error=False),
                claude_tool("m5", "skill-1", "Skill", {"skill": "review"}, now),
                result("skill-1", is_error=False),
                claude_tool("m6", "plugin-skill", "Skill", {"skill": "plugin:sample/inspect"}, now),
                result("plugin-skill", is_error=False),
                {"type": "user", "timestamp": now, "message": {
                    "content": "<command-name>/hand-run</command-name>"}},
                claude_tool("m7", "edit-failed", "Write", {"file_path": "b.py"}, now),
                result("edit-failed", is_error=True),
                claude_tool("m8", "commit", "Bash", {"command": "git commit -m done"}, now),
                result("commit", is_error=False),
                claude_tool("m9", "commit-dry", "Bash", {"command": "git commit --dry-run"}, now),
                result("commit-dry", is_error=False),
                # This successful edit happens after the passing checks, so it leaves this session unverified.
                claude_tool("m10", "edit-last", "MultiEdit", {"file_path": "c.py"}, now),
                result("edit-last", is_error=False),
            ]
            write_jsonl(root / "project" / "session-a.jsonl", events)

            report = audit.summarize(audit.collect(paths=[root]))

        self.assertEqual(report["work"]["edits"], 2)
        self.assertEqual(report["work"]["checks"], 3)
        self.assertEqual(report["work"]["checks_passed"], 2)
        self.assertEqual(report["work"]["checks_failed"], 0)
        self.assertEqual(report["work"]["distinct_passing_checks"], 1)
        self.assertEqual(report["work"]["commits"], 1)
        self.assertEqual(report["work"]["verified_edit_sessions"], 0)
        self.assertEqual(report["work"]["unverified_edit_sessions"], 1)
        self.assertEqual(report["skills_used"]["by_name"], {"hand-run": 1, "review": 1})
        self.assertEqual(report["skills_used"]["by_plugin"], {"sample": {"inspect": 1}})
        self.assertIn("gpt-test-unknown", report["work"]["unknown_models"])
        self.assertTrue(any("Only 0% of edit sessions" in item for item in report["findings"]))

    def test_codex_function_calls_and_exit_codes(self):
        now = "2026-10-21T12:00:00+00:00"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "rollout.jsonl"
            events = [
                {"type": "session_meta", "timestamp": now,
                 "payload": {"id": "codex-work", "cwd": "/repo/app"}},
                {"type": "turn_context", "payload": {"model": "gpt-6.1-sol"}},
                {"type": "response_item", "payload": {
                    "type": "function_call", "call_id": "patch", "name": "apply_patch",
                    "arguments": "*** Begin Patch\n*** Update File: a.py\n*** End Patch"}},
                {"type": "response_item", "payload": {
                    "type": "function_call_output", "call_id": "patch", "exit_code": 0}},
                {"type": "response_item", "payload": {
                    "type": "function_call", "call_id": "check", "name": "exec_command",
                    "arguments": json.dumps({"cmd": "npm run test"})}},
                {"type": "response_item", "payload": {
                    "type": "function_call_output", "call_id": "check", "exit_code": 0}},
                {"type": "response_item", "payload": {
                    "type": "function_call", "call_id": "failed-check", "name": "exec_command",
                    "arguments": json.dumps({"cmd": "pytest"})}},
                {"type": "response_item", "payload": {
                    "type": "function_call_output", "call_id": "failed-check", "exit_code": 1}},
                {"type": "response_item", "payload": {
                    "type": "function_call", "call_id": "commit", "name": "exec_command",
                    "arguments": json.dumps({"cmd": "git commit -m done"})}},
                {"type": "response_item", "payload": {
                    "type": "function_call_output", "call_id": "commit", "exit_code": 0}},
                {"type": "response_item", "payload": {
                    "type": "function_call", "call_id": "commit-failed", "name": "exec_command",
                    "arguments": json.dumps({"cmd": "git commit -m no"})}},
                {"type": "response_item", "payload": {
                    "type": "function_call_output", "call_id": "commit-failed", "exit_code": 1}},
                {"type": "user_message", "payload": {
                    "content": "<command-name>/codex-skill</command-name>"}},
                {"type": "event_msg", "payload": {"type": "token_count", "info": {
                    "total_token_usage": {"input_tokens": 100, "cached_input_tokens": 30,
                                          "output_tokens": 20}}}},
            ]
            write_jsonl(path, events)

            report = audit.summarize([audit.parse_codex(path)])

        self.assertEqual(report["work"]["edits"], 1)
        self.assertEqual(report["work"]["checks"], 2)
        self.assertEqual(report["work"]["checks_passed"], 1)
        self.assertEqual(report["work"]["checks_failed"], 1)
        self.assertEqual(report["work"]["commits"], 1)
        self.assertEqual(report["work"]["verified_edit_sessions"], 1)
        self.assertEqual(report["skills_used"]["by_name"], {"codex-skill": 1})
        self.assertGreater(report["work"]["premium_share"], 0)
        self.assertTrue(any("Failed checks are 50%" in item for item in report["findings"]))

    def test_check_pattern_matches_first_segment_only(self):
        self.assertTrue(audit.is_check_command("echo hi && pytest -q"))
        self.assertFalse(audit.is_check_command("echo pytest"))
        self.assertFalse(audit.is_check_command("echo 'pytest; jest'"))
        self.assertTrue(audit.is_check_command("echo hi; pytest -q"))
        self.assertTrue(audit.is_check_command("python -m unittest"))

    def test_human_output_includes_work_proxy_block(self):
        output = io.StringIO()
        with redirect_stdout(output):
            audit.print_report(audit.summarize([]), "all time")

        self.assertIn("Work (proxy — counted from tool calls, not a quality judgement)", output.getvalue())
        self.assertIn("usage per passing check n/a", output.getvalue())

    def test_compare_reports_too_few_checks(self):
        current = audit.summarize([])
        previous = audit.summarize([])
        current["work"]["checks_passed"] = 4
        current["work"]["distinct_passing_checks"] = 4
        previous["work"]["checks_passed"] = 3
        previous["work"]["distinct_passing_checks"] = 3
        comparison = audit.build_comparison(current, previous)

        output = io.StringIO()
        with redirect_stdout(output):
            audit.print_comparison(comparison)

        self.assertIn("n/a (too few checks)", output.getvalue())

    def test_compare_includes_work_rows_and_neutral_premium_share(self):
        current = audit.summarize([])
        previous = audit.summarize([])
        current["work"].update({"weighted_units": 1000, "checks_passed": 8,
                                "distinct_passing_checks": 4, "usage_per_passing_check": 125,
                                "usage_per_distinct_passing_check": 250, "rework_rate": .1,
                                "verified_edit_share": .8, "premium_share": .4})
        previous["work"].update({"weighted_units": 1200, "checks_passed": 8,
                                 "distinct_passing_checks": 3, "usage_per_passing_check": 150,
                                 "usage_per_distinct_passing_check": 400, "rework_rate": .2,
                                 "verified_edit_share": .6, "premium_share": .5})
        output = io.StringIO()
        with redirect_stdout(output):
            audit.print_comparison(audit.build_comparison(current, previous))

        rendered = output.getvalue()
        self.assertIn("Usage per passing check:", rendered)
        self.assertIn("Usage per distinct passing check:", rendered)
        self.assertIn("Rework rate: 10% current · 20% previous", rendered)
        self.assertIn("Verified-edit share: 80% current · 60% previous", rendered)
        self.assertIn("Premium share: 40% current · 50% previous", rendered)
        self.assertIn("· neutral", rendered)


if __name__ == "__main__":
    unittest.main()
