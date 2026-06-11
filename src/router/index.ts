import { createRouter, createWebHistory } from "vue-router";

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: "/",
      redirect: "/settings",
    },
    {
      path: "/settings",
      name: "settings",
      component: () => import("../views/SettingsPage.vue"),
    },
    {
      path: "/skills",
      name: "skills",
      component: () => import("../views/SkillsPage.vue"),
    },
    {
      path: "/points",
      name: "points",
      component: () => import("../views/PointsPage.vue"),
    },
    {
      path: "/cycle-editor",
      name: "cycle-editor",
      component: () => import("../views/CycleEditorPage.vue"),
    },
    {
      path: "/simulator",
      name: "simulator",
      component: () => import("../views/SimulatorPage.vue"),
    },
    {
      path: "/debug-panel",
      name: "debug-panel",
      component: () => import("../views/DebugPanelPage.vue"),
    },
  ],
});

export default router;
