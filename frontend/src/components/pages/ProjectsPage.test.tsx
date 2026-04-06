import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";
import { ProjectsPage } from "@/components/pages/ProjectsPage";

vi.mock("@/components/pages/CreateProjectModal", () => ({
  CreateProjectModal: () => <div data-testid="create-project-modal">Create Project Modal</div>,
}));

function renderPage() {
  const location = memoryLocation({ path: "/app/projects", record: true });
  return {
    ...render(
      <Router hook={location.hook}>
        <ProjectsPage />
      </Router>,
    ),
    location,
  };
}

describe("ProjectsPage", () => {
  beforeEach(() => {
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("shows loading state while projects are being fetched", () => {
    vi.spyOn(API, "listProjects").mockImplementation(
      () => new Promise(() => {}),
    );

    renderPage();
    expect(screen.getByText("Đang tải danh sách dự án...")).toBeInTheDocument();
  });

  it("shows empty state when no projects exist", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });

    renderPage();

    expect(await screen.findByText("Chưa có dự án")).toBeInTheDocument();
    expect(
      screen.getByText("Bấm vào "Dự án mới" hoặc "Nhập ZIP" ở góc trên bên phải để bắt đầu tạo"),
    ).toBeInTheDocument();
  });

  it("renders project cards when data exists", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({
      projects: [
        {
          name: "demo",
          title: "Demo Project",
          style: "Anime",
          thumbnail: null,
          status: {
            current_phase: "production",
            phase_progress: 0.5,
            characters: { total: 2, completed: 2 },
            clues: { total: 2, completed: 1 },
            episodes_summary: { total: 1, scripted: 1, in_production: 1, completed: 0 },
          },
        },
      ],
    });

    renderPage();

    expect(await screen.findByText("Demo Project")).toBeInTheDocument();
    expect(screen.getByText("Anime · Đang sản xuất")).toBeInTheDocument();
    expect(screen.getByText("50%")).toBeInTheDocument();
  });

  it("opens create project modal after clicking new project button", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });

    renderPage();
    await screen.findByText("Chưa có dự án");

    fireEvent.click(screen.getByRole("button", { name: "Dự án mới" }));

    await waitFor(() => {
      expect(useProjectsStore.getState().showCreateModal).toBe(true);
    });
    expect(screen.getByTestId("create-project-modal")).toBeInTheDocument();
  });

  it("imports a zip project, refreshes the list, and navigates to the workspace", async () => {
    vi.spyOn(API, "listProjects")
      .mockResolvedValueOnce({ projects: [] })
      .mockResolvedValueOnce({
        projects: [
          {
            name: "imported-demo",
            title: "Imported Demo",
            style: "Anime",
            thumbnail: null,
            status: {
              current_phase: "completed",
              phase_progress: 1,
              characters: { total: 1, completed: 1 },
              clues: { total: 1, completed: 1 },
              episodes_summary: { total: 1, scripted: 1, in_production: 0, completed: 1 },
            },
          },
        ],
      });
    vi.spyOn(API, "importProject").mockResolvedValue({
      success: true,
      project_name: "imported-demo",
      project: {
        title: "Imported Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [],
        characters: {},
        clues: {},
      },
      warnings: ["Đã tìm thấy tệp/thư mục bổ sung không được nhận dạng: phần bổ sung"],
      conflict_resolution: "none",
      diagnostics: {
        auto_fixed: [{ code: "missing_clues_field", message: "segments[0]: Hoàn thành các trường còn thiếu manh mối_in_segment" }],
        warnings: [{ code: "validation_warning", message: "Đã tìm thấy tệp/thư mục bổ sung không được nhận dạng: phần bổ sung" }],
      },
    });

    const { container, location } = renderPage();
    await screen.findByText("Chưa có dự án");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["zip"], "project.zip", { type: "application/zip" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    await waitFor(() => {
      expect(API.importProject).toHaveBeenCalledWith(file, "prompt");
    });
    await waitFor(() => {
      expect(location.history?.at(-1)).toBe("/app/projects/imported-demo");
    });
    expect(useAppStore.getState().toast?.text).toContain("Cảnh báo nhập khẩu");
  });

  it("shows a structured toast when import fails", async () => {
    vi.spyOn(API, "listProjects").mockResolvedValue({ projects: [] });
    const error = new Error("Xác thực gói nhập thất bại") as Error & {
      detail?: string;
      errors?: string[];
      warnings?: string[];
      diagnostics?: {
        blocking: { code: string; message: string }[];
        auto_fixable: { code: string; message: string }[];
        warnings: { code: string; message: string }[];
      };
    };
    error.detail = "Xác thực gói nhập thất bại";
    error.errors = ["dự án.json bị thiếu", "thiếu tập lệnh/episode_1.json", "Thiếu sơ đồ nhân vật"];
    error.warnings = ["Đã tìm thấy tệp/thư mục bổ sung không được nhận dạng: phần bổ sung"];
    error.diagnostics = {
      blocking: [
        { code: "validation_error", message: "dự án.json bị thiếu" },
        { code: "validation_error", message: "thiếu tập lệnh/episode_1.json" },
      ],
      auto_fixable: [
        { code: "missing_clues_field", message: "segments[0]: Hoàn thành các trường còn thiếu manh mối_in_segment" },
      ],
      warnings: [
        { code: "validation_warning", message: "Đã tìm thấy tệp/thư mục bổ sung không được nhận dạng: phần bổ sung" },
      ],
    };
    vi.spyOn(API, "importProject").mockRejectedValue(error);

    const { container } = renderPage();
    await screen.findByText("Chưa có dự án");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(fileInput, {
      target: { files: [new File(["zip"], "broken.zip", { type: "application/zip" })] },
    });

    await waitFor(() => {
      expect(useAppStore.getState().toast?.text).toContain("Xác thực gói nhập thất bại");
    });
    expect(screen.getByText("Nhập chẩn đoán")).toBeInTheDocument();
    expect(screen.getByText("dự án.json bị thiếu")).toBeInTheDocument();
    expect(screen.getByText("thiếu tập lệnh/episode_1.json")).toBeInTheDocument();
    expect(screen.getByText("segments[0]: Hoàn thành các trường còn thiếu manh mối_in_segment")).toBeInTheDocument();
  });

  it("opens a secondary confirmation when import hits a duplicate project id", async () => {
    vi.spyOn(API, "listProjects")
      .mockResolvedValueOnce({ projects: [] })
      .mockResolvedValueOnce({
        projects: [
          {
            name: "demo",
            title: "Demo",
            style: "Anime",
            thumbnail: null,
            status: {
              current_phase: "completed",
              phase_progress: 1,
              characters: { total: 1, completed: 1 },
              clues: { total: 1, completed: 1 },
              episodes_summary: { total: 1, scripted: 1, in_production: 0, completed: 1 },
            },
          },
        ],
      });
    const conflictError = new Error("Phát hiện xung đột mã dự án") as Error & {
      status?: number;
      detail?: string;
      errors?: string[];
      conflict_project_name?: string;
    };
    conflictError.status = 409;
    conflictError.detail = "Phát hiện xung đột mã dự án";
    conflictError.errors = ["Dự án编号 'demo' Đã tồn tại"];
    conflictError.conflict_project_name = "demo";

    vi.spyOn(API, "importProject")
      .mockRejectedValueOnce(conflictError)
      .mockResolvedValueOnce({
        success: true,
        project_name: "demo-renamed",
        project: {
          title: "Renamed Demo",
          content_mode: "narration",
          style: "Anime",
          episodes: [],
          characters: {},
          clues: {},
        },
        warnings: [],
        conflict_resolution: "renamed",
        diagnostics: {
          auto_fixed: [],
          warnings: [],
        },
      });

    const { container, location } = renderPage();
    await screen.findByText("Chưa có dự án");

    const fileInput = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["zip"], "project.zip", { type: "application/zip" });
    fireEvent.change(fileInput, { target: { files: [file] } });

    expect(await screen.findByText("Đã phát hiện số Dựán trùng lặp")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Tự động đổi tên nhập khẩu" }));

    await waitFor(() => {
      expect(API.importProject).toHaveBeenNthCalledWith(1, file, "prompt");
    });
    await waitFor(() => {
      expect(API.importProject).toHaveBeenNthCalledWith(2, file, "rename");
    });
    await waitFor(() => {
      expect(location.history?.at(-1)).toBe("/app/projects/demo-renamed");
    });
  });
});
