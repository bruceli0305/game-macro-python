import { describe, expect, it } from "vitest";
import { summarizeProfileIssues } from "../utils/profile-issue-summary";
import type { ProfileValidationIssue } from "../utils/profile-validation";

function issue(path: string, severity: "error" | "warning" = "error"): ProfileValidationIssue {
  return { path, message: path, severity };
}

describe("profile issue summary", () => {
  it("counts severities and caps visible issues", () => {
    const summary = summarizeProfileIssues(
      [issue("a"), issue("b", "warning"), issue("c"), issue("d")],
      2
    );

    expect(summary).toMatchObject({
      errorCount: 3,
      warningCount: 1,
      remainingCount: 2,
    });
    expect(summary.shownIssues.map((item) => item.path)).toEqual(["a", "b"]);
  });

  it("handles zero limits", () => {
    const summary = summarizeProfileIssues([issue("a")], 0);

    expect(summary.shownIssues).toEqual([]);
    expect(summary.remainingCount).toBe(1);
  });
});
