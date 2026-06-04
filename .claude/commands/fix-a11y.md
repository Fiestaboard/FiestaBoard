Fix accessibility findings on a feature branch and open a PR.

Use the `a11y-engineer` agent. Paste the findings list (typically the output of `/qa-a11y` or `/qa-a11y-docs`) as input; the agent will ask if none is provided.

The agent will:
1. Verify `git status` is clean (asks before continuing if not).
2. Create a `fix-a11y-<area>` feature branch.
3. Group findings into logical commits — one fix per commit, conventional-commit message (`fix(a11y): …`), citing the WCAG criterion in the body.
4. For web fixes: prefer semantic HTML and Radix primitives; route every new user-facing string (including `aria-label`) through `next-intl` so all 14 locales stay translatable.
5. For doc fixes: rewrite alt text, renumber headings, replace "click here" / bare-URL link text, add code-block languages, add table header rows.
6. Run `/test-web` to confirm `web/tests/a11y.spec.ts` still passes.
7. Open a PR via `gh pr create` listing each finding addressed with WCAG citations and a manual-verification checklist.

The agent has edit and git access but **never** pushes to `main`, **never** uses `--no-verify`, and **never** uses `git add -A`.
