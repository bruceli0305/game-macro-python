import type { ProfileValidationIssue } from "./profile-validation";

export interface ProfileIssueSummary {
  errorCount: number;
  warningCount: number;
  shownIssues: ProfileValidationIssue[];
  remainingCount: number;
}

export function summarizeProfileIssues(
  issues: ProfileValidationIssue[],
  limit = 5
): ProfileIssueSummary {
  const safeLimit = Math.max(0, Math.floor(limit));
  const errorCount = issues.filter((issue) => issue.severity === "error").length;
  const warningCount = issues.filter((issue) => issue.severity === "warning").length;
  return {
    errorCount,
    warningCount,
    shownIssues: issues.slice(0, safeLimit),
    remainingCount: Math.max(0, issues.length - safeLimit),
  };
}
