import { useLocation } from "wouter";
import { Bot } from "lucide-react";
import { GlobalHeader } from "./GlobalHeader";
import { AssetSidebar } from "./AssetSidebar";
import { AgentCopilot } from "@/components/copilot/AgentCopilot";
import { useTasksSSE } from "@/hooks/useTasksSSE";
import { useProjectEventsSSE } from "@/hooks/useProjectEventsSSE";
import { useProjectsStore } from "@/stores/projects-store";
import { useAppStore } from "@/stores/app-store";
import { UI_LAYERS } from "@/utils/ui-layers";

// ---------------------------------------------------------------------------
// StudioLayout — three-column studio workspace shell
// ---------------------------------------------------------------------------

interface StudioLayoutProps {
  children: React.ReactNode;
}

export function StudioLayout({ children }: StudioLayoutProps) {
  const [, setLocation] = useLocation();
  const currentProjectName = useProjectsStore((s) => s.currentProjectName);
  const assistantPanelOpen = useAppStore((s) => s.assistantPanelOpen);
  const toggleAssistantPanel = useAppStore((s) => s.toggleAssistantPanel);

  // Kết nối luồng SSE tác vụ khi vào không gian làm việc
  useTasksSSE(currentProjectName);
  useProjectEventsSSE(currentProjectName);

  return (
    <div className="flex h-screen flex-col bg-gray-950 text-gray-100">
      <GlobalHeader onNavigateBack={() => setLocation("~/app/projects")} />
      <div className="flex flex-1 overflow-hidden">
        <AssetSidebar className="w-[15%] min-w-50 border-r border-gray-800" />
        <main className="flex-1 overflow-auto">
          {children}
        </main>
        <div
          className={`shrink-0 bg-gray-900 transition-[width,min-width,border-color] duration-300 ease-in-out overflow-hidden ${
            assistantPanelOpen ? "border-l border-gray-800" : "border-l border-transparent"
          }`}
          style={{
            width: assistantPanelOpen ? "40%" : "0",
            minWidth: assistantPanelOpen ? "22.5rem" : "0",
          }}
        >
          {/* Luôn được hiển thị nhưng bị ẩn khi Thu gọn, duy trì trạng thái */}
          <div
            className={`h-full transition-opacity duration-200 ${
              assistantPanelOpen ? "opacity-100" : "opacity-0 pointer-events-none"
            }`}
          >
            <AgentCopilot />
          </div>
        </div>
      </div>

      {/* Bóng trợ lý nổi — Cố định ở góc trên bên phải khi Thu gọn */}
      <button
        type="button"
        onClick={toggleAssistantPanel}
        className={`fixed top-14 right-4 flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 shadow-lg shadow-indigo-500/20 transition-all duration-300 ease-in-out ${UI_LAYERS.workspaceFloating} ${
          assistantPanelOpen
            ? "scale-0 opacity-0 pointer-events-none"
            : "scale-100 opacity-100 hover:bg-indigo-500 cursor-pointer"
        }`}
        style={{ transitionDelay: assistantPanelOpen ? "0ms" : "200ms" }}
        title="Mở rộng bảng trợ lý"
        aria-label="Mở rộng bảng trợ lý"
      >
        <Bot className="h-5 w-5 text-white" />
      </button>
    </div>
  );
}
