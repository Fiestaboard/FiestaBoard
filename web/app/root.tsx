/**
 * React Router v7 root module — owns the document shell that pre-RR7
 * lived in a Next.js `app/layout.tsx`.
 *
 * Renders the document shell, mounts the provider tree, and exposes
 * `<Outlet />` for nested routes. Localized `<title>` and
 * `<meta description>` are kept in sync via a `useEffect` on the locale.
 *
 * HA Ingress support: nginx sub_filter rewrites the absolute asset
 * URLs in served bodies and the inlined React Router `"basename":"/"`
 * hydration literal (entrypoint.sh::configure_ingress_path_rewrite);
 * the SPA reads that basename back at runtime to prefix API calls
 * (web/src/lib/base-path.ts). No `<base href>` is involved.
 */
import "./globals.css";

import { Box, PageIconGradientDefs } from "@fiestaboard/ui";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Links, Meta, Outlet, Scripts, ScrollRestoration } from "react-router";

import { BootGate } from "@/components/boot-gate";
import { GlobalAiChatDrawer } from "@/components/global-ai-chat-drawer";
import { GlobalAiPanelProvider } from "@/components/global-ai-panel-context";
import { InstallPrompt } from "@/components/install-prompt";
import { MainContent } from "@/components/main-content";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { PageEditorBridgeProvider } from "@/components/page-editor-bridge-context";
import { PageFadeWrapper } from "@/components/page-fade-wrapper";
import { Providers } from "@/components/providers";
import { ReduceMotionApplier } from "@/components/reduce-motion-applier";
import { ScheduleEditorBridgeProvider } from "@/components/schedule-editor-bridge-context";
import { SkipToContent } from "@/components/skip-to-content";
import { ThemeColorMeta } from "@/components/theme-color-meta";
import { Toaster } from "@/components/ui/sonner";
import { WizardProvider } from "@/components/wizard-provider";
import i18n from "@/i18n/i18next";
import { appUrl } from "@/lib/base-path";
import { readCookieString, shouldShowPride } from "@/lib/pride";

import type { Route } from "./+types/root";

// Module-load side effect: ensure i18next is initialized before any
// `useTranslation` runs anywhere in the tree.
void i18n;

// Classic <script> injected into <head> so it executes during document
// parsing, before the deferred module bundle. vite.config.ts's
// `experimental.renderBuiltUrl` routes every JS-hosted asset URL through
// this global, which prepends the React Router basename under HA Ingress
// (nginx rewrites the inlined `"basename":"/"` hydration literal — see
// web/src/lib/base-path.ts). The basename global is read lazily at call
// time, so script ordering relative to the hydration context script
// doesn't matter. Filenames arrive relative ("assets/chunk.js").
const ASSET_URL_HELPER = `window.__fbAssetUrl=function(f){var c=window.__reactRouterContext,b=c&&c.basename;return((!b||b==="/")?"":b.replace(/\\/+$/,""))+"/"+f};`;

// appUrl() wrapping matters for the CLIENT-side <Links /> re-render: at
// prerender time `window` is undefined so these emit the plain absolute
// paths into the HTML (which nginx sub_filter rewrites under Ingress),
// but when React re-renders Links in the browser the hrefs are computed
// fresh — without the runtime prefix they'd revert to the host root and
// 404 inside Home Assistant. (There is deliberately no body-level
// backtick sub_filter for /icons/ etc. — see entrypoint.sh — because it
// would double-prefix these appUrl() literals.)
export const links: Route.LinksFunction = () => [
  { rel: "icon", href: appUrl("/favicon.ico"), sizes: "any" },
  { rel: "icon", href: appUrl("/icons/favicon-32x32.png"), type: "image/png", sizes: "32x32" },
  { rel: "apple-touch-icon", href: appUrl("/icons/apple-touch-icon.png") },
  { rel: "manifest", href: appUrl("/manifest.json") },
];

export const meta: Route.MetaFunction = () => [
  { charSet: "utf-8" },
  { name: "viewport", content: "width=device-width, initial-scale=1, viewport-fit=cover" },
  // Locale-aware title and description are set client-side in
  // `RootBody` below — these defaults exist so the initial HTML render
  // and any prerender pass include something sensible.
  { title: "FiestaBoard" },
  { name: "description", content: "Open-source platform for controlling split-flap displays" },
  { name: "theme-color", content: "#fafafa", media: "(prefers-color-scheme: light)" },
  { name: "theme-color", content: "#0a0a0a", media: "(prefers-color-scheme: dark)" },
];

