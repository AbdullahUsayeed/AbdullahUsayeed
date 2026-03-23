"""
Project Flux — Block Registry
==============================
The Block Registry is the single source of truth for every Xcos block type
that the platform supports.  It encodes:

  • The exact Xcos/Scilab internal name (``xcos_name``)
  • How many input / output ports the block exposes
  • Which parameters exist, their default values, and human-readable labels
  • Which parameters are "tunable" (exposed as sliders in the UI)
  • The canonical Xcos XML ``<style>`` string

The AI engine, graph compiler, and frontend slider system all derive their
knowledge from this registry—there is no other place where block metadata lives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ParameterSpec:
    """Specification for a single block parameter."""

    name: str
    default: float
    label: str
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    tunable: bool = True          # exposed as a slider in the UI
    unit: Optional[str] = None    # displayed next to the slider


@dataclass(frozen=True)
class BlockSpec:
    """Full specification for one Xcos block type."""

    canonical_name: str           # matches models.BlockType
    xcos_name: str                # internal Scilab/Xcos block identifier
    n_inputs: int
    n_outputs: int
    params: List[ParameterSpec]
    xcos_style: str = ""          # CSS-like style string stored in ZCOS XML
    description: str = ""

    def default_params(self) -> Dict[str, float]:
        return {p.name: p.default for p in self.params}

    def param_names(self) -> List[str]:
        return [p.name for p in self.params]

    def tunable_params(self) -> List[ParameterSpec]:
        return [p for p in self.params if p.tunable]


# ---------------------------------------------------------------------------
# Registry definition — add new block types here and only here.
# ---------------------------------------------------------------------------

BLOCK_REGISTRY: Dict[str, BlockSpec] = {
    "STEP": BlockSpec(
        canonical_name="STEP",
        xcos_name="STEP_FUNCTION",
        n_inputs=0,
        n_outputs=1,
        description="Generates a step signal at a configurable time.",
        params=[
            ParameterSpec("step_time",  0.0,  "Step Time",      0.0,   None,  True,  "s"),
            ParameterSpec("initial",    0.0,  "Initial Value", -1e6,   1e6,   True,  ""),
            ParameterSpec("final",      1.0,  "Final Value",   -1e6,   1e6,   True,  ""),
        ],
    ),
    "SINE": BlockSpec(
        canonical_name="SINE",
        xcos_name="GENSIN_f",
        n_inputs=0,
        n_outputs=1,
        description="Generates a sinusoidal signal.",
        params=[
            ParameterSpec("amplitude",  1.0,  "Amplitude",  0.0,   1e6,  True,  ""),
            ParameterSpec("frequency",  1.0,  "Frequency",  0.0,   1e6,  True,  "Hz"),
            ParameterSpec("phase",      0.0,  "Phase",     -360.0, 360.0, True, "°"),
        ],
    ),
    "CONSTANT": BlockSpec(
        canonical_name="CONSTANT",
        xcos_name="CONST_m",
        n_inputs=0,
        n_outputs=1,
        description="Outputs a constant scalar value.",
        params=[
            ParameterSpec("value", 1.0, "Value", -1e6, 1e6, True, ""),
        ],
    ),
    "GAIN": BlockSpec(
        canonical_name="GAIN",
        xcos_name="GAINBLK_f",
        n_inputs=1,
        n_outputs=1,
        description="Multiplies the input signal by a scalar gain.",
        params=[
            ParameterSpec("gain", 1.0, "Gain", -1e6, 1e6, True, ""),
        ],
    ),
    "SUM": BlockSpec(
        canonical_name="SUM",
        xcos_name="SUMMATION",
        n_inputs=2,
        n_outputs=1,
        description="Sums two or more input signals with optional sign inversion.",
        params=[
            ParameterSpec("n_inputs", 2.0, "Number of Inputs", 2.0, 8.0, False, ""),
            ParameterSpec("signs",    1.0, "Signs (+1/-1)",    -1.0, 1.0, False, ""),
        ],
    ),
    "INTEGRATOR": BlockSpec(
        canonical_name="INTEGRATOR",
        xcos_name="INTEGRAL_m",
        n_inputs=1,
        n_outputs=1,
        description="Continuous-time integrator (1/s).",
        params=[
            ParameterSpec("initial_condition", 0.0, "Initial Condition", -1e6, 1e6, True, ""),
        ],
    ),
    "DERIVATIVE": BlockSpec(
        canonical_name="DERIVATIVE",
        xcos_name="DERIV",
        n_inputs=1,
        n_outputs=1,
        description="Numerical derivative (s) — use with care; adds noise.",
        params=[],
    ),
    "TRANSFER_FUNCTION": BlockSpec(
        canonical_name="TRANSFER_FUNCTION",
        xcos_name="CLR",
        n_inputs=1,
        n_outputs=1,
        description="Continuous-time transfer function H(s) = num/den.",
        params=[
            # Coefficients encoded as a single float here for schema simplicity;
            # the compiler expands them into Scilab polynomial strings.
            ParameterSpec("num_order", 0.0, "Numerator Order",   0.0, 10.0, False, ""),
            ParameterSpec("den_order", 1.0, "Denominator Order", 1.0, 10.0, False, ""),
        ],
    ),
    "PID": BlockSpec(
        canonical_name="PID",
        xcos_name="PID",
        n_inputs=1,
        n_outputs=1,
        description="Parallel PID controller (Kp + Ki/s + Kd*s).",
        params=[
            ParameterSpec("kp", 1.0,  "Proportional Gain (Kp)", 0.0, 1e4, True, ""),
            ParameterSpec("ki", 0.1,  "Integral Gain (Ki)",     0.0, 1e4, True, ""),
            ParameterSpec("kd", 0.01, "Derivative Gain (Kd)",   0.0, 1e4, True, ""),
        ],
    ),
    "SATURATION": BlockSpec(
        canonical_name="SATURATION",
        xcos_name="SATURATION",
        n_inputs=1,
        n_outputs=1,
        description="Clamps the signal between lower and upper bounds.",
        params=[
            ParameterSpec("lower", -1.0, "Lower Limit", -1e6, 0.0,  True, ""),
            ParameterSpec("upper",  1.0, "Upper Limit",  0.0, 1e6,  True, ""),
        ],
    ),
    "SCOPE": BlockSpec(
        canonical_name="SCOPE",
        xcos_name="CSCOPE",
        n_inputs=1,
        n_outputs=0,
        description="Records and displays simulation signals.",
        params=[
            ParameterSpec("refresh_period", 0.1, "Refresh Period", 0.01, 10.0, False, "s"),
            ParameterSpec("buffer_size",  128.0, "Buffer Size",    16.0, 4096.0, False, ""),
        ],
    ),
    "MUX": BlockSpec(
        canonical_name="MUX",
        xcos_name="MUX",
        n_inputs=2,
        n_outputs=1,
        description="Multiplexes multiple scalar inputs into a vector.",
        params=[
            ParameterSpec("n_inputs", 2.0, "Number of Inputs", 2.0, 16.0, False, ""),
        ],
    ),
    "DEMUX": BlockSpec(
        canonical_name="DEMUX",
        xcos_name="DEMUX",
        n_inputs=1,
        n_outputs=2,
        description="De-multiplexes a vector signal into scalar outputs.",
        params=[
            ParameterSpec("n_outputs", 2.0, "Number of Outputs", 2.0, 16.0, False, ""),
        ],
    ),
    "PRODUCT": BlockSpec(
        canonical_name="PRODUCT",
        xcos_name="PROD_f",
        n_inputs=2,
        n_outputs=1,
        description="Element-wise product of two scalar signals.",
        params=[],
    ),
    "SECOND_ORDER": BlockSpec(
        canonical_name="SECOND_ORDER",
        xcos_name="CLR",  # implemented as a transfer function at the XML level
        n_inputs=1,
        n_outputs=1,
        description=(
            "Second-order system parameterised by natural frequency (ωn) "
            "and damping ratio (ζ). H(s) = ωn² / (s² + 2ζωn·s + ωn²)."
        ),
        params=[
            ParameterSpec("natural_frequency", 10.0, "Natural Frequency (ωn)", 0.001, 1e4, True,  "rad/s"),
            ParameterSpec("damping_ratio",       0.7, "Damping Ratio (ζ)",      0.0,   2.0, True,  ""),
        ],
    ),
}


def get_block_spec(block_type: str) -> BlockSpec:
    """Return the BlockSpec for *block_type*, raising KeyError if unknown."""
    spec = BLOCK_REGISTRY.get(block_type.upper())
    if spec is None:
        supported = ", ".join(sorted(BLOCK_REGISTRY.keys()))
        raise KeyError(
            f"Unknown block type {block_type!r}. "
            f"Supported types: {supported}."
        )
    return spec
