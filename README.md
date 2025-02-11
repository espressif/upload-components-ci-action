# GitHub Action to upload ESP-IDF components to the component registry

This action uploads [ESP-IDF](https://github.com/espressif/esp-idf) components from a GitHub repository
to [Espressif Component Registry](https://components.espressif.com).

## Usage

This action can be used to upload one or more components to a given `namespace` in the registry.
The action requires `api_token`, `namespace` and `components` inputs to be set.

### Handling versions

If the version in the manifest file is not already in the registry, this action will upload it,
if it is already in the registry, the action will skip the upload silently.
Every version of the component can be uploaded to the registry only once and cannot be replaced.

It is recommended to change the version in the manifest only when it's ready to be published.
An alternative supported workflow is to set parameter `skip_pre_release` to `true`
and use [pre-release](https://semver.org/#spec-item-9) versions (like `1.0.0-dev`) during development
and then change the version to a stable (like `1.0.0`) for release.

If the version of the component is not specified in the manifest file, you can use the `version` parameter.
It must be a valid [component version](https://docs.espressif.com/projects/idf-component-manager/en/latest/reference/versioning.html) optionally prefixed with the character "v".
I.e. versions formatted like `v1.2.3` or `1.2.3` are supported.

### Example workflows

#### Uploading one component in with the version in the `idf_component.yml` file

To upload a component named `my_component` from the root of the repository,
add the following workflow to the `.github/workflows/upload_component.yml` file.

```yaml
name: Push component to https://components.espressif.com
on:
  push:
jobs:
  upload_components:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: "recursive"
      - name: Upload component to the component registry
        uses: espressif/upload-components-ci-action@v2
        with:
          components: "my_component: . " # component_name: directory
          namespace: "espressif"
          api_token: ${{ secrets.IDF_COMPONENT_API_TOKEN }}
```

#### Uploading one component with the version from the git tag

To upload components only on tagged commits, add an on-push-tags rule
to the workflow and set `version` input to `${{ github.ref_name }}`.

```yaml
name: Push component to https://components.espressif.com
on:
  push:
    tags:
      - v*
jobs:
  upload_components:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: "recursive"
      - name: Upload component to the component registry
        uses: espressif/upload-components-ci-action@v2
        with:
          components: |
            my_component: .
          version: ${{ github.ref_name }}
          namespace: "espressif"
          api_token: ${{ secrets.IDF_COMPONENT_API_TOKEN }}
```

#### Uploading multiple components from the current repository

If you want to upload multiple components from the same repository, you can specify the `;` or new-line separated list of components in the `components` parameter.
The component should be specified as `component_name:relative/directory_name` pairs.
If the desired component name matches the directory name, you can omit the component name.

i.e. `my_super_component:components/my_component` will upload the component from the `components/my_component` directory with the name `my_super_component`
and `components/another_component` will upload the component from the `components/another_component` directory with the name `another_component`.

```yaml
name: Push components to https://components.espressif.com
on:
  push:
    branches:
      - main
jobs:
  upload_components:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: "recursive"
      - name: Upload components to the component registry
        uses: espressif/upload-components-ci-action@v2
        with:
          components: |
            my_super_component:components/my_component
            components/another_component
          namespace: "espressif"
          api_token: ${{ secrets.IDF_COMPONENT_API_TOKEN }}
```

#### Uploading a component through a workflow from a different repository

```yaml
name: Push component to https://components.espressif.com
on:
  push:
    branches:
      - main
jobs:
  upload_components:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          submodules: "recursive"
          repository: "another/repository"
      - name: Save information about repository to the github environment
        run:
          echo "GITHUB_REPOSITORY_URL=`git config --get remote.origin.url`" >> "$GITHUB_ENV";
          echo "GITHUB_COMMIT_SHA=`git rev-parse HEAD`" >> "$GITHUB_ENV";
      - name: Upload components to the component registry
        uses: espressif/upload-components-ci-action@v2
        with:
          name: "example"
          namespace: "espressif"
          api_token: ${{ secrets.IDF_COMPONENT_API_TOKEN }}
          repository_url: ${{ env.GITHUB_REPOSITORY_URL }}
          commit_sha: ${{ env.GITHUB_COMMIT_SHA }}
```

## Parameters

| Input            | Optional | Default                           | Description                                                                                                                                                                                                                                               |
| ---------------- | -------- | --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| api_token        | ❌       |                                   | API Token for the component registry                                                                                                                                                                                                                      |
| namespace        | ❌       |                                   | Component namespace                                                                                                                                                                                                                                       |
| components       | ❌       |                                   | Semicolon or new-line separated list of `component_name:relative/path` pairs. If the desired component name in the registry matches the directory name, the component name can be omitted. For a component in the root of the repo, the name is required. |
| version          | ✔        |                                   | Version of the components, if not specified in the manifest. Should be a [semver](https://semver.org/) like `1.2.3` or `v1.2.3`. The version will be applied to all components.                                                                           |
| skip_pre_release | ✔        | False                             | Set this flag to `true`, `t`, `yes` or `1` to skip [pre-release](https://semver.org/#spec-item-9) versions.                                                                                                                                               |
| dry_run          | ✔        | False                             | Set this flag to `true`, `t`, `yes` or `1` to upload a component for validation only without creating a version in the registry.                                                                                                                          |
| registry_url     | ✔        | https://components.espressif.com/ | IDF Component registry URL                                                                                                                                                                                                                                |
| repository_url   | ✔        | Current working repository        | URL of the repository where component is located. Set to empty string if you don't want to send the information about the repository.                                                                                                                     |
| commit_sha       | ✔        | Current commit SHA                | Git commit SHA of the component version. Set to empty string if you don't want to send the information about the repository.                                                                                                                              |
