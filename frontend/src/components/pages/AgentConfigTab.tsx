import { useCallback, useEffect, useRef, useState } from "react";
import { ChevronDown, Eye, EyeOff, Loader2, SlidersHorizontal, Terminal, X } from "lucide-react";
import { useWarnUnsaved } from "@/hooks/useWarnUnsaved";
import ClaudeColor from "@lobehub/icons/es/Claude/components/Color";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useConfigStatusStore } from "@/stores/config-status-store";
import type { GetSystemConfigResponse, SystemConfigPatch } from "@/types";
import { TabSaveFooter } from "./TabSaveFooter";

// ---------------------------------------------------------------------------
// Draft types
// ---------------------------------------------------------------------------

interface AgentDraft {
  anthropicKey: string;        // new API key input (empty = don't change)
  anthropicBaseUrl: string;    // in-place editing; empty = clear
  anthropicModel: string;      // in-place editing; empty = clear
  haikuModel: string;
  opusModel: string;
  sonnetModel: string;
  subagentModel: string;
  cleanupDelaySeconds: string;
  maxConcurrentSessions: string;
}

function buildDraft(data: GetSystemConfigResponse): AgentDraft {
  const s = data.settings;
  return {
    anthropicKey: "",
    anthropicBaseUrl: s.anthropic_base_url ?? "",
    anthropicModel: s.anthropic_model ?? "",
    haikuModel: s.anthropic_default_haiku_model ?? "",
    opusModel: s.anthropic_default_opus_model ?? "",
    sonnetModel: s.anthropic_default_sonnet_model ?? "",
    subagentModel: s.claude_code_subagent_model ?? "",
    cleanupDelaySeconds: String(s.agent_session_cleanup_delay_seconds ?? 300),
    maxConcurrentSessions: String(s.agent_max_concurrent_sessions ?? 5),
  };
}

function deepEqual(a: AgentDraft, b: AgentDraft): boolean {
  return (
    a.anthropicKey === b.anthropicKey &&
    a.anthropicBaseUrl === b.anthropicBaseUrl &&
    a.anthropicModel === b.anthropicModel &&
    a.haikuModel === b.haikuModel &&
    a.opusModel === b.opusModel &&
    a.sonnetModel === b.sonnetModel &&
    a.subagentModel === b.subagentModel &&
    a.cleanupDelaySeconds === b.cleanupDelaySeconds &&
    a.maxConcurrentSessions === b.maxConcurrentSessions
  );
}

function buildPatch(draft: AgentDraft, saved: AgentDraft): SystemConfigPatch {
  const patch: SystemConfigPatch = {};
  if (draft.anthropicKey.trim()) patch.anthropic_api_key = draft.anthropicKey.trim();
  if (draft.anthropicBaseUrl !== saved.anthropicBaseUrl)
    patch.anthropic_base_url = draft.anthropicBaseUrl || "";
  if (draft.anthropicModel !== saved.anthropicModel)
    patch.anthropic_model = draft.anthropicModel || "";
  if (draft.haikuModel !== saved.haikuModel)
    patch.anthropic_default_haiku_model = draft.haikuModel || "";
  if (draft.opusModel !== saved.opusModel)
    patch.anthropic_default_opus_model = draft.opusModel || "";
  if (draft.sonnetModel !== saved.sonnetModel)
    patch.anthropic_default_sonnet_model = draft.sonnetModel || "";
  if (draft.subagentModel !== saved.subagentModel)
    patch.claude_code_subagent_model = draft.subagentModel || "";
  if (draft.cleanupDelaySeconds !== saved.cleanupDelaySeconds)
    patch.agent_session_cleanup_delay_seconds = Number(draft.cleanupDelaySeconds) || 300;
  if (draft.maxConcurrentSessions !== saved.maxConcurrentSessions)
    patch.agent_max_concurrent_sessions = Number(draft.maxConcurrentSessions) || 5;
  return patch;
}

// ---------------------------------------------------------------------------
// Shared style constants
// ---------------------------------------------------------------------------

const cardClassName = "rounded-xl border border-gray-800 bg-gray-950/40 p-4";
const inputClassName =
  "w-full rounded-lg border border-gray-700 bg-gray-900/80 px-3 py-2 text-sm text-gray-200 placeholder:text-gray-600 focus:border-indigo-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60";
const smallBtnClassName =
  "rounded p-1 text-gray-500 hover:text-gray-300 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none";

