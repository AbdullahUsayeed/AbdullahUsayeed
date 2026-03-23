// ---------------------------------------------------------------------------
// Project Flux — Zustand Store
// ---------------------------------------------------------------------------

import { create } from "zustand";
import type { BlockRegistry, SimulationModel, SimulationResult } from "./types";

export type AppStatus =
  | "idle"
  | "generating"
  | "running"
  | "success"
  | "error";

interface FluxStore {
  // Model state
  model: SimulationModel | null;
  setModel: (m: SimulationModel | null) => void;

  // Simulation state
  status: AppStatus;
  setStatus: (s: AppStatus) => void;
  jobId: string | null;
  setJobId: (id: string | null) => void;
  result: SimulationResult | null;
  setResult: (r: SimulationResult | null) => void;
  ghostResult: SimulationResult | null; // previous run for "ghost trace"
  setGhostResult: (r: SimulationResult | null) => void;

  // UI state
  errorMessage: string | null;
  setErrorMessage: (msg: string | null) => void;
  blockRegistry: BlockRegistry | null;
  setBlockRegistry: (reg: BlockRegistry) => void;

  // Actions
  commitResult: (r: SimulationResult) => void;
}

export const useFluxStore = create<FluxStore>((set, get) => ({
  model: null,
  setModel: (m) => set({ model: m }),

  status: "idle",
  setStatus: (s) => set({ status: s }),
  jobId: null,
  setJobId: (id) => set({ jobId: id }),
  result: null,
  setResult: (r) => set({ result: r }),
  ghostResult: null,
  setGhostResult: (r) => set({ ghostResult: r }),

  errorMessage: null,
  setErrorMessage: (msg) => set({ errorMessage: msg }),
  blockRegistry: null,
  setBlockRegistry: (reg) => set({ blockRegistry: reg }),

  commitResult: (r) => {
    const prev = get().result;
    set({
      result: r,
      // Archive the previous successful result as the ghost trace
      ghostResult: prev?.status === "success" ? prev : get().ghostResult,
      status: r.status === "success" ? "success" : "error",
      errorMessage: r.error_message ?? null,
    });
  },
}));
