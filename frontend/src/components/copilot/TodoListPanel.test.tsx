import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Turn, TodoItem } from "@/types";
import { TodoListPanel, extractLatestTodos } from "./TodoListPanel";

function makeTodo(
  content: string,
  status: TodoItem["status"] = "pending",
): TodoItem {
  return {
    content,
    activeForm: `Đang xử lý${content}`,
    status,
  };
}

function makeTodoTurn(
  todos: TodoItem[],
  overrides: Partial<Turn["content"][number]> = {},
): Turn {
  return {
    type: "assistant",
    content: [
      {
        type: "tool_use",
        id: "todo-1",
        name: "TodoWrite",
        input: { todos },
        ...overrides,
      },
    ],
  };
}

describe("TodoListPanel", () => {
  it("ignores failed TodoWrite updates when deriving the latest visible todos", () => {
    const previousTodos = [makeTodo("Giữ nhiệm vụ cũ", "in_progress")];
    const failedTodos = [makeTodo("Thất bạinhiệm vụ mới")];
    const turns = [
      makeTodoTurn(previousTodos),
      makeTodoTurn(failedTodos, { is_error: true, result: "write failed" }),
    ];

    expect(extractLatestTodos(turns, null)).toEqual(previousTodos);

    render(<TodoListPanel turns={turns} draftTurn={null} />);

    expect(screen.getByText("Giữ nhiệm vụ cũ")).toBeInTheDocument();
    expect(screen.queryByText("Thất bạinhiệm vụ mới")).not.toBeInTheDocument();
  });

  it("treats an empty TodoWrite payload as the latest state and hides the panel", () => {
    const turns = [
      makeTodoTurn([makeTodo("nhiệm vụ cũ")]),
      makeTodoTurn([]),
    ];

    expect(extractLatestTodos(turns, null)).toEqual([]);

    const { container } = render(<TodoListPanel turns={turns} draftTurn={null} />);

    expect(screen.queryByText("nhiệm vụ cũ")).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });
});
