export type AppMessageType = "success" | "error" | "warning" | "info";

export interface AppMessagePayload {
  type?: AppMessageType;
  content?: string;
}

export function notifyApp(type: AppMessageType, content: string) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<AppMessagePayload>("app:message", {
    detail: { type, content },
  }));
}
