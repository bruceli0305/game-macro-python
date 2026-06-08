<script setup lang="ts">
import { NCard, NInput, NInputNumber, NSwitch, NSpace, NText } from "naive-ui";
</script>

<template>
  <div>
    <h1 class="text-xl font-bold mb-4">基础配置</h1>
    <n-space vertical size="large">
      <n-card title="用户界面">
        <n-space vertical>
          <n-text>主题</n-text>
          <n-input placeholder="darkly" value="darkly" />
        </n-space>
      </n-card>

      <n-card title="截屏设置">
        <n-space vertical>
          <n-text>显示器策略</n-text>
          <n-input placeholder="primary" value="primary" />
        </n-space>
      </n-card>

      <n-card title="执行设置">
        <n-space vertical>
          <n-space align="center">
            <n-text>启用宏</n-text>
            <n-switch :default-value="false" />
          </n-space>
          <n-text>启停热键</n-text>
          <n-input placeholder="如 F9" />
          <n-text>技能间隔 (ms)</n-text>
          <n-input-number :default-value="50" :min="0" :max="10000" />
        </n-space>
      </n-card>
    </n-space>
  </div>
</template>
