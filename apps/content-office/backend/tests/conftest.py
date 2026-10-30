"""Test-wide isolation: never read or write the operator's real YouTube token file."""
import pytest


@pytest.fixture(autouse=True)
def isolated_secrets_file(tmp_path_factory, monkeypatch):
    path = tmp_path_factory.mktemp("office-secrets") / "youtube-tokens.json"
    monkeypatch.setenv("OFFICE_SECRETS_FILE", str(path))
    return path
