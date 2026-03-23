// ---------------------------------------------------------------------------
// Project Flux — PromptBar
// The natural-language input at the top of the workspace.
// ---------------------------------------------------------------------------

import { useState } from "react";

interface Props {
  onGenerate: (prompt: string) => void;
  onRefine: (instruction: string) => void;
  hasModel: boolean;
  isLoading: boolean;
}

export function PromptBar({ onGenerate, onRefine, hasModel, isLoading }: Props) {
  const [value, setValue] = useState("");

  const handleSubmit = () => {
    const trimmed = value.trim();
    if (!trimmed) return;
    if (hasModel) {
      onRefine(trimmed);
    } else {
      onGenerate(trimmed);
    }
    setValue("");
  };

  const placeholder = hasModel
    ? "Refine your model… (e.g. 'Add a low-pass filter to the output')"
    : "Describe your system… (e.g. 'Second-order system, ωn=10 rad/s, ζ=0.7, unit step input')";

  return (
    <div
      style={{
        display: "flex",
        gap: 8,
        padding: "12px 16px",
        background: "#1e2130",
        borderBottom: "1px solid #2d3148",
      }}
    >
      <input
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={(e) => e.key === "Enter" && handleSubmit()}
        placeholder={placeholder}
        disabled={isLoading}
        style={{
          flex: 1,
          padding: "10px 14px",
          borderRadius: 8,
          border: "1px solid #3d4170",
          background: "#151722",
          color: "#e2e8f0",
          fontSize: 14,
          outline: "none",
        }}
      />
      <button
        onClick={handleSubmit}
        disabled={isLoading || !value.trim()}
        style={{
          padding: "10px 20px",
          borderRadius: 8,
          border: "none",
          background: isLoading ? "#374155" : "#4f46e5",
          color: "#fff",
          cursor: isLoading ? "not-allowed" : "pointer",
          fontSize: 14,
          fontWeight: 600,
          transition: "background 0.2s",
        }}
      >
        {isLoading ? "…" : hasModel ? "Refine" : "Generate"}
      </button>
    </div>
  );
}
