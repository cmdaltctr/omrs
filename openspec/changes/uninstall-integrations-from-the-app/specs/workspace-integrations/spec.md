## ADDED Requirements

### Requirement: An installed entry can be uninstalled from the page

An installed entry that is not a base entry and is not `web` SHALL show Uninstall when the server can uninstall. Uninstall SHALL open a dialog that lists the packages to remove and the packages kept because something else needs them, with Cancel and Uninstall. While the job runs, the card SHALL show progress; after success it SHALL show "Removed, restart to apply" with the restart action. When the server refuses because a setting uses the extra, the card SHALL show the reason and the setting, and no Uninstall and no lasting command. When the extra is in the install receipt and no setting uses it, the card SHALL also show the lasting command without the extra. The card SHALL take its restart state from the entry's `pending_restart`, never from the last job alone.

#### Scenario: Uninstall Chroma

- **WHEN** Chroma is installed and unused, and the user presses Uninstall, then Uninstall in the dialog
- **THEN** the dialog MUST have listed the Chroma packages, and the card MUST show "Removed, restart to apply"

#### Scenario: In use

- **WHEN** `vector_store` is `chroma`
- **THEN** the Chroma card MUST show that `vector_store` uses it, and MUST NOT show Uninstall or the lasting command

#### Scenario: Base entry

- **WHEN** the user opens the Magika or pdf-inspector card
- **THEN** the card MUST NOT show Uninstall

#### Scenario: Extra in the receipt

- **WHEN** the live install is `omrs[web,hybrid]` and the user views the Hybrid search card
- **THEN** the card MUST show Uninstall and the lasting command `uv tool install --reinstall "omrs[web] @ <source>"`

#### Scenario: Removed stays removed after another job

- **WHEN** Chroma was uninstalled in this launch and an install of Azure then succeeded
- **THEN** the Chroma card MUST still show "Removed, restart to apply", and the Azure card MUST show "Installed, restart to use"
