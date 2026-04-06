import { useEffect } from "react";

/**
 * Ngăn người dùng làm mới/làm mới các tab khi có những thay đổi không lưu trữ.
 */
export function useWarnUnsaved(isDirty: boolean) {
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e: BeforeUnloadEvent) => {
      e.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);
}
