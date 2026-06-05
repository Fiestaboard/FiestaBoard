import "./globals.css";

import type { Metadata, Viewport } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages, getTranslations } from "next-intl/server";

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

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover",
};

/**
 * Localize `<title>` and `<meta name="description">` so screen-reader
 * users (and the browser tab) get the document title in the active
 * locale instead of the English source string. The static-icon and
 * manifest entries stay verbatim — they're locale-independent.
 *
 * WCAG 2.2 AA: 2.4.2 Page Titled, 3.1.1 Language of Page.
 */
export async function generateMetadata(): Promise<Metadata> {
  const t = await getTranslations("metadata");
  return {
    title: t("appTitle"),
    description: t("appDescription"),
    icons: {
      icon: [
        { url: "/icons/favicon-16x16.png", sizes: "16x16", type: "image/png" },
        { url: "/icons/favicon-32x32.png", sizes: "32x32", type: "image/png" },
        { url: "/icons/favicon-48x48.png", sizes: "48x48", type: "image/png" },
        { url: "/favicon.ico", sizes: "any" },
      ],
      apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
    },
    manifest: "/manifest.json",
  };
}

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();
  const isPrideMonth = new Date().getMonth() === 5;

  return (
    <html lang={locale} suppressHydrationWarning className={isPrideMonth ? "pride-month" : undefined}>
      <head>
        <meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content="#0a0a0a" media="(prefers-color-scheme: dark)" />
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="icon" href="/icons/favicon-32x32.png" type="image/png" sizes="32x32" />
        <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
      </head>
      <body className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
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
        <NextIntlClientProvider messages={messages}>
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
                        <PageFadeWrapper>{children}</PageFadeWrapper>
                      </MainContent>
                      <Toaster />
                      <InstallPrompt />
                    </WizardProvider>
                  </GlobalAiPanelProvider>
                </PageEditorBridgeProvider>
              </ScheduleEditorBridgeProvider>
            </BootGate>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
