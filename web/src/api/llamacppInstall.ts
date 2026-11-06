/**
 * Typed client for the pinned llama.cpp build that OMRS provisions. Shapes
 * follow `openapi.yaml` (`getLlamacppBuild`, `installLlamacppBuild`). A failed
 * job gives one fixed reason and a plain line, never text from a process.
 */
import type { ApiClient, CallOptions } from "./client";

/** The Linux x86-64 builds a user may pick. macOS arm64 has one build and no choice. */
export type LlamacppFlavour = "cpu" | "cuda";

export type InstallJobState = "idle" | "running" | "succeeded" | "failed";

/** The fixed reasons of a failed install job. */
export type InstallJobReason = "not-supported" | "download-failed" | "file-changed" | "binary-check-failed" | "cuda-device-missing" | "failed";

export interface LlamacppInstallJob {
  state: InstallJobState;
  /** The flavour the job was asked for; `null` for the detected one. */
  flavour: LlamacppFlavour | null;
  /** The last progress line, for example "Downloading <archive name>". */
  line: string | null;
  reason: InstallJobReason | null;
  message: string | null;
}

export interface LlamacppBuild {
  status: "ok";
  /** The pinned build tag, for example `b11941`. */
  build: string;
  /** The flavour that fits this host; `null` when no build is pinned for it. */
  detected: "metal" | LlamacppFlavour | null;
  /** The flavours the user may pick. Empty on macOS and on an unpinned platform. */
  choices: LlamacppFlavour[];
  /** The provisioned `llama-server`; `null` when none is placed. */
  installed_path: string | null;
  job: LlamacppInstallJob;
}

const PATH = "/v1/llamacpp/router/install";

export function getLlamacppBuild(api: ApiClient, options: CallOptions = {}): Promise<LlamacppBuild> {
  return api.request<LlamacppBuild>("GET", PATH, { signal: options.signal });
}

/** Starts the install job. Without a flavour the server takes the detected one. */
export function installLlamacppBuild(api: ApiClient, flavour: LlamacppFlavour | null, options: CallOptions = {}): Promise<LlamacppBuild> {
  return api.request<LlamacppBuild>("POST", PATH, { body: flavour === null ? {} : { flavour }, signal: options.signal });
}
