"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  Badge,
  Box,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  Code,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Check, Copy, KeyRound, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { api } from "@/lib/api";

/**
 * Build the Claude Desktop config snippet the user will paste into
 * ``~/Library/Application Support/Claude/claude_desktop_config.json``.
 *
 * Claude Desktop's ``mcpServers`` only accepts **stdio** entries, so for a
 * remote HTTP MCP server like FiestaBoard we wrap it with the ``mcp-remote``
 * Node proxy. The trailing slash on the URL matters: hitting ``/api/mcp``
 * triggers a FastAPI 307 to ``/api/mcp/`` that drops the ``:4420`` port,
 * which Node's fetch follows and times out on. ``--allow-http`` is required
 * because the proxy refuses plaintext targets by default.
 *
 * URL host/protocol come from ``window.location`` so the snippet matches
 * however the user is currently reaching FiestaBoard (``localhost``,
 * ``fiestaboard.local``, a LAN IP, etc.).
 */
function buildClaudeDesktopConfig(token: string): string {
  let host = "fiestaboard.local:4420";
  if (typeof window !== "undefined" && window.location?.host) {
    host = window.location.host;
  }
  const proto = typeof window !== "undefined" && window.location?.protocol === "https:" ? "https" : "http";
  const url = `${proto}://${host}/api/mcp/`;
  const args = ["-y", "mcp-remote", url];
  if (proto === "http") args.push("--allow-http");
  args.push("--header", `Authorization: Bearer ${token}`);
  const config = {
    mcpServers: {
      fiestaboard: {
        command: "npx",
        args,
      },
    },
  };
  return JSON.stringify(config, null, 2);
}

