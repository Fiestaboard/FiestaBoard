"use client";

/**
 * Account settings — rendered as a stack of sibling cards on the
 * Account tab in Settings:
 *
 *   1. Signed in (identity readout)
 *   2. Change username
 *   3. Change password
 *   4. Sign out
 *   5. Disable login (password-gated, with warning modal)
 *
 * Hides itself entirely when auth is disabled or the user isn't
 * signed in.
 */

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Input,
  Label,
  Skeleton,
} from "@fiestaboard/ui";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, ShieldAlert, ShieldCheck, ShieldOff, UserCircle2, UserCog } from "lucide-react";
import { type FormEvent, type ReactNode, useState } from "react";
import { toast } from "sonner";

import { useRouter } from "@/hooks/use-router";
import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

export function AccountSection() {
  const t = useTranslations("accountSection");
  const router = useRouter();
  const queryClient = useQueryClient();

  const { data: authStatus, isLoading } = useQuery({
    queryKey: ["auth-status"],
    queryFn: api.getAuthStatus,
    staleTime: 30_000,
    retry: false,
  });

  if (isLoading) {
    return (
      <Card data-testid="account-loading">
        <CardHeader>
          <Skeleton className="h-4 w-24" />
        </CardHeader>
        <CardContent>
          <Skeleton className="h-20 w-full" />
        </CardContent>
      </Card>
    );
  }
  if (!authStatus) {
    return null;
  }

  // Auth is currently off — render a single "turn it on" card so the
  // tab still has a reason to exist and the user has a discoverable
  // path back to a locked-down install.
  if (authStatus.mode === "disabled") {
    return <EnableLoginCard />;
  }

  // Auth is on but the visitor isn't signed in — they shouldn't even
  // be reaching this page; the middleware will route them to /login.
  if (!authStatus.enabled || !authStatus.authenticated) {
    return null;
  }

  const username = authStatus.username ?? "—";

  const handleSignOut = async () => {
    try {
      await api.logout();
    } catch {
      // Server cookie clear is best-effort.
    }
    queryClient.removeQueries({ queryKey: ["auth-status"] });
    router.replace("/login");
  };

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserCircle2 className="h-4 w-4 text-muted-foreground" />
            {t("signedIn.title")}
          </CardTitle>
          <CardDescription>
            {t.rich("signedIn.description", {
              name: () => <span className="font-mono text-foreground">{username}</span>,
            })}
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserCog className="h-4 w-4 text-muted-foreground" />
            {t("changeUsername.title")}
          </CardTitle>
          <CardDescription>{t("changeUsername.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <ChangeUsernameForm currentUsername={username} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            {t("changePassword.title")}
          </CardTitle>
          <CardDescription>{t("changePassword.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <ChangePasswordForm />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <LogOut className="h-4 w-4 text-muted-foreground" />
            {t("signOut.title")}
          </CardTitle>
          <CardDescription>{t("signOut.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={handleSignOut}>
            <LogOut className="h-4 w-4" /> {t("signOut.button")}
          </Button>
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldOff className="h-4 w-4 text-destructive" />
            {t("disableLogin.title")}
          </CardTitle>
          <CardDescription>{t("disableLogin.description")}</CardDescription>
        </CardHeader>
        <CardContent>
          <DisableAuthDialog username={username} />
        </CardContent>
      </Card>
    </>
  );
}

function ChangeUsernameForm({ currentUsername }: { currentUsername: string }) {
  const t = useTranslations("accountSection");
  const queryClient = useQueryClient();
  const [newUsername, setNewUsername] = useState(currentUsername);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!newUsername.trim() || !password) return;
    setSubmitting(true);
    try {
      await api.changeUsername(password, newUsername.trim());
      setPassword("");
      toast.success(t("changeUsername.success"));
      queryClient.invalidateQueries({ queryKey: ["auth-status"] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("changeUsername.failure"));
    } finally {
      setSubmitting(false);
    }
  };

  const unchanged = newUsername.trim() === currentUsername;

  return (
    <form className="space-y-4 max-w-sm" onSubmit={onSubmit} aria-label={t("changeUsername.formAriaLabel")}>
      <div className="space-y-2">
        <Label htmlFor="account-username">{t("changeUsername.newUsernameLabel")}</Label>
        <Input
          id="account-username"
          autoComplete="username"
          value={newUsername}
          onChange={(e) => setNewUsername(e.target.value)}
          disabled={submitting}
          required
          maxLength={64}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="account-username-password">{t("changeUsername.currentPasswordLabel")}</Label>
        <Input
          id="account-username-password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          disabled={submitting}
          required
        />
      </div>
      <Button type="submit" disabled={submitting || unchanged || !password}>
        {submitting ? t("changeUsername.submitting") : t("changeUsername.submit")}
      </Button>
    </form>
  );
}

function ChangePasswordForm() {
  const t = useTranslations("accountSection");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword.length < 8) {
      setError(t("changePassword.tooShort"));
      return;
    }
    if (newPassword !== confirm) {
      setError(t("changePassword.mismatch"));
      return;
    }
    setSubmitting(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      toast.success(t("changePassword.success"));
    } catch (err) {
      setError(err instanceof Error ? err.message : t("changePassword.failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="space-y-4 max-w-sm" onSubmit={onSubmit} aria-label={t("changePassword.formAriaLabel")}>
      <div className="space-y-2">
        <Label htmlFor="account-current-password">{t("changePassword.currentPasswordLabel")}</Label>
        <Input
          id="account-current-password"
          type="password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
          disabled={submitting}
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="account-new-password">{t("changePassword.newPasswordLabel")}</Label>
        <Input
          id="account-new-password"
          type="password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          disabled={submitting}
          required
          minLength={8}
        />
        <p className="text-xs text-muted-foreground">{t("changePassword.newPasswordHint")}</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="account-confirm-password">{t("changePassword.confirmPasswordLabel")}</Label>
        <Input
          id="account-confirm-password"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          disabled={submitting}
          required
          minLength={8}
        />
      </div>
      {error && (
        <p className="text-sm text-destructive" role="alert">
          {error}
        </p>
      )}
      <Button type="submit" disabled={submitting || !currentPassword || !newPassword}>
        {submitting ? t("changePassword.submitting") : t("changePassword.submit")}
      </Button>
    </form>
  );
}

function DisableAuthDialog({ username }: { username: string }) {
  const t = useTranslations("accountSection");
  const tCommon = useTranslations("common");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onConfirm = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (!password) return;
    setSubmitting(true);
    try {
      await api.disableAuth(password);
      toast.success(t("disableLogin.success"));
      setPassword("");
      setOpen(false);
      // The install is now wide open — drop cached auth state and
      // send the user home. /login no longer applies.
      queryClient.removeQueries({ queryKey: ["auth-status"] });
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : t("disableLogin.failure"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <AlertDialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) {
          setPassword("");
          setError(null);
        }
      }}
    >
      <AlertDialogTrigger asChild>
        <Button type="button" variant="destructive">
          <ShieldOff className="h-4 w-4" /> {t("disableLogin.button")}
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-destructive" />
            {t("disableLogin.dialogTitle")}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3 text-sm">
              <p>
                {t.rich("disableLogin.dialogBody1", {
                  name: () => <span className="font-mono">{username}</span>,
                })}
              </p>
              <p>
                {t.rich("disableLogin.dialogBody2", {
                  strong: (chunks: ReactNode) => <strong>{chunks}</strong>,
                })}
              </p>
              <p>{t("disableLogin.dialogBody3")}</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <form onSubmit={onConfirm} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="disable-auth-password">{t("disableLogin.confirmPasswordLabel")}</Label>
            <Input
              id="disable-auth-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
              required
              autoFocus
            />
          </div>
          {error && (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          )}
          <AlertDialogFooter>
            {/* Plain buttons rather than AlertDialogCancel /
                AlertDialogAction so the Radix primitives don't
                pre-close the dialog and shadow the form submit. */}
            <Button type="button" variant="outline" disabled={submitting} onClick={() => setOpen(false)}>
              {tCommon("cancel")}
            </Button>
            <Button type="submit" variant="destructive" disabled={submitting || !password}>
              {submitting ? t("disableLogin.confirming") : t("disableLogin.confirm")}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function EnableLoginCard() {
  const t = useTranslations("accountSection");
  const router = useRouter();
  const queryClient = useQueryClient();
  const [submitting, setSubmitting] = useState(false);

  const onEnable = async () => {
    setSubmitting(true);
    try {
      await api.setAuthPreference(true);
      // /login now renders the setup form (mode flipped to "enabled",
      // no user exists yet). Drop the cached status so the next render
      // sees the new mode.
      queryClient.removeQueries({ queryKey: ["auth-status"] });
      router.push("/login");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : t("enableLogin.failure"));
      setSubmitting(false);
    }
  };

  return (
    <Card className="border-brand/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4 text-brand" />
          {t("enableLogin.title")}
        </CardTitle>
        <CardDescription>
          {t.rich("enableLogin.description", {
            strong: (chunks: ReactNode) => <strong>{chunks}</strong>,
          })}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{t("enableLogin.body")}</p>
        <Button type="button" variant="brand" onClick={onEnable} disabled={submitting}>
          <ShieldCheck className="h-4 w-4" />
          {submitting ? t("enableLogin.submitting") : t("enableLogin.button")}
        </Button>
      </CardContent>
    </Card>
  );
}
