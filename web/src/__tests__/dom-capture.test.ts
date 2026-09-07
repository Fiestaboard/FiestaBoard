/**
 * Regression tests for the docs-capture sanitiser.
 *
 * `stripInertMarkup` used to be four regexes over serialised markup, and
 * CodeQL flagged three of them (`js/bad-tag-filter`,
 * `js/incomplete-multi-character-sanitization`).
 *
 * Two cases here are the guards that would have caught those: a script whose
 * own text carries an end tag, and an attribute value that reads as markup.
 * Both fail against the regexes and pass against a parser. The rest pin down
 * behaviour the capture output depends on — what must go, and what must
 * survive — so a future rewrite cannot quietly change either.
 *
 * Vitest runs under jsdom, so `stripInertMarkup` gets a real parsed tree here
 * exactly as it gets Chrome's in the capture path.
 */
import { describe, expect, it } from "vitest";

import { normaliseVolatileIds, stripInertMarkup } from "../../tests/lib/dom-capture";

/** Parse a fragment the way a browser would, and return its root element. */
function parse(html: string): Element {
  const host = document.createElement("div");
  host.innerHTML = html;
  return host;
}

describe("stripInertMarkup", () => {
  it("removes a script whose own text contains an end tag", () => {
    // Script text is serialised verbatim by both Chrome and jsdom, so a
    // script carrying `</script>` in its body serialises as
    // `<script></script></script>`. The old `<script\b[^>]*>[\s\S]*?<\/script>`
    // stopped at the first end tag and left the trailing one behind, which is
    // the `js/bad-tag-filter` finding. Removing the element cannot half-match.
    const host = document.createElement("div");
    const script = document.createElement("script");
    script.textContent = "</script>";
    host.append(document.createElement("p"), script);
    host.querySelector("p")!.textContent = "keep me";

    const out = stripInertMarkup(host);

    expect(out.toLowerCase()).not.toContain("script");
    expect(out).toContain("keep me");
  });

  it("removes inline handlers whatever their quoting or case", () => {
    // Serialisation normalises quoting, so this pins the contract rather than
    // reproducing a past failure: handlers go, and the elements stay.
    const out = stripInertMarkup(parse(`<b ONCLICK="a()">x</b><i onmouseover='b()'>y</i><u onfocus=c()>z</u>`));

    expect(out.toLowerCase()).not.toContain("onclick");
    expect(out.toLowerCase()).not.toContain("onmouseover");
    expect(out.toLowerCase()).not.toContain("onfocus");
    expect(out).toContain(">x<");
    expect(out).toContain(">y<");
    expect(out).toContain(">z<");
  });

  it("leaves markup after a '>' inside an attribute value untouched", () => {
    // Tailwind arbitrary variants put a bare '>' in class names. Chrome
    // escapes it on the way out and jsdom does not, so this is the shape of
    // input where `[^>]*` would end a tag match early.
    const html = `<div class="has-[>svg]:px-2"><span onclick="x()" data-slot="label">keep me</span></div>`;
    const out = stripInertMarkup(parse(html));

    expect(out).toContain("keep me");
    expect(out).toContain('data-slot="label"');
    expect(out.toLowerCase()).not.toContain("onclick");
  });

  it("does not treat attribute text that looks like markup as markup", () => {
    // A regex over serialised markup cannot tell an attribute value from an
    // element, so the old sanitiser deleted the tags out of the middle of
    // this title (`js/incomplete-multi-character-sanitization`).
    const el = document.createElement("i");
    el.setAttribute("title", "<script>zap</script>");
    el.setAttribute("data-slot", "label");
    el.textContent = "keep me";
    const host = document.createElement("div");
    host.append(el);

    const out = stripInertMarkup(host);

    expect(out).toContain("keep me");
    expect(host.querySelector("i")!.getAttribute("title")).toBe("<script>zap</script>");
    expect(out).toContain("zap");
  });

  it("removes tabindex, toasts, and caller-supplied attributes only", () => {
    const html =
      `<div tabindex="-1" data-slot="root" data-noise="1">` +
      `<ol data-sonner-toaster><li>toast</li></ol>` +
      `<span data-current-char="A">A</span></div>`;
    const out = stripInertMarkup(parse(html), ["data-noise"]);

    expect(out).not.toContain("tabindex");
    expect(out).not.toContain("data-noise");
    expect(out).not.toContain("toast");
    // Attributes the render depends on must survive.
    expect(out).toContain('data-slot="root"');
    expect(out).toContain('data-current-char="A"');
  });

  it("leaves attributes that merely contain 'on' alone", () => {
    const out = stripInertMarkup(parse(`<div data-online="yes" aria-orientation="vertical">x</div>`));

    expect(out).toContain('data-online="yes"');
    expect(out).toContain('aria-orientation="vertical"');
  });
});

describe("normaliseVolatileIds", () => {
  it("renumbers seeded UUIDs in first-appearance order, keeping them distinct", () => {
    const html =
      `<i id="a-3f2504e0-4f89-41d3-9a0c-0305e82c3301"></i>` +
      `<i id="b-6ba7b810-9dad-11d1-80b4-00c04fd430c8"></i>` +
      `<i id="c-3f2504e0-4f89-41d3-9a0c-0305e82c3301"></i>`;
    const out = normaliseVolatileIds(html);

    expect(out).not.toContain("3f2504e0");
    expect(out).toContain("00000000-0000-4000-8000-000000000000");
    expect(out).toContain("00000000-0000-4000-8000-000000000001");
    // Same source id renumbers to the same target; different ids stay different.
    expect(out.match(/00000000-0000-4000-8000-000000000000/g)).toHaveLength(2);
  });

  it("renumbers base-ui generated ids", () => {
    const out = normaliseVolatileIds(`<i id="base-ui-_r_1a_"></i><i for="base-ui-_r_2b_"></i>`);

    expect(out).not.toContain("base-ui-_r_");
    expect(out).toContain("fb-c0");
    expect(out).toContain("fb-c1");
  });
});
