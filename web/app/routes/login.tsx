/**
 * Login / first-run setup page.
 *
 * Renders one of three states based on /api/auth/status:
 *   - auth disabled -> redirect home (page should never have been shown)
 *   - setup required (no user yet) -> "Create administrator" form
 *   - otherwise -> standard "Sign in" form
 *
 * Talks to the API directly with credentials:"include" because lib/api.ts's
 * fetchApi swallows the FastAPI `detail` body (see api.ts comment), and we
 * want to surface "wrong password" / "account locked" cleanly.
 *
 * Accessibility:
 *   - All visible strings route through `useTranslations("login")` so
 *     screen readers don't read English under a non-English `<html lang>`
 *     (WCAG 3.1.1 Language of Page, 3.1.2 Language of Parts).
 *   - A wrong password clears the password field, marks it invalid and
 *     moves focus there (07e `326:34407`): the username was right often
 *     enough that retyping it is the wrong default. A failed setup returns
 *     focus to the field that failed
 *     (WCAG 2.4.3 Focus Order, 3.3.1 Error Identification).
 *   - The "authentication docs" link (first-run picker and setup only; the
 *     sign-in form has no such footer in 07e) opens in a new tab and carries
 *     a visually-hidden "(opens in new tab)" string for screen readers
 *     (WCAG 2.4.4 Link Purpose, 3.2.5 Change on Request).
 *
 * The sign-in form follows 07e Sign in (`326:40175` phone, `326:32474` /
 * `326:34407` desktop): wordmark, "Sign in to …", the hub line, password
 * reveal, "Keep me signed in on this browser" and a forgotten-password line
 * that leads to /reset-password. 07e titles the card with the hub's own name;
 * the hub withholds that name from anyone not signed in
 * (src/system/hub_identity.py), so the title keeps the product name and the
 * hub line names the address this browser reached instead.
 */

import {
  Alert,
  AlertDescription,
  AlertTitle,
  BoardBackdrop,
  Box,
  Button,
  Card,
  Checkbox,
  FiestaLogo,
  Flex,
  Heading,
  Input,
  Label,
  SecretInput,
  Stack,
  StatusDot,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { Spinner } from "@fiestaboard/ui/components/feedback/spinner";
import { CircleHelp, ShieldAlert, ShieldCheck, ShieldQuestion } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useDeviceOnline } from "@/hooks/use-hub-connection";
import { useRouter, useSearchParams } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import type { AuthStatusResponse } from "@/lib/api";
import { apiUrl, appUrl } from "@/lib/base-path";
import { hubLineStatus } from "@/lib/hub-identity";
import { browserHostname } from "@/lib/network-hint";
import { safeRedirect } from "@/lib/safe-redirect";

type AuthStatus = AuthStatusResponse;

