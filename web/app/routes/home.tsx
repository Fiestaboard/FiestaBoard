/**
 * Route module for `/`. Re-exports the page component from the legacy
 * `src/app/page.tsx` location. We kept the source under `src/app/` to
 * minimize churn in this PR — the `app/routes/` files are thin RR7
 * adapters around the canonical implementations.
 */
export { default } from "@/app/page";
