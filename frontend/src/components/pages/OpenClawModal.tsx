/**
 * OpenClaw Phương thức khởi động tích hợp
 * PromptVùng (có thể sao chép, bao gồm URL Skill.md động), hướng dẫn 3 bước,"Nhận mã thông báo API"Nút
 */
import { useCallback, useMemo, useState } from "react";
import { copyText } from "@/utils/clipboard";
import { Check, Copy, ExternalLink, X } from "lucide-react";
import { useLocation } from "wouter";

// 🦞 SVG lobster icon (inline, no external dep)
function LobsterIcon({ className }: { className?: string }) {
  return (
    <span className={className} aria-hidden="true" role="img">
      🦞
    </span>
  );
}

interface OpenClawModalProps {
  onClose: () => void;
}

// Sử dụng dữ liệu bước (tĩnh, được quảng bá bên ngoài thành phần để tránh phải xây dựng lại mỗi lần kết xuất)
const STEPS = [
  {
    step: "01",
    title: "Gửi lời nhắc trên tới OpenClaw của Bạn",
    desc: "Sao chép Lời nhắc và dán vào OpenClaw để gửi",
  },
  {
    step: "02",
    title: "OpenClaw Học kỹ năng từ tài liệu kỹ năng",
    desc: "OpenClaw Tài liệu ArcReel Skill sẽ được đọc tự động để có được tất cả các phương pháp sử dụng API và Công cụ có sẵn.",
  },
  {
    step: "03",
    title: "OpenClaw Tương tác với ArcReel và TạoVideo",
    desc: "Mô tảBạnĐối với nhu cầu sáng tạo, OpenClaw sẽ gọi ArcReel Hoàn thànhDựán quản lý, tạo kịch bản và tạo Video",
  },
] as const;

export function OpenClawModal({ onClose }: OpenClawModalProps) {
  const [, navigate] = useLocation();
  const [copied, setCopied] = useState(false);

  // task 7.3：Tự động điều chỉnh Hiện tại địa chỉ truy cập
  const skillUrl = useMemo(
    () => `${window.location.origin}/skill.md`,
    [],
  );

  const systemPrompt = useMemo(
    () => `Tìm hiểu ${skillUrl} Sau đó theo dõi kỹ năng học cách tạo Video bằng ArcReel`,
    [skillUrl],
  );

  const handleCopyPrompt = useCallback(async () => {
    await copyText(systemPrompt);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [systemPrompt]);

  // task 7.4：Chuyển đến trang quản lý API Key
  const handleGoToApiKeys = useCallback(() => {
    onClose();
    navigate("/app/settings?section=api-keys");
  }, [navigate, onClose]);

  const handleBackdropClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      if (e.target === e.currentTarget) onClose();
    },
    [onClose],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4 py-8"
      onClick={handleBackdropClick}
      onKeyDown={handleKeyDown}
    >
      <div className="relative flex w-full max-w-lg flex-col rounded-2xl border border-gray-800 bg-gray-900 shadow-2xl shadow-black/60 max-h-[90vh] overflow-y-auto">
        {/* ——— Thanh trên cùng ———— */}
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-gray-800 bg-gray-900 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <LobsterIcon className="text-xl leading-none" />
            <div>
              <h2 className="text-sm font-semibold text-gray-100">OpenClaw Hướng dẫn tích hợp</h2>
              <p className="text-xs text-gray-500">Kết nối ArcReel với OpenClaw AI Agent</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1 text-gray-500 transition-colors hover:bg-gray-800 hover:text-gray-300"
            aria-label="Đóng"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-5">
          {/* ——— Prompt Diện tích ———— */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-medium text-gray-400">Prompt</span>
              <button
                type="button"
                onClick={() => void handleCopyPrompt()}
                className="inline-flex items-center gap-1 rounded-md border border-gray-700 bg-gray-800 px-2 py-1 text-xs text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-700"
              >
                {copied ? (
                  <>
                    <Check className="h-3 w-3 text-emerald-400" />
                    Đã sao chép
                  </>
                ) : (
                  <>
                    <Copy className="h-3 w-3" />
                    Sao chép
                  </>
                )}
              </button>
            </div>
            <div className="rounded-xl border border-indigo-500/20 bg-gray-950 p-3">
              <pre className="whitespace-pre-wrap font-mono text-xs leading-5 text-indigo-200">
                {systemPrompt}
              </pre>
            </div>
            <p className="mt-1.5 text-xs text-gray-600">
              Skill Địa chỉ tài liệu:
              <a
                href={skillUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="ml-1 inline-flex items-center gap-0.5 text-indigo-400 hover:text-indigo-300"
              >
                {skillUrl}
                <ExternalLink className="h-3 w-3" />
              </a>
            </p>
          </div>

          {/* ——— 3 Hướng dẫn các bước ———— */}
          <div>
            <div className="mb-3 text-xs font-medium text-gray-400">Các bước sử dụng</div>
            <div className="space-y-2">
              {STEPS.map(({ step, title, desc }) => (
                <div
                  key={step}
                  className="flex gap-3 rounded-xl border border-gray-800 bg-gray-950/50 px-3.5 py-3"
                >
                  <div className="flex-shrink-0 font-mono text-xs font-bold text-indigo-500/70 pt-0.5">
                    {step}
                  </div>
                  <div>
                    <div className="text-xs font-semibold text-gray-200">{title}</div>
                    <div className="mt-0.5 text-xs leading-4.5 text-gray-500">{desc}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* ——— Nút thao tác ———— */}
          <div className="flex gap-2 pt-1">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 rounded-xl border border-gray-700 bg-gray-800 px-4 py-2.5 text-sm text-gray-300 transition-colors hover:border-gray-600 hover:bg-gray-700"
            >
              Đóng
            </button>
            <button
              type="button"
              onClick={handleGoToApiKeys}
              className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-xl bg-indigo-600 px-4 py-2.5 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
            >
              Nhận mã thông báo API
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
