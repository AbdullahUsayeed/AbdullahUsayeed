// ---------------------------------------------------------------------------
// System Link — ParameterSidebar
// "Smart Sliders" for real-time parameter tuning.
// Sliders are generated dynamically from the Block Registry.
// Changes are debounced (150 ms) so the backend only receives one request
// per gesture rather than one per animation frame.
// ---------------------------------------------------------------------------

import { useCallback, useEffect, useRef } from "react";
import type { BlockDefinition, BlockRegistry, SimulationModel } from "../types";

interface Props {
  model: SimulationModel;
  registry: BlockRegistry;
  onUpdate: (blockId: string, param: string, value: number) => void;
}

interface SliderProps {
  block: BlockDefinition;
  param: {
    name: string;
    label: string;
    min?: number;
    max?: number;
    unit?: string;
  };
  value: number;
  onChange: (value: number) => void;
}

function ParamSlider({ block: _block, param, value, onChange }: SliderProps) {
  const min = param.min ?? -100;
  const max = param.max ?? 100;
  const step = (max - min) / 200;

  return (
    <div style={{ marginBottom: 14 }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          marginBottom: 4,
        }}
      >
        <span style={{ fontSize: 12, color: "#94a3b8" }}>{param.label}</span>
        <span style={{ fontSize: 12, color: "#e2e8f0", fontVariantNumeric: "tabular-nums" }}>
          {value.toFixed(3)}{param.unit ? ` ${param.unit}` : ""}
        </span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(parseFloat(e.target.value))}
        style={{ width: "100%", accentColor: "#6366f1" }}
      />
    </div>
  );
}

export function ParameterSidebar({ model, registry, onUpdate }: Props) {
  // Only show blocks that have tunable parameters
  const tunableBlocks = model.blocks.filter((block) => {
    const spec = registry[block.type];
    return spec && spec.params.some((p) => p.tunable);
  });

  // Debounce timer: fire onUpdate 150 ms after the user stops dragging.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up any pending timer when the component unmounts.
  useEffect(() => {
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, []);

  const handleChange = useCallback(
    (blockId: string, paramName: string, value: number) => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => {
        onUpdate(blockId, paramName, value);
      }, 150);
    },
    [onUpdate]
  );

  if (tunableBlocks.length === 0) return null;

  return (
    <div
      style={{
        width: 260,
        background: "#1e2130",
        borderLeft: "1px solid #2d3148",
        padding: "16px 14px",
        overflowY: "auto",
        flexShrink: 0,
      }}
    >
      <div
        style={{
          fontSize: 11,
          fontWeight: 700,
          color: "#6366f1",
          letterSpacing: "0.1em",
          textTransform: "uppercase",
          marginBottom: 14,
        }}
      >
        Smart Sliders
      </div>

      {tunableBlocks.map((block) => {
        const spec = registry[block.type];
        return (
          <div key={block.id} style={{ marginBottom: 20 }}>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "#e2e8f0",
                marginBottom: 8,
                borderBottom: "1px solid #2d3148",
                paddingBottom: 4,
              }}
            >
              {block.label ?? block.type}
            </div>
            {spec.params
              .filter((p) => p.tunable)
              .map((param) => (
                <ParamSlider
                  key={param.name}
                  block={block}
                  param={param}
                  value={block.parameters[param.name] ?? param.default}
                  onChange={(v) => handleChange(block.id, param.name, v)}
                />
              ))}
          </div>
        );
      })}
    </div>
  );
}
