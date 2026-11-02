## ADDED Requirements

### Requirement: A local decision model can run as a managed runtime

A `llamacpp` decision model entry SHALL choose `external` or `managed`. A managed entry SHALL run as runtime `decision-<entry name>` under the same lease, adoption, idle-stop and stop rules as the other managed runtimes. Its spec SHALL declare the model file and, for an image entry, the projector file as separate files. It SHALL bind `127.0.0.1` and serve one request at a time.

#### Scenario: Managed image entry starts with both files

- **GIVEN** a managed image entry with a Q8_0 model file and its projector file
- **WHEN** a router first needs it
- **THEN** OMRS SHALL start `llama-server` with the model file and the projector file
- **AND** `GET /v1/runtimes` SHALL list the runtime `decision-<entry name>`

#### Scenario: External entry starts nothing

- **GIVEN** an external entry with an address
- **WHEN** a router needs it
- **THEN** OMRS SHALL start no process and SHALL send requests to that address

### Requirement: A managed decision runtime checks its build

Before it starts a managed decision runtime, OMRS SHALL read the `llama-server` build number and refuse a build below the floor that serves the decision request with images. The refusal SHALL name the build found and the floor.

#### Scenario: Old build

- **GIVEN** a `llama-server` build below the floor
- **WHEN** the runtime would start
- **THEN** it SHALL NOT start and the reason SHALL be `wrong-build`