export function Layout({ children }: { children: React.ReactNode }) {
  // Server-side this would honor a request-bound locale; in SPA mode
  // we lean on i18next-browser-languagedetector and patch `<html lang>`
  // imperatively in `RootBody` once it boots.
  //
  // `pride-month` gates the rainbow logo, dark sidebar base, WebGL aurora,
  // and click-to-celebrate confetti via CSS rules in `globals.css`. The
  // class lands on `<html>` BEFORE the theme hook adds `light`/`dark` —
  // navigation tests compare html.class strings across theme toggles and
  // depend on that insertion order (see `web/tests/navigation.spec.ts:72-101`).
  //
  // The initial className comes from useState (FOUC-free first paint in
  // June). In SPA mode the prerender runs with `typeof document === "undefined"`
  // so the `hide_festive_months` cookie can't be read at build time —
  // `shouldShowPride` falls back to "active" in June. `suppressHydrationWarning`
  // (kept for the theme hook's classList mutation) means React won't reconcile
  // the `<html>` className across re-renders, so a re-render alone can't
  // remove the class on the client. The effect below imperatively toggles
  // it via classList — that way it composes with the theme hook's
  // `dark`/`light` class without clobbering them.
  const [initialIsPrideMonth] = useState(() => shouldShowPride(new Date(), readCookieString()));
  useEffect(() => {
    const active = shouldShowPride(new Date(), readCookieString());
    document.documentElement.classList.toggle("pride-month", active);
  }, []);
  return (
    <html lang="en" className={initialIsPrideMonth ? "pride-month" : undefined} suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: ASSET_URL_HELPER }} />
        <Meta />
        <Links />
      </head>
      <body className="font-sans antialiased">
        {children}
        <ScrollRestoration />
        <Scripts />
      </body>
    </html>
  );
}

export default function Root() {
  return <RootBody />;
}

function RootBody() {
  const { i18n: rrtI18n, t } = useTranslation();

  // Keep `<html lang>` and `<title>` / description in sync with the
  // active locale. WCAG 2.2 AA: 2.4.2 Page Titled, 3.1.1 Language.
  useEffect(() => {
    const sync = () => {
      const lang = rrtI18n.language || "en";
      document.documentElement.lang = lang;
      const titleKey = t("metadata.appTitle");
      if (titleKey && titleKey !== "metadata.appTitle") {
        document.title = titleKey;
      }
      const descKey = t("metadata.appDescription");
      if (descKey && descKey !== "metadata.appDescription") {
        let meta = document.querySelector('meta[name="description"]');
        if (!meta) {
          meta = document.createElement("meta");
          meta.setAttribute("name", "description");
          document.head.appendChild(meta);
        }
        meta.setAttribute("content", descKey);
      }
    };
    sync();
    rrtI18n.on("languageChanged", sync);
    return () => {
      rrtI18n.off("languageChanged", sync);
    };
  }, [rrtI18n, t]);

  return (
    <>
      <PageIconGradientDefs />
      <Providers>
        <ThemeColorMeta />
        <ReduceMotionApplier />
        <BootGate>
          <ScheduleEditorBridgeProvider>
            <PageEditorBridgeProvider>
              <GlobalAiPanelProvider>
                <WizardProvider>
                  <SkipToContent />
                  <NavigationSidebar />
                  <GlobalAiChatDrawer />
                  <MainContent>
                    <PageFadeWrapper>
                      <Outlet />
                    </PageFadeWrapper>
                  </MainContent>
                  <Toaster />
                  <InstallPrompt />
                </WizardProvider>
              </GlobalAiPanelProvider>
            </PageEditorBridgeProvider>
          </ScheduleEditorBridgeProvider>
        </BootGate>
      </Providers>
    </>
  );
}

/**
 * Rendered during client-side hydration when the user lands on a
 * route whose chunks haven't loaded yet. The `Layout` export above
 * already provides the `<html>` / `<head>` / `<body>` shell, so this
 * is just the visible body content.
 */
export function HydrateFallback() {
  return <Box style={{ minHeight: "100vh" }} />;
}
