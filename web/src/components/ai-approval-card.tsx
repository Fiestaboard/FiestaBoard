"use client";

import { Box, Button, Card, Flex, Text } from "@fiestaboard/ui";
import { Hand } from "lucide-react";
import { useEffect, useRef } from "react";

import { detailForTool, labelForTool } from "@/components/ai-tool-labels";
import { useTranslations } from "@/i18n/translations";
import type { ToolCall } from "@/lib/ai-chat-types";

export interface AiApprovalCardProps {
  /** The destructive call the turn is paused on. */
  call: ToolCall;
  onApprove: () => void;
  onDeny: () => void;
  /**
   * "Approve and don't ask again in this chat". Offered only when given AND
   * the call is not system-gated: restart, shutdown and update ask every
   * time, whatever the user chose for the rest of the conversation.
   */
  onApproveAll?: () => void;
  /** True while the resume request is in flight. */
  busy?: boolean;
}

const DESCRIPTION_KEYS: Record<string, string> = {
  delete_page: "description.deletePage",
  delete_schedule: "description.deleteSchedule",
  delete_collection: "description.deleteCollection",
  uninstall_plugin: "description.uninstallPlugin",
  trigger_system_update: "description.triggerSystemUpdate",
};

/**
 * Approve / Deny for a tool the MCP server annotates as destructive. The
 * server has already emitted the `tool_call` and ended the stream with
 * `awaiting_approval`; nothing runs until Approve re-POSTs the transcript.
 *
 * Deny takes focus when the card mounts: the safe answer is one keypress
 * away, and a stray Enter on the composer cannot approve a delete.
 */
export function AiApprovalCard({ call, onApprove, onDeny, onApproveAll, busy = false }: AiApprovalCardProps) {
  const t = useTranslations("aiApprovalCard");
  const tools = useTranslations("aiChatPanel");
  const denyRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    denyRef.current?.focus();
  }, []);

  const detail = detailForTool(call);
  const descriptionKey = DESCRIPTION_KEYS[call.name];
  const offerApproveAll = onApproveAll !== undefined && !call.system_gated;

  return (
    <Card
      data-testid="ai-approval-card"
      role="group"
      aria-label={t("heading")}
      className="gap-2 border-destructive/40 px-3 py-3"
    >
      <Flex align="center" gap="2">
        <Hand className="size-4 shrink-0 text-hue-yellow" aria-hidden="true" />
        <Text as="span" size="sm" weight="semibold">
          {t("heading")}
        </Text>
      </Flex>
      <Box>
        <Text size="sm">
          {labelForTool(call, tools)}
          {detail ? (
            <Text as="span" tone="muted">
              {" · "}
              {detail}
            </Text>
          ) : null}
        </Text>
        <Text size="xs" tone="muted" className="mt-0.5">
          {descriptionKey ? t(descriptionKey, { detail: detail ?? "" }) : t("description.generic")}
        </Text>
      </Box>
      <Flex gap="2" align="center" justify="end" className="flex-wrap">
        {offerApproveAll ? (
          <Button
            type="button"
            size="sm"
            variant="ghost"
            className="mr-auto text-xs text-muted-foreground"
            onClick={onApproveAll}
            disabled={busy}
          >
            {t("approveAll")}
          </Button>
        ) : null}
        <Button ref={denyRef} type="button" size="sm" variant="outline" onClick={onDeny} disabled={busy}>
          {t("deny")}
        </Button>
        <Button type="button" size="sm" variant="destructive" onClick={onApprove} disabled={busy}>
          {busy ? t("working") : t("approve")}
        </Button>
      </Flex>
    </Card>
  );
}