async function fetchAuthStatus(): Promise<AuthStatus> {
  const res = await fetch(apiUrl("/auth/status"), {
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) {
    throw new Error(`Auth status request failed: ${res.status}`);
  }
  return res.json();
}

async function postJson(
  path: string,
  body: Record<string, unknown>,
): Promise<{ ok: boolean; status: number; detail?: string }> {
  const res = await fetch(apiUrl(path), {
    method: "POST",
    credentials: "include",
    cache: "no-store",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let detail: string | undefined;
  try {
    const data = await res.json();
    if (data && typeof data.detail === "string") {
      detail = data.detail;
    }
  } catch {
    /* no JSON body */
  }
  return { ok: res.ok, status: res.status, detail };
}

export default function LoginPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirectTo = safeRedirect(searchParams.get("redirect"));
  const t = useTranslations("login");
  const tCommon = useTranslations("common");
  const tReset = useTranslations("passwordReset");

  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  // ``firstRunChoice`` tracks the local UI state of the first-run picker:
  // ``null`` = show the picker; ``"enable"`` = drop into the setup form;
  // ``"skip"`` = POST /auth/preference {enabled:false} and bounce home.
  const [firstRunChoice, setFirstRunChoice] = useState<"enable" | "skip" | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  // "Keep me signed in on this browser" — defaults to checked (matches Home Assistant). When
  // off, the server issues a session cookie that the browser drops on close.
  const [rememberMe, setRememberMe] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  // A rejected username/password pair: 07e `326:34407` titles the alert and
  // marks the password field, so it is told apart from other failures.
  const [wrongCredentials, setWrongCredentials] = useState(false);
  // Where focus goes after this error; set with the error, read by the effect.
  const wrongCredentialsRef = useRef(false);

  // Refs let us restore focus after a failed submit so the user can retry
  // without re-tabbing past the skip link, sidebar, etc.
  const usernameInputRef = useRef<HTMLInputElement>(null);
  const passwordInputRef = useRef<HTMLInputElement>(null);

  // Guard against re-firing the bounce navigation if either `router` or
  // `redirectTo` references change after we've already left. Without it
  // the effect can chain a second navigation that overwrites a search/hash
  // the user has since added.
  const hasBounced = useRef(false);

  // Resolve /auth/status on mount so we know which form to render.
  useEffect(() => {
    let cancelled = false;
    fetchAuthStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        // If auth is disabled, this page has no purpose — bounce home.
        if (!s.enabled) {
          if (!hasBounced.current) {
            hasBounced.current = true;
            router.replace(redirectTo);
          }
          return;
        }
        // Already signed in -> straight to the redirect target.
        if (s.authenticated && !hasBounced.current) {
          hasBounced.current = true;
          router.replace(redirectTo);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setStatusError(err instanceof Error ? err.message : "Failed to check auth status");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router, redirectTo]);

  const handleLogin = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setFormError(null);
      setWrongCredentials(false);
      wrongCredentialsRef.current = false;
      setSubmitting(true);
      try {
        const res = await postJson("/auth/login", {
          username,
          password,
          remember_me: rememberMe,
        });
        if (res.ok) {
          router.replace(redirectTo);
          return;
        }
        if (res.status === 429) {
          setFormError(res.detail || t("tooManyAttempts"));
        } else if (res.status === 401) {
          // Our own words, not the server's English detail: the alert has a
          // title and a hint in the reader's language. The password goes, so
          // the retry starts from an empty field (focus moves there below).
          setPassword("");
          setWrongCredentials(true);
          wrongCredentialsRef.current = true;
          setFormError(t("invalidCredentials"));
        } else if (res.status === 409) {
          // User store is empty — drop into setup mode.
          setStatus((s) => (s ? { ...s, setup_required: true } : s));
          setFormError(null);
        } else {
          setFormError(res.detail || t("signInFailedStatus", { status: res.status }));
        }
      } catch {
        setFormError(t("networkError"));
      } finally {
        setSubmitting(false);
      }
    },
    [username, password, rememberMe, router, redirectTo, t],
  );

  const handleSetup = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setFormError(null);
      if (password.length < 8) {
        setFormError(t("passwordTooShort"));
        // Send focus back to the password field so the user can correct it
        // without re-tabbing (WCAG 3.3.1 Error Identification).
        passwordInputRef.current?.focus();
        return;
      }
      if (password !== confirmPassword) {
        setFormError(t("passwordsDontMatch"));
        passwordInputRef.current?.focus();
        return;
      }
      setSubmitting(true);
      try {
        const res = await postJson("/auth/setup", { username, password });
        if (res.ok) {
          router.replace(redirectTo);
          return;
        }
        if (res.status === 409) {
          setFormError(res.detail || t("adminExists"));
          setStatus((s) => (s ? { ...s, setup_required: false } : s));
        } else {
          setFormError(res.detail || t("setupFailedStatus", { status: res.status }));
        }
      } catch {
        setFormError(t("networkError"));
      } finally {
        setSubmitting(false);
      }
    },
    [username, password, confirmPassword, router, redirectTo, t],
  );

  const handleSkipAuth = useCallback(async () => {
    setFormError(null);
    setSubmitting(true);
    try {
      const res = await postJson("/auth/preference", { enabled: false });
      if (res.ok) {
        router.replace(redirectTo);
        return;
      }
      setFormError(res.detail || t("couldNotDisableAuth", { status: res.status }));
    } catch {
      setFormError(t("networkError"));
    } finally {
      setSubmitting(false);
    }
  }, [router, redirectTo, t]);

  // After a failed sign-in or setup submit, return focus to the failing
  // field. Triggers whenever ``formError`` transitions from null to a string
  // while we're not mid-submit (the submit handler clears submitting after).
  // A wrong password goes back to the (now empty) password field; anything
  // else (lockout, network, setup conflicts) to the username.
  // Keyed on the error and the submit only: anything else changing while the
  // reader retypes must not pull focus away mid-word.
  useEffect(() => {
    if (formError && !submitting) {
      (wrongCredentialsRef.current ? passwordInputRef : usernameInputRef).current?.focus();
    }
  }, [formError, submitting]);

  // --- Render states --------------------------------------------------------

  if (statusError) {
    return (
      <CenteredCard
        tCommon={tCommon}
        icon={<ShieldAlert className="h-6 w-6 text-destructive" />}
        title={t("apiUnreachableTitle")}
      >
        <Alert variant="destructive">
          <AlertDescription>{statusError}</AlertDescription>
        </Alert>
      </CenteredCard>
    );
  }

  if (!status) {
    return (
      <CenteredCard
        tCommon={tCommon}
        icon={<Spinner size="lg" className="size-6" label={null} />}
        title={t("loadingTitle")}
      >
        <Text tone="muted">{t("loadingDescription")}</Text>
      </CenteredCard>
    );
  }

  // While redirecting we render a placeholder rather than flashing the form.
  if (!status.enabled || status.authenticated) {
    return (
      <CenteredCard
        tCommon={tCommon}
        icon={<Spinner size="lg" className="size-6" label={null} />}
        title={t("redirectingTitle")}
      >
        <Text tone="muted">{t("redirectingDescription")}</Text>
      </CenteredCard>
    );
  }

  // First-run picker: the env var is unset and the admin hasn't chosen
  // yet. Offer to lock the install down or keep it open.
  if (status.first_run && firstRunChoice === null) {
    return (
      <CenteredCard
        tCommon={tCommon}
        icon={<ShieldQuestion className="h-6 w-6 text-brand" />}
        title={t("protectTitle")}
        description={t("protectDescription")}
        docsFooter
      >
        <Stack gap="3">
          <Button
            type="button"
            variant="brand"
            className="w-full"
            onClick={() => setFirstRunChoice("enable")}
            disabled={submitting}
          >
            <ShieldCheck className="h-4 w-4" /> {t("protectEnableButton")}
          </Button>
          <Button type="button" variant="outline" className="w-full" onClick={handleSkipAuth} disabled={submitting}>
            {submitting ? (
              <>
                <Spinner label={null} className="h-4 w-4" /> {t("disablingButton")}
              </>
            ) : (
              t("protectSkipButton")
            )}
          </Button>
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <Text size="xs" tone="muted">
            {t("protectFootnote")}
          </Text>
        </Stack>
      </CenteredCard>
    );
  }

  if (status.setup_required) {
    return (
      <CenteredCard
        tCommon={tCommon}
        icon={<ShieldCheck className="h-6 w-6 text-brand" />}
        title={t("setupTitle")}
        description={t("setupDescription")}
        docsFooter
      >
        <Box as="form" className="space-y-4" onSubmit={handleSetup}>
          <Stack gap="2">
            <Label htmlFor="username">{t("usernameLabel")}</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              required
              autoFocus
              ref={usernameInputRef}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
            />
          </Stack>
          <Stack gap="2">
            <Label htmlFor="password">{t("passwordLabel")}</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              ref={passwordInputRef}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
            <Text size="xs" tone="muted">
              {t("passwordMinHint")}
            </Text>
          </Stack>
          <Stack gap="2">
            <Label htmlFor="confirm-password">{t("confirmPasswordLabel")}</Label>
            <Input
              id="confirm-password"
              name="confirm-password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={submitting}
            />
          </Stack>
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <Button type="submit" variant="brand" className="w-full" disabled={submitting}>
            {submitting ? (
              <>
                <Spinner label={null} className="h-4 w-4" /> {t("creatingButton")}
              </>
            ) : (
              t("createButton")
            )}
          </Button>
        </Box>
      </CenteredCard>
    );
  }

  return (
    <CenteredCard tCommon={tCommon} title={t("signInTitle")} subtitle={<LoginHubLine />}>
      <Box as="form" className="space-y-4" onSubmit={handleLogin}>
        {formError && (
          <Alert variant="destructive" id="login-error">
            {wrongCredentials ? (
              <>
                <AlertTitle>{formError}</AlertTitle>
                <AlertDescription>{t("invalidCredentialsHint")}</AlertDescription>
              </>
            ) : (
              <AlertDescription>{formError}</AlertDescription>
            )}
          </Alert>
        )}
        <Stack gap="2">
          <Label htmlFor="username">{t("usernameLabel")}</Label>
          <Input
            id="username"
            name="username"
            autoComplete="username"
            required
            autoFocus
            ref={usernameInputRef}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={submitting}
          />
        </Stack>
        <Stack gap="2">
          <Label htmlFor="password">{t("passwordLabel")}</Label>
          <SecretInput
            id="password"
            name="password"
            autoComplete="current-password"
            required
            ref={passwordInputRef}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
            // Stays marked until the next submit, tied to the alert that says why.
            aria-invalid={wrongCredentials || undefined}
            aria-describedby={wrongCredentials ? "login-error" : undefined}
            // Dots, not the kit's monospace for keys and tokens.
            className="font-sans"
            showLabel={tReset("show")}
            hideLabel={tReset("hide")}
          />
        </Stack>
        <Flex align="center" gap="2">
          <Checkbox
            id="remember-me"
            name="remember-me"
            checked={rememberMe}
            onChange={(e) => setRememberMe(e.target.checked)}
            disabled={submitting}
          />
          <Label htmlFor="remember-me" className="cursor-pointer">
            {t("rememberMeLabel")}
          </Label>
        </Flex>
        {/* 40px, 44 on a phone (07e `326:32474`, `326:40175`), as /reset-password's (BB-FC-10). */}
        <Button type="submit" variant="brand" size="lg" className="h-11 w-full sm:h-10" disabled={submitting}>
          {submitting ? (
            <>
              <Spinner label={null} className="h-4 w-4" /> {t("submittingButton")}
            </>
          ) : (
            t("submitButton")
          )}
        </Button>
        <Flex gap="2" align="start">
          <CircleHelp className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden="true" />
          <Text size="xs" tone="muted">
            {t.rich("forgotPassword", {
              link: (chunks) => <TextLink href={appUrl("/reset-password")}>{chunks}</TextLink>,
            })}
          </Text>
        </Flex>
      </Box>
    </CenteredCard>
  );
}

