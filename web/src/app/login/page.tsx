"use client";

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
 *   All visible strings route through next-intl's `login.*` namespace so
 *   screen readers don't read English under a non-English `<html lang>`
 *   (WCAG 3.1.1 Language of Page, 3.1.2 Language of Parts).
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Lock, ShieldAlert, ShieldCheck, ShieldQuestion, Loader2 } from "lucide-react";
import type { AuthStatusResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { FiestaLogo } from "@/components/fiesta-logo";

type AuthStatus = AuthStatusResponse;

async function fetchAuthStatus(): Promise<AuthStatus> {
  const res = await fetch("/api/auth/status", {
    credentials: "include",
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
  const res = await fetch(`/api${path}`, {
    method: "POST",
    credentials: "include",
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
  const redirectTo = searchParams.get("redirect") || "/";
  const t = useTranslations("login");

  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  // ``firstRunChoice`` tracks the local UI state of the first-run picker:
  // ``null`` = show the picker; ``"enable"`` = drop into the setup form;
  // ``"skip"`` = POST /auth/preference {enabled:false} and bounce home.
  const [firstRunChoice, setFirstRunChoice] = useState<"enable" | "skip" | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  // "Keep me logged in" — defaults to checked (matches Home Assistant). When
  // off, the server issues a session cookie that the browser drops on close.
  const [rememberMe, setRememberMe] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  // Resolve /auth/status on mount so we know which form to render.
  useEffect(() => {
    let cancelled = false;
    fetchAuthStatus()
      .then((s) => {
        if (cancelled) return;
        setStatus(s);
        // If auth is disabled, this page has no purpose — bounce home.
        if (!s.enabled) {
          router.replace(redirectTo);
          return;
        }
        // Already signed in -> straight to the redirect target.
        if (s.authenticated) {
          router.replace(redirectTo);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setStatusError(
            err instanceof Error ? err.message : "Failed to check auth status",
          );
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
          setFormError(res.detail || t("invalidCredentials"));
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
        return;
      }
      if (password !== confirmPassword) {
        setFormError(t("passwordsDontMatch"));
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

  // --- Render states --------------------------------------------------------

  if (statusError) {
    return (
      <CenteredCard
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
        icon={<Loader2 className="h-6 w-6 animate-spin" />}
        title={t("loadingTitle")}
      >
        <p className="text-sm text-muted-foreground">{t("loadingDescription")}</p>
      </CenteredCard>
    );
  }

  // While redirecting we render a placeholder rather than flashing the form.
  if (!status.enabled || status.authenticated) {
    return (
      <CenteredCard
        icon={<Loader2 className="h-6 w-6 animate-spin" />}
        title={t("redirectingTitle")}
      >
        <p className="text-sm text-muted-foreground">{t("redirectingDescription")}</p>
      </CenteredCard>
    );
  }

  // First-run picker: the env var is unset and the admin hasn't chosen
  // yet. Offer to lock the install down or keep it open.
  if (status.first_run && firstRunChoice === null) {
    return (
      <CenteredCard
        icon={<ShieldQuestion className="h-6 w-6 text-brand" />}
        title={t("protectTitle")}
        description={t("protectDescription")}
      >
        <div className="space-y-3">
          <Button
            type="button"
            variant="brand"
            className="w-full"
            onClick={() => setFirstRunChoice("enable")}
            disabled={submitting}
          >
            <ShieldCheck className="h-4 w-4" /> {t("protectEnableButton")}
          </Button>
          <Button
            type="button"
            variant="outline"
            className="w-full"
            onClick={handleSkipAuth}
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> {t("disablingButton")}
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
          <p className="text-xs text-muted-foreground">{t("protectFootnote")}</p>
        </div>
      </CenteredCard>
    );
  }

  if (status.setup_required) {
    return (
      <CenteredCard
        icon={<ShieldCheck className="h-6 w-6 text-brand" />}
        title={t("setupTitle")}
        description={t("setupDescription")}
      >
        <form className="space-y-4" onSubmit={handleSetup}>
          <div className="space-y-2">
            <Label htmlFor="username">{t("usernameLabel")}</Label>
            <Input
              id="username"
              name="username"
              autoComplete="username"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="password">{t("passwordLabel")}</Label>
            <Input
              id="password"
              name="password"
              type="password"
              autoComplete="new-password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
            <p className="text-xs text-muted-foreground">{t("passwordMinHint")}</p>
          </div>
          <div className="space-y-2">
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
          </div>
          {formError && (
            <Alert variant="destructive">
              <AlertDescription>{formError}</AlertDescription>
            </Alert>
          )}
          <Button
            type="submit"
            variant="brand"
            className="w-full"
            disabled={submitting}
          >
            {submitting ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" /> {t("creatingButton")}
              </>
            ) : (
              t("createButton")
            )}
          </Button>
        </form>
      </CenteredCard>
    );
  }

  return (
    <CenteredCard
      icon={<Lock className="h-6 w-6 text-brand" />}
      title={t("signInTitle")}
      description={t("signInDescription")}
    >
      <form className="space-y-4" onSubmit={handleLogin}>
        <div className="space-y-2">
          <Label htmlFor="username">{t("usernameLabel")}</Label>
          <Input
            id="username"
            name="username"
            autoComplete="username"
            required
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            disabled={submitting}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="password">{t("passwordLabel")}</Label>
          <Input
            id="password"
            name="password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            disabled={submitting}
          />
        </div>
        <div className="flex items-center gap-2">
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
        </div>
        {formError && (
          <Alert variant="destructive">
            <AlertDescription>{formError}</AlertDescription>
          </Alert>
        )}
        <Button
          type="submit"
          variant="brand"
          className="w-full"
          disabled={submitting}
        >
          {submitting ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> {t("submittingButton")}
            </>
          ) : (
            t("submitButton")
          )}
        </Button>
      </form>
    </CenteredCard>
  );
}

// --- Layout helper -----------------------------------------------------------

function CenteredCard({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  const t = useTranslations("login");
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background p-4">
      <div className="mb-6 flex items-center gap-3">
        <Image
          src="/icons/favicon-32x32.png"
          alt=""
          width={36}
          height={36}
          className="flex-shrink-0"
        />
        <FiestaLogo className="text-2xl" />
      </div>
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center gap-2">
            {icon}
            <CardTitle as="h1">{title}</CardTitle>
          </div>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>{children}</CardContent>
        <CardFooter className="text-xs text-muted-foreground">
          {t.rich("changeLater", {
            link: (chunks) => (
              <a
                href="https://fiestaboard.app/docs/setup/authentication"
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-foreground"
              >
                {chunks}
              </a>
            ),
          })}
        </CardFooter>
      </Card>
    </div>
  );
}
