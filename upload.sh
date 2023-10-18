#!/bin/bash

IFS=';' read -ra DIRECTORIES <<<"$(echo -e "${COMPONENTS_DIRECTORIES:-.}" | tr -d '[:space:]')"
NAMESPACE=${COMPONENTS_NAMESPACE:-espressif}
UPLOAD_ARGUMENTS=("--allow-existing" "--namespace=${NAMESPACE}" )
if [[ "${SKIP_PRE_RELEASE,,}" =~ ^(true|t|yes|1)$ ]]; then
    UPLOAD_ARGUMENTS+=("--skip-pre-release")
fi
if [[ "${DRY_RUN,,}" =~ ^(true|t|yes|1)$ ]]; then
    UPLOAD_ARGUMENTS+=("--dry-run")
fi

if [ -n "$COMPONENT_VERSION" ]; then
    if [ "$COMPONENT_VERSION" == "git" ]; then
        git fetch --force --tags
        if ! git describe --exact-match; then
            echo "Version is set to 'git', but the current commit is not tagged. Skipping the upload."
            exit 0
        fi
    fi
    UPLOAD_ARGUMENTS+=("--version=${COMPONENT_VERSION//v/}")
fi

NUMBER_OF_DIRECTORIES="${#DIRECTORIES[@]}"
echo "Processing $NUMBER_OF_DIRECTORIES components"

for ITEM in "${DIRECTORIES[@]}"; do
    FULL_PATH="${GITHUB_WORKSPACE?}/${ITEM}"
    if [ "$NUMBER_OF_DIRECTORIES" -eq "1" ] && [ "${ITEM}" == "." ] && [ -z "${COMPONENT_NAME}" ]; then
        echo "To upload a single component, either specify the component name or directory, which will be used as the component name"
        exit 1
    fi

    if [ "${ITEM}" == "." ]; then
        NAME=${COMPONENT_NAME?"Name is required to upload a component from the root of the repository."}
    else
        NAME=$(basename "$(realpath "${FULL_PATH}")")
    fi

    echo "Processing component \"$NAME\" at $ITEM"
    compote component upload "${UPLOAD_ARGUMENTS[@]}" --project-dir="${FULL_PATH}" --name="${NAME}"

    EXIT_CODE=$?
    if [ "$EXIT_CODE" -ne "0" ]; then
        echo "An error occurred while uploading the new version of ${NAMESPACE}/${NAME}."
        exit 1
    fi
done