/**
 * "● fiestapi.local · Online" under the sign-in title (07e `326:40175`).
 * The page only renders once /auth/status has answered, so the hub is known
 * to be reachable; the device's own network state can still say otherwise.
 * No /status poll: it needs a session this page does not have yet.
 */
function LoginHubLine() {
  const tStatus = useTranslations("statusBanners");
  const deviceOnline = useDeviceOnline();
  const host = browserHostname();
  const status = hubLineStatus({ host, hubReachable: true, deviceOnline });
  if (!host || !status) return null;
  const words = { online: tStatus("hubOnline"), remote: tStatus("hubRemote"), unreachable: tStatus("hubUnreachable") };
  const dot = { online: "success", remote: "info", unreachable: "danger" } as const;
  return (
    <Flex align="center" gap="1.5" className="min-w-0" data-slot="login-hub-line" data-status={status}>
      <StatusDot status={dot[status]} size="md" className="shrink-0" aria-hidden="true" />
      <Text size="xs" tone="muted" className="min-w-0 truncate">
        {host} · {words[status]}
      </Text>
    </Flex>
  );
}

// --- Layout helper -----------------------------------------------------------

/**
 * The card every state of this page sits in, laid out like 07e Sign in and
 * its sibling /reset-password: the board backdrop from 640px, the wordmark
 * inside the card, an H1, then the state's own content.
 */
