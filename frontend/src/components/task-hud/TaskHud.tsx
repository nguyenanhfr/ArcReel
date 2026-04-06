import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { motion, AnimatePresence } from "framer-motion";
import { Image, Video, Check, X, Loader2, ChevronDown } from "lucide-react";
import { useAnchoredPopover } from "@/hooks/useAnchoredPopover";
import { useAppStore } from "@/stores/app-store";
import { useTasksStore } from "@/stores/tasks-store";
import type { TaskItem } from "@/types";
import { UI_LAYERS } from "@/utils/ui-layers";
import { POPOVER_BG } from "@/components/ui/Popover";

// ---------------------------------------------------------------------------
// Task status icon — visual indicator per task state
// ---------------------------------------------------------------------------

function TaskStatusIcon({ status }: { status: TaskItem["status"] }) {
  switch (status) {
    case "running":
      return <Loader2 className="h-3.5 w-3.5 animate-spin text-indigo-400" />;
    case "queued":
      return <div className="h-2 w-2 rounded-full bg-gray-500" />;
    case "succeeded":
      return <Check className="h-3.5 w-3.5 text-emerald-400" />;
    case "failed":
      return <X className="h-3.5 w-3.5 text-red-400" />;
  }
}

// ---------------------------------------------------------------------------
// RunningProgressBar — Đang chạyThanh tiến trình động cho các nhiệm vụ
// ---------------------------------------------------------------------------

