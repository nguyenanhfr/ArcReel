import { useState, useEffect, useCallback, useMemo } from "react";
import { API } from "@/api";
import type { UsageStat } from "@/types";

const currencyFmt = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const percentFmt = new Intl.NumberFormat("zh-CN", { style: "percent", maximumFractionDigits: 0 });

const TIME_RANGES = [
  { label: "7 ngày qua", days: 7 },
  { label: "30 ngày qua", days: 30 },
  { label: "全部", days: 0 },
];

export function UsageStatsSection() {
  const [stats, setStats] = useState<UsageStat[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(7);
  const [providerFilter, setProviderFilter] = useState<string>("");

  const fetchStats = useCallback(async () => {
    setLoading(true);
    const params: { provider?: string; start?: string; end?: string } = {};
    if (providerFilter) params.provider = providerFilter;
    if (timeRange > 0) {
      const start = new Date();
      start.setDate(start.getDate() - timeRange);
      params.start = start.toISOString().split("T")[0];
      params.end = new Date().toISOString().split("T")[0];
    }
    try {
      const res = await API.getUsageStatsGrouped(params);
      setStats(res.stats || []);
    } catch {
      setStats([]);
    }
    setLoading(false);
  }, [timeRange, providerFilter]);

  useEffect(() => {
    void fetchStats();
  }, [fetchStats]);

  // Derive unique providers for filter dropdown
  const providers = useMemo(
    () => Array.from(new Set(stats.map((s) => s.provider))).sort(),
    [stats],
  );

  return (
    <div className="space-y-6 p-6">
      <div>
        <h3 className="text-lg font-semibold text-gray-100">用量统计</h3>
        <p className="mt-1 text-sm text-gray-500">Xem thống kê cuộc gọi API cho từng nhà cung cấp</p>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-3">
        {TIME_RANGES.map((r) => (
          <button
            key={r.days}
            type="button"
            onClick={() => setTimeRange(r.days)}
            className={`rounded-lg px-3 py-1.5 text-sm focus-visible:ring-2 focus-visible:ring-indigo-500/60 focus-visible:outline-none ${
              timeRange === r.days
                ? "bg-indigo-600 text-white"
                : "border border-gray-700 text-gray-400 hover:text-gray-200"
            }`}
          >
            {r.label}
          </button>
        ))}
        {providers.length > 0 && (
          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            aria-label="Lọc theo nhà cung cấp"
            className="rounded-lg border border-gray-700 bg-gray-900 px-3 py-1.5 text-sm text-gray-300 focus:border-indigo-500/60 focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500/60"
          >
            <option value="">Tất cả nhà cung cấp</option>
            {providers.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        )}
      </div>

      {/* Stats */}
      {loading ? (
        <div className="text-sm text-gray-500">Đang tải...</div>
      ) : stats.length === 0 ? (
        <div className="text-sm text-gray-500">Chưa có dữ liệu</div>
      ) : (
        <div className="space-y-3">
          {stats.map((s) => (
            <div key={`${s.provider}-${s.call_type}`} className="rounded-xl border border-gray-800 bg-gray-950/40 p-4">
              <div className="flex items-center justify-between">
                <div>
                  <span className="text-sm font-medium text-gray-100">{s.display_name ?? s.provider}</span>
                  <span className="ml-2 text-xs text-gray-500">{s.call_type}</span>
                </div>
                <span className="text-sm text-gray-300">
                  {currencyFmt.format(s.total_cost_usd)}
                </span>
              </div>
              <div className="mt-2 flex flex-wrap gap-6 text-xs tabular-nums text-gray-400">
                <span>Gọi: {s.total_calls}</span>
                <span>Thành công: {s.success_calls}</span>
                <span>
                  Tỷ lệ thành công:{" "}
                  {s.total_calls > 0
                    ? percentFmt.format(s.success_calls / s.total_calls)
                    : "0%"}
                </span>
                {s.call_type === "text" ? (
                  s.total_calls > 0 && <span>Loại: Văn bản生成</span>
                ) : s.total_duration_seconds !== undefined && (
                  <span>Thời lượng: {s.total_duration_seconds}s</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
