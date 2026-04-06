import GeminiColor from "@lobehub/icons/es/Gemini/components/Color";
import GrokMono from "@lobehub/icons/es/Grok/components/Mono";
import OpenAIMono from "@lobehub/icons/es/OpenAI/components/Mono";
import VertexAIColor from "@lobehub/icons/es/VertexAI/components/Color";
import VolcengineColor from "@lobehub/icons/es/Volcengine/components/Color";

export const PROVIDER_NAMES: Record<string, string> = {
  "gemini-aistudio": "AI Studio",
  "gemini-vertex": "Vertex AI",
  ark: "Hòm núi lửa",
  grok: "Grok",
  openai: "OpenAI",
};

/**
 * Hiển thị biểu tượng nhà cung cấp tương ứng dựa trên Id nhà cung cấp.
 * Hỗ trợ gemini-aistudio, gemini-vertex, grok, ark và phần còn lại hiển thị chữ cái đầu tiên.
 */
export function ProviderIcon({ providerId, className }: { providerId: string; className?: string }) {
  const cls = className ?? "h-6 w-6";
  if (providerId === "gemini-vertex") return <VertexAIColor className={cls} />;
  if (providerId.startsWith("gemini")) return <GeminiColor className={cls} />;
  if (providerId.startsWith("grok")) return <GrokMono className={cls} />;
  if (providerId === "ark") return <VolcengineColor className={cls} />;
  if (providerId === "openai") return <OpenAIMono className={cls} />;
  // Fallback: first letter badge
  return (
    <span className={`inline-flex items-center justify-center rounded bg-gray-700 text-xs font-bold uppercase text-gray-300 ${cls}`}>
      {providerId[0]}
    </span>
  );
}
