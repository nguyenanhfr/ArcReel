import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { useConfigStatusStore } from "@/stores/config-status-store";
import { SystemConfigPage } from "@/components/pages/SystemConfigPage";
import type { GetSystemConfigResponse, ProviderInfo } from "@/types";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeConfigResponse(
  overrides?: Partial<GetSystemConfigResponse["settings"]>,
): GetSystemConfigResponse {
  return {
    settings: {
      default_video_backend: "gemini/veo-3",
      default_image_backend: "gemini/imagen-4",
      default_text_backend: "",
      text_backend_script: "",
      text_backend_overview: "",
      text_backend_style: "",
      video_generate_audio: true,
      anthropic_api_key: { is_set: true, masked: "sk-ant-***" },
      anthropic_base_url: "",
      anthropic_model: "",
      anthropic_default_haiku_model: "",
      anthropic_default_opus_model: "",
      anthropic_default_sonnet_model: "",
      claude_code_subagent_model: "",
      agent_session_cleanup_delay_seconds: 300,
      agent_max_concurrent_sessions: 5,
      ...overrides,
    },
    options: {
      video_backends: ["gemini/veo-3"],
      image_backends: ["gemini/imagen-4"],
      text_backends: [],
    },
  };
}

function makeProviders(overrides?: Partial<ProviderInfo>): { providers: ProviderInfo[] } {
  return {
    providers: [
      {
        id: "gemini",
        display_name: "Google Gemini",
        description: "Google Gemini API",
        status: "ready",
        media_types: ["image", "video", "text"],
        capabilities: [],
        configured_keys: ["api_key"],
        missing_keys: [],
        ...overrides,
      },
    ],
  };
}

function renderPage(path = "/app/settings") {
  const location = memoryLocation({ path, record: true });
  return render(
    <Router hook={location.hook}>
      <SystemConfigPage />
    </Router>,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("SystemConfigPage", () => {
  beforeEach(() => {
    useConfigStatusStore.setState(useConfigStatusStore.getInitialState(), true);
    vi.restoreAllMocks();

    // Default: silence child section network calls so tests don't hang
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(makeConfigResponse());
    vi.spyOn(API, "getProviders").mockResolvedValue(makeProviders());
    vi.spyOn(API, "listCustomProviders").mockResolvedValue({ providers: [] });
    vi.spyOn(API, "getProviderConfig").mockResolvedValue({
      id: "gemini",
      display_name: "Google Gemini",
      status: "ready",
      media_types: ["image", "video"],
      capabilities: [],
      fields: [],
    } as never);
    vi.spyOn(API, "listCredentials").mockResolvedValue({ credentials: [] });
    vi.spyOn(API, "getUsageStatsGrouped").mockResolvedValue({ stats: [], period: { start: "", end: "" } });
  });

  it("renders the page header", () => {
    renderPage();
    expect(screen.getByText("Cài đặt")).toBeInTheDocument();
    expect(screen.getByText("Hệ thốngQuản lý quyền truy cập cấu hình và API")).toBeInTheDocument();
  });

  it("renders all 5 sidebar sections", () => {
    renderPage();
    expect(screen.getByRole("button", { name: /đại lý/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /nhà cung cấp/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Lựa chọn mô hình/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Thống kê sử dụng/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /API quản lý/ })).toBeInTheDocument();
  });

  it("defaults to the Phần đại lý", () => {
    renderPage();
    const agentButton = screen.getByRole("button", { name: /đại lý/ });
    // Active sidebar item has the indigo border class applied
    expect(agentButton.className).toContain("border-indigo-500");
  });

  it("clicking Nhà cung cấp biến nó thành phần hoạt động", async () => {
    renderPage();
    const providersButton = screen.getByRole("button", { name: /nhà cung cấp/ });
    fireEvent.click(providersButton);
    await waitFor(() => {
      expect(providersButton.className).toContain("border-indigo-500");
    });
  });

  it("clicking Lựa chọn mô hình làm cho nó trở thành phần hoạt động", async () => {
    renderPage();
    const mediaButton = screen.getByRole("button", { name: /Lựa chọn mô hình/ });
    fireEvent.click(mediaButton);
    await waitFor(() => {
      expect(mediaButton.className).toContain("border-indigo-500");
    });
  });

  it("clicking Thống kê sử dụng làm cho nó trở thành phần hoạt động", async () => {
    renderPage();
    const usageButton = screen.getByRole("button", { name: /Thống kê sử dụng/ });
    fireEvent.click(usageButton);
    await waitFor(() => {
      expect(usageButton.className).toContain("border-indigo-500");
    });
  });

  it("shows config warning banner when there are config issues", async () => {
    // Simulate unconfigured anthropic key to trigger an issue
    vi.spyOn(API, "getSystemConfig").mockResolvedValue(
      makeConfigResponse({ anthropic_api_key: { is_set: false, masked: null } }),
    );
    vi.spyOn(API, "getProviders").mockResolvedValue(makeProviders({ status: "ready" }));

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Cấu hình yêu cầu sau đây vẫn chưa được hoàn thành:")).toBeInTheDocument();
    });
    expect(
      screen.getByRole("button", { name: /Tác nhân ArcReel API Key/ }),
    ).toBeInTheDocument();
  });

  it("does not show warning banner when config is complete", async () => {
    renderPage();

    // Give time for config status to load
    await waitFor(() => {
      expect(API.getProviders).toHaveBeenCalled();
    });

    expect(screen.queryByText("Cấu hình yêu cầu sau đây vẫn chưa được hoàn thành:")).not.toBeInTheDocument();
  });

  it("renders the back link that navigates to projects", () => {
    renderPage();
    const link = screen.getByRole("link", { name: "Quay lại sảnh dự án" });
    expect(link).toBeInTheDocument();
    expect(link).toHaveAttribute("href", "/app/projects");
  });
});
