import {
  Alert,
  AlertDescription,
  BoardBackdrop,
  Box,
  Button,
  Card,
  FiestaLogo,
  Flex,
  Heading,
  Label,
  SecretInput,
  Stack,
  Text,
  TextLink,
} from "@fiestaboard/ui";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { useTranslations } from "@/i18n/translations";
import { authApi } from "@/lib/api/auth";
import { ApiError } from "@/lib/api/core";
import { appUrl } from "@/lib/base-path";

const RESET_COMMAND = "docker compose exec -u appuser fiestaboard python -m src.auth.password_reset";

export default function ResetPassword() {
  const t = useTranslations("passwordReset");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const codeInput = useRef<HTMLInputElement>(null);
  const confirmInput = useRef<HTMLInputElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    if (done) heading.current?.focus();
  }, [done]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setError(null);
    if (password !== confirm) {
      setError(t("mismatch"));
      confirmInput.current?.focus();
      return;
    }
    setBusy(true);
    try {
      await authApi.resetPassword(code.trim(), password);
      setCode("");
      setPassword("");
      setConfirm("");
      setDone(true);
    } catch (err) {
      setError(
        t(
          err instanceof ApiError && (err.status === 400 || err.status === 422)
            ? "invalid"
            : err instanceof ApiError && err.status === 429
              ? "rateLimited"
              : "network",
        ),
      );
      codeInput.current?.focus();
    } finally {
      setBusy(false);
    }
  }

  return (
    <Flex
      direction="col"
      align="center"
      justify="center"
      className="relative isolate min-h-svh w-screen bg-background px-4 py-6 sm:p-8"
    >
      <meta name="referrer" content="no-referrer" />
      <BoardBackdrop
        phrases={["WELCOME", "GOOD MORNING", "HELLO WORLD", "72 AND CLEAR"]}
        fixed
        className="hidden sm:block"
      />
      <Card className="relative z-10 w-full max-w-[440px] gap-4 p-6 sm:p-8">
        <FiestaLogo size="sm" className="mb-4" />
        <Heading level={1} size="xl" ref={heading} tabIndex={-1}>
          {t(done ? "successTitle" : "title")}
        </Heading>
        {done ? (
          <Stack gap="4">
            <Text role="status" size="sm">
              {t("success")}
            </Text>
            <Text size="xs" tone="muted">
              {t("tokenUnchanged")}
            </Text>
            <TextLink href={appUrl("/login")}>{t("signIn")}</TextLink>
          </Stack>
        ) : (
          <>
            <Text size="sm" tone="muted">
              {t("description")}
            </Text>
            <Stack gap="2" className="rounded-lg bg-muted p-4">
              <Text size="sm">{t("commandHint")}</Text>
              <Text as="span" size="xs" className="break-all font-mono">
                {RESET_COMMAND}
              </Text>
              <Text size="xs" tone="muted" id="reset-code-hint">
                {t("expiry")}
              </Text>
            </Stack>
            <Box as="form" onSubmit={submit} className="space-y-4" aria-busy={busy}>
              {error && (
                <Alert variant="destructive" role="alert">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}
              <Stack gap="1.5">
                <Label htmlFor="reset-code">{t("code")}</Label>
                <SecretInput
                  ref={codeInput}
                  id="reset-code"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  autoComplete="off"
                  autoCapitalize="none"
                  spellCheck={false}
                  required
                  maxLength={256}
                  readOnly={busy}
                  aria-describedby="reset-code-hint"
                  showLabel={t("show")}
                  hideLabel={t("hide")}
                />
              </Stack>
              <Stack gap="1.5">
                <Label htmlFor="new-password">{t("password")}</Label>
                <SecretInput
                  id="new-password"
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={1024}
                  readOnly={busy}
                  aria-describedby="password-hint"
                  showLabel={t("show")}
                  hideLabel={t("hide")}
                />
                <Text id="password-hint" size="xs" tone="muted">
                  {t("passwordHint")}
                </Text>
              </Stack>
              <Stack gap="1.5">
                <Label htmlFor="confirm-password">{t("confirm")}</Label>
                <SecretInput
                  ref={confirmInput}
                  id="confirm-password"
                  value={confirm}
                  onChange={(event) => setConfirm(event.target.value)}
                  autoComplete="new-password"
                  required
                  minLength={8}
                  maxLength={1024}
                  readOnly={busy}
                  showLabel={t("show")}
                  hideLabel={t("hide")}
                />
              </Stack>
              <Text size="xs" tone="muted">
                {t("warning")}
              </Text>
              <Button type="submit" size="lg" className="h-11 w-full sm:h-10" disabled={busy}>
                {t(busy ? "resetting" : "submit")}
              </Button>
              <TextLink href={appUrl("/login")}>{t("back")}</TextLink>
            </Box>
          </>
        )}
      </Card>
    </Flex>
  );
}
