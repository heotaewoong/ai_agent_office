"""LangSmith 공개 샘플 실행기의 키 파일 읽기. 실제 전송은 하지 않는다."""
import importlib.util
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'langsmith_public_probe.py'
spec = importlib.util.spec_from_file_location('langsmith_public_probe', SCRIPT)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


class KeyFileTests(unittest.TestCase):
    def test_shell_key_wins_and_file_is_not_read(self):
        env = {'LANGSMITH_API_KEY': 'from-shell', 'HEOBRAIN_LANGSMITH_KEY_FILE': '/nonexistent/key'}
        self.assertEqual(probe.load_key_file(env), 'env')
        self.assertEqual(env['LANGSMITH_API_KEY'], 'from-shell')

    def test_owner_only_file_is_loaded_into_this_process(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'langsmith.key'
            path.write_text('lsv2-test\n', encoding='utf-8')
            os.chmod(path, 0o600)
            env = {'HEOBRAIN_LANGSMITH_KEY_FILE': str(path)}
            self.assertEqual(probe.load_key_file(env), 'file')
            self.assertEqual(env['LANGSMITH_API_KEY'], 'lsv2-test')

    @unittest.skipIf(os.name == 'nt', 'POSIX permission bits')
    def test_file_others_can_read_is_refused(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / 'langsmith.key'
            path.write_text('lsv2-test', encoding='utf-8')
            os.chmod(path, 0o644)
            env = {'HEOBRAIN_LANGSMITH_KEY_FILE': str(path)}
            with self.assertRaises(SystemExit):
                probe.load_key_file(env)
            self.assertNotIn('LANGSMITH_API_KEY', env)

    def test_missing_or_empty_file_leaves_no_key(self):
        with TemporaryDirectory() as folder:
            empty = Path(folder) / 'empty.key'
            empty.write_text('  \n', encoding='utf-8')
            os.chmod(empty, 0o600)
            for path in (Path(folder) / 'missing.key', empty):
                env = {'HEOBRAIN_LANGSMITH_KEY_FILE': str(path)}
                self.assertIsNone(probe.load_key_file(env))
                self.assertNotIn('LANGSMITH_API_KEY', env)


if __name__ == '__main__':
    unittest.main()
