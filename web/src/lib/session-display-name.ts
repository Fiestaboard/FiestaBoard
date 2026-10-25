import type { SessionSummary } from "./api/sessions";

/** Readable presentation of legacy browser UA names; metadata is not device attestation. */
export function sessionDisplayName(
  session: Pick<SessionSummary, "kind" | "device_name">,
  browserFallback: string,
): string {
  const name = session.device_name;
  if (session.kind !== "browser" || !/^Mozilla\//i.test(name)) return name;

  // Edge and Firefox on iOS can also advertise Chrome/Safari compatibility.
  const browser = /\bEdg(?:e|A|iOS)?\//.test(name)
    ? "Edge"
    : /\b(?:Firefox|FxiOS)\//.test(name)
      ? "Firefox"
      : // A truncated Chromium UA may omit the later Edge/Opera identity.
        // Only label Chrome when its full compatibility suffix is present.
        /\b(?:Chrome|CriOS)\/.*\bSafari\/[\d.]+$/.test(name) && !/\b(?:OPR|SamsungBrowser)\//.test(name)
        ? "Chrome"
        : /\bVersion\//.test(name) && /\bAppleWebKit\//.test(name)
          ? "Safari"
          : browserFallback;
  const platform = /\b(?:iPhone|iPad|iPod)\b/.test(name)
    ? "iOS"
    : /\bAndroid\b/.test(name)
      ? "Android"
      : /\bWindows\b/.test(name)
        ? "Windows"
        : /\bMacintosh\b|\bMac OS X\b/.test(name)
          ? "macOS"
          : /\bLinux\b/.test(name)
            ? "Linux"
            : null;
  return platform ? `${browser} · ${platform}` : browser;
}
