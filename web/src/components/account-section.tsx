"use client";

/**
 * Account settings card shown on the profile page when authentication is
 * enabled. Lets the signed-in admin:
 *
 *   - change their username (gated by current password)
 *   - change their password
 *   - sign out
 *
 * Hides itself entirely when auth is disabled so local-only installs see
 * no UI clutter related to a feature they aren't using.
 */

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ShieldCheck, LogOut } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
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

  // Hide the section entirely when auth is off or the user isn't signed in.
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
  if (!authStatus || !authStatus.enabled || !authStatus.authenticated) {
    return null;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          Account
        </CardTitle>
        <CardDescription>
          Signed in as{" "}
          <span className="font-mono">{authStatus.username ?? "—"}</span>
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        <ChangeUsernameForm currentUsername={authStatus.username ?? ""} />
        <div className="border-t" />
        <ChangePasswordForm />
        <div className="border-t" />
        <Button
          type="button"
          variant="outline"
          onClick={async () => {
            try {
              await api.logout();
            } catch {
              // Ignore — the server-side cookie clear is best-effort and
              // we want the redirect to happen either way.
            }
            queryClient.removeQueries({ queryKey: ["auth-status"] });
            router.replace("/login");
          }}
        >
          <LogOut className="h-4 w-4" /> Sign out
        </Button>
      </CardContent>
    </Card>
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
    <form className="space-y-3 max-w-sm" onSubmit={onSubmit} aria-label="Change username">
      <h3 className="text-sm font-medium">Change username</h3>
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
    <form className="space-y-3 max-w-sm" onSubmit={onSubmit} aria-label="Change password">
      <h3 className="text-sm font-medium">Change password</h3>
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
