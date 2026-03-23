"""
Project Flux — Intermediate Representation (IR) Models
=======================================================
These Pydantic V2 models form the canonical "language" between:
  - The AI engine  (produces SimulationModel from NL prompts)
  - The graph compiler  (validates & transforms to ZCOS XML)
  - The FastAPI layer  (serialises/deserialises over HTTP/WS)

Nothing downstream ever touches raw ZCOS; everything goes through here.
"""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class BlockType(str, Enum):
    """Canonical block types understood by the Block Registry."""

    STEP = "STEP"
    SINE = "SINE"
    GAIN = "GAIN"
    SUM = "SUM"
    INTEGRATOR = "INTEGRATOR"
    DERIVATIVE = "DERIVATIVE"
    TRANSFER_FUNCTION = "TRANSFER_FUNCTION"
    PID = "PID"
    SATURATION = "SATURATION"
    SCOPE = "SCOPE"
    MUX = "MUX"
    DEMUX = "DEMUX"
    CONSTANT = "CONSTANT"
    PRODUCT = "PRODUCT"
    SECOND_ORDER = "SECOND_ORDER"


class PortType(str, Enum):
    INPUT = "input"
    OUTPUT = "output"


# ---------------------------------------------------------------------------
# Sub-models
# ---------------------------------------------------------------------------


class Position(BaseModel):
    """2-D canvas coordinates (pixels, origin = top-left)."""

    x: float = Field(default=0.0, description="Horizontal position on the canvas.")
    y: float = Field(default=0.0, description="Vertical position on the canvas.")


class PortDefinition(BaseModel):
    """
    A single port on a block.  Port indices are 1-based to match Xcos conventions.
    """

    id: str = Field(description="Globally unique UID for this port.")
    index: Annotated[int, Field(ge=1)] = Field(
        description="1-based port index within the block."
    )
    port_type: PortType = Field(description="Whether this is an input or output port.")
    connected: bool = Field(
        default=False, description="True once the graph compiler has verified a link."
    )


class BlockDefinition(BaseModel):
    """
    A single Xcos block in its canonical JSON form.

    ``parameters`` holds the numeric values that will be written into the
    ZCOS XML <exprs> element (e.g. ``{"gain": 2.0}``).
    ``ports`` is populated by the compiler when the block is instantiated from
    the Block Registry; the AI does NOT need to supply it.
    """

    id: str = Field(description="Globally unique UID for this block (uuid4).")
    type: BlockType = Field(description="Canonical block type from BlockType enum.")
    label: Optional[str] = Field(
        default=None, description="Human-readable label shown in the UI."
    )
    parameters: Dict[str, float] = Field(
        default_factory=dict,
        description=(
            "Key-value pairs of block parameters. "
            "Keys must match the Block Registry spec for this block type."
        ),
    )
    position: Position = Field(default_factory=Position)
    ports: List[PortDefinition] = Field(
        default_factory=list,
        description="Populated by the compiler; do not set manually.",
    )

    @field_validator("parameters")
    @classmethod
    def parameters_must_be_finite(cls, v: Dict[str, float]) -> Dict[str, float]:
        import math

        for key, val in v.items():
            if not math.isfinite(val):
                raise ValueError(
                    f"Parameter '{key}' must be a finite float, got {val!r}."
                )
        return v


class Connection(BaseModel):
    """
    A directed link from one block-port to another.

    Port indices are 1-based integers matching Xcos's ExplicitLink conventions.
    """

    id: str = Field(description="Globally unique UID for this link (uuid4).")
    source_block: str = Field(description="UID of the source block.")
    source_port: Annotated[int, Field(ge=1)] = Field(
        description="1-based output-port index on the source block."
    )
    target_block: str = Field(description="UID of the target block.")
    target_port: Annotated[int, Field(ge=1)] = Field(
        description="1-based input-port index on the target block."
    )

    @model_validator(mode="after")
    def source_and_target_must_differ(self) -> "Connection":
        if self.source_block == self.target_block:
            raise ValueError(
                "A connection cannot start and end on the same block "
                f"(block_id={self.source_block!r})."
            )
        return self


