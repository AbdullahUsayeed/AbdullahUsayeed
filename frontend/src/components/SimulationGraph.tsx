// ---------------------------------------------------------------------------
// System Link — SimulationGraph
// Renders the time-domain simulation result using Recharts.
// Ghost traces (previous run) are shown as light gray lines.
// ---------------------------------------------------------------------------

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { SimulationResult } from "../types";

const COLORS = ["#6366f1", "#22d3ee", "#f59e0b", "#10b981", "#f43f5e"];
const GHOST_COLOR = "rgba(148, 163, 184, 0.3)";

interface Props {
  result: SimulationResult | null;
  ghostResult: SimulationResult | null;
  /** When true, shows a "Computing…" badge so the user knows a new run is in flight. */
  isLoading?: boolean;
}

function buildChartData(result: SimulationResult): Record<string, number>[] {
  return result.time.map((t, idx) => {
    const row: Record<string, number> = { t };
    for (const [key, vals] of Object.entries(result.signals)) {
      row[key] = vals[idx] ?? 0;
    }
    return row;
  });
}

export function SimulationGraph({ result, ghostResult, isLoading = false }: Props) {
  if (!result || result.status !== "success") {
    return (
      <div
        style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#64748b",
          fontSize: 14,
        }}
      >
        {result?.status === "error"
          ? null /* error shown by ErrorBanner */
          : isLoading
          ? "Running simulation…"
          : "Generate a simulation to see results here."}
      </div>
    );
  }

  const data = buildChartData(result);
  const ghostData = ghostResult?.status === "success"
    ? buildChartData(ghostResult)
    : null;

  const signalKeys = Object.keys(result.signals);

  return (
    <div style={{ flex: 1, padding: "16px 16px 0", position: "relative" }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 8,
        }}
      >
        <span style={{ color: "#94a3b8", fontSize: 12 }}>
          Simulation Output
        </span>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          {/* Progressive loading badge — visible while next result is computing */}
          {isLoading && (
            <span
              style={{
                fontSize: 11,
                color: "#818cf8",
                background: "rgba(99, 102, 241, 0.12)",
                border: "1px solid rgba(99, 102, 241, 0.35)",
                borderRadius: 4,
                padding: "2px 8px",
              }}
            >
              ⟳ Computing…
            </span>
          )}
          {result.execution_time_ms != null && (
            <span style={{ color: "#475569", fontSize: 11 }}>
              Executed in {result.execution_time_ms.toFixed(0)} ms
            </span>
          )}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <LineChart>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e2130" />
          <XAxis
            dataKey="t"
            type="number"
            domain={["auto", "auto"]}
            label={{ value: "Time (s)", position: "insideBottom", offset: -4, fill: "#64748b", fontSize: 11 }}
            tick={{ fill: "#64748b", fontSize: 11 }}
          />
          <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
          <Tooltip
            contentStyle={{ background: "#1e2130", border: "1px solid #2d3148", borderRadius: 6 }}
            labelStyle={{ color: "#94a3b8" }}
            itemStyle={{ color: "#e2e8f0" }}
            formatter={(v: number) => v.toFixed(4)}
            labelFormatter={(l: number) => `t = ${l.toFixed(3)} s`}
          />
          <Legend wrapperStyle={{ color: "#94a3b8", fontSize: 12 }} />

          {/* Ghost traces from previous run */}
          {ghostData &&
            signalKeys.map((key) => (
              <Line
                key={`ghost_${key}`}
                data={ghostData}
                dataKey={key}
                dot={false}
                stroke={GHOST_COLOR}
                strokeWidth={1.5}
                strokeDasharray="4 2"
                name={`${key} (prev)`}
                isAnimationActive={false}
              />
            ))}

          {/* Current result */}
          {signalKeys.map((key, idx) => (
            <Line
              key={key}
              data={data}
              dataKey={key}
              dot={false}
              stroke={COLORS[idx % COLORS.length]}
              strokeWidth={2}
              name={key}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
