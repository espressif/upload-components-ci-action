from unittest.mock import patch

import pytest
import requests

from upload import parse_components_input, split_component_str, Component,upload_arguments, args_to_list, mock_version_if_not_provided, get_oidc_token, FatalError, ensure_token, MissingAuthConfigurationError
from pathlib import Path

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv('GITHUB_WORKSPACE', '/fake/workspace')
    monkeypatch.setenv('COMPONENTS_NAMESPACE', 'test_ns')
    monkeypatch.setenv('COMPONENTS', 'comp1;comp2')
    monkeypatch.setenv('COMPONENT_VERSION', 'v1.0.0')
    monkeypatch.setenv('REPOSITORY_URL', 'https://fake.repo.url')
    monkeypatch.setenv('COMMIT_SHA', 'a' * 40)
    monkeypatch.setenv('COMPONENT_NAME', 'fake_component')
    monkeypatch.setenv('IDF_COMPONENT_API_TOKEN', 'fake_token')

def test_main_no_failure(mock_env):
    from upload import main

    with patch('upload.upload_components', return_value=[]) as mock_process:
        main()
        mock_process.assert_called_once()


@pytest.mark.parametrize(
    'component_str,expected_name,expected_path',
    [
        ('comp:.', 'comp', '.'),
        ('comp1', None, 'comp1'),
        ('comp1:path/to/comp1', 'comp1', 'path/to/comp1'),
        ('  comp1 : path/to/comp1  ', 'comp1', 'path/to/comp1'),
    ],
)
def test_split_component_str(component_str, expected_name, expected_path):
    component = split_component_str(component_str)
    assert component.name == expected_name
    assert component.path == expected_path


@pytest.mark.parametrize(
        "components_str, expected_components",
        [
            # Single component with no colon
            ("comp1", [Component(name=None, path="comp1")]),
            # Multiple components with different separators
            ("comp1;\ncomp2", [Component(name=None, path="comp1"), Component(name=None, path="comp2")]),
            ("comp1\ncomp2", [Component(name=None, path="comp1"), Component(name=None, path="comp2")]),
            ("comp1;comp2", [Component(name=None, path="comp1"), Component(name=None, path="comp2")]),

            # Components with explicit path
            ("comp1:./comp1;\ncomp2:./comp2", [Component(name="comp1", path="./comp1"), Component(name="comp2", path="./comp2")]),
            # Component with extra spaces
            ("  comp1  :  ./  \n\n", [Component(name="comp1", path="./")]),
            # Mixed empty parts and valid component (ignores empty entries)
            ("comp1;\n   ;\ncomp2:./comp2", [Component(name=None, path="comp1"), Component(name="comp2", path="./comp2")]),
        ],
    )
def test_parse_components_input_parametrized(monkeypatch, components_str, expected_components):
    monkeypatch.setenv("COMPONENTS", components_str)
    result = parse_components_input()
    assert result == expected_components


@pytest.mark.parametrize(
    "input_args,expected",
    [
        ({}, []),
        ({"flag": None}, ["--flag"]),
        ({"option": "value"}, ["--option", "value"]),
        (
            {"a": None, "b": "val", "c": None, "d": "123"},
            ["--a", "--b", "val", "--c", "--d", "123"],
        ),
    ],
)
def test_args_to_list(input_args, expected):
    result = args_to_list(input_args)
    assert result == expected


def test_mock_version_if_not_provided():
    result = mock_version_if_not_provided({}, Path(''))["version"]
    assert result.startswith("1000.1000.1000-mock.")


def test_mock_version_if_provided_in_input():
    assert mock_version_if_not_provided({"version": "1.2.3"}, Path(''))["version"] == "1.2.3"


def test_mock_version_if_not_provided_even_in_manifest(tmp_path):
    (tmp_path / "idf_component.yml").touch()
    result = mock_version_if_not_provided({}, tmp_path)['version']
    assert result.startswith("1000.1000.1000-mock.")


def test_mock_version_if_provided_in_manifest(tmp_path):
    (tmp_path / "idf_component.yml").write_text("version: 1.2.3")
    assert mock_version_if_not_provided({}, tmp_path) == {}

# V1 to V2 Migration Tests
def test_v2_format_components_input(monkeypatch):
    """Test v2 format: components: "my_component:." """
    monkeypatch.setenv("COMPONENTS", "my_component:.")
    # Clear any legacy inputs
    monkeypatch.delenv("COMPONENT_NAME", raising=False)
    monkeypatch.delenv("COMPONENT_DIRECTORIES", raising=False)

    result = parse_components_input()
    expected = [Component(name="my_component", path=".")]
    assert result == expected