function CenteredCard({
  icon,
  title,
  description,
  subtitle,
  children,
  tCommon,
  docsFooter = false,
}: {
  icon?: React.ReactNode;
  title: string;
  description?: string;
  /** A line under the title in place of a description (the sign-in hub line). */
  subtitle?: React.ReactNode;
  children: React.ReactNode;
  tCommon: ReturnType<typeof useTranslations>;
  /**
   * The "change this later" docs footnote, for the first-run picker and the
   * setup form only: the sign-in form has none in 07e (BB-C-10).
   */
  docsFooter?: boolean;
}) {
  const t = useTranslations("login");
  return (
    <Flex
      direction="col"
      align="center"
      justify="center"
      className="relative isolate min-h-svh w-full bg-background px-4 py-6 sm:p-8"
    >
      <BoardBackdrop
        phrases={["WELCOME", "GOOD MORNING", "HELLO WORLD", "72 AND CLEAR"]}
        fixed
        className="hidden sm:block"
      />
      {/* 398px, as 07e draws the auth card (`326:32474`, BB-FC-10). */}
      <Card className="relative z-10 w-full max-w-[398px] gap-4 p-6 sm:p-8">
        <FiestaLogo size="sm" />
        <Stack gap="1">
          <Flex align="center" gap="2">
            {icon}
            <Heading level={1} size="xl">
              {title}
            </Heading>
          </Flex>
          {subtitle}
          {description && (
            <Text size="sm" tone="muted">
              {description}
            </Text>
          )}
        </Stack>
        {children}
        {docsFooter && (
          // One paragraph, so the sentence wraps as text (BB-C-10).
          <Text as="p" size="xs" tone="muted">
            {t.rich("changeLater", {
              link: (chunks) => (
                <TextLink
                  href="https://fiestaboard.app/docs/setup/authentication"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  {chunks}
                  {/* sr-only cue lets screen-reader users know this link
                      leaves the app (WCAG 2.4.4 / 3.2.5). */}
                  <Text as="span" className="sr-only">
                    {" "}
                    {tCommon("opensInNewTab")}
                  </Text>
                </TextLink>
              ),
            })}
          </Text>
        )}
      </Card>
    </Flex>
  );
}
