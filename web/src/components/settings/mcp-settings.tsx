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
  Code,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Flex,
  PageSection,
  Skeleton,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Bot, Check, Copy, KeyRound, Loader2, RefreshCw, Trash2 } from "lucide-react";
import { type ReactNode, useMemo, useState } from "react";
import { toast } from "sonner";

import { useTranslations } from "@/i18n/translations";
import { api } from "@/lib/api";

/** Env var that pins the MCP token when set — never translated. */
const MCP_TOKEN_ENV_VAR = "FIESTABOARD_MCP_TOKEN";

/** MCP endpoint path — never translated. */
const MCP_ENDPOINT = "/api/mcp";

/** npm package name of the stdio proxy Claude Desktop shells out to — never translated. */
const MCP_REMOTE_PACKAGE = "mcp-remote";

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
  const t = useTranslations("mcpSettings");
  const tCommon = useTranslations("common");
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
      toast.success(t("toastTokenRevoked"));
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
      toast.error(t("toastCopyFailed"));
    }
  };

  const configSnippet = useMemo(() => (revealedToken ? buildClaudeDesktopConfig(revealedToken) : ""), [revealedToken]);

  if (isLoading || !status) {
    return (
      <PageSection>
        <Skeleton className="h-5 w-44" />
        <Skeleton className="mt-2 h-4 w-72" />
      </PageSection>
    );
  }

  const isPinnedByEnv = status.source === "env";
  const hasToken = status.configured;
  const rotateLabel = hasToken ? t("rotateTokenButton") : t("generateTokenButton");

  return (
    <>
      <PageSection
        icon={<Bot />}
        title={t("title")}
        description={
          <>
            {t.rich("description", {
              endpoint: () => <Code className="font-mono text-xs">{MCP_ENDPOINT}</Code>,
              link: (chunks: ReactNode) => (
                <TextLink
                  href="https://github.com/Fiestaboard/FiestaBoard/blob/main/docs/setup/MCP_CLIENTS.md"
                  target="_blank"
                  rel="noreferrer"
                  className="underline underline-offset-2"
                >
                  {chunks}
                </TextLink>
              ),
            })}
          </>
        }
        className="space-y-4"
      >
        <Flex align="center" gap="2">
          <Text as="span" size="sm" weight="medium">
            {t("statusLabel")}
          </Text>
          {isPinnedByEnv ? (
            <Badge variant="secondary" className="gap-1.5">
              <KeyRound className="h-3 w-3" />
              {t("pinnedByEnvBadge", { envVar: MCP_TOKEN_ENV_VAR })}
            </Badge>
          ) : hasToken ? (
            <Badge variant="default" className="gap-1.5 bg-emerald-600 hover:bg-emerald-600">
              <Check className="h-3 w-3" />
              {t("configuredBadge")}
            </Badge>
          ) : (
            <Badge variant="outline">{tCommon("notConfigured")}</Badge>
          )}
        </Flex>

        {isPinnedByEnv && (
          <Text tone="muted">
            {t.rich("pinnedByEnvDescription", {
              envVar: () => <Code className="font-mono text-xs">{MCP_TOKEN_ENV_VAR}</Code>,
              envFile: () => <Code className="font-mono text-xs">.env</Code>,
            })}
          </Text>
        )}

        {!isPinnedByEnv && !hasToken && <Text tone="muted">{t("noTokenDescription")}</Text>}

        {!isPinnedByEnv && hasToken && <Text tone="muted">{t("activeTokenDescription")}</Text>}

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
                {t("revokeTokenButton")}
              </Button>
            )}
          </Flex>
        )}
      </PageSection>

      {/* "Are you sure you want to rotate?" — only shown when there's an
          existing token whose rotation would invalidate something. */}
      <AlertDialog open={confirmingRotate} onOpenChange={(open) => !open && setConfirmingRotate(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{hasToken ? t("rotateConfirmTitle") : t("generateConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>
              {hasToken ? t("rotateConfirmDescription") : t("generateConfirmDescription", { endpoint: MCP_ENDPOINT })}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={rotateMutation.isPending}>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => rotateMutation.mutate()} disabled={rotateMutation.isPending}>
              {rotateMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {hasToken ? t("rotateConfirmButton") : t("generateConfirmButton")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={confirmingClear} onOpenChange={(open) => !open && setConfirmingClear(false)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("revokeConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("revokeConfirmDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={clearMutation.isPending}>{tCommon("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => clearMutation.mutate()}
              disabled={clearMutation.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {clearMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : null}
              {t("revokeConfirmButton")}
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
            <DialogTitle>{t("revealTitle")}</DialogTitle>
            <DialogDescription className="flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 flex-shrink-0 text-amber-500" />
              <Text as="span" size="sm" tone="muted">
                {t("revealDescription")}
              </Text>
            </DialogDescription>
          </DialogHeader>

          <Stack gap="4">
            <Box>
              <Flex align="center" justify="between" className="mb-1.5">
                <Text as="span" size="sm" weight="medium">
                  {t("tokenLabel")}
                </Text>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => revealedToken && handleCopy(revealedToken, "token")}
                  className="h-7 gap-1.5"
                >
                  {copied === "token" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied === "token" ? t("copiedButton") : t("copyButton")}
                </Button>
              </Flex>
              <Code className="block w-full break-all rounded bg-muted px-3 py-2 font-mono text-xs">
                {revealedToken}
              </Code>
            </Box>

            <Box>
              <Flex align="center" justify="between" className="mb-1.5">
                <Text as="span" size="sm" weight="medium">
                  {t("configSnippetLabel")}
                </Text>
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={() => handleCopy(configSnippet, "config")}
                  className="h-7 gap-1.5"
                >
                  {copied === "config" ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
                  {copied === "config" ? t("copiedButton") : t("copyButton")}
                </Button>
              </Flex>
              <Text size="xs" tone="muted" className="mb-2">
                {t.rich("configSnippetDescription", {
                  configPath: () => (
                    <Code className="font-mono">~/Library/Application Support/Claude/claude_desktop_config.json</Code>
                  ),
                  mcpRemoteLink: () => (
                    <TextLink
                      href="https://www.npmjs.com/package/mcp-remote"
                      target="_blank"
                      rel="noreferrer"
                      className="underline underline-offset-2"
                    >
                      {MCP_REMOTE_PACKAGE}
                    </TextLink>
                  ),
                  npx: () => <Code className="font-mono">npx</Code>,
                  commandNotFound: () => <Code className="font-mono">command not found</Code>,
                  npxQuoted: () => <Code className="font-mono">&quot;npx&quot;</Code>,
                  whichNpx: () => <Code className="font-mono">which npx</Code>,
                })}
              </Text>
              <pre className="max-h-64 overflow-auto rounded bg-muted px-3 py-2 font-mono text-xs">{configSnippet}</pre>
            </Box>

            <Text size="xs" tone="muted">
              {t.rich("claudeCodeDescription", {
                label: (chunks: ReactNode) => (
                  <Text as="span" size="xs" weight="semibold" tone="muted">
                    {chunks}
                  </Text>
                ),
              })}
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
              {t.rich("claudeWebDescription", {
                label: (chunks: ReactNode) => (
                  <Text as="span" size="xs" weight="semibold" tone="muted">
                    {chunks}
                  </Text>
                ),
              })}
            </Text>
          </Stack>

          <DialogFooter>
            <Button onClick={() => setRevealedToken(null)}>{t("savedItButton")}</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
