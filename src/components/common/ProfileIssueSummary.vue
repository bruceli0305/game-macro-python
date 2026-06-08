<script setup lang="ts">
import { computed } from "vue";
import { NAlert, NTag } from "naive-ui";
import { summarizeProfileIssues } from "../../utils/profile-issue-summary";
import type { ProfileValidationIssue } from "../../utils/profile-validation";

const props = withDefaults(
  defineProps<{
    issues: ProfileValidationIssue[];
    title?: string;
    limit?: number;
  }>(),
  {
    title: "配置检查",
    limit: 5,
  }
);

const summary = computed(() => summarizeProfileIssues(props.issues, props.limit));
const alertType = computed(() => (summary.value.errorCount > 0 ? "error" : "warning"));
</script>

<template>
  <n-alert
    v-if="issues.length > 0"
    :type="alertType"
    :title="title"
    class="profile-issue-summary"
  >
    <div class="issue-meta">
      <n-tag v-if="summary.errorCount > 0" size="small" type="error">
        错误 {{ summary.errorCount }}
      </n-tag>
      <n-tag v-if="summary.warningCount > 0" size="small" type="warning">
        警告 {{ summary.warningCount }}
      </n-tag>
    </div>

    <ul class="issue-list">
      <li v-for="issue in summary.shownIssues" :key="`${issue.path}:${issue.message}`">
        <span class="issue-message">{{ issue.message }}</span>
        <span class="issue-path">{{ issue.path }}</span>
      </li>
    </ul>

    <div v-if="summary.remainingCount > 0" class="issue-more">
      还有 {{ summary.remainingCount }} 项未显示
    </div>
  </n-alert>
</template>

<style scoped>
.profile-issue-summary {
  margin-bottom: 12px;
}

.issue-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.issue-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 0;
  padding-left: 16px;
}

.issue-message {
  color: rgb(243 244 246);
}

.issue-path {
  display: block;
  margin-top: 2px;
  color: rgb(156 163 175);
  font-size: 12px;
  word-break: break-all;
}

.issue-more {
  margin-top: 8px;
  color: rgb(156 163 175);
  font-size: 12px;
}
</style>
