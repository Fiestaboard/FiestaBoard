import path from "node:path";

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) throw new Error(`Missing ${name}; see tests/prod-a11y/README.md.`);
  return value;
}

/** No default target: an audit must never silently reach an existing user hub. */
export function readCampaign() {
  if (required("AUDIT_SYNTHETIC_ONLY") !== "yes") {
    throw new Error("AUDIT_SYNTHETIC_ONLY must be yes for a dedicated synthetic-data hub.");
  }
  const baseURL = new URL(required("BASE_URL"));
  const allowedHosts = new Set(["localhost", "127.0.0.1", "[::1]", "host.docker.internal", "fb-dev-hub"]);
  if (
    !["http:", "https:"].includes(baseURL.protocol) ||
    !allowedHosts.has(baseURL.hostname) ||
    baseURL.username ||
    baseURL.password ||
    baseURL.pathname !== "/" ||
    baseURL.search ||
    baseURL.hash
  ) {
    throw new Error("BASE_URL must be a local dedicated hub origin without credentials, path or query.");
  }
  const kind = required("AUDIT_CAMPAIGN");
  if (kind !== "published" && kind !== "candidate") {
    throw new Error("AUDIT_CAMPAIGN must be published or candidate.");
  }
  const image = required("AUDIT_IMAGE");
  if (!/^[a-z0-9./:_-]+@sha256:[a-f0-9]{64}$/.test(image)) {
    throw new Error("AUDIT_IMAGE must contain an immutable sha256 image digest, not only a tag.");
  }
  const sourceSha = required("AUDIT_SOURCE_SHA");
  if (!/^[a-f0-9]{40}$/.test(sourceSha)) throw new Error("AUDIT_SOURCE_SHA must be a full source SHA.");
  const auth = required("AUDIT_AUTH");
  if (auth !== "disabled" && auth !== "authenticated") {
    throw new Error("This route survey requires AUDIT_AUTH=disabled or authenticated.");
  }
  const storageState = process.env.AUDIT_STORAGE_STATE;
  if (auth === "authenticated" && !storageState) {
    throw new Error("Authenticated surveys need a synthetic session in AUDIT_STORAGE_STATE.");
  }
  if (auth === "disabled" && storageState) throw new Error("Do not supply session state for disabled auth.");
  const runId = required("AUDIT_RUN_ID");
  if (!/^prod-a11y-[a-z0-9-]+$/.test(runId)) {
    throw new Error("AUDIT_RUN_ID must start prod-a11y- and contain lowercase letters, digits or hyphens.");
  }
  const artifactRoot = required("AUDIT_ARTIFACT_DIR");
  if (!path.isAbsolute(artifactRoot)) throw new Error("AUDIT_ARTIFACT_DIR must be an absolute mounted path.");
  return {
    baseURL: baseURL.origin,
    kind,
    image,
    sourceSha,
    auth,
    runId,
    dataset: required("AUDIT_DATASET_ID"),
    artifactDir: path.join(artifactRoot, runId),
    storageState,
  };
}

export const campaign = readCampaign();
