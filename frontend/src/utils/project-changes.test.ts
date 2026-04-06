import { describe, expect, it } from "vitest";
import type { ProjectChange } from "@/types";
import {
  formatGroupedDeferredText,
  formatGroupedNotificationText,
  groupChangesByType,
} from "./project-changes";

function makeChange(overrides: Partial<ProjectChange> = {}): ProjectChange {
  return {
    entity_type: "character",
    action: "created",
    entity_id: "Trương Tam",
    label: "Nhân vật「Trương Tam",
    important: true,
    focus: null,
    ...overrides,
  };
}

describe("project-changes utils", () => {
  it("groups changes by entity_type and action", () => {
    const groups = groupChangesByType([
      makeChange({ entity_id: "Trương Tam", label: "Nhân vật「Trương Tam" }),
      makeChange({ entity_id: "John Doe", label: "Nhân vật「John Doe" }),
      makeChange({
        entity_type: "clue",
        entity_id: "mặt dây chuyền ngọc bích",
        label: "Manh mối「mặt dây chuyền ngọc bích",
      }),
      makeChange({
        entity_type: "character",
        action: "updated",
        entity_id: "Vương Vũ",
        label: "Nhân vật「Vương Vũ",
      }),
    ]);

    expect(groups).toHaveLength(3);
    expect(groups[0]).toMatchObject({
      key: "character:created",
      changes: [expect.objectContaining({ entity_id: "Trương Tam" }), expect.objectContaining({ entity_id: "John Doe" })],
    });
    expect(groups[1].key).toBe("clue:created");
    expect(groups[2].key).toBe("character:updated");
  });

  it("formats grouped notification text and truncates long lists", () => {
    const [singleGroup] = groupChangesByType([
      makeChange({ entity_id: "Trương Tam", label: "Nhân vật「Trương Tam" }),
    ]);
    expect(formatGroupedNotificationText(singleGroup)).toBe("Nhân vật「Zhang San"đã được tạo");

    const [grouped] = groupChangesByType([
      makeChange({ entity_id: "Trương Tam", label: "Nhân vật「Trương Tam" }),
      makeChange({ entity_id: "John Doe", label: "Nhân vật「John Doe" }),
      makeChange({ entity_id: "Vương Vũ", label: "Nhân vật「Vương Vũ" }),
      makeChange({ entity_id: "Triệu Lưu", label: "Nhân vật「Triệu Lưu" }),
      makeChange({ entity_id: "Tiền Kỳ", label: "Nhân vật「Tiền Kỳ" }),
      makeChange({ entity_id: "tắm nắng", label: "Nhân vật「"Sunba"" }),
    ]);

    expect(formatGroupedNotificationText(grouped)).toBe(
      "Thêm 6 Nhân vật mới: Zhang San, Li Si, Wang Wu, Zhao Liu, Qian Qi...",
    );
    expect(formatGroupedDeferredText(grouped)).toBe(
      "AI 6 Nhân vật mới vừa được thêm vào: Zhang San, Li Si, Wang Wu, Zhao Liu, Qian Qi...vv., bấm vào để xem",
    );
  });
});
