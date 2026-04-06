import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Router, useLocation } from "wouter";
import { memoryLocation } from "wouter/memory-location";
import { API, type ProjectEventStreamOptions } from "@/api";
import { useProjectEventsSSE } from "./useProjectEventsSSE";
import { useAppStore } from "@/stores/app-store";
import { useProjectsStore } from "@/stores/projects-store";

function HookHarness({ projectName }: { projectName: string }) {
  useProjectEventsSSE(projectName);
  const [location] = useLocation();
  return <div data-testid="location">{location}</div>;
}

function renderHarness(path = "/") {
  const { hook } = memoryLocation({ path });
  return render(
    <Router hook={hook}>
      <HookHarness projectName="demo" />
    </Router>,
  );
}

describe("useProjectEventsSSE", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    useAppStore.setState(useAppStore.getInitialState(), true);
    useProjectsStore.setState(useProjectsStore.getInitialState(), true);
    vi.restoreAllMocks();
    vi.spyOn(API, "getProject").mockResolvedValue({
      project: {
        title: "Demo",
        content_mode: "narration",
        style: "Anime",
        episodes: [{ episode: 1, title: "Tập 1", script_file: "scripts/episode_1.json" }],
        characters: { hero: { description: "dũng cảm" } },
        clues: {},
      },
      scripts: {
        "episode_1.json": {
          episode: 1,
          title: "Tập 1",
          content_mode: "narration",
          duration_seconds: 4,
          summary: "",
          novel: { title: "", chapter: "" },
          segments: [],
        },
      },
    });
  });

  it("refreshes and navigates to the focused workspace target for remote changes", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/");
    expect(capturedOptions).toBeDefined();
    expect(capturedOptions?.projectName).toBe("demo");

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-1",
          fingerprint: "fp-1",
          generated_at: "2026-03-01T00:00:00Z",
          source: "filesystem",
          changes: [
            {
              entity_type: "character",
              action: "created",
              entity_id: "hero",
              label: "Nhân vật「hero」",
              focus: {
                pane: "characters",
                anchor_type: "character",
                anchor_id: "hero",
              },
              important: true,
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalledWith("demo");
      expect(screen.getByTestId("location")).toHaveTextContent("/characters");
    });
    expect(useAppStore.getState().scrollTarget).toEqual(
      expect.objectContaining({
        type: "character",
        id: "hero",
        route: "/characters",
      }),
    );
    expect(useAppStore.getState().workspaceNotifications[0]).toEqual(
      expect.objectContaining({
        text: "AI Nhân vật "anh hùng" vừa được thêm vào, bấm vào để xem",
        target: expect.objectContaining({
          type: "character",
          id: "hero",
          route: "/characters",
        }),
      }),
    );
    expect(useAppStore.getState().assistantToolActivitySuppressed).toBe(true);
  });

  it("defers focus when the user is editing", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/");
    const input = document.createElement("input");
    document.body.appendChild(input);
    input.focus();

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-2",
          fingerprint: "fp-2",
          generated_at: "2026-03-01T00:00:00Z",
          source: "worker",
          changes: [
            {
              entity_type: "clue",
              action: "updated",
              entity_id: "mặt dây chuyền ngọc bích",
              label: "Manh mối「mặt dây chuyền ngọc bích",
              focus: {
                pane: "clues",
                anchor_type: "clue",
                anchor_id: "mặt dây chuyền ngọc bích",
              },
              important: true,
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalledWith("demo");
      expect(useAppStore.getState().workspaceNotifications[0]?.target?.id).toBe("mặt dây chuyền ngọc bích");
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/");
    expect(useAppStore.getState().scrollTarget).toBeNull();
  });

  it("shows a toast without navigation for generation completion batches", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/episodes/1");

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-3",
          fingerprint: "fp-3",
          generated_at: "2026-03-01T00:00:00Z",
          source: "worker",
          changes: [
            {
              entity_type: "segment",
              action: "storyboard_ready",
              entity_id: "E1S01",
              label: "Phân cảnh「E1S01」",
              episode: 1,
              focus: null,
              important: true,
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalledWith("demo");
      expect(useAppStore.getState().toast?.text).toBe("Phân cảnh「E1S01」Phân cảnh Ảnh đã được tạo");
    });
    expect(useAppStore.getState().toast?.tone).toBe("success");
    expect(useAppStore.getState().workspaceNotifications[0]).toEqual(
      expect.objectContaining({
        text: "Phân cảnh「E1S01」Phân cảnh Ảnh đã được tạo",
        tone: "success",
        target: null,
      }),
    );
    expect(screen.getByTestId("location")).toHaveTextContent("/episodes/1");
    expect(useAppStore.getState().scrollTarget).toBeNull();
  });

  it("groups remote changes by type and invalidates only the touched entity keys", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/");

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-grouped",
          fingerprint: "fp-grouped",
          generated_at: "2026-03-01T00:00:00Z",
          source: "filesystem",
          changes: [
            {
              entity_type: "character",
              action: "created",
              entity_id: "hero",
              label: "Nhân vật「hero」",
              focus: {
                pane: "characters",
                anchor_type: "character",
                anchor_id: "hero",
              },
              important: true,
            },
            {
              entity_type: "character",
              action: "created",
              entity_id: "mage",
              label: "Nhân vật「mage」",
              focus: {
                pane: "characters",
                anchor_type: "character",
                anchor_id: "mage",
              },
              important: true,
            },
            {
              entity_type: "clue",
              action: "updated",
              entity_id: "mặt dây chuyền ngọc bích",
              label: "Manh mối「mặt dây chuyền ngọc bích",
              focus: {
                pane: "clues",
                anchor_type: "clue",
                anchor_id: "mặt dây chuyền ngọc bích",
              },
              important: true,
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalledWith("demo");
      expect(useAppStore.getState().toast?.text).toBe("Manh mối「"Mặt dây chuyền ngọc bích" đã được cập nhật");
    });

    expect(useAppStore.getState().getEntityRevision("character:hero")).toBe(1);
    expect(useAppStore.getState().getEntityRevision("character:mage")).toBe(1);
    expect(useAppStore.getState().getEntityRevision("clue:mặt dây chuyền ngọc bích")).toBe(1);
    expect(useAppStore.getState().getEntityRevision("segment:SEG-404")).toBe(0);
    expect(useAppStore.getState().workspaceNotifications).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          text: "AI Thêm 2 Nhân vật mới: hero, image, click để xem",
          target: expect.objectContaining({
            type: "character",
            id: "hero",
            route: "/characters",
          }),
        }),
        expect.objectContaining({
          text: "AI Mạnh mối "Mặt Dây Ngọc" vừa được cập nhật, click để xem",
          target: expect.objectContaining({
            type: "clue",
            id: "mặt dây chuyền ngọc bích",
            route: "/clues",
          }),
        }),
      ]),
    );
  });

  it("refreshes without changing focus for webui-originated batches", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/clues");

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-3",
          fingerprint: "fp-3",
          generated_at: "2026-03-01T00:00:00Z",
          source: "webui",
          changes: [
            {
              entity_type: "clue",
              action: "updated",
              entity_id: "mặt dây chuyền ngọc bích",
              label: "Manh mối「mặt dây chuyền ngọc bích",
              focus: {
                pane: "clues",
                anchor_type: "clue",
                anchor_id: "mặt dây chuyền ngọc bích",
              },
              important: true,
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    await waitFor(() => {
      expect(API.getProject).toHaveBeenCalledWith("demo");
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/clues");
    expect(useAppStore.getState().scrollTarget).toBeNull();
    expect(useAppStore.getState().workspaceNotifications).toHaveLength(0);
  });

  it("defers remote navigation when a workspace edit marker is present", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/characters");
    const editingMarker = document.createElement("div");
    editingMarker.setAttribute("data-workspace-editing", "true");
    document.body.appendChild(editingMarker);

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-4",
          fingerprint: "fp-4",
          generated_at: "2026-03-01T00:00:00Z",
          source: "filesystem",
          changes: [
            {
              entity_type: "clue",
              action: "updated",
              entity_id: "mặt dây chuyền ngọc bích",
              label: "Manh mối「mặt dây chuyền ngọc bích",
              focus: {
                pane: "clues",
                anchor_type: "clue",
                anchor_id: "mặt dây chuyền ngọc bích",
              },
              important: true,
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    await waitFor(() => {
      expect(useAppStore.getState().workspaceNotifications[0]?.target?.id).toBe("mặt dây chuyền ngọc bích");
    });
    expect(screen.getByTestId("location")).toHaveTextContent("/characters");
    expect(useAppStore.getState().scrollTarget).toBeNull();
  });

  it("extracts asset_fingerprints from SSE changes and updates store", async () => {
    let capturedOptions: ProjectEventStreamOptions | undefined;
    vi.spyOn(API, "openProjectEventStream").mockImplementation((options) => {
      capturedOptions = options;
      return { close: vi.fn() } as unknown as EventSource;
    });

    renderHarness("/");

    act(() => {
      capturedOptions?.onChanges?.(
        {
          project_name: "demo",
          batch_id: "batch-fp",
          fingerprint: "fp-fp",
          generated_at: "2026-03-01T00:00:00Z",
          source: "worker",
          changes: [
            {
              entity_type: "segment",
              action: "storyboard_ready",
              entity_id: "E1S01",
              label: "Phân cảnh「E1S01」",
              focus: null,
              important: true,
              asset_fingerprints: { "storyboards/scene_E1S01.png": 1710288000 },
            },
          ],
        },
        new MessageEvent("changes"),
      );
    });

    // fingerprints Nên ghi vào store ngay (đồng bộ) không cần chờ getProject
    expect(useProjectsStore.getState().getAssetFingerprint("storyboards/scene_E1S01.png")).toBe(1710288000);
  });
});
