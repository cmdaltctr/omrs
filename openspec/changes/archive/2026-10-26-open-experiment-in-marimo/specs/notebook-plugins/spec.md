## ADDED Requirements

### Requirement: The shipped manifest is found in an installed application

The marimo manifest SHALL ship inside the `omrs` package as package data and SHALL be found through the package resources, both in a source checkout and in an installed wheel. It SHALL stay data only. The plugin list SHALL name the path of each shipped manifest. The starter notebook and the plugin README SHALL stay outside the wheel.

#### Scenario: Installed wheel

- **WHEN** the application runs from a built wheel
- **THEN** the shipped manifest path exists, parses as a valid manifest and is an approved manifest for registration

#### Scenario: Wheel contents

- **WHEN** the wheel is built
- **THEN** it holds the marimo manifest below the `omrs` package
- **AND** it holds no file from the top-level `plugins/` folder

### Requirement: An editor launch can use a project environment

An editor launch SHALL be able to run its notebook kernel in a given project virtual environment when the manifest declares the `project_environment` capability. The host SHALL supply the environment path in the private launch configuration, SHALL keep the registered executable and the manifest launch arguments unchanged, and SHALL mark the environment as not writable. A launch that asks for a project environment SHALL be refused when the manifest does not declare the capability.

#### Scenario: Launch configuration

- **WHEN** the host launches an editor with a project environment
- **THEN** the private launch configuration names the absolute environment path, marks it not writable and turns off automatic `.env` loading
- **AND** the argv is the registered executable followed by the manifest launch arguments

#### Scenario: Manifest without the capability

- **WHEN** a launch asks for a project environment and the manifest does not declare `project_environment`
- **THEN** the launch is refused and no process starts

## MODIFIED Requirements

### Requirement: Plugin manifests are constrained data
A plugin manifest SHALL declare its identity, schema/version, capabilities, executable reference, tested compatibility range, and supported structured launch/probe arguments. When a manifest declares a structured conversion recipe, the recipe's only substitutions SHALL be a source path and an output path that the host sets. Registration and enabling SHALL require explicit trust. Manifests SHALL not supply shell strings, Python hooks, credentials, or installation commands.

#### Scenario: Manifest attempts executable hooks
- **WHEN** a manifest requests a shell command, dynamic Python import, unsupported substitution, or installer action
- **THEN** registration SHALL reject it without launching a process

#### Scenario: Manifest is approved
- **WHEN** the operator approves a valid manifest and executable
- **THEN** the registration SHALL retain their identity and approval
- **AND** a changed manifest or executable reference SHALL require revalidation and approval

#### Scenario: Conversion recipe uses a launch substitution
- **WHEN** a manifest's conversion recipe uses a substitution other than the source path and the output path
- **THEN** registration SHALL reject the manifest