function RunningProgressBar() {
  return (
    <div className="relative mt-1 h-0.5 w-full overflow-hidden rounded-full bg-gray-800">
      <motion.div
        className="absolute inset-y-0 left-0 w-1/3 rounded-full bg-gradient-to-r from-indigo-500 via-indigo-400 to-indigo-500"
        animate={{ x: ["0%", "200%"] }}
        transition={{
          duration: 1.5,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// TaskRow — Mục tác vụ đơn lẻ (bao gồm tô sáng Hoàn thành, Thất bạiMở rộng và thanh tiến trình đang chạy)
// ---------------------------------------------------------------------------

function TaskRow({
  task,
  isFading,
  expandedErrorId,
  onToggleError,
}: {
  task: TaskItem;
  isFading: boolean;
  expandedErrorId: string | null;
  onToggleError: (taskId: string) => void;
}) {
  const statusLabel: Record<TaskItem["status"], string> = {
    running: "Đang tạo...",
    queued: "Đang xếp hàng",
    succeeded: "Đã hoàn thành",
    failed: "Thất bại",
  };

  const statusColor: Record<TaskItem["status"], string> = {
    running: "text-indigo-400",
    queued: "text-gray-500",
    succeeded: "text-emerald-400",
    failed: "text-red-400",
  };

  // Xác định kiểu nền hàng dựa trên trạng thái
  const rowBg =
    task.status === "failed"
      ? "bg-red-500/10"
      : task.status === "succeeded" && !isFading
        ? "bg-emerald-500/10"
        : "";

  const isErrorExpanded = expandedErrorId === task.task_id;
  const hasError = task.status === "failed" && task.error_message;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, height: 0 }}
      animate={{
        opacity: isFading ? 0 : 1,
        height: isFading ? 0 : "auto",
      }}
      exit={{ opacity: 0, height: 0 }}
      transition={{ duration: isFading ? 0.4 : 0.2 }}
      className="overflow-hidden"
    >
      {/* Nội dung hàng chính */}
      <div
        className={`flex items-center gap-2 px-3 py-1.5 text-sm ${rowBg} ${
          hasError ? "cursor-pointer hover:bg-red-500/15" : ""
        }`}
        onClick={hasError ? () => onToggleError(task.task_id) : undefined}
      >
        <TaskStatusIcon status={task.status} />
        <span className="font-mono text-xs text-gray-400">
          {task.resource_id}
        </span>
        <span className="flex-1 truncate text-gray-300">{task.task_type}</span>
        <span className={`text-xs ${statusColor[task.status]}`}>
          {statusLabel[task.status]}
        </span>
        {hasError && (
          <ChevronDown
            className={`h-3 w-3 text-gray-500 transition-transform ${
              isErrorExpanded ? "rotate-180" : ""
            }`}
          />
        )}
      </div>

      {/* Đang chạyThanh tiến trình nhiệm vụ */}
      {task.status === "running" && (
        <div className="px-3 pb-1">
          <RunningProgressBar />
        </div>
      )}

      {/* Thất bạiChi tiết lỗi của tác vụ Vùng mở rộng */}
      <AnimatePresence>
        {hasError && isErrorExpanded && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.15 }}
            className="overflow-hidden"
          >
            <div className="mx-3 mb-1.5 rounded bg-red-500/5 px-2 py-1.5 text-xs text-red-300/80">
              {task.error_message}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

// ---------------------------------------------------------------------------
// ChannelSection — Được nhóm theo kênh Ảnh/Video, bao gồm logic mờ dần tự động
// ---------------------------------------------------------------------------

function ChannelSection({
  title,
  icon: Icon,
  tasks,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  tasks: TaskItem[];
}) {
  // Theo dõi ID tác vụ mờ dần
  const [fadingIds, setFadingIds] = useState<Set<string>>(new Set());
  // Theo dõi các ID tác vụ đã bị mờ hoàn toàn (nên ẩn)
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(new Set());
  // Lưutham khảo hẹn giờ để dọn dẹp
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Thất bạiChi tiết lỗi tác vụTrạng thái mở rộng
  const [expandedErrorId, setExpandedErrorId] = useState<string | null>(null);

  const toggleError = useCallback((taskId: string) => {
    setExpandedErrorId((prev) => (prev === taskId ? null : taskId));
  }, []);

  // Theo dõi các thay đổi trạng thái tác vụ và tự động mờ dần đối với tác vụ đã thành công Cài đặt
  useEffect(() => {
    const succeededTasks = tasks.filter(
      (t) =>
        t.status === "succeeded" &&
        !fadingIds.has(t.task_id) &&
        !hiddenIds.has(t.task_id),
    );

    for (const task of succeededTasks) {
      if (timersRef.current.has(task.task_id)) continue;

      // 3 Bắt đầu mờ dần hoạt ảnh sau vài giây
      const fadeTimer = setTimeout(() => {
        setFadingIds((prev) => new Set(prev).add(task.task_id));

        // Đánh dấu là ẩn sau khi hoạt ảnh mờ dần Hoàn thành (400ms)
        const hideTimer = setTimeout(() => {
          setHiddenIds((prev) => new Set(prev).add(task.task_id));
          timersRef.current.delete(task.task_id);
        }, 400);

        timersRef.current.set(task.task_id + "_hide", hideTimer);
      }, 3000);

      timersRef.current.set(task.task_id, fadeTimer);
    }

    return () => {
      // Xóa tất cả bộ tính giờ khi thành phần được gỡ cài đặt
      for (const timer of timersRef.current.values()) {
        clearTimeout(timer);
      }
    };
  }, [tasks, fadingIds, hiddenIds]);

  const running = tasks.filter((t) => t.status === "running");
  const queued = tasks.filter((t) => t.status === "queued");
  const recent = tasks
    .filter((t) => t.status === "succeeded" || t.status === "failed")
    .filter((t) => !hiddenIds.has(t.task_id))
    .slice(0, 5);

  const visible = [...running, ...queued, ...recent];

  return (
    <div>
      <div className="flex items-center gap-2 px-3 py-2 text-xs font-semibold text-gray-400">
        <Icon className="h-3.5 w-3.5" />
        {title}
        {running.length > 0 && (
          <span className="ml-auto text-indigo-400">
            {running.length} Đang chạy
          </span>
        )}
      </div>
      <AnimatePresence>
        {visible.map((task) => (
          <TaskRow
            key={task.task_id}
            task={task}
            isFading={fadingIds.has(task.task_id)}
            expandedErrorId={expandedErrorId}
            onToggleError={toggleError}
          />
        ))}
      </AnimatePresence>
      {visible.length === 0 && (
        <div className="px-3 py-2 text-xs text-gray-600">Chưa có nhiệm vụ nào</div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TaskHud — Bảng bật lên hiển thị trạng thái hàng đợi tác vụ trong thời gian thực
// ---------------------------------------------------------------------------

export function TaskHud({ anchorRef }: { anchorRef: RefObject<HTMLElement | null> }) {
  const { taskHudOpen, setTaskHudOpen } = useAppStore();
  const { tasks, stats } = useTasksStore();
  const { panelRef, positionStyle } = useAnchoredPopover({
    open: taskHudOpen,
    anchorRef,
    onClose: () => setTaskHudOpen(false),
    sideOffset: 4,
  });

  const imageTasks = tasks.filter((t) => t.media_type === "image");
  const videoTasks = tasks.filter((t) => t.media_type === "video");

  if (typeof document === "undefined") return null;

  return createPortal(
    <AnimatePresence>
      {taskHudOpen && (
        <motion.div
          ref={panelRef}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.15 }}
          className={`fixed w-80 isolate rounded-lg border border-gray-800 shadow-xl ${UI_LAYERS.workspacePopover}`}
          style={{
            ...positionStyle,
            backgroundColor: POPOVER_BG,
          }}
        >
          {/* Cột thống kê */}
          <div className="flex gap-3 border-b border-gray-800 px-3 py-2 text-xs text-gray-400">
            <span>
              排队{" "}
              <strong className="text-gray-200">{stats.queued}</strong>
            </span>
            <span>
              运行{" "}
              <strong className="text-indigo-400">{stats.running}</strong>
            </span>
            <span>
              Hoàn thành{" "}
              <strong className="text-emerald-400">{stats.succeeded}</strong>
            </span>
            <span>
              Thất bại{" "}
              <strong className="text-red-400">{stats.failed}</strong>
            </span>
          </div>

          {/* Kênh đôi */}
          <div className="max-h-80 divide-y divide-gray-800/50 overflow-y-auto">
            <ChannelSection title="Ảnhkênh" icon={Image} tasks={imageTasks} />
            <ChannelSection title="Videokênh" icon={Video} tasks={videoTasks} />
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
