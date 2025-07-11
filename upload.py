#! /usr/bin/env python

import os
import random
import re
import string
import subprocess
import sys

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path

import requests

from idf_component_tools.constants import MANIFEST_FILENAME
from ruamel.yaml import YAML
from ruamel.yaml import YAMLError


class UntaggedCommit(Exception):
    pass


class FatalError(Exception):
    pass


class MissingAuthConfigurationError(Exception):
    """Raised when no valid authentication method (api_token or OIDC) is configured."""

    pass


@dataclass
class Component:
    name: str | None
    path: str


def getenv_bool(var_name: str, default: bool = False) -> bool:
    value = os.getenv(var_name, '').lower().strip()
    return value in ['true', 't', 'yes', '1'] or default


def setup_environment_variables():
    """
    Set environment variables required for the 'compote component upload' command.
    """
    os.environ['IDF_COMPONENT_API_TIMEOUT'] = '1800'


def split_component_str(component_str: str) -> Component:
    """
    Split component string into name and path.
    """

    component = component_str.strip()

    if ':' not in component_str:
        return Component(name=None, path=component)

    name, path = component_str.split(':', maxsplit=1)
    return Component(name=name.strip(), path=path.strip())


def parse_legacy_inputs() -> list[Component] | None:
    """
    Parse legacy v1 inputs (name and directories) for backward compatibility.
    Returns None if no legacy inputs are found.
    """
    # Handle legacy 'name' input for single component in root
    component_name = os.getenv('COMPONENT_NAME')

    # Handle legacy 'directories' input for multiple components
    directories_str = os.getenv('COMPONENT_DIRECTORIES')

    if component_name and not directories_str:
        # v1 single component in root scenario
        return [Component(name=component_name, path='.')]

    if directories_str and not component_name:
        # v1 multiple directories scenario (semicolon-separated only)
        return [Component(name=None, path=dir.strip()) for dir in directories_str.split(';') if dir.strip()]

    return None


def validate_input_precedence():
    """
    Validate input precedence and warn about conflicting inputs.
    """
    has_new_format = bool(os.getenv('COMPONENTS'))
    has_legacy_name = bool(os.getenv('COMPONENT_NAME'))
    has_legacy_dirs = bool(os.getenv('COMPONENT_DIRECTORIES'))

    if has_new_format and (has_legacy_name or has_legacy_dirs):
        print("WARNING: Both v2 'components' and legacy v1 inputs detected.")
        print("Using v2 'components' input. Legacy inputs will be ignored.")

    if has_legacy_name and has_legacy_dirs:
        raise FatalError(
            "Cannot use both 'name' and 'directories' legacy inputs simultaneously. "
            "Use 'name' for single component in root, or 'directories' for multiple components."
        )


def provide_migration_guidance():
    """
    Provide helpful migration guidance for common v1 to v2 issues.
    """
    component_name = os.getenv('COMPONENT_NAME')
    directories = os.getenv('COMPONENT_DIRECTORIES')

    if component_name or directories:
        print('INFO: Detected legacy v1 inputs. Consider migrating to v2 format:')
        if component_name:
            print(f"  v1: name: '{component_name}'")
            print(f"  v2: components: '{component_name}:.'")
        if directories:
            print(f"  v1: directories: '{directories}'")
            dirs_list = [d.strip() for d in directories.split(';') if d.strip()]
            v2_format = '\n'.join([f'    {d}' for d in dirs_list])
            print(f'  v2: components: |\n{v2_format}')
        print('  See migration guide: https://github.com/espressif/upload-components-ci-action#upgrading-from-v1-to-v2')


def parse_components_input() -> list[Component]:
    """
    Parse components input with backward compatibility for v1 inputs.
    """
    # Try new v2 format first
    components_str = os.getenv('COMPONENTS')
    if components_str:
        return [split_component_str(component) for component in re.split('[;\n]', components_str) if component.strip()]

    # Fall back to legacy v1 inputs
    legacy_components = parse_legacy_inputs()
    if legacy_components:
        return legacy_components

    # If neither new nor legacy inputs are provided, raise an error
    raise FatalError("No components specified. Use 'components' input or legacy 'name'/'directories' inputs.")


def get_oidc_token() -> str:
    github_oidc_url = os.getenv('ACTIONS_ID_TOKEN_REQUEST_URL')
    github_token_request = os.getenv('ACTIONS_ID_TOKEN_REQUEST_TOKEN')
    registry_url = os.getenv('IDF_COMPONENT_REGISTRY_URL') or 'https://components.espressif.com'

    if not github_oidc_url or not github_token_request:
        raise MissingAuthConfigurationError

    try:
        response = requests.get(
            f'{github_oidc_url}',
            headers={'Authorization': f'Bearer {github_token_request}'},
            timeout=5,
            params={'audience': registry_url},
        )
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        raise FatalError('Failed to fetch OIDC token due to a request error') from e

    oidc_token: str = response.json().get('value')

    if not oidc_token:
        raise FatalError('Failed to receive an OIDC token.')

    return oidc_token


