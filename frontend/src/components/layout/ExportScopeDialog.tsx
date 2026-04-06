import { useState, useEffect } from "react";
import { Package, History, Clapperboard, ArrowLeft, Loader2 } from "lucide-react";
import { Popover } from "@/components/ui/Popover";
import type { RefObject } from "react";
import type { EpisodeMeta } from "@/types/project";

export type ExportScope = "current" | "full" | "jianying-draft";

const DRAFT_PATH_STORAGE_KEY = "arcreel_jianying_draft_path";

function getDefaultDraftPath(): string {
  const isWindows =
    typeof navigator !== "undefined" &&
    navigator.userAgent.includes("Windows");
  return isWindows
    ? String.raw`C:\Users\BạnTên người dùng\AppData\Local\JianyingPro\User Data\Projects\com.lveditor.draft`
    : "/Users/BạnTên người dùng/Phim/JianyingPro/Dữ liệu người dùng/Dự án/com.lveditor.draft";
}

interface ExportScopeDialogProps {
  open: boolean;
  onClose: () => void;
  onSelect: (scope: ExportScope) => void;
  anchorRef: RefObject<HTMLElement | null>;
  episodes?: EpisodeMeta[];
  onJianyingExport?: (episode: number, draftPath: string, jianyingVersion: string) => void;
  jianyingExporting?: boolean;
}