def test_v1_legacy_name_input(monkeypatch):
    """Test v1 legacy: name: "my_component" """
    # Clear new format
    monkeypatch.delenv("COMPONENTS", raising=False)
    # Set legacy name input
    monkeypatch.setenv("COMPONENT_NAME", "my_component")
    monkeypatch.delenv("COMPONENT_DIRECTORIES", raising=False)

    result = parse_components_input()
    expected = [Component(name="my_component", path=".")]
    assert result == expected

def test_v1_legacy_directories_input(monkeypatch):
    """Test v1 legacy: directories: "components/comp1;components/comp2" """
    # Clear new format
    monkeypatch.delenv("COMPONENTS", raising=False)
    # Set legacy directories input (semicolon-separated only)
    monkeypatch.delenv("COMPONENT_NAME", raising=False)
    monkeypatch.setenv("COMPONENT_DIRECTORIES", "components/comp1;components/comp2")

    result = parse_components_input()
    expected = [
        Component(name=None, path="components/comp1"),
        Component(name=None, path="components/comp2")
    ]
    assert result == expected

def test_input_precedence_v2_over_legacy(monkeypatch, capsys):
    """Test precedence: v2 components takes priority over legacy inputs with warning """
    # Set both new and legacy inputs
    monkeypatch.setenv("COMPONENTS", "new_component:.")
    monkeypatch.setenv("COMPONENT_NAME", "legacy_component")

    from upload import validate_input_precedence
    validate_input_precedence()

    # Check that warning is printed
    captured = capsys.readouterr()
    assert "WARNING: Both v2 'components' and legacy v1 inputs detected." in captured.out
    assert "Using v2 'components' input. Legacy inputs will be ignored." in captured.out

    # Verify v2 format takes precedence
    result = parse_components_input()
    expected = [Component(name="new_component", path=".")]
    assert result == expected

def test_conflicting_legacy_inputs_error(monkeypatch):
    """Test error when both legacy name and directories are provided """
    # Clear new format
    monkeypatch.delenv("COMPONENTS", raising=False)
    # Set both legacy inputs (should cause error)
    monkeypatch.setenv("COMPONENT_NAME", "my_component")
    monkeypatch.setenv("COMPONENT_DIRECTORIES", "components/comp1")

    from upload import validate_input_precedence, FatalError

    with pytest.raises(FatalError) as exc_info:
        validate_input_precedence()

    assert "Cannot use both 'name' and 'directories' legacy inputs simultaneously" in str(exc_info.value)

def test_migration_guidance_for_legacy_name(monkeypatch, capsys):
    """Test migration guidance is shown for legacy name input """
    monkeypatch.setenv("COMPONENT_NAME", "my_component")
    monkeypatch.delenv("COMPONENT_DIRECTORIES", raising=False)

    from upload import provide_migration_guidance
    provide_migration_guidance()

    captured = capsys.readouterr()
    assert "INFO: Detected legacy v1 inputs. Consider migrating to v2 format:" in captured.out
    assert "v1: name: 'my_component'" in captured.out
    assert "v2: components: 'my_component:.'" in captured.out
    assert "See migration guide: https://github.com/espressif/upload-components-ci-action#upgrading-from-v1-to-v2" in captured.out

def test_migration_guidance_for_legacy_directories(monkeypatch, capsys):
    """Test migration guidance is shown for legacy directories input """
    monkeypatch.delenv("COMPONENT_NAME", raising=False)
    monkeypatch.setenv("COMPONENT_DIRECTORIES", "comp1;comp2")

    from upload import provide_migration_guidance
    provide_migration_guidance()

    captured = capsys.readouterr()
    assert "INFO: Detected legacy v1 inputs. Consider migrating to v2 format:" in captured.out
    assert "v1: directories: 'comp1;comp2'" in captured.out
    assert "comp1" in captured.out
    assert "comp2" in captured.out
    assert "See migration guide: https://github.com/espressif/upload-components-ci-action#upgrading-from-v1-to-v2" in captured.out

def test_no_components_specified_error(monkeypatch):
    """Test error when no components are specified """
    # Clear all component inputs
    monkeypatch.delenv("COMPONENTS", raising=False)
    monkeypatch.delenv("COMPONENT_NAME", raising=False)
    monkeypatch.delenv("COMPONENT_DIRECTORIES", raising=False)

    from upload import FatalError

    with pytest.raises(FatalError) as exc_info:
        parse_components_input()

    assert "No components specified. Use 'components' input or legacy 'name'/'directories' inputs." in str(exc_info.value)

