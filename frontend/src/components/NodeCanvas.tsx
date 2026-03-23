// ---------------------------------------------------------------------------
// Project Flux — NodeCanvas (React Flow workspace)
// Renders the block diagram as interactive nodes.
// Dragging a node updates its position in the model (visual only).
// ---------------------------------------------------------------------------

import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Node,
  type NodeProps,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { BlockDefinition, Connection, SimulationModel } from "../types";

// ── Custom node component ────────────────────────────────────────────────────

const BLOCK_COLORS: Record<string, string> = {
  STEP:              "#4f46e5",
  SINE:              "#0891b2",
  CONSTANT:          "#0891b2",
  GAIN:              "#d97706",
  SUM:               "#059669",
  INTEGRATOR:        "#7c3aed",
  DERIVATIVE:        "#7c3aed",
  TRANSFER_FUNCTION: "#be185d",
  PID:               "#be185d",
  SATURATION:        "#dc2626",
  SCOPE:             "#16a34a",
  MUX:               "#64748b",
  DEMUX:             "#64748b",
  PRODUCT:           "#d97706",
  SECOND_ORDER:      "#be185d",
};

function FluxBlockNode({ data }: NodeProps) {
  const block = data.block as BlockDefinition;
  const color = BLOCK_COLORS[block.type] ?? "#64748b";

  return (
    <div
      style={{
        background: "#1e2130",
        border: `2px solid ${color}`,
        borderRadius: 8,
        padding: "8px 14px",
        minWidth: 100,
        textAlign: "center",
        boxShadow: `0 0 12px ${color}44`,
      }}
    >
      {/* Input handles */}
      {Array.from({ length: data.nInputs as number }).map((_, i) => (
        <Handle
          key={`in-${i}`}
          type="target"
          position={Position.Left}
          id={`in-${i + 1}`}
          style={{ top: `${((i + 1) / ((data.nInputs as number) + 1)) * 100}%` }}
        />
      ))}

      <div style={{ fontSize: 10, color: "#64748b", marginBottom: 2 }}>
        {block.type}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: "#e2e8f0" }}>
        {block.label ?? block.type}
      </div>

      {/* Key parameter values */}
      {Object.entries(block.parameters)
        .slice(0, 2)
        .map(([k, v]) => (
          <div key={k} style={{ fontSize: 10, color: "#94a3b8" }}>
            {k}: {typeof v === "number" ? v.toFixed(2) : v}
          </div>
        ))}

      {/* Output handles */}
      {Array.from({ length: data.nOutputs as number }).map((_, i) => (
        <Handle
          key={`out-${i}`}
          type="source"
          position={Position.Right}
          id={`out-${i + 1}`}
          style={{ top: `${((i + 1) / ((data.nOutputs as number) + 1)) * 100}%` }}
        />
      ))}
    </div>
  );
}

const NODE_TYPES = { fluxBlock: FluxBlockNode };

// ── Conversion helpers ───────────────────────────────────────────────────────

function modelToNodes(model: SimulationModel): Node[] {
  return model.blocks.map((block) => ({
    id: block.id,
    type: "fluxBlock",
    position: { x: block.position.x, y: block.position.y },
    data: {
      block,
      nInputs: 1,   // rough default; could derive from registry
      nOutputs: 1,
    },
  }));
}

function modelToEdges(connections: Connection[]): Edge[] {
  return connections.map((c) => ({
    id: c.id,
    source: c.source_block,
    sourceHandle: `out-${c.source_port}`,
    target: c.target_block,
    targetHandle: `in-${c.target_port}`,
    style: { stroke: "#6366f1", strokeWidth: 2 },
    animated: true,
  }));
}

// ── Component ────────────────────────────────────────────────────────────────

interface Props {
  model: SimulationModel;
}

export function NodeCanvas({ model }: Props) {
  const nodes = modelToNodes(model);
  const edges = modelToEdges(model.connections);

  return (
    <div style={{ flex: 1, background: "#0f1117", position: "relative" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={NODE_TYPES}
        fitView
        proOptions={{ hideAttribution: true }}
        style={{ background: "#0f1117" }}
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#1e2130"
        />
        <Controls style={{ background: "#1e2130", border: "1px solid #2d3148" }} />
        <MiniMap
          style={{ background: "#1e2130" }}
          nodeColor={(n) =>
            BLOCK_COLORS[(n.data?.block as BlockDefinition | undefined)?.type ?? ""] ?? "#64748b"
          }
        />
      </ReactFlow>
    </div>
  );
}
