import { useMemo } from "react";
import { useLocation, useNavigate, useParams as useRRParams, useSearchParams as useRRSearchParams } from "react-router";

/**
 * Mirrors the Next.js navigation options this codebase already passes.
 * `scroll: false` maps to React Router's `preventScrollReset`, which is
 * what keeps <ScrollRestoration> (mounted in root.tsx) from yanking the
 * viewport back to the top on an in-page URL update.
 */
export type NavigateOptions = {
  scroll?: boolean;
};

type Router = {
  push: (href: string, options?: NavigateOptions) => void;
  replace: (href: string, options?: NavigateOptions) => void;
  back: () => void;
  forward: () => void;
};

export function useRouter(): Router {
  const navigate = useNavigate();
  return useMemo<Router>(
    () => ({
      push: (href, options) => navigate(href, { preventScrollReset: options?.scroll === false }),
      replace: (href, options) => navigate(href, { replace: true, preventScrollReset: options?.scroll === false }),
      back: () => navigate(-1),
      forward: () => navigate(1),
    }),
    [navigate],
  );
}

export function usePathname(): string {
  return useLocation().pathname;
}

// Mirrors Next's `useSearchParams()` shape (returns just the read-only
// params, not RR7's `[params, setParams]` tuple). Call sites that need
// to *write* search params should use `useNavigate()` directly.
export function useSearchParams(): URLSearchParams {
  const [params] = useRRSearchParams();
  return params;
}

export function useParams<T extends Record<string, string | undefined> = Record<string, string | undefined>>(): T {
  return useRRParams() as T;
}