export function ExportScopeDialog({
  open,
  onClose,
  onSelect,
  anchorRef,
  episodes = [],
  onJianyingExport,
  jianyingExporting = false,
}: ExportScopeDialogProps) {
  const [mode, setMode] = useState<"select" | "jianying-form">("select");
  const [selectedEpisode, setSelectedEpisode] = useState<number>(
    episodes.length > 0 ? episodes[0].episode : 1,
  );
  const [draftPath, setDraftPath] = useState<string>(
    () => localStorage.getItem(DRAFT_PATH_STORAGE_KEY) || getDefaultDraftPath(),
  );
  const [jianyingVersion, setJianyingVersion] = useState("6");

  // Reset mode when popover closes
  useEffect(() => {
    if (!open) {
      setMode("select");
    }
  }, [open]);

  // Sync selected episode when episodes change
  useEffect(() => {
    if (episodes.length > 0) {
      setSelectedEpisode(episodes[0].episode);
    }
  }, [episodes]);

  const handleJianyingSubmit = () => {
    if (!draftPath.trim() || !onJianyingExport) return;
    localStorage.setItem(DRAFT_PATH_STORAGE_KEY, draftPath.trim());
    onJianyingExport(selectedEpisode, draftPath.trim(), jianyingVersion);
  };

  return (
    <Popover
      open={open}
      onClose={onClose}
      anchorRef={anchorRef}
      width="w-80"
      className="rounded-lg border border-gray-700 p-3 shadow-xl"
    >
      {mode === "select" ? (
        <>
          <p className="mb-3 text-xs font-medium text-gray-300">Chọn phạm vi xuất</p>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => onSelect("current")}
              className="flex items-start gap-3 rounded-md border border-gray-700 px-3 py-2.5 text-left transition-colors hover:border-indigo-500 hover:bg-indigo-500/10"
            >
              <Package className="mt-0.5 h-4 w-4 shrink-0 text-indigo-400" />
              <div>
                <div className="text-sm font-medium text-gray-200">
                  Chỉ phiên bản hiện tại
                  <span className="ml-1.5 rounded bg-indigo-500/20 px-1.5 py-0.5 text-[10px] text-indigo-300">
                    Đề xuất
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-gray-500">
                  Không bao gồm lịch sử phiên bản, kích thước nhỏ hơn
                </p>
              </div>
            </button>
            <button
              type="button"
              onClick={() => onSelect("full")}
              className="flex items-start gap-3 rounded-md border border-gray-700 px-3 py-2.5 text-left transition-colors hover:border-gray-500 hover:bg-gray-800"
            >
              <History className="mt-0.5 h-4 w-4 shrink-0 text-gray-400" />
              <div>
                <div className="text-sm font-medium text-gray-200">Tất cả dữ liệu</div>
                <p className="mt-0.5 text-xs text-gray-500">
                  Bao gồm toàn bộ lịch sử phiên bản
                </p>
              </div>
            </button>
            <button
              type="button"
              onClick={() => setMode("jianying-form")}
              className="flex items-start gap-3 rounded-md border border-gray-700 px-3 py-2.5 text-left transition-colors hover:border-amber-500 hover:bg-amber-500/10"
            >
              <Clapperboard className="mt-0.5 h-4 w-4 shrink-0 text-amber-400" />
              <div>
                <div className="text-sm font-medium text-gray-200">
                  Xuất làm bản nháp Jianying
                </div>
                <p className="mt-0.5 text-xs text-gray-500">
                  Tạo ZIP bản nháp có thể nhập vào Jianying
                </p>
              </div>
            </button>
          </div>
        </>
      ) : (
        <>
          <div className="mb-3 flex items-center gap-2">
            <button
              type="button"
              onClick={() => setMode("select")}
              className="rounded p-0.5 text-gray-400 transition-colors hover:bg-gray-800 hover:text-gray-200"
              aria-label="返回"
            >
              <ArrowLeft className="h-4 w-4" />
            </button>
            <p className="text-xs font-medium text-gray-300">Xuất làm bản nháp Jianying</p>
          </div>
          <div className="flex flex-col gap-3">
            {/* Episode selector — hidden when only one episode */}
            {episodes.length > 1 && (
              <div>
                <label htmlFor="jianying-episode-select" className="mb-1 block text-xs text-gray-400">
                  Chọn tập số
                </label>
                <select
                  id="jianying-episode-select"
                  value={selectedEpisode}
                  onChange={(e) => setSelectedEpisode(Number(e.target.value))}
                  className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 outline-none focus:border-indigo-500"
                >
                  {episodes.map((ep) => (
                    <option key={ep.episode} value={ep.episode}>
                      Không. {ep.episode} đặt — {ep.title}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {/* JianYing version selector */}
            <div>
              <label htmlFor="jianying-version-select" className="mb-1 block text-xs text-gray-400">
                Phiên bản Jianying
              </label>
              <select
                id="jianying-version-select"
                value={jianyingVersion}
                onChange={(e) => setJianyingVersion(e.target.value)}
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 outline-none focus:border-indigo-500"
              >
                <option value="6">Clip 6.0 trở lên (Đề xuất)</option>
                <option value="5">Cắt bỏ 5.x</option>
              </select>
            </div>

            {/* Draft path input */}
            <div>
              <label htmlFor="jianying-draft-path" className="mb-1 block text-xs text-gray-400">
                Đường dẫn thư mục bản nháp
              </label>
              <input
                id="jianying-draft-path"
                type="text"
                value={draftPath}
                onChange={(e) => setDraftPath(e.target.value)}
                placeholder="Đường dẫn thư mục bản nháp Jianying"
                className="w-full rounded-md border border-gray-700 bg-gray-800 px-2.5 py-1.5 text-sm text-gray-200 placeholder:text-gray-600 outline-none focus:border-indigo-500"
              />
              <p className="mt-1.5 text-[11px] leading-relaxed text-gray-500">
                Vui lòng nhập đường dẫn đầy đủ đến thư mục bản nháp Jianying. Mở Jianying → Cài đặt → Vị trí bản nháp để xem.
              </p>
            </div>

            {/* Submit */}
            <button
              type="button"
              onClick={handleJianyingSubmit}
              disabled={!draftPath.trim() || jianyingExporting}
              className="flex items-center justify-center gap-1.5 rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white transition-colors hover:bg-amber-500 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {jianyingExporting ? (
                <>
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Đang xuất...
                </>
              ) : (
                "Xuất bản nháp"
              )}
            </button>
          </div>
        </>
      )}
    </Popover>
  );
}
