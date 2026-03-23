// ---------------------------------------------------------------------------
// Project Flux — ErrorBanner
// Displays user-friendly error messages from the simulation engine.
// ---------------------------------------------------------------------------

import { AlertTriangle } from "lucide-react";

interface Props {
  message: string;
  onDismiss: () => void;
}

export function ErrorBanner({ message, onDismiss }: Props) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        gap: 10,
        padding: "12px 16px",
        background: "#1f1315",
        borderBottom: "1px solid #7f1d1d",
        color: "#fca5a5",
        fontSize: 13,
      }}
    >
      <AlertTriangle size={16} style={{ flexShrink: 0, marginTop: 1, color: "#f87171" }} />
      <span style={{ flex: 1 }}>{message}</span>
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
  );
}
