"""
Project Flux — ZCOS Compiler
==============================
Transforms a validated ``SimulationModel`` IR into a gzip-compressed Xcos
(.zcos) file that Scilab can execute headlessly.

Pipeline
--------
  SimulationModel
      │
      ▼
  GraphValidator  ←  raises GraphValidationError on topology problems
      │
      ▼
  ExecutionGraph  ←  topological sort (Kahn's algorithm); detects cycles
      │
      ▼
  PortInstantiator  ←  assigns UID to every port using Block Registry
      │
      ▼
  XcosXMLBuilder  ←  assembles lxml tree (NO string concatenation)
      │
      ▼
  gzip bytes  →  written to disk or returned in-memory

Design principles
-----------------
• XML is built via lxml Element API only—no f-strings or string concatenation
  in the XML-generation path.
• Every block / port / link receives a deterministic UUID4.
• Port indices are 1-based throughout, matching Xcos conventions.
• The compiler raises ``GraphValidationError`` with *user-friendly* messages;
  the FastAPI layer translates these into the UI error strings.
"""

from __future__ import annotations

import gzip
import uuid
from collections import deque
from typing import Dict, List, Set, Tuple

from lxml import etree

from backend.block_registry import BLOCK_REGISTRY, BlockSpec, get_block_spec
from backend.models import (
    BlockDefinition,
    BlockType,
    Connection,
    PortDefinition,
    PortType,
    SimulationModel,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class GraphValidationError(Exception):
    """Raised when the simulation graph has a topology problem.

    The message is always user-friendly (no raw Xcos internals).
    """


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _new_uid() -> str:
    """Return a fresh UUID4 string."""
    return str(uuid.uuid4())


def _compute_second_order_tf(
    natural_frequency: float, damping_ratio: float
) -> Tuple[List[float], List[float]]:
    """
    Convert (ωn, ζ) to transfer-function coefficients.

    H(s) = ωn² / (s² + 2ζωn·s + ωn²)

    Returns (numerator_coeffs, denominator_coeffs) in descending power order.
    """
    wn = natural_frequency
    zeta = damping_ratio
    return ([wn ** 2], [1.0, 2 * zeta * wn, wn ** 2])


# ---------------------------------------------------------------------------
# Stage 1: Graph Validator
# ---------------------------------------------------------------------------


class GraphValidator:
    """
    Validates the topology of a SimulationModel before XML generation.

    Checks performed
    ----------------
    1. All connection block-IDs reference real blocks.
    2. Port indices do not exceed the block's registered port count.
    3. No output port is used more than once as a source.
    4. Every input port has exactly one driver.
    5. There is at least one SCOPE block (simulation must have an observer).
    """

    def __init__(self, model: SimulationModel) -> None:
        self.model = model
        self._block_map: Dict[str, BlockDefinition] = {
            b.id: b for b in model.blocks
        }

    def validate(self) -> None:
        self._check_connections_reference_real_blocks()
        self._check_port_indices_in_range()
        self._check_no_duplicate_source_ports()
        self._check_every_input_port_has_driver()
        self._check_scope_exists()

    # -- individual checks ---------------------------------------------------

    def _check_connections_reference_real_blocks(self) -> None:
        for conn in self.model.connections:
            for attr, bid in [
                ("source_block", conn.source_block),
                ("target_block", conn.target_block),
            ]:
                if bid not in self._block_map:
                    raise GraphValidationError(
                        f"Connection '{conn.id}' references unknown block "
                        f"'{bid}' ({attr}). "
                        "Please re-generate the model or check your block list."
                    )

    def _check_port_indices_in_range(self) -> None:
        for conn in self.model.connections:
            src_spec = get_block_spec(self._block_map[conn.source_block].type.value)
            dst_spec = get_block_spec(self._block_map[conn.target_block].type.value)

            if conn.source_port > src_spec.n_outputs:
                raise GraphValidationError(
                    f"Block '{self._block_map[conn.source_block].label or conn.source_block}' "
                    f"only has {src_spec.n_outputs} output port(s), "
                    f"but connection '{conn.id}' references output port {conn.source_port}."
                )
            if conn.target_port > dst_spec.n_inputs:
                raise GraphValidationError(
                    f"Block '{self._block_map[conn.target_block].label or conn.target_block}' "
                    f"only has {dst_spec.n_inputs} input port(s), "
                    f"but connection '{conn.id}' references input port {conn.target_port}."
                )

    def _check_no_duplicate_source_ports(self) -> None:
        seen: set[Tuple[str, int]] = set()
        for conn in self.model.connections:
            key = (conn.source_block, conn.source_port)
            if key in seen:
                block_label = (
                    self._block_map[conn.source_block].label
                    or conn.source_block
                )
                raise GraphValidationError(
                    f"Output port {conn.source_port} of block '{block_label}' "
                    "is connected to more than one target. "
                    "Please insert a Mux block if you need to fan out a signal."
                )
            seen.add(key)

    def _check_every_input_port_has_driver(self) -> None:
        driven: set[Tuple[str, int]] = {
            (c.target_block, c.target_port) for c in self.model.connections
        }
        for block in self.model.blocks:
            spec = get_block_spec(block.type.value)
            for port_idx in range(1, spec.n_inputs + 1):
                if (block.id, port_idx) not in driven:
                    label = block.label or block.id
                    raise GraphValidationError(
                        f"Input port {port_idx} of block '{label}' is not connected. "
                        "Would you like me to wire it up automatically?"
                    )

    def _check_scope_exists(self) -> None:
        has_scope = any(b.type == BlockType.SCOPE for b in self.model.blocks)
        if not has_scope:
            raise GraphValidationError(
                "Your model has no Scope block. "
                "Add a SCOPE block so the simulation has something to record."
            )


# ---------------------------------------------------------------------------
# Stage 2: Execution Graph (topological sort)
# ---------------------------------------------------------------------------


class ExecutionGraph:
    """
    Computes a stable topological ordering of blocks using Kahn's algorithm.

    This ensures Xcos receives blocks in dependency order:
      sources (Step, Sine, Constant) → operations (Gain, Sum, …) → sinks (Scope)

    Without this ordering, Xcos may encounter algebraic-loop errors or produce
    non-deterministic results for multi-input/output and nested subsystems.

    Raises
    ------
    GraphValidationError
        If the connection graph contains a cycle (algebraic loop without a
        memory element).  The error message guides the user to break the loop
        with an Integrator block.
    """

    def __init__(self, model: SimulationModel) -> None:
        self.model = model

    def sorted_blocks(self) -> List[BlockDefinition]:
        """
        Return blocks in topological (dependency-first) order.

        Blocks at the same level are sorted by their canonical type name so
        that compilation is fully deterministic regardless of the order the AI
        produced them.
        """
        block_map: Dict[str, BlockDefinition] = {b.id: b for b in self.model.blocks}

        # Build adjacency list and in-degree map from signal-flow connections.
        # An edge source_block → target_block means "source must be initialised
        # before target" (signal flows from source to target).
        adjacency: Dict[str, Set[str]] = {b.id: set() for b in self.model.blocks}
        in_degree: Dict[str, int] = {b.id: 0 for b in self.model.blocks}

        for conn in self.model.connections:
            src, dst = conn.source_block, conn.target_block
            if dst not in adjacency[src]:
                adjacency[src].add(dst)
                in_degree[dst] += 1

        # Seed the queue with zero-in-degree nodes, sorted for determinism.
        queue: deque[str] = deque(
            sorted(
                (bid for bid, deg in in_degree.items() if deg == 0),
                key=lambda bid: block_map[bid].type.value,
            )
        )

        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for neighbor in sorted(adjacency[node]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(result) != len(self.model.blocks):
            raise GraphValidationError(
                "Your model contains an algebraic loop — a circular signal path "
                "with no memory element. Xcos cannot solve this algebraically. "
                "Add an INTEGRATOR block in the feedback path to break the cycle."
            )

        return [block_map[bid] for bid in result]


# ---------------------------------------------------------------------------
# Stage 3: Port Instantiator
# ---------------------------------------------------------------------------


def instantiate_ports(model: SimulationModel) -> Dict[str, Dict[str, PortDefinition]]:
    """
    For each block, create PortDefinition objects keyed by (block_id, port_type, index).

    Returns a nested dict:  port_map[block_id]["{input|output}_{index}"] = PortDefinition
    """
    driven_inputs: set[Tuple[str, int]] = {
        (c.target_block, c.target_port) for c in model.connections
    }
    driven_outputs: set[Tuple[str, int]] = {
        (c.source_block, c.source_port) for c in model.connections
    }

    port_map: Dict[str, Dict[str, PortDefinition]] = {}
    for block in model.blocks:
        spec = get_block_spec(block.type.value)
        port_map[block.id] = {}

        for i in range(1, spec.n_inputs + 1):
            port_map[block.id][f"input_{i}"] = PortDefinition(
                id=_new_uid(),
                index=i,
                port_type=PortType.INPUT,
                connected=(block.id, i) in driven_inputs,
            )

        for i in range(1, spec.n_outputs + 1):
            port_map[block.id][f"output_{i}"] = PortDefinition(
                id=_new_uid(),
                index=i,
                port_type=PortType.OUTPUT,
                connected=(block.id, i) in driven_outputs,
            )

    return port_map


# ---------------------------------------------------------------------------
# Stage 4: ZCOS XML Builder
# ---------------------------------------------------------------------------

_XCOS_NS = "http://www.scilab.org/ns/scicos/1.0"
_XCOS_SCHEMA = "http://www.scilab.org/ns/scicos/1.0 xcos.xsd"


class XcosXMLBuilder:
    """
    Builds the lxml Element tree that represents a valid .zcos file.

    The XML structure follows the Scilab Xcos format exactly:
      <XcosDiagram>
        <mxCell …/>          ← canvas root
        <Block …>
          <ExplicitInputPort …/>
          <ExplicitOutputPort …/>
        </Block>
        <ExplicitLink …/>
      </XcosDiagram>
    """

    def __init__(
        self,
        model: SimulationModel,
        port_map: Dict[str, Dict[str, PortDefinition]],
        sorted_blocks: List[BlockDefinition],
    ) -> None:
        self.model = model
        self.port_map = port_map
        self._sorted_blocks = sorted_blocks
        # Maps (block_id, "input"|"output", index) → UID used in the XML
        self._xml_port_uid: Dict[Tuple[str, str, int], str] = {}

    def build(self) -> etree._Element:
        root = etree.Element("XcosDiagram")
        root.set("background", "-1")
        root.set("finalIntegrationTime", str(self.model.config.final_time))
        root.set("integratorAbsTolerance", str(self.model.config.absolute_tolerance))
        root.set("integratorRelTolerance", str(self.model.config.relative_tolerance))
        root.set("solver", self.model.config.solver)

        # Canvas root cell (required by Xcos parser)
        cell0 = etree.SubElement(root, "mxCell")
        cell0.set("id", "0")
        cell1 = etree.SubElement(root, "mxCell")
        cell1.set("id", "1")
        cell1.set("parent", "0")

        for block in self._sorted_blocks:
            self._add_block(root, block)

        for conn in self.model.connections:
            self._add_link(root, conn)

        return root

    # -- block element -------------------------------------------------------

    def _add_block(self, parent: etree._Element, block: BlockDefinition) -> None:
        spec = get_block_spec(block.type.value)
        el = etree.SubElement(parent, "Block")
        el.set("id", block.id)
        el.set("interfaceFunctionName", spec.xcos_name)
        el.set("simulationFunctionName", spec.xcos_name)
        el.set("style", spec.xcos_style or spec.xcos_name)
        el.set("value", block.label or block.type.value)
        el.set("parent", "1")

        # Geometry
        geom = etree.SubElement(el, "mxGeometry")
        geom.set("x", str(int(block.position.x)))
        geom.set("y", str(int(block.position.y)))
        geom.set("width", "40")
        geom.set("height", "40")
        geom.set("as", "geometry")

        # Parameters (exprs)
        exprs_el = etree.SubElement(el, "mxCell")
        exprs_el.set("as", "exprs")
        exprs_el.text = self._encode_params(block, spec)

        # Input ports
        ports = self.port_map.get(block.id, {})
        for i in range(1, spec.n_inputs + 1):
            port_def = ports.get(f"input_{i}")
            uid = port_def.id if port_def else _new_uid()
            self._xml_port_uid[(block.id, "input", i)] = uid
            port_el = etree.SubElement(el, "ExplicitInputPort")
            port_el.set("id", uid)
            port_el.set("ordering", str(i))
            port_el.set("parent", block.id)
            port_el.set("style", "ExplicitInputPort")
            self._add_port_geometry(port_el, "input", i, spec.n_inputs)

        # Output ports
        for i in range(1, spec.n_outputs + 1):
            port_def = ports.get(f"output_{i}")
            uid = port_def.id if port_def else _new_uid()
            self._xml_port_uid[(block.id, "output", i)] = uid
            port_el = etree.SubElement(el, "ExplicitOutputPort")
            port_el.set("id", uid)
            port_el.set("ordering", str(i))
            port_el.set("parent", block.id)
            port_el.set("style", "ExplicitOutputPort")
            self._add_port_geometry(port_el, "output", i, spec.n_outputs)

    @staticmethod
    def _add_port_geometry(
        port_el: etree._Element,
        direction: str,
        index: int,
        total: int,
    ) -> None:
        geom = etree.SubElement(port_el, "mxGeometry")
        geom.set("as", "geometry")
        geom.set("relative", "1")
        # Distribute ports evenly along the block edge
        ratio = index / (total + 1)
        if direction == "input":
            geom.set("x", "-1")
            geom.set("y", str(round(ratio, 4)))
        else:
            geom.set("x", "1")
            geom.set("y", str(round(ratio, 4)))

    @staticmethod
    def _encode_params(block: BlockDefinition, spec: BlockSpec) -> str:
        """
        Encode block parameters as a newline-delimited Scilab expression string.

        Special handling for SECOND_ORDER: converts (ωn, ζ) to TF coefficients.
        """
        if block.type == BlockType.SECOND_ORDER:
            wn = block.parameters.get("natural_frequency", 10.0)
            zeta = block.parameters.get("damping_ratio", 0.7)
            num, den = _compute_second_order_tf(wn, zeta)
            num_str = "[" + " ".join(str(c) for c in num) + "]"
            den_str = "[" + " ".join(str(c) for c in den) + "]"
            return f"{num_str}\n{den_str}"

        lines: List[str] = []
        for p in spec.params:
            val = block.parameters.get(p.name, p.default)
            lines.append(str(val))
        return "\n".join(lines) if lines else "[]"

    # -- link element --------------------------------------------------------

    def _add_link(self, parent: etree._Element, conn: Connection) -> None:
        src_uid = self._xml_port_uid.get((conn.source_block, "output", conn.source_port))
        dst_uid = self._xml_port_uid.get((conn.target_block, "input", conn.target_port))

        if src_uid is None or dst_uid is None:
            raise GraphValidationError(
                f"Internal compiler error: could not resolve port UIDs for "
                f"connection '{conn.id}'. This is a bug—please report it."
            )

        el = etree.SubElement(parent, "ExplicitLink")
        el.set("id", conn.id)
        el.set("source", src_uid)
        el.set("target", dst_uid)
        el.set("parent", "1")

        geom = etree.SubElement(el, "mxGeometry")
        geom.set("relative", "1")
        geom.set("as", "geometry")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compile_to_zcos(model: SimulationModel) -> bytes:
    """
    Full pipeline: validate → topological sort → instantiate ports → build XML → gzip.

    Parameters
    ----------
    model : SimulationModel
        A fully populated IR model (typically produced by SimulationArchitect).

    Returns
    -------
    bytes
        Gzip-compressed Xcos XML ready for ``scilab-cli``.

    Raises
    ------
    GraphValidationError
        If the model topology is invalid or contains an algebraic loop.
        Message is always user-friendly.
    """
    # Stage 1: Validate topology
    GraphValidator(model).validate()

    # Stage 2: Topological sort — ensures Xcos receives blocks in dependency order
    sorted_blocks = ExecutionGraph(model).sorted_blocks()

    # Stage 3: Instantiate ports
    port_map = instantiate_ports(model)

    # Stage 4: Build XML tree (using dependency-ordered block list)
    builder = XcosXMLBuilder(model, port_map, sorted_blocks)
    root = builder.build()

    # Serialise to bytes
    xml_bytes = etree.tostring(
        root,
        xml_declaration=True,
        encoding="UTF-8",
        pretty_print=False,
    )

    # Stage 5: Gzip
    return gzip.compress(xml_bytes, compresslevel=9)
