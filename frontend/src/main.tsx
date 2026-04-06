// main.tsx — New entry point using wouter + StudioLayout
// Replaces main.js as the application entry point.
// The old main.js is kept as a reference during the migration.

import { createRoot } from "react-dom/client";
import { AppRoutes } from "./router";
import { useAuthStore } from "@/stores/auth-store";

import "./index.css";
import "./css/styles.css";
import "./css/app.css";
import "./css/studio.css";

// Khôi phục trạng thái Đăng nhập từ localStorage
useAuthStore.getState().initialize();

// ---------------------------------------------------------------------------
// Tự động ẩn thanh cuộn toàn cục: mờ dần khi cuộn, dừng trong 1,2 giây rồi mờ dần
// ---------------------------------------------------------------------------
{
  const timers = new WeakMap<Element, ReturnType<typeof setTimeout>>();

  document.addEventListener(
    "scroll",
    (e) => {
      const el = e.target;
      if (!(el instanceof HTMLElement)) return;

      // Hiển thị thanh cuộn
      el.dataset.scrolling = "";

      // XóaĐồng hồ hẹn giờ ẩn lần cuối
      const prev = timers.get(el);
      if (prev) clearTimeout(prev);

      // 1.2s Ẩn sau khi không cuộn
      timers.set(
        el,
        setTimeout(() => {
          delete el.dataset.scrolling;
          timers.delete(el);
        }, 1200),
      );
    },
    true, // capture phase — Ghi lại các sự kiện cuộn cho tất cả các phần tử con
  );
}

const root = document.getElementById("app-root");
if (root) {
  createRoot(root).render(<AppRoutes />);
}
