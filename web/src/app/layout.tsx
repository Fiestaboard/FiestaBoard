import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";
import { Providers } from "@/components/providers";
import { Toaster } from "@/components/ui/sonner";
import { NavigationSidebar } from "@/components/navigation-sidebar";
import { WizardProvider } from "@/components/wizard-provider";
import { InstallPrompt } from "@/components/install-prompt";
import { PageFadeWrapper } from "@/components/page-fade-wrapper";
import { MainContent } from "@/components/main-content";
import { ThemeColorMeta } from "@/components/theme-color-meta";
import { ReduceMotionApplier } from "@/components/reduce-motion-applier";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "FiestaBoard Control",
  description: "Home hub for your FiestaBoard display",
  icons: {
    icon: [
      { url: "/icons/favicon-16x16.png", sizes: "16x16", type: "image/png" },
      { url: "/icons/favicon-32x32.png", sizes: "32x32", type: "image/png" },
      { url: "/icons/favicon-48x48.png", sizes: "48x48", type: "image/png" },
      { url: "/favicon.ico", sizes: "any" },
    ],
    apple: [
      { url: "/icons/apple-touch-icon.png", sizes: "180x180", type: "image/png" },
    ],
  },
  manifest: "/manifest.json",
};

export default async function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale} suppressHydrationWarning>
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no" />
        <meta name="theme-color" content="#fafafa" media="(prefers-color-scheme: light)" />
        <meta name="theme-color" content="#0a0a0a" media="(prefers-color-scheme: dark)" />
        <link rel="icon" href="/favicon.ico" sizes="any" />
        <link rel="icon" href="/icons/favicon-32x32.png" type="image/png" sizes="32x32" />
        <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png" />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased min-h-screen overflow-x-hidden`}
      >
        <svg width="0" height="0" aria-hidden="true" style={{ position: 'absolute' }}>
          <defs>
            <linearGradient id="page-icon-gradient" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="var(--fiesta-red)" />
              <stop offset="50%" stopColor="var(--fiesta-orange)" />
              <stop offset="100%" stopColor="var(--fiesta-purple)" />
            </linearGradient>
          </defs>
        </svg>
        <NextIntlClientProvider messages={messages}>
          <Providers>
            <ThemeColorMeta />
            <ReduceMotionApplier />
            <WizardProvider>
              <NavigationSidebar />
              <MainContent>
                <PageFadeWrapper>
                  {children}
                </PageFadeWrapper>
              </MainContent>
              <Toaster />
              <InstallPrompt />
            </WizardProvider>
          </Providers>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
