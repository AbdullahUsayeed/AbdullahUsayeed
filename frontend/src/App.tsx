// ---------------------------------------------------------------------------
// Project Flux — App (Root Component)
// ---------------------------------------------------------------------------

import { useEffect, useState } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { ErrorBanner } from "./components/ErrorBanner";
import { NodeCanvas } from "./components/NodeCanvas";
import { ParameterSidebar } from "./components/ParameterSidebar";
import { PromptBar } from "./components/PromptBar";
import { SimulationGraph } from "./components/SimulationGraph";
import { useSimulation } from "./hooks/useSimulation";
import { useFluxStore } from "./store";
import { getBlockRegistry, diagnoseSimulation } from "./api/client";
import type { DiagnoseResponse } from "./api/client";

export default function App() {
  const store = useFluxStore();
  const { generate, refine, updateParam } = useSimulation();

  // ── Diagnosis state (local — no need to persist to global store) ──
  const [diagnosis, setDiagnosis] = useState<DiagnoseResponse | null>(null);
  const [isDiagnosing, setIsDiagnosing] = useState(false);

  // Load Block Registry once on startup
  useEffect(() => {
    getBlockRegistry()
      .then(store.setBlockRegistry)
      .catch(console.error);
  }, [store.setBlockRegistry]);

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
      {/* Header */}
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
          Project Flux
        </span>
        <span style={{ fontSize: 11, color: "#475569" }}>
          AI-Native Control Systems Simulation
        </span>
        {isLoading && (
          <span
            style={{
              marginLeft: "auto",
              fontSize: 11,
              color: "#6366f1",
              animation: "pulse 1s infinite",
            }}
          >
            {store.status === "generating" ? "Generating model…" : "Running simulation…"}
          </span>
        )}
      </div>

      {/* Prompt bar */}
      <PromptBar
        onGenerate={generate}
        onRefine={(instruction) => {
          if (store.model) refine(store.model, instruction);
        }}
        hasModel={!!store.model}
        isLoading={isLoading}
      />

      {/* Error banner — shows "Why did this fail?" when a model is present */}
      {store.errorMessage && (
        <ErrorBanner
          message={store.errorMessage}
          onDismiss={handleDismissError}
          onDiagnose={store.model ? handleDiagnose : undefined}
          isDiagnosing={isDiagnosing}
          diagnosis={diagnosis}
        />
      )}

      {/* AI reasoning strip */}
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

      {/* Main workspace */}
      <div style={{ flex: 1, display: "flex", overflow: "hidden" }}>
        {/* Node diagram */}
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

        {/* Parameter sidebar */}
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

      {/* Simulation result graph */}
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
    </div>
  );
}
