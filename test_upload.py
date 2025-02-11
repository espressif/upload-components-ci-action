from unittest.mock import patch

import pytest

from upload import parse_components_input, split_component_str, Component, args_to_list

@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv('GITHUB_WORKSPACE', '/fake/workspace')
    monkeypatch.setenv('COMPONENTS_NAMESPACE', 'test_ns')
    monkeypatch.setenv('COMPONENTS', 'comp1;comp2')
    monkeypatch.setenv('COMPONENT_VERSION', 'v1.0.0')
    monkeypatch.setenv('REPOSITORY_URL', 'https://fake.repo.url')
    monkeypatch.setenv('COMMIT_SHA', 'a' * 40)
    monkeypatch.setenv('COMPONENT_NAME', 'fake_component')

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
            # Empty string should result in no components
            ("", []),
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
