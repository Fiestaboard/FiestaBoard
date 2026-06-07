/**
 * Compat shim for `next/navigation` on React Router v7.
 *
 * The 19 files in this codebase that import from `next/navigation` keep
 * working unchanged: Vite's `resolve.alias` (see `vite.config.ts`) redirects
 * the import here. Each function exposes the same shape `next/navigation`
 * does — `useRouter().push/replace/back/forward/refresh/prefetch`,
 * `usePathname()`, `useSearchParams()`, `useParams()`.
 *
 * Semantic notes:
 *  - `router.refresh()` is a no-op. Next.js used it to bust server cache
 *    + re-fetch RSC payloads; in a fully-client RR7 SPA there is no server
 *    cache and TanStack Query handles re-fetch. Call sites that did
 *    `router.refresh()` to react to a server-side change should use
 *    `queryClient.invalidateQueries()` instead — but the no-op preserves
 *    behavior for everything that wasn't truly relying on it.
 *  - `router.prefetch()` is a no-op. RR7 has its own prefetching via
 *    `<Link prefetch="intent">` which we expose through `next/link`.
 *  - `useParams()` returns `Record<string, string | undefined>` in RR7,
 *    not `Record<string, string | string[]>` like Next.js. Call sites
 *    that did `params.id as string` keep working; catch-all routes
 *    aren't used in this codebase (verified during migration).
 */
import { useMemo } from "react";
import {
  useLocation,
  useNavigate,
  useParams as useRRParams,
  useSearchParams as useRRSearchParams,
} from "react-router";

type AppRouterInstance = {
  push: (href: string) => void;
  replace: (href: string) => void;
  back: () => void;
  forward: () => void;
  refresh: () => void;
  prefetch: (href: string) => void;
};

export function useRouter(): AppRouterInstance {
  const navigate = useNavigate();
  return useMemo(
    () => ({
      push: (href: string) => {
        navigate(href);
      },
      replace: (href: string) => {
        navigate(href, { replace: true });
      },
      back: () => {
        navigate(-1);
      },
      forward: () => {
        navigate(1);
      },
      refresh: () => {
        // no-op: RR7 doesn't have RSC cache to bust
      },
      prefetch: () => {
        // no-op: RR7 prefetching is per-Link, not router-driven
      },
    }),
    [navigate],
  );
}

export function usePathname(): string {
  return useLocation().pathname;
}

export function useSearchParams(): URLSearchParams {
  const [params] = useRRSearchParams();
  return params;
}

export function useParams<T extends Record<string, string | undefined> = Record<string, string | undefined>>(): T {
  return useRRParams() as T;
}

export function redirect(href: string): never {
  // In Next.js this throws a special error caught by the framework.
  // In RR7 SPA, the legitimate use during render is rare; we navigate
  // imperatively and throw to short-circuit the calling render.
  if (typeof window !== "undefined") {
    window.location.assign(href);
  }
  throw new Error(`REDIRECT:${href}`);
}

export function notFound(): never {
  throw new Response("Not Found", { status: 404 });
}
