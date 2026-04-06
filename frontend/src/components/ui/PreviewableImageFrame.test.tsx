import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PreviewableImageFrame } from "./PreviewableImageFrame";

describe("PreviewableImageFrame", () => {
  it("opens a fullscreen preview and closes from both the close button and backdrop", () => {
    render(
      <PreviewableImageFrame src="/demo.png" alt="Sơ đồ ví dụ">
        <img src="/demo.png" alt="Sơ đồ ví dụ" />
      </PreviewableImageFrame>,
    );

    const trigger = screen.getByRole("button", { name: "Hình ảnh mẫu xem trước toàn màn hình" });

    fireEvent.click(trigger);
    expect(
      screen.getByRole("dialog", { name: "Hình ảnh mẫu xem trước toàn màn hình" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "ĐóngXem trước toàn màn hình" }));
    expect(
      screen.queryByRole("dialog", { name: "Hình ảnh mẫu xem trước toàn màn hình" }),
    ).not.toBeInTheDocument();

    fireEvent.click(trigger);
    const dialog = screen.getByRole("dialog", { name: "Hình ảnh mẫu xem trước toàn màn hình" });
    const backdrop = dialog.parentElement?.parentElement;
    expect(backdrop).not.toBeNull();

    fireEvent.click(backdrop as HTMLElement);

    expect(
      screen.queryByRole("dialog", { name: "Hình ảnh mẫu xem trước toàn màn hình" }),
    ).not.toBeInTheDocument();
  }, 10_000);
});
