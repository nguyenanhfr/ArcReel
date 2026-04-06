import { useCallback, useEffect, useRef } from "react";
import { API } from "@/api";
import { uid } from "@/utils/id";
import { useAssistantStore } from "@/stores/assistant-store";
import type {
  AssistantSnapshot,
  PendingQuestion,
  SessionMeta,
  SessionStatus,
  Turn,
} from "@/types";

export interface AttachedImage {
  id: string;
  dataUrl: string;
  mimeType: string;
}

// ---------------------------------------------------------------------------
// Helpers — Được chuyển từ use-assistant-state.js cũ
// ---------------------------------------------------------------------------

function parseSsePayload(event: MessageEvent): Record<string, unknown> {
  try {
    return JSON.parse(event.data || "{}");
  } catch {
    return {};
  }
}

function applyTurnPatch(prev: Turn[], patch: Record<string, unknown>): Turn[] {
  const op = patch.op as string;
  if (op === "reset") return (patch.turns as Turn[]) ?? [];
  if (op === "append" && patch.turn) {
    const newTurn = patch.turn as Turn;
    // Lượt lạc quan ở cuối Xóa tránh trùng lặp khi backend nối thêm lượt người dùng thực
    if (
      newTurn.type === "user" &&
      prev.length > 0 &&
      prev.at(-1)?.uuid?.startsWith(OPTIMISTIC_PREFIX)
    ) {
      return [...prev.slice(0, -1), newTurn];
    }
    return [...prev, newTurn];
  }
  if (op === "replace_last" && patch.turn) {
    return prev.length === 0
      ? [patch.turn as Turn]
      : [...prev.slice(0, -1), patch.turn as Turn];
  }
  return prev;
}

const TERMINAL = new Set(["completed", "error", "interrupted"]);
const OPTIMISTIC_PREFIX = "optimistic-";

function extractTurnText(turn: Turn): string {
  return (
    turn.content
      ?.filter((b) => b.type === "text")
      .map((b) => b.text ?? "")
      .join("") ?? ""
  );
}

function parseTurnTimestamp(turn: Turn | null): number | null {
  if (!turn?.timestamp) return null;
  const parsed = Date.parse(turn.timestamp);
  return Number.isNaN(parsed) ? null : parsed;
}

function findLatestUserTurn(turns: Turn[]): Turn | null {
  for (let i = turns.length - 1; i >= 0; i--) {
    if (turns[i].type === "user") return turns[i];
  }
  return null;
}

// ---------------------------------------------------------------------------
// localStorage helpers — Ghi nhớ phiên cuối cùng được sử dụng bởi mỗi Dựán
// ---------------------------------------------------------------------------

const LAST_SESSION_KEY = "arcreel:lastSessionByProject";

function getLastSessionId(projectName: string): string | null {
  try {
    const map = JSON.parse(localStorage.getItem(LAST_SESSION_KEY) || "{}");
    return map[projectName] ?? null;
  } catch {
    return null;
  }
}