def upload_arguments() -> dict[str, str | None]:
    """
    Prepare arguments for the 'compote component upload' command.
    Returns a dictionary with the arguments.
    For flags without values, the value is set to None.
    """

    upload_args = {
        'allow-existing': None,
        'namespace': os.getenv('COMPONENTS_NAMESPACE', 'espressif'),
    }

    if getenv_bool('SKIP_PRE_RELEASE'):
        upload_args['skip-pre-release'] = None

    if getenv_bool('DRY_RUN'):
        upload_args['dry-run'] = None

    repository_url = os.getenv('REPOSITORY_URL')
    if repository_url:
        upload_args['repository'] = repository_url

    commit_sha = os.getenv('COMMIT_SHA')
    if commit_sha:
        upload_args['commit-sha'] = commit_sha

    version = os.getenv('COMPONENT_VERSION')

    if version:
        version = version.strip().lower()
        upload_args['version'] = get_version_from_git() if version == 'git' else version

    return upload_args


def args_to_list(args: dict[str, str | None]) -> list[str]:
    """
    Convert upload arguments to a string suitable for command line execution.
    """
    args_list = []
    for key, value in args.items():
        if value is None:
            args_list.append(f'--{key}')
        else:
            args_list.extend([f'--{key}', value])
    return args_list


def get_version_from_git() -> str:
    subprocess.run(['git', 'fetch', '--force', '--tags'], check=False)
    result = subprocess.run(['git', 'describe', '--exact-match'], capture_output=True, check=False)

    if result.returncode != 0:
        raise UntaggedCommit("Version set to 'git', but commit not tagged. Skipping upload.")

    return str(result.stdout).strip().replace('v', '')


MOCK_VERSION = f'1000.1000.1000-mock.{"".join(random.choices(string.ascii_lowercase, k=8))}'  # noqa: S311


def mock_version_if_not_provided(args: dict[str, str | None], component_full_path: Path) -> dict[str, str | None]:
    """
    Returns a new args dict with a mock version set if needed.
    """
    new_args = deepcopy(args)

    # Check input of the GitHub Action
    if args.get('version') is not None:
        return new_args

    manifest_path = component_full_path / MANIFEST_FILENAME
    # Even if the manifest file does not exist, mock the version
    if not manifest_path.is_file():
        new_args['version'] = MOCK_VERSION
        return new_args

    yaml = YAML()
    # Check if version is already set in manifest
    try:
        content = yaml.load(manifest_path)
    except YAMLError:
        new_args['version'] = MOCK_VERSION
        return new_args

    if not content or not content.get('version'):
        new_args['version'] = MOCK_VERSION

    return new_args


def upload_components(
    components: list[Component],
    workspace_path: Path,
    upload_args: dict[str, str | None],
) -> None:
    failed_components = []

    for component in components:
        args = upload_args.copy()
        component_full_path = workspace_path / component.path

        if component.name is None:
            if component_full_path == workspace_path:
                raise FatalError('Specify component name for the component in the root of the repo.')

            component_name = component_full_path.name

        else:
            component_name = component.name

        args['project-dir'] = component_full_path.as_posix()
        args['name'] = component_name

        if 'repository' in args and 'commit-sha' in args:
            args['repository-path'] = component.path

        if getenv_bool('DRY_RUN'):
            args = mock_version_if_not_provided(args, component_full_path)

        command = ['compote', 'component', 'upload'] + args_to_list(args)
        print(f'Executing command: {" ".join(command)}')
        result = subprocess.run(command, check=False).returncode

        if result != 0:
            failed_components.append(component_name)

    if failed_components:
        raise FatalError(f'Failed to upload components: {", ".join(failed_components)}')


def ensure_token():
    if getenv_bool('DRY_RUN'):
        return

    if os.getenv('IDF_COMPONENT_API_TOKEN'):
        print('Using ESP Component Registry token.')
        return

    try:
        os.environ['IDF_COMPONENT_API_TOKEN'] = get_oidc_token()
        print('Using GitHub OIDC token.')
    except MissingAuthConfigurationError as e:
        raise FatalError(
            'Failed to authenticate: no valid token provided.\n'
            "- If you intended to use the ESP Component Registry token, please set the 'api_token' "
            'input in your workflow.\n'
            '- If you intended to use GitHub OIDC for authentication, ensure that your workflow has '
            'the required permissions:\n'
            '  permissions:\n'
            '    id-token: write\n'
            '\n'
            'Refer to the documentation for proper setup of authentication methods.'
        ) from e


def main() -> None:
    setup_environment_variables()

    # Validate input precedence and provide migration guidance
    validate_input_precedence()
    provide_migration_guidance()

    workspace_path = Path(os.environ['GITHUB_WORKSPACE'])

    components = parse_components_input()

    try:
        upload_args = upload_arguments()
    except UntaggedCommit as e:
        print(e)
        return

    try:
        ensure_token()
        upload_components(
            workspace_path=workspace_path,
            components=components,
            upload_args=upload_args,
        )
    except FatalError as e:
        print(e)
        sys.exit(1)


if __name__ == '__main__':
    main()
