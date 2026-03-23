// ---------------------------------------------------------------------------
// Project Flux — useSimulation hook
// Orchestrates the generate → subscribe → result lifecycle.
// ---------------------------------------------------------------------------

import { useCallback } from "react";
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

  const run = useCallback(
    (jobIdP: Promise<{ job_id: string }>) => {
      store.setStatus("running");
      store.setErrorMessage(null);

      jobIdP.then(({ job_id }) => {
        store.setJobId(job_id);
        const cleanup = subscribeToJob(
          job_id,
          () => {},
          (result) => {
            store.commitResult(result);
            cleanup();
          }
        );
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
