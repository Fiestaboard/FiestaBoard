/**
 * Compat shim for `next/dynamic` on React Router v7 + Vite.
 *
 * Three call sites exist in the codebase (schedule/page.tsx,
 * pages/page.tsx, wizard-provider.tsx). The `next/dynamic` signature is:
 *
 *   dynamic(() => import("./Foo"), { loading: Spinner, ssr: false })
 *
 * Translation:
 *  - `() => import(...)` → React.lazy
 *  - `loading: Component` → fallback wrapped in <Suspense>
 *  - `ssr: false` → ignored (RR7 SPA mode has no SSR anyway)
 *
 * Default exports vs named exports: next/dynamic expects the loader to
 * resolve to either a module with `default` or a callable. We normalize
 * both shapes.
 */
import { type ComponentType, lazy, Suspense } from "react";

type DynamicOptions = {
  loading?: ComponentType;
  ssr?: boolean;
};

type Loader<P> = () => Promise<ComponentType<P> | { default: ComponentType<P> }>;

export default function dynamic<P extends object>(loader: Loader<P>, options: DynamicOptions = {}): ComponentType<P> {
  const Loading = options.loading;
  const Lazy = lazy(async () => {
    const mod = await loader();
    if (mod && typeof mod === "object" && "default" in mod) {
      return mod as { default: ComponentType<P> };
    }
    return { default: mod as ComponentType<P> };
  });
  return function DynamicComponent(props: P) {
    return (
      <Suspense fallback={Loading ? <Loading /> : null}>
        <Lazy {...props} />
      </Suspense>
    );
  };
}
