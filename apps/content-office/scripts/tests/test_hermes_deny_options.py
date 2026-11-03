"""Option regressions and native-source fixtures; never execute these commands."""
import importlib.util
from pathlib import Path
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "hermes-deny-floor.py"

# The native offline harness consumes these literal tuples, never a shell.
SOURCE_OPTION_CASES = [
    ("grouped_force_push", "git push -vf origin main", True),
    ("grouped_recursive_delete", "rm -fvr ./artifact-tree", True),
    ("grouped_upper_recursive", "rm -vfR ./artifact-tree", True),
    ("grouped_flags_after_operand", "rm ./artifact-tree -fvr", True),
    ("grouped_absolute_rm", "/usr/bin/rm -fvr ./artifact-tree", True),
    ("grouped_git_globals", "git -C './repo dir' -c color.ui=never push -qvf origin main", True),
    ("grouped_git_attached_globals", "git -C./repo -ccolor.ui=never push -vf origin main", True),
    ("grouped_git_after_operand", "git push origin main -vf", True),
    ("grouped_signed_noarg", "git push --signed -vf origin main", True),
    ("grouped_signed_value", "git push --signed=if-asked -vf origin main", True),
    ("grouped_submodule_value", "git push --recurse-submodules=check -vf origin main", True),
    ("grouped_force_before_option_value", "git push -vfooption origin main", True),
    ("force_refspec_after_separator", "git push -- origin +HEAD:main", True),
    ("shell_payload_rm", "bash -c 'rm -fvr ./artifact-tree'", True),
    ("shell_payload_git", "bash -c 'git push -vf origin main'", True),
    ("actual_command_substitution", "echo \"$(rm -fvr ./artifact-tree)\"", True),
    ("literal_rm_short_filename", "rm -- -fvr", False),
    ("literal_rm_r_filename", "rm -- -rfile", False),
    ("literal_rm_long_filename", "rm -- --recursive-report", False),
    ("literal_push_short_ref", "git push -- origin -f", False),
    ("literal_push_grouped_ref", "git push -- origin -vf", False),
    ("push_option_next_is_flag_data", "git push -o -vf origin main", False),
    ("push_option_plus_is_data", "git push -o +option origin main", False),
    ("push_option_attached_is_data", "git push -ovf origin main", False),
    ("push_option_in_bundle_is_data", "git push -vo-vf origin main", False),
    ("push_long_option_next_is_data", "git push --push-option -vf origin main", False),
    ("push_long_option_attached_is_data", "git push --push-option=-vf origin main", False),
    ("push_repo_value_is_data", "git push --repo=-vf origin main", False),
    ("push_receive_pack_value_is_data", "git push --receive-pack=-vf origin main", False),
    ("push_exec_value_is_data", "git push --exec=-vf origin main", False),
    ("git_config_push_is_data", "git -c 'alias.review=push -vf origin main' status", False),
    ("git_directory_push_is_data", "git -C push status", False),
    ("git_exact_subcommand", "git show push -vf", False),
    ("quoted_git_subcommand_is_data", "git 'push --force'", False),
    ("quoted_rm_prose", "printf '%s\\n' 'rm -fvr ./artifact-tree'", False),
    ("quoted_git_prose", "echo 'git push -vf origin main'", False),
    ("quoted_substitution_data", "echo '$(rm -fvr ./artifact-tree)'", False),
    ("python_argument_is_data", "python -c \"print('rm -fvr ./artifact-tree')\"", False),
    ("quoted_redirection_filename", "rm -- 'file>name'", False),
    ("escaped_redirection_filename", r"rm -- file\>name", False),
    ("quoted_redirection_option_value", "git push -o 'note > harmless' origin main", False),
    ("normal_follow_tags", "git push origin --follow-tags main", False),
    ("normal_plus_in_branch", "git push origin topic+draft", False),
    ("normal_rm_version", "rm --version", False),
]

# (name, command, reason), deliberately without an expected-safe verdict.
SOURCE_OPTION_LIMITS = [
    ("real_rm_redirection", "rm -fvr ./artifact-tree > ./listing.log", "real redirection is outside the added token grammar"),
    ("real_git_redirection", "git push -vf origin main > ./push.log", "real redirection is outside the added token grammar"),
    ("env_split_string", "env -S 'rm -fvr ./artifact-tree'", "env -S argv reconstruction is not added"),
    ("unknown_git_global", "git --config-env=example.value=EXAMPLE_ENV push -vf origin main", "global options outside the declared grammar remain uncovered"),
    ("dynamic_shell_payload", 'bash -c "$COMMAND"', "variable-built program text is not expanded"),
]


class DangerousOptionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("deny_options_candidate", SCRIPT)
        cls.guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.guard)

    def assert_decisions(self, cases):
        classify = getattr(self.guard, "dangerous_options", None)
        self.assertTrue(callable(classify), "dangerous_options(tokens) is not implemented")
        for tokens, expected in cases:
            with self.subTest(tokens=tokens):
                before = list(tokens)
                self.assertIs(classify(tokens), expected)
                self.assertEqual(tokens, before, "option classification must not rewrite argv")

    def test_rm_recursion_in_known_short_options_and_after_operands(self):
        self.assert_decisions([
            (["rm", "-fvr", "./artifact-tree"], True),
            (["rm", "-vfR", "./artifact-tree"], True),
            (["rm", "-Ivr", "./artifact-tree"], True),
            (["rm", "-r", "./artifact-tree"], True),
            (["rm", "-R", "./artifact-tree"], True),
            (["rm", "./artifact-tree", "-fvr"], True),
            (["/usr/bin/rm", "-fvr", "./artifact-tree"], True),
            (["rm", "--recursive", "./artifact-tree"], True),
        ])

    def test_rm_separator_and_nonrecursive_arguments_are_data(self):
        self.assert_decisions([
            (["rm", "--", "-fvr"], False),
            (["rm", "--", "-rfile"], False),
            (["rm", "--", "--recursive-report"], False),
            (["rm", "--version"], False),
            (["rm", "-fvd", "report.tmp"], False),
            (["rm", "-iI", "report.tmp"], False),
            (["rm", "--", "file>name"], False),
            (["printf", "%s\n", "rm -fvr ./artifact-tree"], False),
        ])

    def test_git_push_short_force_options_and_refspecs(self):
        self.assert_decisions([
            (["git", "push", "-vf", "origin", "main"], True),
            (["git", "push", "-qvf", "origin", "main"], True),
            (["git", "push", "-4vf", "origin", "main"], True),
            (["git", "push", "origin", "main", "-vf"], True),
            (["/usr/bin/git", "push", "-vf", "origin", "main"], True),
            (["git", "push", "origin", "+HEAD:main"], True),
            (["git", "push", "--", "origin", "+HEAD:main"], True),
            (["git", "push", "origin", "topic+draft"], False),
        ])

    def test_git_globals_consume_only_their_own_values(self):
        self.assert_decisions([
            (["git", "-C", "./repo dir", "-c", "color.ui=never", "push", "-vf", "origin", "main"], True),
            (["git", "-C./repo", "-ccolor.ui=never", "push", "-vf", "origin", "main"], True),
            (["git", "-C", "", "-C", "./repo", "push", "-vf", "origin", "main"], True),
            (["git", "--no-pager", "push", "-vf", "origin", "main"], True),
            (["git", "-c", "alias.review=push -vf origin main", "status"], False),
            (["git", "-Calias-push", "status"], False),
            (["git", "-C", "push", "status"], False),
            (["git", "show", "push", "-vf"], False),
            (["git", "push --force"], False),
            (["echo", "git", "push", "-vf", "origin", "main"], False),
        ])

    def test_push_short_option_values_cannot_become_force_flags(self):
        self.assert_decisions([
            (["git", "push", "-o", "-vf", "origin", "main"], False),
            (["git", "push", "-o", "+option", "origin", "main"], False),
            (["git", "push", "-ovf", "origin", "main"], False),
            (["git", "push", "-vo-vf", "origin", "main"], False),
            (["git", "push", "-vfooption", "origin", "main"], True),
            (["git", "push", "-ovalue", "origin", "main", "-vf"], True),
        ])

    def test_push_long_value_options_do_not_consume_later_real_flags(self):
        cases = []
        for option in ("--repo", "--receive-pack", "--exec", "--push-option"):
            cases.extend([
                (["git", "push", option, "-vf", "origin", "main"], False),
                (["git", "push", option + "=-vf", "origin", "main"], False),
                (["git", "push", option, "value", "-vf", "origin", "main"], True),
            ])
        self.assert_decisions(cases)

    def test_push_signed_is_noarg_and_separator_ends_flag_parsing(self):
        self.assert_decisions([
            (["git", "push", "--signed", "-vf", "origin", "main"], True),
            (["git", "push", "--no-signed", "-vf", "origin", "main"], True),
            (["git", "push", "--signed=if-asked", "-vf", "origin", "main"], True),
            (["git", "push", "--recurse-submodules=check", "-vf", "origin", "main"], True),
            (["git", "push", "--no-recurse-submodules", "-vf", "origin", "main"], True),
            (["git", "push", "--", "origin", "-vf"], False),
            (["git", "push", "--", "origin", "-f"], False),
            (["git", "push", "origin", "--follow-tags", "main"], False),
        ])


if __name__ == "__main__":
    unittest.main()
