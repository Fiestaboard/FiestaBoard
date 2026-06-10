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

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, LogOut, ShieldAlert, ShieldCheck, ShieldOff, UserCircle2, UserCog } from "lucide-react";
import { type FormEvent, useState } from "react";
import { toast } from "sonner";

import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useRouter } from "@/hooks/use-router";
import { api } from "@/lib/api";

export function AccountSection() {
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
            Signed in
          </CardTitle>
          <CardDescription>
            You&apos;re currently signed in as <span className="font-mono text-foreground">{username}</span>.
          </CardDescription>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <UserCog className="h-4 w-4 text-muted-foreground" />
            Change username
          </CardTitle>
          <CardDescription>Pick a new sign-in name. Requires your current password.</CardDescription>
        </CardHeader>
        <CardContent>
          <ChangeUsernameForm currentUsername={username} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <KeyRound className="h-4 w-4 text-muted-foreground" />
            Change password
          </CardTitle>
          <CardDescription>
            Rotate your password. Any other sessions signed in with the old password will be signed out.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <ChangePasswordForm />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <LogOut className="h-4 w-4 text-muted-foreground" />
            Sign out
          </CardTitle>
          <CardDescription>End your current session. You&apos;ll be sent back to the sign-in page.</CardDescription>
        </CardHeader>
        <CardContent>
          <Button type="button" variant="outline" onClick={handleSignOut}>
            <LogOut className="h-4 w-4" /> Sign out
          </Button>
        </CardContent>
      </Card>

      <Card className="border-destructive/40">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldOff className="h-4 w-4 text-destructive" />
            Disable login
          </CardTitle>
          <CardDescription>
            Turn off authentication entirely. Anyone who can reach this FiestaBoard on the network will be able to
            change settings and read API keys. Not recommended unless this device is on a fully trusted private network.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DisableAuthDialog username={username} />
        </CardContent>
      </Card>
    </>
  );
}

function ChangeUsernameForm({ currentUsername }: { currentUsername: string }) {
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
      toast.success("Username updated");
      queryClient.invalidateQueries({ queryKey: ["auth-status"] });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Username change failed");
    } finally {
      setSubmitting(false);
    }
  };

  const unchanged = newUsername.trim() === currentUsername;

  return (
    <form className="space-y-4 max-w-sm" onSubmit={onSubmit} aria-label="Change username">
      <div className="space-y-2">
        <Label htmlFor="account-username">New username</Label>
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
        <Label htmlFor="account-username-password">Current password</Label>
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
        {submitting ? "Saving…" : "Save username"}
      </Button>
    </form>
  );
}

function ChangePasswordForm() {
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (newPassword.length < 8) {
      setError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setSubmitting(true);
    try {
      await api.changePassword(currentPassword, newPassword);
      setCurrentPassword("");
      setNewPassword("");
      setConfirm("");
      toast.success("Password updated");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Password change failed");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <form className="space-y-4 max-w-sm" onSubmit={onSubmit} aria-label="Change password">
      <div className="space-y-2">
        <Label htmlFor="account-current-password">Current password</Label>
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
        <Label htmlFor="account-new-password">New password</Label>
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
        <p className="text-xs text-muted-foreground">At least 8 characters.</p>
      </div>
      <div className="space-y-2">
        <Label htmlFor="account-confirm-password">Confirm new password</Label>
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
        {submitting ? "Saving…" : "Save password"}
      </Button>
    </form>
  );
}

function DisableAuthDialog({ username }: { username: string }) {
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
      toast.success("Authentication disabled");
      setPassword("");
      setOpen(false);
      // The install is now wide open — drop cached auth state and
      // send the user home. /login no longer applies.
      queryClient.removeQueries({ queryKey: ["auth-status"] });
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to disable auth");
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
          <ShieldOff className="h-4 w-4" /> Disable login
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2">
            <ShieldAlert className="h-5 w-5 text-destructive" />
            Disable login for this FiestaBoard?
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-3 text-sm">
              <p>
                Turning off login removes the <span className="font-mono">{username}</span> account and opens this
                FiestaBoard up to anyone who can reach it on the network — they&apos;ll be able to read your API keys,
                change your board configuration, and modify any settings.
              </p>
              <p>
                Only do this if this device is on a fully trusted private network (no roommates, no guests, no
                smart-home devices you don&apos;t control). Strongly <strong>not recommended</strong> if this
                FiestaBoard is reachable from the internet.
              </p>
              <p>
                Your board keeps displaying as normal either way — this only controls who can sign in to change
                settings.
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <form onSubmit={onConfirm} className="space-y-3">
          <div className="space-y-2">
            <Label htmlFor="disable-auth-password">Confirm your current password to continue</Label>
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
              Cancel
            </Button>
            <Button type="submit" variant="destructive" disabled={submitting || !password}>
              {submitting ? "Disabling…" : "Yes, disable login"}
            </Button>
          </AlertDialogFooter>
        </form>
      </AlertDialogContent>
    </AlertDialog>
  );
}

function EnableLoginCard() {
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
      toast.error(err instanceof Error ? err.message : "Could not enable login");
      setSubmitting(false);
    }
  };

  return (
    <Card className="border-brand/40">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4 text-brand" />
          Turn on login
        </CardTitle>
        <CardDescription>
          Login is currently <strong>off</strong>. Anyone who can reach this FiestaBoard on the network can read your
          API keys, change your board configuration, and modify any settings.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Strongly recommended if you share Wi-Fi with people you don&apos;t fully trust (roommates, guests, smart-home
          devices), or if this FiestaBoard is reachable from the internet. Your board keeps displaying as normal either
          way — login only controls who can sign in to change settings.
        </p>
        <Button type="button" variant="brand" onClick={onEnable} disabled={submitting}>
          <ShieldCheck className="h-4 w-4" />
          {submitting ? "Enabling…" : "Set up a username & password"}
        </Button>
      </CardContent>
    </Card>
  );
}
