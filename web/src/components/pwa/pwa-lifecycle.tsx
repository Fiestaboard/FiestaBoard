"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { usePathname } from "@/hooks/use-router";
import { startLastKnownRecorder } from "@/lib/pwa/last-known-recorder";
import { registerServiceWorker } from "@/lib/pwa/register-service-worker";
import { clearAccountDataOnDevice } from "@/lib/pwa/sign-out";

/**
 * The app's installed-app plumbing (web 2.8), mounted once in the root,
 * outside BootGate so it also runs while the app boots offline. It draws
 * nothing:
 *
 * - registers the app-shell service worker (secure contexts only);
 * - records the last-known board frame as the app polls it;
 * - wipes that frame on the sign-in page, where nobody is signed in.
 */
export function PwaLifecycle() {
  const queryClient = useQueryClient();
  const pathname = usePathname();

  useEffect(() => {
    if (import.meta.env.DEV) return;
    void registerServiceWorker();
  }, []);

  useEffect(() => startLastKnownRecorder(queryClient), [queryClient]);

  // The router pathname is already relative to the basename (HA Ingress).
  const onSignIn = pathname.startsWith("/login");
  useEffect(() => {
    if (onSignIn) void clearAccountDataOnDevice();
  }, [onSignIn]);

  return null;
}
