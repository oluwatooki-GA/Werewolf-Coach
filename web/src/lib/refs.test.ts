import { describe, expect, it } from "vitest";
import { splitRefs } from "./refs";

describe("splitRefs", () => {
  it("leaves a message with no line number alone", () => {
    expect(splitRefs("Why did you stay quiet?")).toEqual(["Why did you stay quiet?"]);
  });

  it("pulls a line number out of a sentence, keeping the words around it in order", () => {
    expect(splitRefs("Eve quickly doubted Di's claim (R2-4). Why?")).toEqual([
      "Eve quickly doubted Di's claim (",
      { ref: "R2-4" },
      "). Why?",
    ]);
  });

  it("finds several, including one at the very start or end", () => {
    expect(splitRefs("R1-1 and R2-10")).toEqual([{ ref: "R1-1" }, " and ", { ref: "R2-10" }]);
  });

  it("does not mistake other words for a line number", () => {
    expect(splitRefs("MR1-2 and R12 and R1-")).toEqual(["MR1-2 and R12 and R1-"]);
  });
});
