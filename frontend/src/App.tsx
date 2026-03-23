// ---------------------------------------------------------------------------
// System Link — App (Root Component)
// ---------------------------------------------------------------------------

import { useEffect, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { Settings, Crown } from "lucide-react";
import { ErrorBanner } from "./components/ErrorBanner";
import { NodeCanvas } from "./components/NodeCanvas";
import { ParameterSidebar } from "./components/ParameterSidebar";
import { PromptBar } from "./components/PromptBar";
import { SettingsPanel } from "./components/SettingsPanel";
import { SimulationGraph } from "./components/SimulationGraph";
import { useSimulation } from "./hooks/useSimulation";
import { useFluxStore } from "./store";
import { getBlockRegistry, diagnoseSimulation, validateLicenseKey } from "./api/client";
import type { DiagnoseResponse } from "./api/client";

export default function App() {
  const store = useFluxStore();
  const { generate, refine, updateParam } = useSimulation();

  // ── UI state ──────────────────────────────────────────────────────────────
  const [diagnosis, setDiagnosis] = useState<DiagnoseResponse | null>(null);
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [showSettings, setShowSettings] = useState(false);

  const isPro = store.license.tier === "pro";

  // Load Block Registry once on startup
  useEffect(() => {
    getBlockRegistry()
      .then(store.setBlockRegistry)
      .catch(console.error);
  }, [store.setBlockRegistry]);

  // Re-validate saved license key on startup (silently)
  useEffect(() => {
    const savedKey = store.license.key;
    if (!savedKey) return;

    validateLicenseKey(savedKey)
      .then((res) => {
        if (res.valid) {
          store.activateLicense(savedKey);
        } else {
          store.deactivateLicense();
        }
      })
      .catch(() => {
        // Network issue — keep current state, don't penalise user
      });
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const isLoading =
    store.status === "generating" || store.status === "running";

  const handleDiagnose = async () => {
    if (!store.model || !store.errorMessage) return;
    setIsDiagnosing(true);
    setDiagnosis(null);
    try {
      const result = await diagnoseSimulation(store.model, store.errorMessage);
      setDiagnosis(result);
    } catch {
      setDiagnosis({
        diagnosis: "Diagnosis service unavailable.",
        suggestion: "Check that all input ports are connected and a SCOPE block exists.",
      });
    } finally {
      setIsDiagnosing(false);
    }
  };

  const handleDismissError = () => {
    store.setErrorMessage(null);
    setDiagnosis(null);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100vh" }}>
      {/* ── Header ─────────────────────────────────────────────────────────── */}
      <div
        style={{
          padding: "10px 16px",
          background: "#151722",
          borderBottom: "1px solid #2d3148",
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <div
          style={{
            width: 8,
            height: 8,
            borderRadius: "50%",
            background: "#6366f1",
            boxShadow: "0 0 8px #6366f1",
          }}
        />
        <span style={{ fontWeight: 700, fontSize: 15, color: "#e2e8f0" }}>
          System Link
        </span>
        <span style={{ fontSize: 11, color: "#475569" }}>
          AI-Native Control Systems Simulation
        </span>

        {isLoading && (
          <span
            style={{
              fontSize: 11,
              color: "#6366f1",
              animation: "pulse 1s infinite",
            }}
          >
            {store.status === "generating" ? "Generating model…" : "Running simulation…"}
          </span>
        )}

        {/* Tier badge + settings — pushed to the right */}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          {isPro && (
            <span
              style={{
                display: "flex",
                alignItems: "center",
                gap: 4,
                padding: "3px 10px",
                borderRadius: 20,
                background: "rgba(99,102,241,0.15)",
                border: "1px solid rgba(99,102,241,0.3)",
                color: "#818cf8",
                fontSize: 11,
                fontWeight: 700,
              }}
            >
              <Crown size={11} />
              PRO
            </span>
          )}
          <button
            onClick={() => setShowSettings(true)}
            title="Settings"
            style={{
              background: "none",
              border: "none",
              color: "#64748b",
              cursor: "pointer",
              padding: 4,
              display: "flex",
              alignItems: "center",
            }}
          >
            <Settings size={16} />
          </button>
        </div>
      </div>

      {/* ── Prompt bar ─────────────────────────────────────────────────────── */}
      <PromptBar
        onGenerate={generate}
        onRefine={(instruction) => {
          if (store.model) refine(store.model, instruction);
        }}
        hasModel={!!store.model}
        isLoading={isLoading}
      />

      {/* ── Error banner ────────────────────────────────────────────────────── */}
      {store.errorMessage && (
        <ErrorBanner
          message={store.errorMessage}
          onDismiss={handleDismissError}
          onDiagnose={store.model ? handleDiagnose : undefined}
          isDiagnosing={isDiagnosing}
          diagnosis={diagnosis}
        />
      )}

      {/* ── AI reasoning strip ──────────────────────────────────────────────── */}
      {store.model?.metadata?.explanation && (
        <div
          style={{
            padding: "8px 16px",
            background: "#0f172a",
            borderBottom: "1px solid #1e293b",
            fontSize: 12,
            color: "#64748b",
            fontStyle: "italic",
          }}
        >
          💡 {store.model.metadata.explanation}
        </div>
      )}

      {/* ── Main workspace ──────────────────────────────────────────────────── */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {store.model ? (
          <ReactFlowProvider>
            <NodeCanvas model={store.model} />
          </ReactFlowProvider>
        ) : (
          <div
            style={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#334155",
              fontSize: 14,
              flexDirection: "column",
              gap: 8,
            }}
          >
            <div style={{ fontSize: 40 }}>⚡</div>
            <div>Enter a prompt above to generate your simulation model.</div>
            <div style={{ fontSize: 12, color: "#1e293b" }}>
              e.g. "Design a PID-controlled DC motor with Kp=2, Ki=0.5, Kd=0.1"
            </div>
          </div>
        )}

        {store.model && store.blockRegistry && (
          <ParameterSidebar
            model={store.model}
            registry={store.blockRegistry}
            onUpdate={(blockId, param, value) => {
              if (store.model) updateParam(store.model, blockId, param, value);
            }}
          />
        )}
      </div>

      {/* ── Simulation result graph ─────────────────────────────────────────── */}
      <div
        style={{
          height: 380,
          borderTop: "1px solid #2d3148",
          background: "#0f1117",
          display: "flex",
          flexDirection: "column",
        }}
      >
        <SimulationGraph
          result={store.result}
          ghostResult={store.ghostResult}
          isLoading={isLoading}
        />
      </div>

      {/* ── Footer ─────────────────────────────────────────────────────────── */}
      <div
        style={{
          padding: "6px 16px",
          background: "#0c0f19",
          borderTop: "1px solid #1a1f35",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: 4,
          fontSize: 11,
          color: "#334155",
        }}
      >
        Proudly built by{" "}
        <a
          href="https://usayeed.com"
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: "#6366f1", textDecoration: "none", fontWeight: 600 }}
        >
          Usayeed
        </a>
      </div>

      {/* ── Settings panel (modal) ──────────────────────────────────────────── */}
      {showSettings && <SettingsPanel onClose={() => setShowSettings(false)} />}
    </div>
  );
}
