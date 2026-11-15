"use client";

import {
  Box,
  Button,
  InstallCard,
  type InstallCardState,
  InstallSteps,
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Stack,
  TextLink,
} from "@fiestaboard/ui";
import { Check, Ellipsis, Plus } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { useTranslations } from "@/i18n/translations";
import { classifyInstallSuccess, onApiSuccess } from "@/lib/api/success-events";
import { isPanelPath } from "@/lib/chromeless";
import { deviceWord, hubHost } from "@/lib/pwa/device-words";
import { canInstallOnSecureOrigin, isIosSafari, isSecureOrigin, isStandalone } from "@/lib/pwa/environment";
import { HTTPS_HELP_URL } from "@/lib/pwa/https-help";
import {
  type InstallSuccess,
  markNeverOffer,
  markOffered,
  readInstallTrigger,
  recordInstallSuccess,
} from "@/lib/pwa/install-trigger";

/** Chromium's install event: stashed until the person asks to install. */
export interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

/** Render `<Box id={INSTALL_OFFER_SLOT_ID} />` where a page wants the install card. */
export const INSTALL_OFFER_SLOT_ID = "install-offer-slot";

type Offer =
  { kind: "card"; state: InstallCardState; reason: InstallSuccess; count: number } | { kind: "sheet" } | null;

/**
 * The install offer (WEB-12; 07 `58:33496`, `58:34465`, notes `58:34443`,
 * `58:35364`). Never on load: it waits for a real success (the 3rd send or
 * a saved page, counted from successful API calls), shows once, and "Not now"
 * snoozes it for 30 days.
 *
 * - **Chromium, secure:** the stashed `beforeinstallprompt` backs a real
 *   Install button in an `InstallCard`, in the page flow.
 * - **Safari on iPhone/iPad, secure:** Safari has no install prompt, so the
 *   same moment opens the Add to Home Screen sheet with Safari's real steps.
 * - **http:** no service worker, so nothing to install. The card says so and
 *   draws no Install button (`state="needs-https"`, "no fake button").
 * - **Already installed, the FiestaPanel viewer, or a browser that can't
 *   install at all:** nothing.
 */
export function InstallPrompt() {
  const t = useTranslations("installPrompt");
  const [offer, setOffer] = useState<Offer>(null);
  const deferred = useRef<BeforeInstallPromptEvent | null>(null);

  // Stash the browser's install event from the first moment, without showing
  // anything: the offer itself waits for a success.
  useEffect(() => {
    const onBeforeInstall = (event: Event) => {
      event.preventDefault();
      deferred.current = event as BeforeInstallPromptEvent;
    };
    const onInstalled = () => {
      deferred.current = null;
      markNeverOffer();
      setOffer(null);
    };
    window.addEventListener("beforeinstallprompt", onBeforeInstall);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onBeforeInstall);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  useEffect(
    () =>
      onApiSuccess((event) => {
        const kind = classifyInstallSuccess(event);
        if (!kind) return;
        if (isStandalone() || isPanelPath(window.location.pathname)) return;
        if (!canInstallOnSecureOrigin()) return;
        const counts = readInstallTrigger();
        if (!recordInstallSuccess(kind)) return;
        let next: Offer;
        if (!isSecureOrigin()) {
          next = { kind: "card", state: "needs-https", reason: kind, count: counts.sends + 1 };
        } else if (isIosSafari()) {
          next = { kind: "sheet" };
        } else if (deferred.current) {
          next = { kind: "card", state: "available", reason: kind, count: counts.sends + 1 };
        } else {
          // Secure, but the browser has offered nothing to install (already
          // installed, or it declined): keep the count, show nothing.
          return;
        }
        markOffered();
        setOffer(next);
      }),
    [],
  );

  const install = async () => {
    const event = deferred.current;
    if (!event || offer?.kind !== "card") return;
    setOffer({ ...offer, state: "installing" });
    try {
      await event.prompt();
      const { outcome } = await event.userChoice;
      if (outcome === "accepted") markNeverOffer();
    } finally {
      // The browser's prompt can be used once; either way the offer is done.
      deferred.current = null;
      setOffer(null);
    }
  };

  if (offer === null) return null;

  if (offer.kind === "sheet") {
    const close = (never: boolean) => {
      if (never) markNeverOffer();
      setOffer(null);
    };
    return (
      <Sheet open onOpenChange={(open) => !open && close(false)}>
        <SheetContent side="bottom" grabber labels={{ close: t("close") }}>
          <SheetHeader className="min-h-12 justify-center pr-12 text-left sm:text-left">
            <SheetTitle>{t("sheetTitle")}</SheetTitle>
          </SheetHeader>
          <Stack gap="3" className="pt-2">
            <SheetDescription>{t("sheetIntro")}</SheetDescription>
            <InstallSteps
              aria-label={t("sheetTitle")}
              steps={[
                { id: "share", text: t("stepShare"), icon: <Ellipsis /> },
                { id: "add", text: t("stepAdd"), icon: <Plus /> },
                { id: "open", text: t("stepOpen"), icon: <Check /> },
              ]}
            />
          </Stack>
          <SheetFooter className="flex-row flex-wrap items-center justify-start gap-2 pb-6">
            <Button variant="secondary" size="touch" onClick={() => close(false)}>
              {t("gotIt")}
            </Button>
            <Button variant="ghost" size="touch" onClick={() => close(true)}>
              {t("dontShowAgain")}
            </Button>
          </SheetFooter>
        </SheetContent>
      </Sheet>
    );
  }

  const device = t(`device.${deviceWord()}`);
  const host = hubHost();
  const needsHttps = offer.state === "needs-https";

  const card = (
    // PageLayout's card gutter, so the card lines up with the cards above it.
    <Box className="container mx-auto max-w-full px-4 pb-6 md:px-6" data-testid="install-offer">
      <InstallCard
        className="max-w-2xl"
        state={offer.state}
        title={needsHttps ? t("httpsTitle") : t("title", { device })}
        onInstall={needsHttps ? undefined : install}
        onDismiss={() => {
          // "Not now": hold the offer for 30 days from this moment.
          markOffered();
          setOffer(null);
        }}
        labels={{ install: t("install"), notNow: t("notNow") }}
      >
        {needsHttps ? (
          <>
            {t("httpsBody", { host })}{" "}
            <TextLink href={HTTPS_HELP_URL} target="_blank" rel="noreferrer">
              {t("httpsHelp")}
            </TextLink>
          </>
        ) : (
          <>
            {offer.reason === "save" ? t("reasonSave") : t("reasonSends", { count: String(offer.count) })}{" "}
            {t("body", { host })}
          </>
        )}
      </InstallCard>
    </Box>
  );
  // A page can host the card in its own flow (07 `58:33496` draws it under
  // Home's board) by rendering an element with this id; otherwise it sits at
  // the end of the main content.
  const slot = document.getElementById(INSTALL_OFFER_SLOT_ID);
  return slot ? createPortal(card, slot) : card;
}
