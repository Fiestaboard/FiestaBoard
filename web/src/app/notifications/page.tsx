"use client";

import { useState, useCallback } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Bell,
  Plus,
  Trash2,
  Clock,
  Loader2,
  Play,
  XCircle,
  MessageSquare,
} from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { PageHeader } from "@/components/page-header";
import { PageLayout } from "@/components/page-layout";
import { PageToolbar } from "@/components/page-toolbar";
import type { Notification, NotificationCreate } from "@/lib/api";
import { queryKeys } from "@/hooks/use-board";
import { useTranslations } from "next-intl";

const PRIORITY_PRESETS = [
  { label: "0", value: 0 },
  { label: "1", value: 1 },
  { label: "2", value: 2 },
  { label: "3", value: 3 },
  { label: "4", value: 4 },
  { label: "5", value: 5 },
  { label: "6", value: 6 },
  { label: "7", value: 7 },
  { label: "8", value: 8 },
  { label: "9", value: 9 },
  { label: "10", value: 10 },
];

const DURATION_PRESETS = [
  { label: "15s", value: 15 },
  { label: "30s", value: 30 },
  { label: "1m", value: 60 },
  { label: "2m", value: 120 },
  { label: "5m", value: 300 },
  { label: "10m", value: 600 },
];

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m`;
}

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function priorityLabel(priority: number): string {
  if (priority >= 7) return "High";
  if (priority >= 4) return "Medium";
  return "Low";
}

function statusVariant(status: string): "default" | "secondary" | "outline" {
  switch (status) {
    case "queued":
      return "default";
    case "displayed":
      return "secondary";
    default:
      return "outline";
  }
}

/* ── Create / Edit Form ─────────────────────────────────── */
interface NotificationFormProps {
  onSubmit: (data: NotificationCreate) => Promise<void>;
  onCancel: () => void;
  isSubmitting: boolean;
}

function NotificationForm({
  onSubmit,
  onCancel,
  isSubmitting,
}: NotificationFormProps) {
  const t = useTranslations("notifications");
  const tc = useTranslations("common");
  const [message, setMessage] = useState("");
  const [priority, setPriority] = useState(0);
  const [durationSeconds, setDurationSeconds] = useState(30);

  const handleSubmit = async () => {
    if (!message.trim()) return;
    await onSubmit({ message: message.trim(), priority, duration_seconds: durationSeconds });
  };

  return (
    <div className="space-y-4 pt-4">
      <div className="space-y-2">
        <Label htmlFor="notification-message">{t("message")}</Label>
        <Input
          id="notification-message"
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder={t("messagePlaceholder")}
          maxLength={132}
        />
        <p className="text-xs text-muted-foreground">{message.length}/132</p>
      </div>

      <div className="space-y-2">
        <Label htmlFor="notification-priority">{t("priority")}</Label>
        <Select
          value={String(priority)}
          onValueChange={(v) => setPriority(Number(v))}
        >
          <SelectTrigger id="notification-priority">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRIORITY_PRESETS.map((p) => (
              <SelectItem key={p.value} value={String(p.value)}>
                {p.label} – {priorityLabel(p.value)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="notification-duration">{t("duration")}</Label>
        <Select
          value={String(durationSeconds)}
          onValueChange={(v) => setDurationSeconds(Number(v))}
        >
          <SelectTrigger id="notification-duration">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {DURATION_PRESETS.map((d) => (
              <SelectItem key={d.value} value={String(d.value)}>
                {d.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex gap-2 pt-2">
        <Button
          onClick={handleSubmit}
          disabled={!message.trim() || isSubmitting}
          className="flex-1"
        >
          {isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          {tc("save")}
        </Button>
        <Button variant="outline" onClick={onCancel}>
          {tc("cancel")}
        </Button>
      </div>
    </div>
  );
}

/* ── Notification Card ────────────────────────────────────── */
interface NotificationCardProps {
  notification: Notification;
  onDelete: (id: string) => void;
  onDisplay?: (id: string) => void;
  onExpire?: (id: string) => void;
}

function NotificationCard({
  notification,
  onDelete,
  onDisplay,
  onExpire,
}: NotificationCardProps) {
  const t = useTranslations("notifications");

  return (
    <Card className="animate-card-fade-in">
      <CardContent className="flex items-start justify-between gap-4 py-4 px-5">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Badge variant={statusVariant(notification.status)}>
              {t(notification.status)}
            </Badge>
            {notification.priority > 0 && (
              <Badge variant="outline">
                P{notification.priority} – {priorityLabel(notification.priority)}
              </Badge>
            )}
            <span className="text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" />
              {formatDuration(notification.duration_seconds)}
            </span>
          </div>
          <p className="text-sm font-medium break-words">
            <MessageSquare className="inline h-3.5 w-3.5 mr-1 text-muted-foreground" />
            {notification.message}
          </p>
          <div className="text-xs text-muted-foreground space-x-3">
            <span>{t("createdAt")}: {formatTimestamp(notification.created_at)}</span>
            {notification.displayed_at && (
              <span>{t("displayedAt")}: {formatTimestamp(notification.displayed_at)}</span>
            )}
            {notification.expired_at && (
              <span>{t("expiredAt")}: {formatTimestamp(notification.expired_at)}</span>
            )}
          </div>
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {notification.status === "queued" && onDisplay && (
            <Button size="icon" variant="ghost" onClick={() => onDisplay(notification.id)} title={t("displayNow")}>
              <Play className="h-4 w-4" />
            </Button>
          )}
          {notification.status === "displayed" && onExpire && (
            <Button size="icon" variant="ghost" onClick={() => onExpire(notification.id)} title={t("markExpired")}>
              <XCircle className="h-4 w-4" />
            </Button>
          )}
          <Button size="icon" variant="ghost" onClick={() => onDelete(notification.id)} className="text-destructive hover:text-destructive">
            <Trash2 className="h-4 w-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/* ── Main Page ────────────────────────────────────────────── */
export default function NotificationsPage() {
  const t = useTranslations("notifications");
  const tc = useTranslations("common");
  const queryClient = useQueryClient();

  const [sheetOpen, setSheetOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: queryKeys.notifications,
    queryFn: api.getNotifications,
    refetchInterval: 10000,
  });

  const notifications = data?.notifications ?? [];
  const queued = notifications.filter((n) => n.status === "queued");
  const history = notifications.filter((n) => n.status === "displayed" || n.status === "expired");

  const createMutation = useMutation({
    mutationFn: (data: NotificationCreate) => api.createNotification(data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteNotification(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });

  const displayMutation = useMutation({
    mutationFn: (id: string) => api.displayNotification(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });

  const expireMutation = useMutation({
    mutationFn: (id: string) => api.expireNotification(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: queryKeys.notifications }),
  });

  const handleCreate = useCallback(
    async (data: NotificationCreate) => {
      return new Promise<void>((resolve, reject) => {
        createMutation.mutate(data, {
          onSuccess: () => {
            toast.success(t("created"));
            setSheetOpen(false);
            resolve();
          },
          onError: (error) => {
            toast.error(`${t("createFailed")}: ${error.message}`);
            reject(error);
          },
        });
      });
    },
    [createMutation, t],
  );

  const handleDelete = useCallback(
    (id: string) => {
      deleteMutation.mutate(id, {
        onSuccess: () => {
          toast.success(t("deleted"));
          setDeleteTarget(null);
        },
        onError: (error) => toast.error(`${t("deleteFailed")}: ${error.message}`),
      });
    },
    [deleteMutation, t],
  );

  const handleDisplay = useCallback(
    (id: string) => {
      displayMutation.mutate(id, {
        onSuccess: () => toast.success(t("displayed")),
        onError: (error) => toast.error(error.message),
      });
    },
    [displayMutation, t],
  );

  const handleExpire = useCallback(
    (id: string) => {
      expireMutation.mutate(id, {
        onSuccess: () => toast.success(t("expired")),
        onError: (error) => toast.error(error.message),
      });
    },
    [expireMutation, t],
  );

  return (
    <PageLayout>
      <PageHeader
        icon={Bell}
        title={t("title")}
        description={t("description")}
      />

      <PageToolbar
        right={
          <Button onClick={() => setSheetOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            {t("createNotification")}
          </Button>
        }
      />

      <Tabs defaultValue="queue" className="animate-card-fade-in" style={{ animationDelay: "100ms" }}>
        <TabsList>
          <TabsTrigger value="queue">
            {t("queue")} {queued.length > 0 && `(${queued.length})`}
          </TabsTrigger>
          <TabsTrigger value="history">
            {t("history")} {history.length > 0 && `(${history.length})`}
          </TabsTrigger>
        </TabsList>

        <TabsContent value="queue" className="space-y-3 mt-4">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-xl" />
              ))}
            </div>
          ) : queued.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                <Bell className="mx-auto h-8 w-8 mb-2 opacity-50" />
                <p>{t("noQueuedNotifications")}</p>
              </CardContent>
            </Card>
          ) : (
            queued.map((n) => (
              <NotificationCard
                key={n.id}
                notification={n}
                onDelete={(id) => setDeleteTarget(id)}
                onDisplay={handleDisplay}
              />
            ))
          )}
        </TabsContent>

        <TabsContent value="history" className="space-y-3 mt-4">
          {isLoading ? (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <Skeleton key={i} className="h-24 w-full rounded-xl" />
              ))}
            </div>
          ) : history.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-muted-foreground">
                <Clock className="mx-auto h-8 w-8 mb-2 opacity-50" />
                <p>{t("noHistory")}</p>
              </CardContent>
            </Card>
          ) : (
            history.map((n) => (
              <NotificationCard
                key={n.id}
                notification={n}
                onDelete={(id) => setDeleteTarget(id)}
                onExpire={n.status === "displayed" ? handleExpire : undefined}
              />
            ))
          )}
        </TabsContent>
      </Tabs>

      {/* Create notification sheet */}
      <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
        <SheetContent>
          <SheetHeader>
            <SheetTitle>{t("createNotification")}</SheetTitle>
            <SheetDescription>{t("description")}</SheetDescription>
          </SheetHeader>
          <NotificationForm
            onSubmit={handleCreate}
            onCancel={() => setSheetOpen(false)}
            isSubmitting={createMutation.isPending}
          />
        </SheetContent>
      </Sheet>

      {/* Delete confirmation dialog */}
      <AlertDialog open={!!deleteTarget} onOpenChange={() => setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("deleteConfirmTitle")}</AlertDialogTitle>
            <AlertDialogDescription>{t("deleteConfirmDescription")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tc("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => deleteTarget && handleDelete(deleteTarget)}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {tc("delete")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </PageLayout>
  );
}
