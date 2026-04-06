import { createPortal } from "react-dom";
import { useAnchoredPopover } from "@/hooks/useAnchoredPopover";
import { UI_LAYERS } from "@/utils/ui-layers";
import type { RefObject, ReactNode, CSSProperties } from "react";

// ---------------------------------------------------------------------------
// Popover — Bảng điều khiển bật lên hợp nhất nguyên thủy
// ---------------------------------------------------------------------------
// Tất cả các bảng điều khiển popover phải sử dụng thành phần này thay vì kết hợp thủ công createPortal + useAnchoredPopover.
// Nó thoát khỏi bối cảnh xếp tầng gốc (chẳng hạn như làm mờ phông nền của tiêu đề) thông qua cổng thông tin,
// Đảm bảo độ mờ nền và quản lý chỉ mục z thống nhất.

/** Màu nền mặc định của bảng điều khiển (gray-900 = rgb(17 24 39)) */
export const POPOVER_BG = "rgb(17 24 39)";

type PopoverAlign = "start" | "center" | "end";
type PopoverLayer = keyof typeof UI_LAYERS;

interface PopoverProps {
  open: boolean;
  onClose?: () => void;
  anchorRef: RefObject<HTMLElement | null>;
  children: ReactNode;
  /** Tailwind width class, e.g. "w-72", "w-96" */
  width?: string;
  /** Tên lớp bổ sung (được thêm vào phần tử gốc của bảng điều khiển) */
  className?: string;
  /** Kiểu nội tuyến bổ sung */
  style?: CSSProperties;
  /** Độ lệch điểm neo (px), mặc định 8 */
  sideOffset?: number;
  /** Căn chỉnh, mặc định "end" */
  align?: PopoverAlign;
  /** z-index Cấp độ, mặc định "workspacePopover" */
  layer?: PopoverLayer;
  /** Màu nền tùy chỉnh, POPOVER_BG mặc định */
  backgroundColor?: string;
}

export function Popover({
  open,
  onClose,
  anchorRef,
  children,
  width = "w-72",
  className = "",
  style,
  sideOffset = 8,
  align,
  layer = "workspacePopover",
  backgroundColor = POPOVER_BG,
}: PopoverProps) {
  const { panelRef, positionStyle } = useAnchoredPopover({
    open,
    anchorRef,
    onClose,
    sideOffset,
    align,
  });

  if (!open || typeof document === "undefined") return null;

  return createPortal(
    <div
      ref={panelRef}
      className={`fixed isolate ${width} ${UI_LAYERS[layer]} ${className}`}
      style={{
        ...positionStyle,
        backgroundColor,
        ...style,
      }}
    >
      {children}
    </div>,
    document.body,
  );
}
