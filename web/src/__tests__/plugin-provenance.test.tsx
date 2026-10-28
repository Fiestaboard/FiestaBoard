import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PluginProvenance, repositoryProvenance } from "@/components/plugin-provenance";

describe("repository provenance", () => {
  it.each([
    "https://github.com/Fiestaboard/plugin.git",
    "git@github.com:fiestaboard/plugin.git",
    "git+https://github.com/FIESTABOARD/plugin",
  ])("recognizes the GitHub organization from %s", (url) => {
    expect(repositoryProvenance(url)).toBe("official");
  });
  it.each([
    "https://github.com/Fiestaboard-extra/plugin",
    "https://github.com.evil.example/Fiestaboard/plugin",
    "https://code.example/team/plugin",
    "https://github.com/elsewhere/plugin",
  ])("marks a known external repository as Community: %s", (url) => {
    render(<PluginProvenance repository={url} />);
    expect(screen.getByText("Community")).toBeInTheDocument();
  });
  it.each([undefined, null, "", "not a repository", "https://github.com/Fiestaboard", "file:///Fiestaboard/plugin"])(
    "keeps missing or invalid provenance unknown: %s",
    (url) => {
      expect(repositoryProvenance(url)).toBe("unknown");
      render(<PluginProvenance repository={url} />);
      expect(screen.queryByText("Community")).not.toBeInTheDocument();
    },
  );
});
