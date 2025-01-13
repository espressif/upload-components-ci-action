import pytest
from unittest.mock import patch


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("GITHUB_WORKSPACE", "/fake/workspace")
    monkeypatch.setenv("COMPONENTS_NAMESPACE", "test_ns")
    monkeypatch.setenv("COMPONENTS_DIRECTORIES", "comp1;comp2")
    monkeypatch.setenv("COMPONENT_VERSION", "v1.0.0")
    monkeypatch.setenv("REPOSITORY_URL", "https://fake.repo.url")
    monkeypatch.setenv("COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("COMPONENT_NAME", "fake_component")


def test_parse_directories(mock_env):
    from upload import parse_directories

    directories = parse_directories()
    assert directories == ["comp1", "comp2"]


def test_main_no_failure(mock_env):
    from upload import main

    with patch("upload.process_directories", return_value=[]) as mock_process:
        main()
        mock_process.assert_called_once()
