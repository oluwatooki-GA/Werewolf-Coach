import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ChatHeader } from "./ChatHeader";

const header = () => render(<ChatHeader avatar={<span />} title="Strategies" actions={<button>Sort</button>} />);

describe("the top bar", () => {
  it("links to the project's GitHub repository, by name for screen readers", () => {
    header();
    const link = screen.getByRole("link", { name: /GitHub/ });
    expect(link).toHaveAttribute("href", "https://github.com/oluwatooki-GA/Werewolf-Coach");
  });

  it("opens the repository in a new tab, without handing the new page a way back", () => {
    header();
    const link = screen.getByRole("link", { name: /GitHub/ });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link.getAttribute("rel")).toContain("noopener");
  });

  it("shows the GitHub mark, which is a drawing and not read out as a word", () => {
    header();
    const icon = screen.getByRole("link", { name: /GitHub/ }).querySelector("svg");
    expect(icon).not.toBeNull();
    expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("comes after the chat's own actions, at the far right", () => {
    header();
    const sort = screen.getByRole("button", { name: "Sort" });
    const github = screen.getByRole("link", { name: /GitHub/ });
    expect(sort.compareDocumentPosition(github) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });
});
