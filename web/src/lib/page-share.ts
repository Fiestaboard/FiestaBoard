/**
 * A page's portable share string, made in the browser from what the editor
 * holds (UX-1-4: Export works on unsaved edits and on a new page, the way
 * Docs exports the document as it is). Same envelope as the hub's
 * `src/pages/share.py` `encode_page`: base64url of `{"v":1,"page":{…}}`,
 * unpadded, without the server's identity fields, `demo_plugin_id` or tags.
 */
const SHARE_VERSION = 1;
const EXCLUDED = new Set([
  "id",
  "created_at",
  "updated_at",
  "revision",
  "expected_revision",
  "edit_protocol",
  "document_protocol",
  "demo_plugin_id",
  "tags",
]);

export function encodePageShareString(page: Record<string, unknown>): string {
  const content = Object.fromEntries(
    Object.entries(page).filter(([key, value]) => !EXCLUDED.has(key) && value !== undefined),
  );
  const bytes = new TextEncoder().encode(JSON.stringify({ v: SHARE_VERSION, page: content }));
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
