#! /usr/bin/env python

import os
import subprocess
import sys
from pathlib import Path


class UntaggedCommitException(Exception):
    pass


class FatalException(Exception):
    pass


def getenv_bool(var_name: str, default: bool = False) -> bool:
    value = os.getenv(var_name, "").lower().strip()
    return value in ["true", "t", "yes", "1"] or default


def setup_environment_variables():
    deprecated_url = os.getenv("DEPRECATED_IDF_COMPONENT_REGISTRY_URL", "")
    registry_url = os.getenv("IDF_COMPONENT_REGISTRY_URL", "")

    if deprecated_url:
        if not registry_url:
            os.environ["IDF_COMPONENT_REGISTRY_URL"] = deprecated_url
        else:
            print(
                "NOTICE: Both 'service_url' and 'registry_url' inputs are specified. 'registry_url' will be used."
            )

    os.environ["IDF_COMPONENT_API_TIMEOUT"] = "1800"


def parse_directories() -> list[str]:
    dirs_str = os.getenv("COMPONENTS_DIRECTORIES", ".")
    return [directory.strip() for directory in dirs_str.split(";")]


def upload_arguments() -> dict[str, str | None]:
    """
    Prepare arguments for the 'compote component upload' command.
    Returns a dictionary with the arguments.
    For flags without values, the value is set to None.
    """

    upload_args = {
        "allow-existing": None,
        "namespace": os.getenv("COMPONENTS_NAMESPACE", "espressif"),
    }

    if getenv_bool("SKIP_PRE_RELEASE"):
        upload_args["skip-pre-release"] = None

    if getenv_bool("DRY_RUN"):
        upload_args["dry-run"] = None

    repo_url = os.getenv("REPOSITORY_URL")
    if repo_url:
        upload_args["repository"] = repo_url

    commit_sha = os.getenv("COMMIT_SHA")
    if commit_sha:
        upload_args["commit-sha"] = commit_sha

    version = os.getenv("COMPONENT_VERSION")

    if version:
        version = version.strip().lower()
        upload_args["version"] = get_version_from_git() if version == "git" else version

    return upload_args


def args_to_list(args: dict[str, str | None]) -> list[str]:
    """
    Convert upload arguments to a string suitable for command line execution.
    """
    args_list = []
    for key, value in args.items():
        if value is None:
            args_list.append(f"--{key}")
        else:
            args_list.extend([f"--{key}", value])
    return args_list


def get_version_from_git() -> str:
    subprocess.run(["git", "fetch", "--force", "--tags"])
    result = subprocess.run(["git", "describe", "--exact-match"], capture_output=True)

    if result.returncode != 0:
        raise UntaggedCommitException(
            "Version set to 'git', but commit not tagged. Skipping upload."
        )

    return result.stdout.strip().replace("v", "")


def process_directories(
    directories: list[str],
    upload_args: list[str],
) -> list[str]:
    failed_components = []

    github_workspace = Path(os.environ["GITHUB_WORKSPACE"])

    for component_dir in directories:
        args = upload_args.copy()

        path = github_workspace / component_dir

        component_name_env = os.getenv("COMPONENT_NAME")
        if len(directories) == 1 and component_dir == "." and not component_name_env:
            raise FatalException(
                "Specify component name or directory for single component upload."
            )

        if Path(component_dir) == github_workspace:
            component_name = component_name_env
        else:
            component_name = Path(path).resolve().name

        args["project-dir"] = path
        args["name"] = component_name

        result = subprocess.run(
            ["compote", "component", "upload"] + args_to_list(args)
        ).returncode

        if result != 0:
            failed_components.append(component_name)

    return failed_components


def main() -> None:
    setup_environment_variables()
    directories = parse_directories()

    try:
        upload_args = upload_arguments()
    except UntaggedCommitException as e:
        print(e)
        return

    try:
        failed_components = process_directories(
            directories,
            upload_args,
        )
    except FatalException as e:
        print(e)
        sys.exit(1)

    if failed_components:
        print(f"Failed components: {', '.join(failed_components)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