export function McpSettings() {
  const queryClient = useQueryClient();
  const [revealedToken, setRevealedToken] = useState<string | null>(null);
  const [confirmingRotate, setConfirmingRotate] = useState(false);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [copied, setCopied] = useState<"token" | "config" | null>(null);

  const { data: status, isLoading } = useQuery({
    queryKey: ["mcp-token-status"],
    queryFn: () => api.getMcpTokenStatus(),
  });

  const rotateMutation = useMutation({
    mutationFn: () => api.rotateMcpToken(),
    onSuccess: ({ token }) => {
      setRevealedToken(token);
      setConfirmingRotate(false);
      queryClient.invalidateQueries({ queryKey: ["mcp-token-status"] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
      setConfirmingRotate(false);
    },
  });

  const clearMutation = useMutation({
    mutationFn: () => api.clearMcpToken(),
    onSuccess: () => {
      toast.success("MCP token revoked");
      setConfirmingClear(false);
      queryClient.invalidateQueries({ queryKey: ["mcp-token-status"] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
      setConfirmingClear(false);
    },
  });

  const handleCopy = async (text: string, which: "token" | "config") => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(which);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      toast.error("Couldn't copy to clipboard");
    }
  };

  const configSnippet = useMemo(() => (revealedToken ? buildClaudeDesktopConfig(revealedToken) : ""), [revealedToken]);

  if (isLoading || !status) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-44" />
          <Skeleton className="h-4 w-72" />
        </CardHeader>
      </Card>
    );
  }

  const isPinnedByEnv = status.source === "env";
  const hasToken = status.configured;
  const rotateLabel = hasToken ? "Rotate token" : "Generate token";

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Bot className="h-4 w-4" />
            MCP / external clients
          </CardTitle>
          <CardDescription>
            A pre-shared token that lets Claude Desktop, Claude Code, and other MCP clients talk to this FiestaBoard.
            The token authenticates as a single principal — scoped to the{" "}
            <Code className="font-mono text-xs">/api/mcp</Code> endpoint only — so it can&apos;t edit pages or other
            settings. See{" "}
            <TextLink
              href="https://github.com/Fiestaboard/FiestaBoard/blob/main/docs/setup/MCP_CLIENTS.md"
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2"
            >
              MCP client setup
            </TextLink>{" "}
            for client-specific quirks (Desktop needs an stdio proxy; claude.ai web Connectors require public HTTPS and
            OAuth, so they won&apos;t reach a LAN host).
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Flex align="center" gap="2">
            <Text as="span" size="sm" weight="medium">
              Status:
            </Text>
            {isPinnedByEnv ? (
              <Badge variant="secondary" className="gap-1.5">
                <KeyRound className="h-3 w-3" />
                Pinned by FIESTABOARD_MCP_TOKEN
              </Badge>
            ) : hasToken ? (
              <Badge variant="default" className="gap-1.5 bg-emerald-600 hover:bg-emerald-600">
                <Check className="h-3 w-3" />
                Configured
              </Badge>
            ) : (
              <Badge variant="outline">Not configured</Badge>
            )}
          </Flex>

          {isPinnedByEnv && (
            <Text tone="muted">
              The active token is set by the <Code className="font-mono text-xs">FIESTABOARD_MCP_TOKEN</Code>{" "}
              environment variable. Unset it in your <Code className="font-mono text-xs">.env</Code> and restart the
              container before managing the token from this UI.
            </Text>
          )}

          {!isPinnedByEnv && !hasToken && (
            <Text tone="muted">
              No token is configured. External MCP clients will fall back to cookie auth, which Claude Desktop / Claude
              Code don&apos;t support — they&apos;ll fail registration with an opaque error. Generate a token to unblock
              them.
            </Text>
          )}

          {!isPinnedByEnv && hasToken && (
            <Text tone="muted">
              A token is configured and active. Rotate it to invalidate the previous one (any client still using the old
              token will start receiving 401), or revoke it entirely to fall back to cookie-only auth.
            </Text>
          )}

          {!isPinnedByEnv && (
            <Flex wrap gap="2">
              <Button
                onClick={() => setConfirmingRotate(true)}
                disabled={rotateMutation.isPending}
                variant="default"
                className="gap-2"
              >
                {rotateMutation.isPending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
                {rotateLabel}
              </Button>
              {hasToken && (
                <Button
                  onClick={() => setConfirmingClear(true)}
                  disabled={clearMutation.isPending}
                  variant="outline"
                  className="gap-2"
                >
                  {clearMutation.isPending ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    <Trash2 className="h-4 w-4" />
                  )}
                  Revoke token
                </Button>
              )}
            </Flex>
          )}
        </CardContent>
      </Card>

      {/* "Are you sure you want to rotate?" — only shown when there's an
          existing token whose rotation would invalidate something. */}
      <AlertDialog open={confirmingRotate} onOpenChange={(open) => !open && setConfirmingRotate(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{hasToken ? "Rotate MCP token?" : "Generate MCP token?"}</AlertDialogTitle>
            <AlertDialogDescription>
              {hasToken
                ? "Any client still using the previous token will be denied with a 401 + Bearer challenge on its next request. You'll see the new token once — store it somewhere safe (it's not readable from the UI again)."
                : "You'll see the token once — store it somewhere safe (it's not readable from the UI again). External MCP clients will use it to authenticate to /api/mcp."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={rotateMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => rotateMutation.mutate()} disabled={rotateMutation.isPending}>
              {rotateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {hasToken ? "Rotate" : "Generate"}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmingClear} onOpenChange={(open) => !open && setConfirmingClear(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Revoke MCP token?</AlertDialogTitle>
            <AlertDialogDescription>
              External MCP clients will start receiving 401 on their next request. You can always generate a new token
              later.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={clearMutation.isPending}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {clearMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              Revoke
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Reveal-once dialog. Stays open until the user dismisses it, so we
          don't auto-close on an accidental click outside. */}
      <Dialog
        open={revealedToken !== null}
        onOpenChange={(open) => {
          if (!open) setRevealedToken(null);
        }}
      >
        <DialogContent className="sm:max-w-xl">
          <DialogHeader>
            <DialogTitle>Save this token</DialogTitle>
            <DialogDescription className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-500" />
              <Text as="span" size="sm" tone="muted">
                FiestaBoard stores only what&apos;s needed to verify future requests — this is the only time the
                plaintext value is shown. Copy it into your MCP client now.
              </Text>
            </DialogDescription>
          </DialogHeader>

          <Stack gap="4">
            <Box>
              <Flex align="center" justify="between" className="mb-1.5">
                <Text as="span" size="sm" weight="medium">
                  Token
                </Text>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => revealedToken && handleCopy(revealedToken, "token")}
                  className="h-7 gap-1.5"
                >
                  {copied === "token" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied === "token" ? "Copied" : "Copy"}
                </Button>
              </Flex>
              <Code className="block w-full break-all rounded bg-muted px-3 py-2 font-mono text-xs">
                {revealedToken}
              </Code>
            </Box>

            <Box>
              <Flex align="center" justify="between" className="mb-1.5">
                <Text as="span" size="sm" weight="medium">
                  Claude Desktop config snippet
                </Text>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleCopy(configSnippet, "config")}
                  className="h-7 gap-1.5"
                >
                  {copied === "config" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied === "config" ? "Copied" : "Copy"}
                </Button>
              </Flex>
              <Text size="xs" tone="muted" className="mb-2">
                Paste this into{" "}
                <Code className="font-mono">~/Library/Application Support/Claude/claude_desktop_config.json</Code>,
                merging with anything that&apos;s already there, then fully quit and relaunch Claude Desktop (⌘Q —
                closing the window isn&apos;t enough). Claude Desktop only supports stdio MCP servers, so this snippet
                shells out to{" "}
                <TextLink
                  href="https://www.npmjs.com/package/mcp-remote"
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2"
                >
                  mcp-remote
                </TextLink>{" "}
                via <Code className="font-mono">npx</Code> as a proxy — Node 18+ must be installed and{" "}
                <Code className="font-mono">npx</Code> reachable from Claude Desktop&apos;s PATH. If it errors with{" "}
                <Code className="font-mono">command not found</Code>, replace{" "}
                <Code className="font-mono">&quot;npx&quot;</Code> with the absolute path from{" "}
                <Code className="font-mono">which npx</Code>.
              </Text>
              <pre className="max-h-64 overflow-auto rounded bg-muted px-3 py-2 font-mono text-xs">{configSnippet}</pre>
            </Box>

            <Text size="xs" tone="muted">
              <Text as="span" size="xs" weight="semibold" tone="muted">
                Claude Code (CLI):
              </Text>{" "}
              talks HTTP directly — no proxy needed.
              <br />
              <Code className="font-mono">
                claude mcp add fiestaboard --transport http --url{" "}
                {typeof window !== "undefined"
                  ? `${window.location.protocol}//${window.location.host}`
                  : "http://fiestaboard.local:4420"}
                /api/mcp/ --header &quot;Authorization: Bearer &lt;token&gt;&quot;
              </Code>
            </Text>
            <Text size="xs" tone="muted">
              <Text as="span" size="xs" weight="semibold" tone="muted">
                claude.ai web (Connectors):
              </Text>{" "}
              not supported for self-hosted FiestaBoard. The Connectors flow requires a public HTTPS URL and OAuth 2.1
              dynamic client registration, neither of which a LAN host can provide. Use Desktop or Code instead.
            </Text>
          </Stack>

          <DialogFooter>
            <Button onClick={() => setRevealedToken(null)}>I&apos;ve saved it</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
