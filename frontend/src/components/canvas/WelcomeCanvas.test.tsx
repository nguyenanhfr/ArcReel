import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { WelcomeCanvas } from "@/components/canvas/WelcomeCanvas";
import { API } from "@/api";
import { useAppStore } from "@/stores/app-store";

describe("WelcomeCanvas", () => {
  beforeEach(() => {
    useAppStore.setState(useAppStore.getInitialState(), true);
    vi.restoreAllMocks();
  });

  it("shows the project title instead of the internal project name", async () => {
    vi.spyOn(API, "listFiles").mockResolvedValue({ files: { source: [] } });

    render(
      <WelcomeCanvas
        projectName="halou-92d19a04"
        projectTitle="Xin chào Dự án"
      />,
    );

    expect(await screen.findByText("Chào mừng đến Xin chào Dựán!")).toBeInTheDocument();
    expect(screen.queryByText("Chào mừng đến halou-92d19a04！")).not.toBeInTheDocument();
  });
});
