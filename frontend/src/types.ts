// ---------------------------------------------------------------------------
// Project Flux — Shared TypeScript Types
// Mirrors the Pydantic models in backend/models.py
// ---------------------------------------------------------------------------

export type BlockType =
  | "STEP"
  | "SINE"
  | "GAIN"
  | "SUM"
  | "INTEGRATOR"
  | "DERIVATIVE"
  | "TRANSFER_FUNCTION"
  | "PID"
  | "SATURATION"
  | "SCOPE"
  | "MUX"
  | "DEMUX"
  | "CONSTANT"
  | "PRODUCT"
  | "SECOND_ORDER";

export interface Position {
  x: number;
  y: number;
}

export interface BlockDefinition {
  id: string;
  type: BlockType;
  label?: string;
  parameters: Record<string, number>;
  position: Position;
}

export interface Connection {
  id: string;
  source_block: string;
  source_port: number;
  target_block: string;
  target_port: number;
}

export interface AIMetadata {
  intent?: string;
  explanation?: string;
  llm_model?: string;
  confidence?: number;
  raw_prompt?: string;
}

export interface SimulationConfig {
  final_time: number;
  solver: string;
  absolute_tolerance: number;
  relative_tolerance: number;
  max_step_size: number;
}

export interface SimulationModel {
  id: string;
  name?: string;
  blocks: BlockDefinition[];
  connections: Connection[];
  config: SimulationConfig;
  metadata?: AIMetadata;
}

export interface SimulationResult {
  job_id: string;
  status: "success" | "error" | "running";
  time: number[];
  signals: Record<string, number[]>;
  error_message?: string;
  execution_time_ms?: number;
}

export interface ParameterSpec {
  name: string;
  label: string;
  default: number;
  min?: number;
  max?: number;
  tunable: boolean;
  unit?: string;
}

export interface BlockSpec {
  canonical_name: string;
  xcos_name: string;
  n_inputs: number;
  n_outputs: number;
  description: string;
  params: ParameterSpec[];
}

export type BlockRegistry = Record<string, BlockSpec>;

// WebSocket message union
export type WsMessage =
  | { status: "running"; job_id: string }
  | SimulationResult;
