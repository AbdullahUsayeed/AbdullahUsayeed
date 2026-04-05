"""
System Link — Model Auto-Fixer
================================
Post-AI correction layer that applies deterministic, LLM-free fixes to a
``SimulationModel`` before it reaches the graph compiler.

Fixes applied (in order):
  1. Parameter canonicalisation — strip keys unknown to the Block Registry;
     remap near-matches (case-insensitive, underscore-stripped); fill missing
     required keys with registry defaults; clamp values to [min, max].
  2. SCOPE insertion — if the model has no SCOPE block, add one and connect
     it to the first available unconnected output port.
  3. Undriven-input wiring — for every input port that has no incoming
     connection, add an auto-generated CONSTANT(0) block and wire it in.

None of these fixes require an LLM call; they run deterministically in
O(blocks + connections) time.  The ``fix()`` method returns both the
corrected model and a human-readable list of applied changes so callers
can log them at the appropriate severity.
"""

from __future__ import annotations

import logging
import uuid
from typing import Dict, List, Optional, Set, Tuple

from pydantic import ValidationError

from backend.block_registry import BLOCK_REGISTRY, get_block_spec
from backend.models import (
    BlockDefinition,
    BlockType,
    Connection,
    Position,
    SimulationModel,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

_BLOCK_X_GAP = 160  # horizontal distance when placing generated blocks


def _max_x(blocks: List[BlockDefinition]) -> float:
    return max((b.position.x for b in blocks), default=0.0)


def _fresh_uid() -> str:
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class ModelAutoFixer:
    """
    Applies deterministic post-AI corrections to a ``SimulationModel``.

    Typical usage
    -------------
    fixed_model, fixes = ModelAutoFixer().fix(raw_model)
    if fixes:
        log.info("Auto-fixer applied %d correction(s): %s", len(fixes), fixes)
    """

    def fix(
        self, model: SimulationModel
    ) -> Tuple[SimulationModel, List[str]]:
        """
        Run all correction stages in sequence and return the result.

        If any stage would produce an invalid model the entire fix set for
        that stage is silently rolled back and a warning is logged, so the
        original (or partially fixed) model is always returned.

        Returns
        -------
        (fixed_model, applied_fix_descriptions)
            ``applied_fix_descriptions`` is empty when no changes were needed.
        """
        blocks = list(model.blocks)
        connections = list(model.connections)
        applied_fixes: List[str] = []

        # Stage 1: canonicalise parameters
        blocks, param_fixes = self._fix_parameters(blocks)
        applied_fixes.extend(param_fixes)

        # Stage 2: ensure at least one SCOPE block exists
        blocks, connections, scope_fixes = self._ensure_scope(blocks, connections)
        applied_fixes.extend(scope_fixes)

        # Stage 3: wire every undriven input port
        blocks, connections, wire_fixes = self._wire_undriven_inputs(blocks, connections)
        applied_fixes.extend(wire_fixes)

        if not applied_fixes:
            return model, []

        # Re-validate the whole model to guard against any fixer bug.
        model_dict = model.model_dump(mode="json")
        model_dict["blocks"] = [b.model_dump(mode="json") for b in blocks]
        model_dict["connections"] = [c.model_dump(mode="json") for c in connections]
        try:
            fixed = SimulationModel.model_validate(model_dict)
        except (ValidationError, Exception) as exc:
            log.warning(
                "ModelAutoFixer produced an invalid model after %d fix(es); "
                "reverting to original. Error: %s",
                len(applied_fixes),
                exc,
            )
            return model, []

        return fixed, applied_fixes

    # ------------------------------------------------------------------
    # Stage 1 — parameter canonicalisation
    # ------------------------------------------------------------------

    def _fix_parameters(
        self, blocks: List[BlockDefinition]
    ) -> Tuple[List[BlockDefinition], List[str]]:
        """
        For each block:
          • Drop parameter keys not in the Block Registry spec.
          • Remap near-matches (case-insensitive + underscore-stripped).
          • Clamp values outside [min, max].
          • Fill missing required parameters with their registry defaults.
        """
        result: List[BlockDefinition] = []
        fixes: List[str] = []

        for block in blocks:
            try:
                spec = get_block_spec(block.type.value)
            except KeyError:
                result.append(block)
                continue

            if not spec.params:
                # Block has no registered parameters — clear any the AI added.
                if block.parameters:
                    fixes.append(
                        f"{block.type.value}({block.id[:8]}…): "
                        f"removed unexpected params {sorted(block.parameters)}"
                    )
                    block = block.model_copy(update={"parameters": {}})
                result.append(block)
                continue

            spec_names: Set[str] = {p.name for p in spec.params}
            # Normalised (lowercase, no underscores) → canonical name
            normalised: Dict[str, str] = {
                p.name.lower().replace("_", ""): p.name for p in spec.params
            }

            new_params: Dict[str, float] = {}

            for key, val in block.parameters.items():
                canonical: Optional[str]
                if key in spec_names:
                    canonical = key
                else:
                    canonical = normalised.get(key.lower().replace("_", ""))
                    if canonical is None:
                        fixes.append(
                            f"{block.type.value}({block.id[:8]}…): "
                            f"dropped unknown param '{key}'"
                        )
                        continue
                    fixes.append(
                        f"{block.type.value}({block.id[:8]}…): "
                        f"renamed param '{key}' → '{canonical}'"
                    )

                # Clamp to registry [min, max]
                spec_p = next(p for p in spec.params if p.name == canonical)
                clamped = val
                if spec_p.min_value is not None and clamped < spec_p.min_value:
                    fixes.append(
                        f"{block.type.value}({block.id[:8]}…): "
                        f"clamped '{canonical}' {val} → {spec_p.min_value}"
                    )
                    clamped = spec_p.min_value
                if spec_p.max_value is not None and clamped > spec_p.max_value:
                    fixes.append(
                        f"{block.type.value}({block.id[:8]}…): "
                        f"clamped '{canonical}' {val} → {spec_p.max_value}"
                    )
                    clamped = spec_p.max_value
                new_params[canonical] = clamped

            # Fill missing required parameters with registry defaults
            for p in spec.params:
                if p.name not in new_params:
                    new_params[p.name] = p.default
                    fixes.append(
                        f"{block.type.value}({block.id[:8]}…): "
                        f"filled missing param '{p.name}' = {p.default}"
                    )

            if new_params != dict(block.parameters):
                block = block.model_copy(update={"parameters": new_params})

            result.append(block)

        return result, fixes

    # ------------------------------------------------------------------
    # Stage 2 — ensure a SCOPE block exists
    # ------------------------------------------------------------------

    def _ensure_scope(
        self,
        blocks: List[BlockDefinition],
        connections: List[Connection],
    ) -> Tuple[List[BlockDefinition], List[Connection], List[str]]:
        if any(b.type == BlockType.SCOPE for b in blocks):
            return blocks, connections, []

        # Find the first block whose output port 1 is not yet used as a source.
        used_sources: Set[Tuple[str, int]] = {
            (c.source_block, c.source_port) for c in connections
        }
        candidate: Optional[BlockDefinition] = None
        for b in blocks:
            try:
                spec = get_block_spec(b.type.value)
            except KeyError:
                continue
            if spec.n_outputs > 0 and (b.id, 1) not in used_sources:
                candidate = b
                break

        if candidate is None:
            # All output ports are occupied — we cannot safely insert a SCOPE
            # without violating the "no duplicate source port" rule.  Leave it
            # for the GraphValidator to surface a clean error message.
            log.warning(
                "ModelAutoFixer: no SCOPE and all output ports are occupied; "
                "skipping SCOPE insertion (GraphValidator will report this)."
            )
            return blocks, connections, []

        scope_x = _max_x(blocks) + _BLOCK_X_GAP
        scope = BlockDefinition(
            id=_fresh_uid(),
            type=BlockType.SCOPE,
            label="Auto-SCOPE",
            parameters={p.name: p.default for p in BLOCK_REGISTRY["SCOPE"].params},
            position=Position(x=scope_x, y=candidate.position.y),
        )
        conn = Connection(
            id=_fresh_uid(),
            source_block=candidate.id,
            source_port=1,
            target_block=scope.id,
            target_port=1,
        )
        return (
            blocks + [scope],
            connections + [conn],
            [
                f"Added missing SCOPE block, connected to "
                f"{candidate.type.value}({candidate.id[:8]}…)"
            ],
        )

    # ------------------------------------------------------------------
    # Stage 3 — wire every undriven input port
    # ------------------------------------------------------------------

    def _wire_undriven_inputs(
        self,
        blocks: List[BlockDefinition],
        connections: List[Connection],
    ) -> Tuple[List[BlockDefinition], List[Connection], List[str]]:
        """
        For every input port that has no incoming connection, insert an
        auto-generated ``CONSTANT(value=0)`` block and wire it in.
        """
        driven: Set[Tuple[str, int]] = {
            (c.target_block, c.target_port) for c in connections
        }
        new_blocks: List[BlockDefinition] = []
        new_connections: List[Connection] = []
        fixes: List[str] = []

        for block in blocks:
            try:
                spec = get_block_spec(block.type.value)
            except KeyError:
                continue
            for port_idx in range(1, spec.n_inputs + 1):
                if (block.id, port_idx) in driven:
                    continue
                const_block = BlockDefinition(
                    id=_fresh_uid(),
                    type=BlockType.CONSTANT,
                    label="Auto-CONST",
                    parameters={"value": 0.0},
                    position=Position(
                        x=block.position.x - _BLOCK_X_GAP,
                        y=block.position.y + (port_idx - 1) * 60,
                    ),
                )
                conn = Connection(
                    id=_fresh_uid(),
                    source_block=const_block.id,
                    source_port=1,
                    target_block=block.id,
                    target_port=port_idx,
                )
                new_blocks.append(const_block)
                new_connections.append(conn)
                driven.add((block.id, port_idx))  # prevent double-patching
                fixes.append(
                    f"Wired undriven input {port_idx} of "
                    f"{block.type.value}({block.id[:8]}…) with CONSTANT(0)"
                )

        return blocks + new_blocks, connections + new_connections, fixes
