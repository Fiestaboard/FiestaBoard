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
 */

import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Lock, ShieldAlert, ShieldCheck, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
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

type AuthStatus = {
  enabled: boolean;
  setup_required: boolean;
  authenticated: boolean;
  username: string | null;
};

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

  const [status, setStatus] = useState<AuthStatus | null>(null);
  const [statusError, setStatusError] = useState<string | null>(null);

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
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
        const res = await postJson("/auth/login", { username, password });
        if (res.ok) {
          router.replace(redirectTo);
          return;
        }
        if (res.status === 429) {
          setFormError(
            res.detail ||
              "Too many failed login attempts. Please wait a minute and try again.",
          );
        } else if (res.status === 401) {
          setFormError(res.detail || "Invalid username or password.");
        } else if (res.status === 409) {
          // User store is empty — drop into setup mode.
          setStatus((s) => (s ? { ...s, setup_required: true } : s));
          setFormError(null);
        } else {
          setFormError(res.detail || `Sign-in failed (${res.status}).`);
        }
      } catch {
        setFormError("Network error. Please try again.");
      } finally {
        setSubmitting(false);
      }
    },
    [username, password, router, redirectTo],
  );

  const handleSetup = useCallback(
    async (e: FormEvent) => {
      e.preventDefault();
      setFormError(null);
      if (password.length < 8) {
        setFormError("Password must be at least 8 characters long.");
        return;
      }
      if (password !== confirmPassword) {
        setFormError("Passwords do not match.");
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
          setFormError(
            res.detail ||
              "An administrator account already exists. Please sign in instead.",
          );
          setStatus((s) => (s ? { ...s, setup_required: false } : s));
        } else {
          setFormError(res.detail || `Setup failed (${res.status}).`);
        }
      } catch {
        setFormError("Network error. Please try again.");
      } finally {
        setSubmitting(false);
      }
    },
    [username, password, confirmPassword, router, redirectTo],
  );

  // --- Render states --------------------------------------------------------

  if (statusError) {
    return (
      <CenteredCard
        icon={<ShieldAlert className="h-6 w-6 text-destructive" />}
        title="Couldn't reach the API"
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
        title="Loading…"
      >
        <p className="text-sm text-muted-foreground">
          Checking authentication status…
        </p>
      </CenteredCard>
    );
  }

  // While redirecting we render a placeholder rather than flashing the form.
  if (!status.enabled || status.authenticated) {
    return (
      <CenteredCard
        icon={<Loader2 className="h-6 w-6 animate-spin" />}
        title="Redirecting…"
      >
        <p className="text-sm text-muted-foreground">One moment…</p>
      </CenteredCard>
    );
  }

  if (status.setup_required) {
    return (
      <CenteredCard
        icon={<ShieldCheck className="h-6 w-6 text-brand" />}
        title="Create administrator"
        description="No accounts exist yet. Set a username and password to lock down this FiestaBoard."
      >
        <form className="space-y-4" onSubmit={handleSetup}>
          <div className="space-y-2">
            <Label htmlFor="username">Username</Label>
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
            <Label htmlFor="password">Password</Label>
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
            <p className="text-xs text-muted-foreground">
              At least 8 characters.
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="confirm-password">Confirm password</Label>
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
                <Loader2 className="h-4 w-4 animate-spin" /> Creating…
              </>
            ) : (
              "Create account"
            )}
          </Button>
        </form>
      </CenteredCard>
    );
  }

  return (
    <CenteredCard
      icon={<Lock className="h-6 w-6 text-brand" />}
      title="Sign in to FiestaBoard"
      description="Enter your administrator credentials to continue."
    >
      <form className="space-y-4" onSubmit={handleLogin}>
        <div className="space-y-2">
          <Label htmlFor="username">Username</Label>
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
          <Label htmlFor="password">Password</Label>
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
              <Loader2 className="h-4 w-4 animate-spin" /> Signing in…
            </>
          ) : (
            "Sign in"
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
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-background p-4">
      <div className="mb-6">
        <FiestaLogo />
      </div>
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <div className="flex items-center gap-2">
            {icon}
            <CardTitle>{title}</CardTitle>
          </div>
          {description && <CardDescription>{description}</CardDescription>}
        </CardHeader>
        <CardContent>{children}</CardContent>
        <CardFooter className="text-xs text-muted-foreground">
          FiestaBoard authentication is opt-in. Disable it by unsetting{" "}
          <code className="mx-1">FIESTABOARD_AUTH_ENABLED</code> on the host.
        </CardFooter>
      </Card>
    </div>
  );
}
