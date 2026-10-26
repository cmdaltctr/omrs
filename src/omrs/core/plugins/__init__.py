"""External-tool plugins: constrained manifests, registration and editor supervision.

This package is pure core logic (design D10). It reads manifest and
executable files to hash them, but it never starts a process itself:
composition injects a probe runner and a process launcher from
``omrs.integrations.process_launcher``. It imports no ``subprocess``,
``socket``, ``sqlite3``, web framework or notebook runtime.
"""

from __future__ import annotations

from omrs.core.plugins.editor import (
    ConvertResult,
    EditorSession,
    KernelEnvironment,
    LaunchPlan,
    NotebookEditorSupervisor,
    PluginConsentError,
    PluginLaunchError,
    ProcessLauncher,
    build_launch_plan,
)
from omrs.core.plugins.manifest import (
    CONVERT_SUBSTITUTIONS,
    HOST_CONFIG_CAPABILITIES,
    PROJECT_ENVIRONMENT,
    REQUIRED_LAUNCH_CAPABILITIES,
    SUBSTITUTIONS,
    ConvertRecipe,
    ManifestError,
    PluginManifest,
    parse_manifest,
    parse_version,
)
from omrs.core.plugins.registration import (
    COMPATIBLE,
    INCOMPATIBLE,
    NEEDS_APPROVAL,
    UNAVAILABLE,
    UNCHECKED,
    ExecutableIdentity,
    PluginRegistry,
    PluginState,
    PluginTrustError,
    ProbeOutput,
    ProbeRunner,
    inspect_executable,
)

__all__ = [
    "COMPATIBLE",
    "CONVERT_SUBSTITUTIONS",
    "HOST_CONFIG_CAPABILITIES",
    "INCOMPATIBLE",
    "NEEDS_APPROVAL",
    "PROJECT_ENVIRONMENT",
    "REQUIRED_LAUNCH_CAPABILITIES",
    "SUBSTITUTIONS",
    "UNAVAILABLE",
    "UNCHECKED",
    "ConvertRecipe",
    "ConvertResult",
    "EditorSession",
    "ExecutableIdentity",
    "KernelEnvironment",
    "LaunchPlan",
    "ManifestError",
    "NotebookEditorSupervisor",
    "PluginConsentError",
    "PluginLaunchError",
    "PluginManifest",
    "PluginRegistry",
    "PluginState",
    "PluginTrustError",
    "ProbeOutput",
    "ProbeRunner",
    "ProcessLauncher",
    "build_launch_plan",
    "inspect_executable",
    "parse_manifest",
    "parse_version",
]