// Model routing config — static, hoisted to module level to avoid re-creation on each render
const MODEL_ROUTING_FIELDS = [
  {
    key: "haikuModel" as const,
    label: "Haiku 模型",
    envVar: "ANTHROPIC_DEFAULT_HAIKU_MODEL",
    hint: "Nhiệm vụ nhẹ (phân loại, trích xuất, hỏi đáp đơn giản)",
    patchKey: "anthropic_default_haiku_model" as const,
  },
  {
    key: "sonnetModel" as const,
    label: "Sonnet 模型",
    envVar: "ANTHROPIC_DEFAULT_SONNET_MODEL",
    hint: "Nhiệm vụ cân bằng (viết, sắp xếp, lý luận nhiều bước)",
    patchKey: "anthropic_default_sonnet_model" as const,
  },
  {
    key: "opusModel" as const,
    label: "Opus 模型",
    envVar: "ANTHROPIC_DEFAULT_OPUS_MODEL",
    hint: "Nhiệm vụ phức tạp (tạo bài viết dài, phân tích chuyên sâu)",
    patchKey: "anthropic_default_opus_model" as const,
  },
  {
    key: "subagentModel" as const,
    label: "Mô hình đại lý trẻ em",
    envVar: "CLAUDE_CODE_SUBAGENT_MODEL",
    hint: "Subagent Mô hình được sử dụng khi thực hiện song song",
    patchKey: "claude_code_subagent_model" as const,
  },
] as const;

