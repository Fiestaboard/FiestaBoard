import { useMemo } from "react";
import { useLocation, useNavigate, useParams as useRRParams, useSearchParams as useRRSearchParams } from "react-router";

type Router = {
  push: (href: string) => void;
  replace: (href: string) => void;
  back: () => void;
  forward: () => void;
};

export function useRouter(): Router {
  const navigate = useNavigate();
  return useMemo<Router>(
    () => ({
      push: (href) => navigate(href),
      replace: (href) => navigate(href, { replace: true }),
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
