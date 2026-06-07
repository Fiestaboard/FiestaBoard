/**
 * React Router v7 root module — replaces `src/app/layout.tsx`.
 *
 * Renders the document shell, mounts the provider tree, and exposes
 * `<Outlet />` for nested routes. Localized `<title>` and
 * `<meta description>` are kept in sync via a `useEffect` on the locale.
 * The HTML `<base href>` is injected by nginx from `X-Ingress-Path` —
 * the browser uses it to resolve all relative asset URLs (Vite emits
 * `./assets/...`), which is how HA Ingress works without any
 * build-time `assetPrefix`.
 */
import "../src/app/globals.css";
import "@fontsource-variable/geist";
import "@fontsource-variable/geist-mono";

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

import type { Route } from "./+types/root";

// Module-load side effect: ensure i18next is initialized before any
// `useTranslation` runs anywhere in the tree.
void i18n;

export const links: Route.LinksFunction = () => [
  { rel: "icon", href: "/favicon.ico", sizes: "any" },
  { rel: "icon", href: "/icons/favicon-32x32.png", type: "image/png", sizes: "32x32" },
  { rel: "apple-touch-icon", href: "/icons/apple-touch-icon.png" },
  { rel: "manifest", href: "/manifest.json" },
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
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
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
  const [isPrideMonth, setIsPrideMonth] = useState(false);

  useEffect(() => {
    setIsPrideMonth(new Date().getMonth() === 5);
  }, []);

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

  useEffect(() => {
    if (isPrideMonth) {
      document.documentElement.classList.add("pride-month");
    } else {
      document.documentElement.classList.remove("pride-month");
    }
  }, [isPrideMonth]);

  return (
    <>
      <svg width="0" height="0" aria-hidden="true" style={{ position: "absolute" }}>
        <defs>
          <linearGradient id="page-icon-gradient" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="24" y2="24">
            <stop offset="0%" stopColor="var(--icon-g1)" />
            <stop offset="20%" stopColor="var(--icon-g2)" />
            <stop offset="40%" stopColor="var(--icon-g3)" />
            <stop offset="60%" stopColor="var(--icon-g4)" />
            <stop offset="80%" stopColor="var(--icon-g5)" />
            <stop offset="100%" stopColor="var(--icon-g6)" />
          </linearGradient>
        </defs>
      </svg>
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
  return <div style={{ minHeight: "100vh" }} />;
}
