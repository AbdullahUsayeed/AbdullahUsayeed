// ---------------------------------------------------------------------------
// Project Flux — useSimulation hook
// Orchestrates the generate → subscribe → result lifecycle.
//
// Stale-result prevention: a generation counter ensures that if the user
// triggers multiple requests rapidly (e.g. fast slider drags), only the
// *latest* result is committed to the store.  Superseded WebSocket
// subscriptions are closed immediately when a newer request arrives.
// ---------------------------------------------------------------------------

import { useCallback, useRef } from "react";
import {
  generateSimulation,
  refineSimulation,
  subscribeToJob,
  updateParameter,
} from "../api/client";
import { useFluxStore } from "../store";
import type { SimulationModel } from "../types";

export function useSimulation() {
  const store = useFluxStore();

  // Tracks the cleanup function for the currently active WS subscription.
  const activeCleanupRef = useRef<(() => void) | null>(null);
  // Monotonically increasing counter — each invocation of run() bumps it.
  // Any callback that sees its captured generation != current is stale.
  const generationRef = useRef(0);

  const run = useCallback(
    (jobIdP: Promise<{ job_id: string }>) => {
      // Cancel the previous in-flight subscription before starting a new one.
      if (activeCleanupRef.current) {
        activeCleanupRef.current();
        activeCleanupRef.current = null;
      }

      const generation = ++generationRef.current;
      store.setStatus("running");
      store.setErrorMessage(null);

      jobIdP
        .then(({ job_id }) => {
          if (generation !== generationRef.current) return; // superseded
          store.setJobId(job_id);

          const cleanup = subscribeToJob(
            job_id,
            () => {},
            (result) => {
              if (generation !== generationRef.current) return; // superseded
              store.commitResult(result);
              activeCleanupRef.current = null;
              cleanup();
            }
          );
          activeCleanupRef.current = cleanup;
        })
        .catch((err: unknown) => {
          if (generation !== generationRef.current) return;
          const msg =
            err instanceof Error ? err.message : "Request failed. Please try again.";
          store.setStatus("error");
          store.setErrorMessage(msg);
          activeCleanupRef.current = null;
        });
    },
    [store]
  );

  const generate = useCallback(
    (prompt: string) => {
      store.setStatus("generating");
      run(generateSimulation(prompt));
    },
    [run, store]
  );

  const refine = useCallback(
    (model: SimulationModel, instruction: string) => {
      run(refineSimulation(model, instruction));
    },
    [run]
  );

  const updateParam = useCallback(
    (
      model: SimulationModel,
      blockId: string,
      parameter: string,
      value: number
    ) => {
      run(updateParameter(model, blockId, parameter, value));
    },
    [run]
  );

  return { generate, refine, updateParam };
}