def test_legacy_inputs_return_none_when_no_legacy_set(monkeypatch):
    """Test parse_legacy_inputs returns None when no legacy inputs are set """
    monkeypatch.delenv("COMPONENT_NAME", raising=False)
    monkeypatch.delenv("COMPONENT_DIRECTORIES", raising=False)

    from upload import parse_legacy_inputs
    result = parse_legacy_inputs()
    assert result is None

def test_legacy_directories_with_spaces_and_empty_entries(monkeypatch):
    """Test legacy directories parsing handles spaces and empty entries correctly """
    monkeypatch.delenv("COMPONENTS", raising=False)
    monkeypatch.delenv("COMPONENT_NAME", raising=False)
    monkeypatch.setenv("COMPONENT_DIRECTORIES", "comp1; comp2 ;; comp3 ;")

    result = parse_components_input()
    expected = [
        Component(name=None, path="comp1"),
        Component(name=None, path="comp2"),
        Component(name=None, path="comp3")
    ]
    assert result == expected


def test_get_oidc_token_success(monkeypatch):
    class MockResponse:
        def raise_for_status(self): pass
        def json(self): return {'value': 'mocked_oidc_token'}

    monkeypatch.setenv('ACTIONS_ID_TOKEN_REQUEST_URL', 'https://test.com/oidc')
    monkeypatch.setenv('ACTIONS_ID_TOKEN_REQUEST_TOKEN', 'test')
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: MockResponse())

    token = get_oidc_token()
    assert token == 'mocked_oidc_token'


def test_get_oidc_without_permissions():
    with pytest.raises(MissingAuthConfigurationError):
        get_oidc_token()


def test_ensure_token(monkeypatch, capsys):
    monkeypatch.setenv('IDF_COMPONENT_API_TOKEN', 'mocked_token')
    ensure_token()
    captured = capsys.readouterr()
    assert captured.out == 'Using ESP Component Registry token.\n'

def test_ensure_token_no_token(monkeypatch, capsys):
    monkeypatch.delenv('IDF_COMPONENT_API_TOKEN', raising=False)
    message = (
        "Failed to authenticate: no valid token provided.\n"
        "- If you intended to use the ESP Component Registry token, please set the 'api_token' "
        "input in your workflow.\n"
        "- If you intended to use GitHub OIDC for authentication, ensure that your workflow has "
        "the required permissions:\n"
        "  permissions:\n"
        "    id-token: write\n"
        "\n"
        "Refer to the documentation for proper setup of authentication methods."
    )

    with pytest.raises(FatalError, match=message):
        ensure_token()


@pytest.mark.parametrize(
    "env_vars,expected_args",
    [
        ({}, {'allow-existing': None, 'namespace': 'espressif'}),
        ({'COMPONENTS_NAMESPACE': 'custom'}, {'allow-existing': None, 'namespace': 'custom'}),
        ({'SKIP_PRE_RELEASE': 'true'}, {'allow-existing': None, 'namespace': 'espressif', 'skip-pre-release': None}),
        ({'DRY_RUN': 'true'}, {'allow-existing': None, 'namespace': 'espressif', 'dry-run': None}),
        ({'REPOSITORY_URL': 'https://example.com'}, {'allow-existing': None, 'namespace': 'espressif', 'repository': 'https://example.com'}),
        ({'COMMIT_SHA': 'abc123'}, {'allow-existing': None, 'namespace': 'espressif', 'commit-sha': 'abc123'}),
        ({'COMPONENT_VERSION': '  2.0.0  '}, {'allow-existing': None, 'namespace': 'espressif', 'version': '2.0.0'}),
        (
            {
                'COMPONENTS_NAMESPACE': 'myns',
                'SKIP_PRE_RELEASE': 'true',
                'REPOSITORY_URL': 'https://repo.com',
                'COMMIT_SHA': 'def456',
                'COMPONENT_VERSION': '3.0.0'
            },
            {
                'allow-existing': None,
                'namespace': 'myns',
                'skip-pre-release': None,
                'repository': 'https://repo.com',
                'commit-sha': 'def456',
                'version': '3.0.0'
            }
        )
    ]
)
def test_upload_arguments(monkeypatch, env_vars, expected_args):
    for key in ['COMPONENTS_NAMESPACE', 'SKIP_PRE_RELEASE', 'DRY_RUN', 'REPOSITORY_URL', 'COMMIT_SHA', 'COMPONENT_VERSION']:
        monkeypatch.delenv(key, raising=False)

    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)

    result = upload_arguments()
    assert result == expected_args