function saveLastSessionId(projectName: string, sessionId: string): void {
  try {
    const map = JSON.parse(localStorage.getItem(LAST_SESSION_KEY) || "{}");
    map[projectName] = sessionId;
    localStorage.setItem(LAST_SESSION_KEY, JSON.stringify(map));
  } catch {
    // Im lặng thất bại
  }
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Quản lý vòng đời phiên AI Trợ lý:
 * - Đang tải/Tạo phiên
 * - Gửi tin nhắn
 * - SSE Truyền phát tiếp nhận
 * - Ngắt phiên
 */
export function useAssistantSession(projectName: string | null) {
  const store = useAssistantStore;
  const streamRef = useRef<EventSource | null>(null);
  const streamSessionRef = useRef<string | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const statusRef = useRef<string>("idle");
  const pendingSendVersionRef = useRef(0);

  const syncPendingQuestion = useCallback((question: PendingQuestion | null) => {
    store.getState().setPendingQuestion(question);
    store.getState().setAnsweringQuestion(false);
  }, [store]);

  const clearPendingQuestion = useCallback(() => {
    syncPendingQuestion(null);
  }, [syncPendingQuestion]);

  const invalidatePendingSend = useCallback(() => {
    pendingSendVersionRef.current += 1;
    store.getState().setSending(false);
  }, [store]);

  const restoreFailedSend = useCallback((
    sessionId: string,
    optimisticUuid: string,
    previousStatus: SessionStatus | null,
  ) => {
    if (store.getState().currentSessionId !== sessionId) return;

    store.getState().setTurns(
      store.getState().turns.filter((turn) => turn.uuid !== optimisticUuid),
    );
    statusRef.current = previousStatus ?? "idle";
    store.getState().setSessionStatus(previousStatus ?? "idle");
    store.getState().setSending(false);
  }, [store]);

  const applySnapshot = useCallback((snapshot: Partial<AssistantSnapshot>) => {
    const snapshotTurns = (snapshot.turns as Turn[]) ?? [];
    const currentTurns = store.getState().turns;

    // Giữ nguyên lượt lạc quan ở cuối: chỉ khi ảnh chụp nhanh chưa chứa người dùng Hiện tại vòng.
    // Sử dụng đối sánh nội dung thay vì UUID (UUID lạc quan sẽ không bao giờ khớp với UUID thực phụ trợ).
    const lastTurn = currentTurns.at(-1);
    let shouldPreserveOptimistic = false;

    if (lastTurn?.uuid?.startsWith(OPTIMISTIC_PREFIX)) {
      const optText = extractTurnText(lastTurn);

      if (optText) {
        const latestUserTurn = findLatestUserTurn(snapshotTurns);
        if (!latestUserTurn || extractTurnText(latestUserTurn) !== optText) {
          shouldPreserveOptimistic = true;
        } else {
          const latestUserTs = parseTurnTimestamp(latestUserTurn);
          const optimisticTs = parseTurnTimestamp(lastTurn);
          shouldPreserveOptimistic = Boolean(
            latestUserTs !== null &&
            optimisticTs !== null &&
            latestUserTs < optimisticTs,
          );
        }
      }
    }

    if (shouldPreserveOptimistic && lastTurn) {
      store.getState().setTurns([...snapshotTurns, lastTurn]);
    } else {
      store.getState().setTurns(snapshotTurns);
    }

    store.getState().setDraftTurn((snapshot.draft_turn as Turn) ?? null);
    syncPendingQuestion(getPendingQuestionFromSnapshot(snapshot));
  }, [store, syncPendingQuestion]);

  // Đóng流
  const closeStream = useCallback(() => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current);
      reconnectRef.current = null;
    }
    if (streamRef.current) {
      streamRef.current.close();
      streamRef.current = null;
    }
    streamSessionRef.current = null;
  }, []);

  // Kết nối luồng SSE
  const connectStream = useCallback(
    (sessionId: string) => {
      // Nếu đã kết nối với cùng một phiên và kết nối tốt, hãy bỏ qua việc kết nối lại
      if (
        streamRef.current &&
        streamSessionRef.current === sessionId &&
        streamRef.current.readyState !== EventSource.CLOSED
      ) {
        return;
      }

      closeStream();
      streamSessionRef.current = sessionId;

      const url = API.getAssistantStreamUrl(projectName!, sessionId);
      const source = new EventSource(url);
      streamRef.current = source;
      const isActiveStream = () =>
        streamRef.current === source &&
        streamSessionRef.current === sessionId &&
        store.getState().currentSessionId === sessionId;

      source.addEventListener("snapshot", (event) => {
        if (!isActiveStream()) return;
        const data = parseSsePayload(event as MessageEvent);
        const isSending = store.getState().sending;

        // Khi Gửi tin nhắn, backend có thể chưa cắt phiên thành "running"，
        // Tại thời điểm này SSE kết nối với cái cũ "completed" session Nó sẽ bị ngắt kết nối ngay sau khi nhận được ảnh chụp + trạng thái cũ.
        // Bỏ qua các lượt và trạng thái của ảnh chụp nhanh cũ này và giữ lại trạng thái lạc quan của giao diện người dùng.
        if (isSending && typeof data.status === "string" && data.status !== "running") {
          return;
        }

        applySnapshot(data as Partial<AssistantSnapshot>);

        if (typeof data.status === "string") {
          store.getState().setSessionStatus(data.status as "idle");
          statusRef.current = data.status as string;
          // Xóa gửi bất kỳ trạng thái hợp lệ nào nhận được (những trạng thái cũ đã được lọc ở trên).
          // Đặc biệt "running" Cho biết backend đã xác nhận đã nhận Tin nhắn và phải Xóa việc gửi,
          // Nếu không thì tiếp theo "completed" Sẽ được bộ phận bảo vệ isSending của bộ xử lý trạng thái lọc ra.
          store.getState().setSending(false);
        }
      });

      source.addEventListener("patch", (event) => {
        if (!isActiveStream()) return;
        const payload = parseSsePayload(event as MessageEvent);
        const patch = (payload.patch ?? payload) as Record<string, unknown>;
        store.getState().setTurns(applyTurnPatch(store.getState().turns, patch));
        if ("draft_turn" in payload) {
          store.getState().setDraftTurn((payload.draft_turn as Turn) ?? null);
        }
      });

      source.addEventListener("delta", (event) => {
        if (!isActiveStream()) return;
        const payload = parseSsePayload(event as MessageEvent);
        if ("draft_turn" in payload) {
          store.getState().setDraftTurn((payload.draft_turn as Turn) ?? null);
        }
      });

      source.addEventListener("status", (event) => {
        if (!isActiveStream()) return;
        const data = parseSsePayload(event as MessageEvent);
        const status = (data.status as string) ?? statusRef.current;
        const isSending = store.getState().sending;

        // Trong khi gửi tin nhắn, trạng thái kết thúc của phiên cũ sẽ bị bỏ qua.
        // Phần phụ trợ sẽ gửi trạng thái: tới SSE của phiên không chạy:"completed" Sau khi Đóng kết nối,
        // Trạng thái cũ này không được phép kích hoạt closeStream / setSending(false).
        // onerror Cuộc gọi lại sẽ tự động kết nối lại với "running" phiên họp.
        if (isSending && TERMINAL.has(status) && status !== "error") {
          return;
        }

        statusRef.current = status;
        store.getState().setSessionStatus(status as "idle");

        if (TERMINAL.has(status)) {
          store.getState().setSending(false);
          store.getState().setInterrupting(false);
          clearPendingQuestion();
          if (status !== "interrupted") {
            store.getState().setDraftTurn(null);
          }
          closeStream();

          // Turn Sau khi hoàn tất, hãy làm mới danh sách Phiên mới để lấy tiêu đề tóm tắt SDK
          if (projectName) {
            API.listAssistantSessions(projectName).then((res) => {
              const fresh = res.sessions ?? [];
              if (fresh.length > 0) store.getState().setSessions(fresh);
            }).catch(() => {/* Silence Thất bại */});
          }
        }
      });

      source.addEventListener("question", (event) => {
        if (!isActiveStream()) return;
        const payload = parseSsePayload(event as MessageEvent);
        const pendingQuestion = getPendingQuestionFromEvent(payload);
        if (pendingQuestion) {
          syncPendingQuestion(pendingQuestion);
        }
      });

      source.onerror = () => {
        if (!isActiveStream()) return;
        // Điều kiện kết nối lại: Phiên đang chạy hoặc giao diện người dùng là Gửi tin nhắn.
        // Cái sau xử lý việc xử lý phụ trợ cũ "completed" session Tình huống trước mắt của SSE:
        // Sau khi kết nối bị ngắt kết nối, nó cần được kết nối lại. Tại thời điểm này, phần phụ trợ đã đặt phiên thành "running"。
        if (statusRef.current === "running" || store.getState().sending) {
          reconnectRef.current = setTimeout(() => {
            connectStream(sessionId);
          }, 3000);
        }
      };
    },
    [applySnapshot, clearPendingQuestion, projectName, closeStream, store, syncPendingQuestion],
  );

  // Tải phiên
  useEffect(() => {
    if (!projectName) return;
    let cancelled = false;

    async function init() {
      store.getState().setMessagesLoading(true);
      try {
        // Nhận danh sách phiên
        const res = await API.listAssistantSessions(projectName!);
        const sessions = res.sessions ?? [];
        store.getState().setSessions(sessions);

        // Ưu tiên phiên được chọn cuối cùng nếu nó vẫn tồn tại trong danh sách
        const lastId = getLastSessionId(projectName!);
        const sessionId = (lastId && sessions.some((s: SessionMeta) => s.id === lastId))
          ? lastId
          : sessions[0]?.id;
        if (!sessionId) {
          store.getState().setCurrentSessionId(null);
          clearPendingQuestion();
          store.getState().setMessagesLoading(false);
          return;
        }
        if (cancelled) return;

        store.getState().setCurrentSessionId(sessionId);

        // Tải ảnh chụp nhanh phiên
        const session = await API.getAssistantSession(projectName!, sessionId);
        const raw = session as Record<string, unknown>;
        const sessionObj = (raw.session ?? raw) as Record<string, unknown>;
        const status = (sessionObj.status as string) ?? "idle";
        statusRef.current = status;
        store.getState().setSessionStatus(status as "idle");

        if (status === "running") {
          connectStream(sessionId);
        } else {
          const snapshot = await API.getAssistantSnapshot(projectName!, sessionId);
          if (cancelled) return;
          applySnapshot(snapshot);
        }
      } catch {
        // Im lặng thất bại
      } finally {
        if (!cancelled) store.getState().setMessagesLoading(false);
      }
    }

    // Tải danh sách kỹ năng
    API.listAssistantSkills(projectName)
      .then((res) => {
        if (!cancelled) store.getState().setSkills(res.skills ?? []);
      })
      .catch(() => {});

    init();

    return () => {
      cancelled = true;
      invalidatePendingSend();
      closeStream();
    };
  }, [
    projectName,
    applySnapshot,
    clearPendingQuestion,
    connectStream,
    closeStream,
    invalidatePendingSend,
    store,
  ]);

  // Gửi tin nhắn
  const sendMessage = useCallback(
    async (content: string, images?: AttachedImage[]) => {
      if ((!content.trim() && (!images || images.length === 0)) || store.getState().sending) return;

      const sendVersion = pendingSendVersionRef.current + 1;
      pendingSendVersionRef.current = sendVersion;
      const previousStatus = store.getState().sessionStatus;
      let sessionId = store.getState().currentSessionId;
      let optimisticUuid = "";
      store.getState().setSending(true);
      store.getState().setError(null);

      try {
        // Trích xuất dữ liệu base64
        const imagePayload = images?.map((img) => ({
          data: img.dataUrl.split(",")[1] ?? "",
          media_type: img.mimeType,
        }));

        // Cập nhật lạc quan: Hiện tin nhắn trên giao diện người dùng ngay bây giờ
        const optimisticContent: import("@/types").ContentBlock[] = [
          ...(imagePayload ?? []).map((img) => ({
            type: "image" as const,
            source: {
              type: "base64" as const,
              media_type: img.media_type,
              data: img.data,
            },
          })),
          ...(content.trim() ? [{ type: "text" as const, text: content.trim() }] : []),
        ];
        const optimisticTurn: Turn = {
          type: "user",
          content: optimisticContent,
          uuid: `${OPTIMISTIC_PREFIX}${uid()}`,
          timestamp: new Date().toISOString(),
        };
        optimisticUuid = optimisticTurn.uuid ?? "";
        store.getState().setTurns([...store.getState().turns, optimisticTurn]);
        statusRef.current = "running";
        store.getState().setSessionStatus("running");

        // Gửi thống nhất (phiên mới hoặc phiên hiện có)
        const result = await API.sendAssistantMessage(
          projectName!,
          content,
          sessionId,  // null for new session
          imagePayload,
        );

        if (pendingSendVersionRef.current !== sendVersion) return;

        const returnedSessionId = result.session_id;

        // Phiên mới：cập nhật cửa hàng
        if (!sessionId) {
          const newSession: SessionMeta = {
            id: returnedSessionId,
            project_name: projectName!,
            title: content.trim().slice(0, 30) || "ẢnhTin nhắn",
            status: "running",
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
          };
          store.getState().setCurrentSessionId(returnedSessionId);
          store.getState().setSessions([newSession, ...store.getState().sessions]);
          store.getState().setIsDraftSession(false);
          saveLastSessionId(projectName!, returnedSessionId);
          sessionId = returnedSessionId;
        }

        if (store.getState().currentSessionId !== sessionId) return;
        connectStream(sessionId);
      } catch (err) {
        if (pendingSendVersionRef.current !== sendVersion) return;
        store.getState().setError((err as Error).message ?? "Gửi thất bại");
        if (sessionId && optimisticUuid) {
          restoreFailedSend(sessionId, optimisticUuid, previousStatus);
        } else {
          // Phiên mớiTạo thất bại：Quay lại chế độ nháp
          store.getState().setTurns(store.getState().turns.filter(t => t.uuid !== optimisticUuid));
          store.getState().setIsDraftSession(true);
          store.getState().setCurrentSessionId(null);
          statusRef.current = previousStatus ?? "idle";
          store.getState().setSessionStatus(previousStatus ?? "idle");
          store.getState().setSending(false);
        }
      }
    },
    [projectName, connectStream, restoreFailedSend, store],
  );

  const answerQuestion = useCallback(
    async (questionId: string, answers: Record<string, string>) => {
      const sessionId = store.getState().currentSessionId;
      if (!projectName || !sessionId) return;

      store.getState().setError(null);
      store.getState().setAnsweringQuestion(true);

      try {
        await API.answerAssistantQuestion(projectName, sessionId, questionId, answers);
        store.getState().setPendingQuestion(null);
      } catch (err) {
        store.getState().setError((err as Error).message ?? "Trả lời Thất bại");
      } finally {
        store.getState().setAnsweringQuestion(false);
      }
    },
    [projectName, store],
  );

  // Ngắt phiên
  const interrupt = useCallback(async () => {
    const sessionId = store.getState().currentSessionId;
    if (!projectName || !sessionId || statusRef.current !== "running") return;

    store.getState().setInterrupting(true);
    try {
      await API.interruptAssistantSession(projectName, sessionId);
    } catch (err) {
      store.getState().setError((err as Error).message ?? "Thất bại ngắt");
      store.getState().setInterrupting(false);
    }
  }, [projectName, store]);

  // TạoPhiên mới（Lazy Tạo: Chỉ xóa trạng thái, Thực tế Tạo bị trì hoãn cho đến khi Tin nhắn đầu tiên được phát ra)
  const createNewSession = useCallback(async () => {
    if (!projectName) return;

    invalidatePendingSend();
    closeStream();
    store.getState().setTurns([]);
    store.getState().setDraftTurn(null);
    store.getState().setSessionStatus("idle");
    clearPendingQuestion();
    store.getState().setCurrentSessionId(null);
    store.getState().setIsDraftSession(true);
    statusRef.current = "idle";
  }, [projectName, clearPendingQuestion, closeStream, invalidatePendingSend, store]);

  // Chuyển sang phiên được chỉ định
  const switchSession = useCallback(async (sessionId: string) => {
    if (store.getState().currentSessionId === sessionId) return;

    invalidatePendingSend();
    closeStream();
    store.getState().setCurrentSessionId(sessionId);
    store.getState().setIsDraftSession(false);
    store.getState().setTurns([]);
    store.getState().setDraftTurn(null);
    clearPendingQuestion();
    store.getState().setMessagesLoading(true);

    // Nhớ chọn nhé
    if (projectName) saveLastSessionId(projectName, sessionId);

    try {
      const res = await API.getAssistantSession(projectName!, sessionId);
      const raw = res as Record<string, unknown>;
      const sessionObj = (raw.session ?? raw) as Record<string, unknown>;
      const status = (sessionObj.status as string) ?? "idle";
      statusRef.current = status;
      store.getState().setSessionStatus(status as "idle");

      if (status === "running") {
        connectStream(sessionId);
      } else {
        const snapshot = await API.getAssistantSnapshot(projectName!, sessionId);
        applySnapshot(snapshot);
      }
    } catch {
      // Im lặng thất bại
    } finally {
      store.getState().setMessagesLoading(false);
    }
  }, [projectName, applySnapshot, clearPendingQuestion, closeStream, connectStream, invalidatePendingSend, store]);

  // Xóa phiên
  const deleteSession = useCallback(async (sessionId: string) => {
    if (!projectName) return;
    try {
      await API.deleteAssistantSession(projectName, sessionId);
      const sessions = store.getState().sessions.filter((s) => s.id !== sessionId);
      store.getState().setSessions(sessions);

      // Nếu Xóa là phiên Hiện tại, hãy chuyển sang phiên tiếp theo
      if (store.getState().currentSessionId === sessionId) {
        if (sessions.length > 0) {
          await switchSession(sessions[0].id);
        } else {
          invalidatePendingSend();
          closeStream();
          store.getState().setCurrentSessionId(null);
          store.getState().setTurns([]);
          store.getState().setDraftTurn(null);
          store.getState().setSessionStatus(null);
          clearPendingQuestion();
          statusRef.current = "idle";
        }
      }
    } catch {
      // Im lặng thất bại
    }
  }, [projectName, clearPendingQuestion, closeStream, invalidatePendingSend, switchSession, store]);

  return { sendMessage, answerQuestion, interrupt, createNewSession, switchSession, deleteSession };
}

function getPendingQuestionFromSnapshot(
  snapshot: Partial<AssistantSnapshot> | Record<string, unknown>,
): PendingQuestion | null {
  const questions = snapshot.pending_questions as Array<Record<string, unknown>> | undefined;
  const pending = questions?.find(
    (question) =>
      typeof question?.question_id === "string" &&
      Array.isArray(question.questions) &&
      question.questions.length > 0,
  );

  if (!pending) {
    return null;
  }

  return {
    question_id: pending.question_id as string,
    questions: pending.questions as PendingQuestion["questions"],
  };
}

function getPendingQuestionFromEvent(payload: Record<string, unknown>): PendingQuestion | null {
  if (!(typeof payload.question_id === "string" && Array.isArray(payload.questions))) {
    return null;
  }

  return {
    question_id: payload.question_id,
    questions: payload.questions as PendingQuestion["questions"],
  };
}
