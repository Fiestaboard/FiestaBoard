import { stripBasePath } from "./base-path";

/** Return a router-relative destination, never an authority or an escaped path. */
export function safeRedirect(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/";
  const target = stripBasePath(value);
  let decoded = target;
  // Reject encoded delimiters even when nested. Decoding is for validation only.
  for (let depth = 0; depth < 8; depth++) {
    if (/[\\\u0000-\u0020\u007f]/.test(decoded) || decoded.startsWith("//")) return "/";
    const pathname = decoded.split(/[?#]/, 1)[0];
    if (pathname.split("/").some((part) => part === "." || part === "..")) return "/";
    try {
      const next = decodeURIComponent(decoded);
      if (next === decoded) return target;
      decoded = next;
    } catch {
      return "/";
    }
  }
  return "/";
}
