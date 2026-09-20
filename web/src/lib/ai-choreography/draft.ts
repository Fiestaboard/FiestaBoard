// A tolerant reader for a tool block the model is still writing.
//
// The server streams the open fence as `tool_streaming` frames (the whole
// block so far). It is not JSON yet — it ends mid-string more often than
// not — so this walks the text once and keeps only what is complete: the
// tool name, top-level string arguments, and the finished items of
// top-level string arrays, plus the string being written right now so a
// reveal can follow the model's pen. Anything nested or numeric is left
// for the validated `tool_call` that follows.

import type { ToolDraft } from "./types";

interface Reader {
  text: string;
  pos: number;
}

/** Read a JSON string starting at the opening quote. Returns null when unterminated. */
function readString(r: Reader): { value: string; complete: boolean } {
  let out = "";
  let i = r.pos + 1; // past the opening quote
  while (i < r.text.length) {
    const ch = r.text[i];
    if (ch === "\\") {
      const next = r.text[i + 1];
      if (next === undefined) break;
      if (next === "n") out += "\n";
      else if (next === "t") out += "\t";
      else if (next === "u") {
        const hex = r.text.slice(i + 2, i + 6);
        if (hex.length < 4) break;
        out += String.fromCharCode(parseInt(hex, 16));
        i += 4;
      } else out += next;
      i += 2;
      continue;
    }
    if (ch === '"') {
      r.pos = i + 1;
      return { value: out, complete: true };
    }
    out += ch;
    i += 1;
  }
  r.pos = r.text.length;
  return { value: out, complete: false };
}

function skipWs(r: Reader): void {
  while (r.pos < r.text.length && /\s/.test(r.text[r.pos])) r.pos += 1;
}

/** Skip one JSON value we do not keep (number, literal, nested object/array). */
function skipValue(r: Reader): void {
  skipWs(r);
  const ch = r.text[r.pos];
  if (ch === '"') {
    readString(r);
    return;
  }
  if (ch === "{" || ch === "[") {
    let depth = 0;
    let inString = false;
    for (; r.pos < r.text.length; r.pos += 1) {
      const c = r.text[r.pos];
      if (inString) {
        if (c === "\\") r.pos += 1;
        else if (c === '"') inString = false;
        continue;
      }
      if (c === '"') inString = true;
      else if (c === "{" || c === "[") depth += 1;
      else if (c === "}" || c === "]") {
        depth -= 1;
        if (depth === 0) {
          r.pos += 1;
          return;
        }
      }
    }
    return;
  }
  while (r.pos < r.text.length && !/[,}\]]/.test(r.text[r.pos])) r.pos += 1;
}

function readStringArray(r: Reader, key: string, draft: ToolDraft): void {
  // r.pos is at "["
  r.pos += 1;
  const items: string[] = [];
  for (;;) {
    skipWs(r);
    const ch = r.text[r.pos];
    if (ch === undefined) break;
    if (ch === "]") {
      r.pos += 1;
      break;
    }
    if (ch === ",") {
      r.pos += 1;
      continue;
    }
    if (ch === '"') {
      const s = readString(r);
      if (!s.complete) {
        draft.partial = { key, index: items.length, value: s.value };
        break;
      }
      items.push(s.value);
      continue;
    }
    skipValue(r);
  }
  draft.lists[key] = items;
}

/** Read the object at r.pos (an "args" object) into the draft. */
function readArgs(r: Reader, draft: ToolDraft): void {
  r.pos += 1; // past "{"
  for (;;) {
    skipWs(r);
    const ch = r.text[r.pos];
    if (ch === undefined || ch === "}") return;
    if (ch === ",") {
      r.pos += 1;
      continue;
    }
    if (ch !== '"') {
      skipValue(r);
      continue;
    }
    const key = readString(r);
    if (!key.complete) return;
    skipWs(r);
    if (r.text[r.pos] !== ":") return;
    r.pos += 1;
    skipWs(r);
    const vch = r.text[r.pos];
    if (vch === undefined) return;
    if (vch === '"') {
      const s = readString(r);
      if (!s.complete) {
        draft.partial = { key: key.value, value: s.value };
        return;
      }
      draft.strings[key.value] = s.value;
    } else if (vch === "[") {
      readStringArray(r, key.value, draft);
    } else {
      skipValue(r);
    }
  }
}

/** What can be read of the block so far. Never throws. */
export function parseToolDraft(text: string): ToolDraft {
  const draft: ToolDraft = { name: null, strings: {}, lists: {} };
  const r: Reader = { text, pos: text.indexOf("{") };
  if (r.pos < 0) return draft;
  r.pos += 1;
  for (;;) {
    skipWs(r);
    const ch = r.text[r.pos];
    if (ch === undefined || ch === "}") break;
    if (ch === ",") {
      r.pos += 1;
      continue;
    }
    if (ch !== '"') {
      skipValue(r);
      continue;
    }
    const key = readString(r);
    if (!key.complete) break;
    skipWs(r);
    if (r.text[r.pos] !== ":") break;
    r.pos += 1;
    skipWs(r);
    const vch = r.text[r.pos];
    if (vch === undefined) break;
    if ((key.value === "op" || key.value === "tool") && vch === '"') {
      const s = readString(r);
      if (s.complete) draft.name = s.value;
      else break;
    } else if (key.value === "args" && vch === "{") {
      readArgs(r, draft);
    } else {
      skipValue(r);
    }
  }
  return draft;
}