// Small inline clear button shown next to "Hiện tại：" when a value is set
const inlineClearClassName =
  "ml-1.5 inline-flex items-center rounded p-0.5 text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50";

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function SectionHeading({ title, description }: { title: string; description: string }) {
  return (
    <div className="mb-4">
      <h3 className="text-base font-semibold text-gray-100">{title}</h3>
      <p className="mt-1 text-sm text-gray-500">{description}</p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface AgentConfigTabProps {
  visible: boolean;
}

export function AgentConfigTab({ visible }: AgentConfigTabProps) {
  const [remoteData, setRemoteData] = useState<GetSystemConfigResponse | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [draft, setDraft] = useState<AgentDraft>({
    anthropicKey: "",
    anthropicBaseUrl: "",
    anthropicModel: "",
    haikuModel: "",
    opusModel: "",
    sonnetModel: "",
    subagentModel: "",
    cleanupDelaySeconds: "300",
    maxConcurrentSessions: "5",
  });
  const savedRef = useRef<AgentDraft>({
    anthropicKey: "",
    anthropicBaseUrl: "",
    anthropicModel: "",
    haikuModel: "",
    opusModel: "",
    sonnetModel: "",
    subagentModel: "",
    cleanupDelaySeconds: "300",
    maxConcurrentSessions: "5",
  });
  const [saving, setSaving] = useState(false);
  const [clearingField, setClearingField] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showKey, setShowKey] = useState(false);
  const [modelRoutingExpanded, setModelRoutingExpanded] = useState(false);

  // Load config on mount
  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const res = await API.getSystemConfig();
      setRemoteData(res);
      const d = buildDraft(res);
      savedRef.current = d;
      setDraft(d);
    } catch (err) {
      setLoadError((err as Error).message);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const isDirty = !deepEqual(draft, savedRef.current);
  useWarnUnsaved(isDirty);

  const updateDraft = useCallback(
    <K extends keyof AgentDraft>(key: K, value: AgentDraft[K]) => {
      setDraft((prev) => ({ ...prev, [key]: value }));
      setSaveError(null);
    },
    [],
  );

  const handleSave = useCallback(async () => {
    const patch = buildPatch(draft, savedRef.current);
    if (Object.keys(patch).length === 0) return;
    setSaving(true);
    setSaveError(null);
    try {
      const res = await API.updateSystemConfig(patch);
      setRemoteData(res);
      const newDraft = buildDraft(res);
      savedRef.current = newDraft;
      setDraft(newDraft);
      useConfigStatusStore.getState().refresh();
      useAppStore.getState().pushToast("Cấu hình tác nhân ArcReel đã lưu", "success");
    } catch (err) {
      setSaveError((err as Error).message);
    } finally {
      setSaving(false);
    }
  }, [draft]);

  const handleReset = useCallback(() => {
    setDraft(savedRef.current);
    setSaveError(null);
  }, []);

  // Clear a single field immediately via PATCH
  const handleClearField = useCallback(
    async (fieldId: string, patch: SystemConfigPatch, label: string) => {
      setClearingField(fieldId);
      try {
        const res = await API.updateSystemConfig(patch);
        setRemoteData(res);
        const nextSavedDraft = buildDraft(res);
        savedRef.current = nextSavedDraft;
        setDraft(nextSavedDraft);
        useConfigStatusStore.getState().refresh();
        useAppStore.getState().pushToast(`${label} Đã Xóa`, "success");
      } catch (err) {
        useAppStore.getState().pushToast(`Xóa thất bại: ${(err as Error).message}`, "error");
      } finally {
        setClearingField(null);
      }
    },
    [],
  );

  const isBusy = saving || clearingField !== null;

  // Loading / error states
  if (loadError) {
    return (
      <div className={visible ? "px-6 py-8" : "hidden"}>
        <div className="text-sm text-rose-400">Tải thất bại: {loadError}</div>
        <button
          type="button"
          onClick={() => void load()}
          className="mt-3 inline-flex items-center gap-2 rounded-lg border border-gray-700 px-3 py-2 text-sm text-gray-300 hover:border-gray-600 hover:bg-gray-800/50"
        >
          <Loader2 className="h-4 w-4" />
          Thử lại
        </button>
      </div>
    );
  }

  if (!remoteData) {
    return (
      <div className={visible ? "flex items-center gap-2 px-6 py-8 text-gray-400" : "hidden"}>
        <Loader2 className="h-4 w-4 animate-spin text-indigo-400" />
        Đang tải...
      </div>
    );
  }

  const settings = remoteData.settings;

  return (
    <div className={visible ? undefined : "hidden"}>
      <div className="space-y-8 px-6 pb-0 pt-6">
        {/* Page intro */}
        <div>
          <div className="flex items-center gap-3">
            <div className="rounded-2xl border border-gray-800 bg-gray-900 p-3 shadow-inner shadow-white/5">
              <ClaudeColor size={24} />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-gray-100">Tác nhân ArcReel</h2>
              <p className="text-sm text-gray-500">
                Dựa trên SDK Agent Claude, điều khiển Trợ lý AI theo phong cách đối thoại và quy trình làm việc tự động
              </p>
            </div>
          </div>
          <div className="mt-3 flex items-start gap-2 rounded-lg border border-gray-800/60 bg-gray-900/30 px-3 py-2">
            <Terminal className="mt-0.5 h-3.5 w-3.5 shrink-0 text-gray-500" />
            <p className="text-xs text-gray-500">
              Các mục cấu hình tương thích với cách đặt tên biến Claude Code Môi trường và bạn có thể sử dụng API Kế hoạch mã hóa tương thích với Claude Code.
            </p>
          </div>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* Section 1: API Key + Base URL */}
        {/* ----------------------------------------------------------------- */}
        <div>
          <SectionHeading
            title="Thông tin xác thực API"
            description="Khóa API Anthropic là điều kiện cần thiết để tác nhân hoạt động"
          />

          {/* API Key card */}
          <div className={`${cardClassName} space-y-4`}>
            <div>
              <div className="flex items-center justify-between">
                <label htmlFor="agent-anthropic-key" className="text-sm font-medium text-gray-100">
                  API Key
                </label>
                {settings.anthropic_api_key.is_set && (
                  <div className="flex items-center text-xs text-gray-500">
                    <span className="truncate">
                      Hiện tại：{settings.anthropic_api_key.masked ?? "Đã đặt"}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        void handleClearField(
                          "anthropic_api_key",
                          { anthropic_api_key: "" },
                          "Anthropic API Key",
                        )
                      }
                      disabled={isBusy}
                      className={inlineClearClassName}
                      aria-label="Xóa đã lưuKhóa API nhân loại"
                    >
                      {clearingField === "anthropic_api_key" ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <X className="h-3 w-3" />
                      )}
                    </button>
                  </div>
                )}
              </div>
              <p className="mt-0.5 text-xs text-gray-500">
                Tương ứng biến môi trường ANTHROPIC_API_KEY
              </p>
              <div className="relative mt-2">
                <input
                  id="agent-anthropic-key"
                  type={showKey ? "text" : "password"}
                  value={draft.anthropicKey}
                  onChange={(e) => updateDraft("anthropicKey", e.target.value)}
                  placeholder="sk-ant-…"
                  className={`${inputClassName} pr-10`}
                  autoComplete="off"
                  spellCheck={false}
                  name="anthropic_api_key"
                  disabled={saving}
                />
                {draft.anthropicKey && (
                  <button
                    type="button"
                    onClick={() => updateDraft("anthropicKey", "")}
                    className={`absolute right-8 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
                    aria-label="XóaĐầu vào"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setShowKey((v) => !v)}
                  className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
                  aria-label={showKey ? "Ẩn khóa" : "Hiển thị khóa"}
                >
                  {showKey ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                </button>
              </div>
            </div>

            {/* Base URL */}
            <div className="border-t border-gray-800 pt-4">
              <div className="flex items-center justify-between">
                <label htmlFor="agent-base-url" className="text-sm font-medium text-gray-100">
                  Base URL
                </label>
                {settings.anthropic_base_url && (
                  <button
                    type="button"
                    onClick={() =>
                      void handleClearField(
                        "anthropic_base_url",
                        { anthropic_base_url: "" },
                        "Anthropic Base URL",
                      )
                    }
                    disabled={isBusy}
                    className="inline-flex items-center gap-1 rounded text-xs text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
                    aria-label="Xóa đã lưuURL cơ sở nhân chủng học"
                  >
                    {clearingField === "anthropic_base_url" ? (
                      <Loader2 className="h-3 w-3 animate-spin" />
                    ) : (
                      <X className="h-3 w-3" />
                    )}
                    Xóa đã lưu
                  </button>
                )}
              </div>
              <p className="mt-0.5 text-xs text-gray-500">
                Tương ứng ANTHROPIC_BASE_URL, để trống để dùng địa chỉ mặc định chính thức
              </p>
              <div className="relative mt-2">
                <input
                  id="agent-base-url"
                  value={draft.anthropicBaseUrl}
                  onChange={(e) => updateDraft("anthropicBaseUrl", e.target.value)}
                  placeholder="https://anthropic-proxy.example.com"
                  className={`${inputClassName}${draft.anthropicBaseUrl ? " pr-8" : ""}`}
                  autoComplete="off"
                  spellCheck={false}
                  name="anthropic_base_url"
                  disabled={saving}
                />
                {draft.anthropicBaseUrl && (
                  <button
                    type="button"
                    onClick={() => updateDraft("anthropicBaseUrl", "")}
                    className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
                    aria-label="Xóa Base URL Đầu vào"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* ----------------------------------------------------------------- */}
        {/* Section 2: Model Configuration */}
        {/* ----------------------------------------------------------------- */}
        <div>
          <SectionHeading
            title="Cấu hình mô hình"
            description="Chỉ định mô hình Claude mà tác nhân sử dụng. Để trống sẽ dùng giá trị mặc định của Claude Agent SDK."
          />

          <div className={cardClassName}>
            <div className="flex items-center justify-between">
              <label htmlFor="agent-model" className="text-sm font-medium text-gray-100">
                Mô hình mặc định
              </label>
              {settings.anthropic_model && (
                <button
                  type="button"
                  onClick={() =>
                    void handleClearField(
                      "anthropic_model",
                      { anthropic_model: "" },
                      "ANTHROPIC_MODEL",
                    )
                  }
                  disabled={isBusy}
                  className="inline-flex items-center gap-1 rounded text-xs text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none"
                  aria-label="Xóa đã lưuConfiguration Mode"
                >
                  {clearingField === "anthropic_model" ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <X className="h-3 w-3" />
                  )}
                  Xóa đã lưu
                </button>
              )}
            </div>
            <p className="mt-0.5 text-xs text-gray-500">
              Tương ứng ANTHROPIC_MODEL, ghi đè mô hình mặc định
            </p>
            <div className="relative mt-2">
              <input
                id="agent-model"
                value={draft.anthropicModel}
                onChange={(e) => updateDraft("anthropicModel", e.target.value)}
                placeholder="ANTHROPIC_MODEL"
                className={`${inputClassName}${draft.anthropicModel ? " pr-8" : ""}`}
                autoComplete="off"
                spellCheck={false}
                name="anthropic_model"
                disabled={saving}
              />
              {draft.anthropicModel && (
                <button
                  type="button"
                  onClick={() => updateDraft("anthropicModel", "")}
                  className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
                  aria-label="XóaCấu hình mô hìnhĐầu vào"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </div>

            {/* Advanced model routing */}
            <details
              open={modelRoutingExpanded}
              onToggle={(e) => setModelRoutingExpanded(e.currentTarget.open)}
              className="mt-4 rounded-xl border border-gray-800 bg-gray-950/40 p-4"
            >
              <summary className="flex cursor-pointer list-none items-center justify-between text-sm font-medium text-gray-100">
                <span className="inline-flex items-center gap-2">
                  <SlidersHorizontal className="h-4 w-4 text-gray-400" />
                  Định tuyến mô hình nâng cao
                </span>
                <span className="inline-flex h-8 w-8 items-center justify-center rounded-full border border-gray-800 bg-gray-900 text-gray-500">
                  <ChevronDown
                    className={`h-4 w-4 transition-transform duration-200 ${
                      modelRoutingExpanded ? "rotate-180 text-gray-200" : ""
                    }`}
                  />
                </span>
              </summary>
              <p className="mt-2 text-xs text-gray-500">
                Claude Agent SDK Hỗ trợ định tuyến đến các mô hình khác nhau theo cấp độ khả năng. Để trống để sử dụng Mặc định mô hình ở trên.
              </p>
              <div className="mt-4 grid gap-4">
                {MODEL_ROUTING_FIELDS.map(({ key, label, envVar, hint, patchKey }) => {
                  const settingsValue = settings[patchKey];
                  return (
                    <div key={key}>
                      <div className="flex items-center justify-between">
                        <div>
                          <div className="text-sm font-medium text-gray-100">{label}</div>
                          <div className="text-xs text-gray-500">{hint}</div>
                        </div>
                        {settingsValue && (
                          <button
                            type="button"
                            onClick={() =>
                              void handleClearField(
                                patchKey,
                                { [patchKey]: "" } as SystemConfigPatch,
                                label,
                              )
                            }
                            disabled={isBusy}
                            className="inline-flex items-center gap-1 text-xs text-gray-600 transition-colors hover:text-rose-400 disabled:cursor-not-allowed disabled:opacity-50 focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none rounded"
                            aria-label={`Xóa đã lưucủa ${label}`}
                          >
                            {clearingField === patchKey ? (
                              <Loader2 className="h-3 w-3 animate-spin" />
                            ) : (
                              <X className="h-3 w-3" />
                            )}
                            Xóa
                          </button>
                        )}
                      </div>
                      <div className="relative mt-1.5">
                        <input
                          value={draft[key]}
                          onChange={(e) => updateDraft(key, e.target.value)}
                          placeholder={envVar}
                          className={`${inputClassName}${draft[key] ? " pr-8" : ""}`}
                          autoComplete="off"
                          spellCheck={false}
                          disabled={saving}
                        />
                        {draft[key] && (
                          <button
                            type="button"
                            onClick={() => updateDraft(key, "")}
                            className={`absolute right-2 top-1/2 -translate-y-1/2 ${smallBtnClassName}`}
                            aria-label={`Xóa ${label} Đầu vào`}
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </details>
          </div>
        </div>

        {/* Cài đặt nâng cao */}
        <div className={cardClassName}>
          <details>
            <summary className="flex cursor-pointer select-none items-center gap-2 text-sm font-medium text-gray-400 transition-colors hover:text-gray-200">
              <SlidersHorizontal className="h-4 w-4" />
              Cài đặt nâng cao
            </summary>
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-200">
                  Độ trễ dọn dẹp phiên (giây)
                </label>
                <p className="mt-0.5 text-xs text-gray-500">
                  Sau khi phiên kết thúc, hãy đợi thời gian này trước khi giải phóng tài nguyên. Chúng sẽ được tự động khôi phục khi sử dụng lại đối thoại.
                </p>
                <input
                  type="number"
                  min={10}
                  max={3600}
                  value={draft.cleanupDelaySeconds}
                  onChange={(e) => updateDraft("cleanupDelaySeconds", e.target.value)}
                  className={`${inputClassName} mt-1.5 max-w-[120px]`}
                  disabled={saving}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-200">
                  Số phiên đồng thời tối đa
                </label>
                <p className="mt-0.5 text-xs text-gray-500">
                  Đồng thời, giới hạn trên của phiên tác nhân đang hoạt động được duy trì và phiên không sử dụng lâu nhất sẽ tự động được giải phóng khi vượt quá (phiên đã xóa sẽ được duy trì và khôi phục vào lần đối thoại tiếp theo)
                </p>
                <input
                  type="number"
                  min={1}
                  max={20}
                  value={draft.maxConcurrentSessions}
                  onChange={(e) => updateDraft("maxConcurrentSessions", e.target.value)}
                  className={`${inputClassName} mt-1.5 max-w-[120px]`}
                  disabled={saving}
                />
              </div>
            </div>
          </details>
        </div>
      </div>

      <TabSaveFooter
        isDirty={isDirty}
        saving={saving}
        disabled={clearingField !== null}
        error={saveError}
        onSave={() => void handleSave()}
        onReset={handleReset}
      />
    </div>
  );
}
