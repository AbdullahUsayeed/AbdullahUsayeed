// ---------------------------------------------------------------------------
// Project Flux — ErrorBanner
// Displays user-friendly error messages from the simulation engine.
// When a model is available, shows a "Why did this fail?" button that calls
// the /simulate/diagnose endpoint and renders the AI's explanation inline.
// ---------------------------------------------------------------------------

import { AlertTriangle, HelpCircle, Loader } from "lucide-react";

// Keyframe animation for the spinner icon.
const _spinKeyframes = `
@keyframes flux-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
`;

interface Props {
  message: string;
  onDismiss: () => void;
  /** Called when the user clicks "Why did this fail?". */
  onDiagnose?: () => void;
  /** True while the diagnosis request is in flight. */
  isDiagnosing?: boolean;
  /** Diagnosis text returned by the AI (null = not yet requested). */
  diagnosis?: { diagnosis: string; suggestion: string } | null;
}

export function ErrorBanner({
  message,
  onDismiss,
  onDiagnose,
  isDiagnosing = false,
  diagnosis = null,
}: Props) {
  return (
    <div
      style={{
        background: "#1f1315",
        borderBottom: "1px solid #7f1d1d",
        fontSize: 13,
      }}
    >
      {/* Inject the keyframe animation once */}
      <style>{_spinKeyframes}</style>
      {/* ── Primary error row ─────────────────────────────────────── */}
      <div
        style={{
          display: "flex",
          alignItems: "flex-start",
          gap: 10,
          padding: "12px 16px",
          color: "#fca5a5",
        }}
      >
        <AlertTriangle
          size={16}
          style={{ flexShrink: 0, marginTop: 1, color: "#f87171" }}
        />
        <span style={{ flex: 1 }}>{message}</span>

        {/* Diagnose button — only shown when caller provides the handler */}
        {onDiagnose && (
          <button
            onClick={onDiagnose}
            disabled={isDiagnosing}
            title="Ask AI to explain this error"
            style={{
              display: "flex",
              alignItems: "center",
              gap: 5,
              background: "rgba(99, 102, 241, 0.12)",
              border: "1px solid rgba(99, 102, 241, 0.4)",
              borderRadius: 4,
              color: isDiagnosing ? "#6366f1" : "#818cf8",
              cursor: isDiagnosing ? "default" : "pointer",
              fontSize: 11,
              padding: "3px 9px",
              whiteSpace: "nowrap",
            }}
          >
            {isDiagnosing ? (
              <Loader size={11} style={{ animation: "flux-spin 1s linear infinite" }} />
            ) : (
              <HelpCircle size={11} />
            )}
            {isDiagnosing ? "Diagnosing…" : "Why did this fail?"}
          </button>
        )}

        <button
          onClick={onDismiss}
          style={{
            background: "none",
            border: "none",
            color: "#f87171",
            cursor: "pointer",
            fontSize: 16,
            lineHeight: 1,
            padding: 0,
          }}
          aria-label="Dismiss error"
        >
          ×
        </button>
      </div>

      {/* ── Inline AI diagnosis (shown once the response arrives) ──── */}
      {diagnosis && (
        <div
          style={{
            borderTop: "1px solid #3b1a22",
            padding: "10px 16px 12px 42px",
            display: "flex",
            flexDirection: "column",
            gap: 6,
          }}
        >
          <div style={{ color: "#fca5a5" }}>
            <span style={{ fontWeight: 600 }}>Root cause: </span>
            {diagnosis.diagnosis}
          </div>
          <div style={{ color: "#a5b4fc" }}>
            <span style={{ fontWeight: 600 }}>💡 Suggestion: </span>
            {diagnosis.suggestion}
          </div>
        </div>
      )}
    </div>
  );
}
