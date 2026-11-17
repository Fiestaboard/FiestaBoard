// Browser runner entry point. No side effects on import; root owns execution.
export async function runBrowserBatch(config) {
  if (!config?.manifest || typeof config.manifest !== "object") throw new Error("A verified public manifest is required");
  throw new Error("Browser execution is not implemented; no measurement is complete");
}
