// ---------------------------------------------------------------------------
// Project Flux — API Client
// ---------------------------------------------------------------------------

import type {
  BlockRegistry,
  SimulationModel,
  SimulationResult,
  WsMessage,
} from "../types";

const BASE = "/api";

// ── REST helpers ─────────────────────────────────────────────────────────────

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? res.statusText);
  }
  return res.json() as Promise<T>;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(res.statusText);
  return res.json() as Promise<T>;
}

// ── Public API ───────────────────────────────────────────────────────────────

export interface JobResponse {
  job_id: string;
  status: string;
  message?: string;
}

/** Generate a new simulation model from a free-form prompt. */
export async function generateSimulation(prompt: string): Promise<JobResponse> {
  return post<JobResponse>("/simulate", { prompt });
}

/** Modify an existing model via a natural-language instruction. */
export async function refineSimulation(
  model: SimulationModel,
  instruction: string
): Promise<JobResponse> {
  return post<JobResponse>("/simulate/refine", { model, instruction });
}

/** Hot-patch a single block parameter and re-run (slider tuning). */
export async function updateParameter(
  model: SimulationModel,
  blockId: string,
  parameter: string,
  value: number
): Promise<JobResponse> {
  return post<JobResponse>("/simulate/update", {
    model,
    block_id: blockId,
    parameter,
    value,
  });
}

/** Poll a simulation result (REST fallback). */
export async function getResult(jobId: string): Promise<SimulationResult> {
  return get<SimulationResult>(`/simulate/${jobId}`);
}

/** Fetch the full Block Registry from the backend. */
export async function getBlockRegistry(): Promise<BlockRegistry> {
  return get<BlockRegistry>("/blocks");
}

// ── WebSocket ────────────────────────────────────────────────────────────────

/**
 * Open a WebSocket connection for real-time simulation result streaming.
 *
 * @param jobId   The job UUID returned by generateSimulation / refineSimulation.
 * @param onMsg   Called with each parsed WsMessage.
 * @param onDone  Called when the result is final (success or error).
 * @returns A cleanup function that closes the socket.
 */
export function subscribeToJob(
  jobId: string,
  onMsg: (msg: WsMessage) => void,
  onDone: (result: SimulationResult) => void
): () => void {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${protocol}://${window.location.host}/ws/${jobId}`);

  ws.onmessage = (event) => {
    const msg = JSON.parse(event.data as string) as WsMessage;
    onMsg(msg);
    if (msg.status === "success" || msg.status === "error") {
      onDone(msg as SimulationResult);
      ws.close();
    }
  };

  ws.onerror = (err) => {
    console.error("WS error", err);
    ws.close();
  };

  return () => ws.close();
}
