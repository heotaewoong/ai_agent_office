"""Read-only audit contract: no private contents, no profile discovery, fail closed."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).parents[2] / "scripts" / "hermes-team-audit.py"
SKILL = SCRIPT.parent / "templates" / "hermes" / "heobrain-office-audit" / "SKILL.md"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(SCRIPT.is_file(), "read-only audit helper is not implemented")
        spec = importlib.util.spec_from_file_location("hermes_team_audit", SCRIPT)
        self.audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.audit)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name) / "hermes"
        self.home.mkdir(mode=0o700)

    def config(self, text, profile="default"):
        base = self.home if profile == "default" else self.home / "profiles" / profile
        base.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = base / "config.yaml"
        path.write_text(text, encoding="utf-8")
        path.chmod(0o600)
        return path

    def test_off_mode_is_action_needed_without_echoing_secrets(self):
        self.config("approvals:\n  mode: off\n  deny: [PRIVATE_COMMAND]\nterminal:\n  backend: local\nskills:\n  write_approval: false\nmemory:\n  provider: mem0\n  api_key: PRIVATE_KEY\nplatforms:\n  webhook:\n    enabled: false\n    extra:\n      secret: PRIVATE_SECRET\n      host: 127.0.0.1\n")
        report = self.audit.audit(self.home, profiles=())
        encoded = json.dumps(report)
        self.assertEqual(report["profiles"][0]["policy"]["approvals_mode"], "off")
        self.assertIn("approvals_off", report["profiles"][0]["action_needed"])
        self.assertEqual(report["profiles"][0]["policy"]["deny_rule_count"], 1)
        for private in ("PRIVATE_COMMAND", "PRIVATE_KEY", "PRIVATE_SECRET"):
            self.assertNotIn(private, encoded)

    def test_missing_settings_are_unknown_and_no_profiles_are_discovered(self):
        self.config("{}")
        self.config("approvals: {mode: off}", "ada")
        report = self.audit.audit(self.home, profiles=("lumi",))
        self.assertEqual([p["profile"] for p in report["profiles"]], ["default", "lumi"])
        self.assertEqual(report["profiles"][0]["policy"]["approvals_mode"], "unknown")
        self.assertEqual(report["profiles"][1]["config_status"], "missing")
        self.assertEqual(report["runtime_policy"], "unknown")

    def test_parse_errors_do_not_expose_input_or_parser_details(self):
        for text in ("secret: PRIVATE_PARSE_SECRET\nbroken: [", "secret: PRIVATE_PARSE_SECRET\nsecret: duplicate", "- PRIVATE_PARSE_SECRET"):
            with self.subTest(text=text):
                self.config(text)
                report = self.audit.audit(self.home, profiles=())
                self.assertEqual(report["profiles"][0]["config_status"], "invalid")
                self.assertNotIn("PRIVATE_PARSE_SECRET", json.dumps(report))

    def test_invalid_config_never_claims_absent_hooks_or_secret(self):
        self.config("secret: PRIVATE_PARSE_SECRET\nbroken: [")
        profile = self.audit.audit(self.home, profiles=())["profiles"][0]
        self.assertEqual(profile["policy"]["shell_hook_event_counts"]["pre_tool_call"], "unknown")
        self.assertEqual(profile["webhook"]["global_auth_present"], "unknown")
        self.assertEqual(profile["webhook"]["static_routes"]["route_count"], "unknown")
        self.assertEqual(profile["memory"]["mem0_config_key_present"], "unknown")

    def test_changed_config_is_rejected_as_a_stale_snapshot(self):
        config = self.config("approvals: {mode: off}\nsecret: PRIVATE_OLD")
        read = os.read
        def change_after_read(fd, count):
            data = read(fd, count)
            config.write_text("secret: PRIVATE_REPLACEMENT\n", encoding="utf-8")
            return data
        with patch.object(os, "read", side_effect=change_after_read):
            report = self.audit.audit(self.home, profiles=())
        self.assertEqual(report["profiles"][0]["config_status"], "changed_during_read")
        self.assertEqual(report["profiles"][0]["policy"]["approvals_mode"], "unknown")
        self.assertNotIn("PRIVATE_", json.dumps(report))

    def test_fixed_metadata_only_and_readonly_hashes(self):
        config = self.config("hooks:\n  pre_tool_call:\n    - command: PRIVATE_COMMAND\nplatforms:\n  webhook:\n    enabled: true\n    extra:\n      host: 0.0.0.0\n      routes:\n        PRIVATE_ROUTE: {secret: PRIVATE_SECRET}\n")
        env = self.home / ".env"
        env.write_text("TOKEN=PRIVATE_ENV", encoding="utf-8")
        env.chmod(0o600)
        subscriptions = self.home / "webhook_subscriptions.json"
        subscriptions.write_text(json.dumps({"PRIVATE_ROUTE": {"secret": "PRIVATE_SECRET", "prompt": "PRIVATE_BODY"}}))
        subscriptions.chmod(0o600)
        before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in (config, env, subscriptions)}
        report = self.audit.audit(self.home, profiles=())
        after = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in before}
        self.assertEqual(before, after)
        profile = report["profiles"][0]
        self.assertEqual(profile["policy"]["shell_hook_event_counts"]["pre_tool_call"], 1)
        self.assertEqual(profile["webhook"]["subscriptions"]["route_count"], 1)
        self.assertFalse(profile["webhook"]["loopback"])
        for secret in ("PRIVATE_ROUTE", "PRIVATE_SECRET", "PRIVATE_BODY", "PRIVATE_COMMAND", "PRIVATE_ENV"):
            self.assertNotIn(secret, json.dumps(report))

    @unittest.skipUnless(os.name == "posix", "POSIX filesystem security contract")
    def test_symlink_config_and_profile_directory_are_not_read(self):
        outside = Path(self.temp.name) / "outside.yaml"
        outside.write_text("approvals: {mode: off}\nsecret: PRIVATE_SYMLINK")
        (self.home / "config.yaml").symlink_to(outside)
        (self.home / "profiles").mkdir()
        (self.home / "profiles" / "lumi").symlink_to(self.home, target_is_directory=True)
        report = self.audit.audit(self.home, profiles=("lumi",))
        self.assertEqual([p["config_status"] for p in report["profiles"]], ["unsafe_path", "unsafe_path"])
        self.assertNotIn("PRIVATE_SYMLINK", json.dumps(report))

    @unittest.skipUnless(os.name == "posix", "POSIX ownership security contract")
    def test_owner_mismatch_fails_closed(self):
        self.config("approvals: {mode: off}")
        report = self.audit.audit(self.home, profiles=(), expected_uid=os.getuid() + 1)
        self.assertEqual(report["profiles"][0]["config_status"], "owner_mismatch")
        self.assertEqual(report["profiles"][0]["policy"]["approvals_mode"], "unknown")

    @unittest.skipUnless(os.name == "posix", "POSIX special-file security contract")
    def test_named_pipe_is_rejected_before_open(self):
        self.config("{}")
        os.mkfifo(self.home / ".env", 0o600)
        previous = signal.signal(signal.SIGALRM, lambda *_: self.fail("audit blocked opening a FIFO"))
        signal.alarm(2)
        try:
            metadata = self.audit.audit(self.home, profiles=())["profiles"][0]["files"][".env"]
            self.assertEqual(metadata["status"], "unsafe_path")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    @unittest.skipUnless(os.name == "posix", "POSIX special-file race contract")
    def test_regular_file_replaced_with_fifo_does_not_block_open(self):
        config = self.config("{}")
        original_open = os.open
        swapped = False
        def swap_before_open(path, flags, *args, **kwargs):
            nonlocal swapped
            if path == "config.yaml" and not swapped:
                swapped = True
                config.unlink()
                os.mkfifo(config, 0o600)
            return original_open(path, flags, *args, **kwargs)
        previous = signal.signal(signal.SIGALRM, lambda *_: self.fail("FIFO replacement blocked open"))
        signal.alarm(2)
        try:
            with patch.object(os, "open", side_effect=swap_before_open):
                report = self.audit.audit(self.home, profiles=())
            self.assertEqual(report["profiles"][0]["config_status"], "unsafe_path")
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous)

    @unittest.skipUnless(os.name == "posix", "POSIX hardlink contract")
    def test_config_hardlink_cannot_read_an_env_file(self):
        env = self.home / ".env"
        env.write_text("approvals: {mode: off}\nsecret: PRIVATE_ENV")
        env.chmod(0o600)
        os.link(env, self.home / "config.yaml")
        report = self.audit.audit(self.home, profiles=())
        self.assertEqual(report["profiles"][0]["config_status"], "unsafe_path")
        self.assertEqual(report["profiles"][0]["policy"]["approvals_mode"], "unknown")
        self.assertNotIn("PRIVATE_ENV", json.dumps(report))

    def test_unknown_profile_is_rejected_without_path_access(self):
        with self.assertRaises(ValueError):
            self.audit.audit(self.home, profiles=("../../outside",))

    def test_lumi_template_requires_readonly_scope_and_human_approval(self):
        self.assertTrue(SKILL.is_file(), "Lumi audit skill template is not implemented")
        text = SKILL.read_text(encoding="utf-8")
        for required in ("name: heobrain-office-audit", "루미", "⓪", "①", "②", "③", "--hermes-home /home/ihtwa/.hermes", "--profile lumi", "읽기 전용", "외부", "우회"):
            self.assertIn(required, text)
        self.assertNotIn("--accept-hooks", text)
        self.assertNotIn("HERMES_ACCEPT_HOOKS=1", text)

    @unittest.skipUnless(os.name == "posix", "POSIX mode semantics")
    def test_644_file_inside_private_700_home_is_not_claimed_exposed(self):
        path = self.config("{}")
        path.chmod(0o644)
        report = self.audit.audit(self.home, profiles=())
        metadata = report["profiles"][0]["files"]["config.yaml"]
        self.assertEqual(metadata["mode"], "0644")
        self.assertEqual(metadata["ancestor_access"], "restricted")
        self.assertNotIn("public_exposure", report["profiles"][0]["action_needed"])


if __name__ == "__main__":
    unittest.main()