class AIMetadata(BaseModel):
    """
    Freeform metadata produced by the AI layer to document its reasoning.

    This is stored in the IR so that the UI can surface *why* certain
    parameter values were chosen, enabling the "Intelligent Error
    Abstraction" and "Agentic Engineering" features.
    """

    intent: Optional[str] = Field(
        default=None,
        description=(
            "High-level description of what the model is meant to represent "
            "(e.g. 'Second-order under-damped closed-loop system')."
        ),
    )
    explanation: Optional[str] = Field(
        default=None,
        description=(
            "Detailed, plain-English reasoning for every parameter choice. "
            "Used in the UI's 'Why this value?' tooltip."
        ),
    )
    llm_model: Optional[str] = Field(
        default=None,
        description="Name of the LLM that generated this model (e.g. 'gpt-4.1').",
    )
    confidence: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="Self-reported confidence score from the LLM (0–1).",
    )
    raw_prompt: Optional[str] = Field(
        default=None,
        description="Original user prompt that produced this simulation.",
    )


class SimulationConfig(BaseModel):
    """Runtime parameters for the Scilab/Xcos solver."""

    final_time: float = Field(
        default=10.0,
        gt=0.0,
        description="Simulation end time in seconds.",
    )
    solver: str = Field(
        default="LSodar",
        description="Xcos ODE solver identifier.",
    )
    absolute_tolerance: float = Field(default=1e-6, gt=0.0)
    relative_tolerance: float = Field(default=1e-4, gt=0.0)
    max_step_size: float = Field(default=0.0, ge=0.0, description="0 = auto.")


class SimulationResult(BaseModel):
    """
    Returned by the execution worker once Scilab finishes.

    ``time`` and ``signals`` are parallel arrays: ``signals[i]`` is the
    time-series for output channel ``i``.
    """

    job_id: str
    status: str = Field(description="'success' | 'error' | 'running'")
    time: List[float] = Field(default_factory=list)
    signals: Dict[str, List[float]] = Field(
        default_factory=dict,
        description="Map of signal name → sample array.",
    )
    error_message: Optional[str] = Field(
        default=None,
        description=(
            "User-friendly error text (never a raw Xcos/Scilab trace). "
            "Populated by the error-abstraction layer."
        ),
    )
    execution_time_ms: Optional[float] = Field(
        default=None,
        description="Wall-clock time for the Scilab execution in milliseconds.",
    )


# ---------------------------------------------------------------------------
# Top-level IR
# ---------------------------------------------------------------------------


class SimulationModel(BaseModel):
    """
    The canonical Intermediate Representation for a single simulation.

    Lifecycle
    ---------
    1. **AI Engine** produces a ``SimulationModel`` via structured output.
    2. **Graph Compiler** validates topology, assigns port UIDs, generates ZCOS.
    3. **Execution Worker** runs Scilab and populates a ``SimulationResult``.
    4. **FastAPI** streams ``SimulationResult`` back to the React frontend.

    Design contract
    ---------------
    - Block ``id`` fields must be globally unique within the model.
    - Every ``Connection.source_block`` and ``target_block`` must reference an
      existing block ``id``.
    - Port indices must not exceed the block's registered port count.
    """

    id: str = Field(description="Globally unique model UID (uuid4).")
    name: Optional[str] = Field(
        default=None,
        description="Human-readable name shown in the UI history panel.",
    )
    blocks: List[BlockDefinition] = Field(min_length=1)
    connections: List[Connection] = Field(default_factory=list)
    config: SimulationConfig = Field(default_factory=SimulationConfig)
    metadata: Optional[AIMetadata] = None

    @model_validator(mode="after")
    def connection_blocks_must_exist(self) -> "SimulationModel":
        block_ids = {b.id for b in self.blocks}
        for conn in self.connections:
            for attr, bid in (
                ("source_block", conn.source_block),
                ("target_block", conn.target_block),
            ):
                if bid not in block_ids:
                    raise ValueError(
                        f"Connection {conn.id!r}: {attr}={bid!r} does not "
                        "reference a known block."
                    )
        return self

    @model_validator(mode="after")
    def block_ids_must_be_unique(self) -> "SimulationModel":
        seen: set[str] = set()
        for block in self.blocks:
            if block.id in seen:
                raise ValueError(
                    f"Duplicate block id detected: {block.id!r}. "
                    "Every block must have a globally unique UID."
                )
            seen.add(block.id)
        return self
