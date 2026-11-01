import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock


class HostTests(unittest.TestCase):
    def load(self, bridge):
        spec = importlib.util.spec_from_file_location('draft_host', Path(__file__).parents[1] / 'owner-draft-host.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'owner_agent':SimpleNamespace(OwnerError=ValueError), 'owner_bridge':bridge}):
            spec.loader.exec_module(module)
        return module

    def test_public_commands_and_extra_secret_fields_never_reach_remote(self):
        bridge = SimpleNamespace(remote=Mock())
        host = self.load(bridge)
        for message in ({'command':'publish'}, {'command':'schedule'}, {'command':'status','password':'synthetic'}):
            with self.assertRaises(ValueError):
                host.handle(message)
        bridge.remote.assert_not_called()

    def test_claim_id_is_validated_before_server_interaction(self):
        bridge = SimpleNamespace(remote=Mock())
        host = self.load(bridge)
        with self.assertRaises(ValueError):
            host.handle({'command':'claim','id':'../../operator.env'})
        bridge.remote.assert_not_called()

    def test_poll_contains_no_upload_side_effect(self):
        bridge = SimpleNamespace(remote=Mock(return_value=[]))
        host = self.load(bridge)
        self.assertEqual(host.handle({'command':'poll'})['items'], [])
        code = bridge.remote.call_args.args[0]
        self.assertIn('d.pending(store)', code)
        self.assertNotIn('private_upload', code)

    def test_youtube_verification_allows_only_platform_trailing_line_break_normalization(self):
        host = self.load(SimpleNamespace())
        expected = {'title': '승인된 제목', 'description': '첫 문단\n\n둘째 문단\n'}
        self.assertTrue(host.youtube_metadata_matches({'title': '승인된 제목', 'description': '첫 문단\n\n둘째 문단'}, expected))
        self.assertFalse(host.youtube_metadata_matches({'title': '다른 제목', 'description': '첫 문단\n\n둘째 문단'}, expected))
        self.assertFalse(host.youtube_metadata_matches({'title': '승인된 제목', 'description': '첫 문단\n둘째 문단'}, expected))
        self.assertFalse(host.youtube_metadata_matches({'title': '승인된 제목', 'description': '첫 문단\n\n둘째 문단 '}, expected))


if __name__ == '__main__':
    unittest.main()
