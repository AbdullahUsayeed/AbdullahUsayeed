"""
System Link — AI Engine (SimulationArchitect)
================================================
``SimulationArchitect`` is the bridge between a free-form user prompt and a
fully typed ``SimulationModel``.  It is **LLM-agnostic**: the concrete client
is injected at construction time, so swapping OpenAI for a local Llama-3 /
Mistral instance requires only changing an environment variable—no code change.

Architecture
------------
The LLM is constrained to return valid JSON via OpenAI's "Structured Output"
feature (``response_format={"type": "json_schema", ...}``) or, when that is
unavailable, via ``response_format={"type": "json_object"}`` + Pydantic
validation.  This makes the output **deterministic** and **validated** before
it ever touches the compiler.

Key classes
-----------
SimulationArchitect
    Main public class.  Call ``generate(prompt)`` for a fresh model or
    ``refine(existing_model, instruction)`` for AI-driven edits to an
    existing node graph.

_build_system_prompt()
    Returns the fully specified system prompt.  Kept in a function so it
    can be unit-tested and updated independently of the class.

Environment variables
---------------------
OPENAI_API_KEY      Required when using OpenAI backend.
OPENAI_BASE_URL     Override to point to a local inference server.
LLM_MODEL           Model identifier (default: "gpt-4.1").
LLM_TEMPERATURE     Sampling temperature (default: "0.2").
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from textwrap import dedent
from typing import Any, Dict, Optional

from pydantic import ValidationError

from backend.block_registry import BLOCK_REGISTRY
from backend.model_fixer import ModelAutoFixer
from backend.models import AIMetadata, SimulationModel

log = logging.getLogger(__name__)

_DEFAULT_MODEL = os.environ.get("LLM_MODEL", "gpt-4.1")
_DEFAULT_TEMPERATURE = float(os.environ.get("LLM_TEMPERATURE", "0.2"))


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------


def _build_system_prompt() -> str:
    """
    Return the system prompt that transforms the LLM into a control-systems
    simulation compiler.

    The prompt is carefully structured so the model:
      1. Always returns valid JSON matching the SimulationModel schema.
      2. Uses only block types listed in BLOCK_REGISTRY.
      3. Correctly maps control-theory concepts to Xcos block parameters.
      4. Fills the ``metadata.explanation`` field with plain-English reasoning.
    """
    block_summary = "\n".join(
        f"  - {name}: xcos={spec.xcos_name}, inputs={spec.n_inputs}, "
        f"outputs={spec.n_outputs}, params={spec.param_names()}"
        for name, spec in BLOCK_REGISTRY.items()
    )

    return dedent(f"""\
        You are a world-class Control Systems Engineer and Simulation Compiler.
        Your sole task is to convert a user's engineering description into a
        STRICTLY VALID JSON object that matches the SimulationModel schema.

        ════════════════════════════════════════════════════════════════
        AVAILABLE BLOCK TYPES (use ONLY these)
        ════════════════════════════════════════════════════════════════
{block_summary}

        ════════════════════════════════════════════════════════════════
        MANDATORY RULES
        ════════════════════════════════════════════════════════════════
        1. EVERY output port must be connected to something.
           If a signal has nowhere to go, route it to a SCOPE block.
        2. EVERY input port must be driven by exactly one source.
        3. Use 1-based port indices.
        4. All block IDs and connection IDs must be unique UUID4 strings.
        5. The model must contain at least one SCOPE block.
        6. Never leave "parameters" empty for a block that has params—
           always provide sensible values derived from the user's request.
        7. Set metadata.explanation to a plain-English paragraph that
           justifies EVERY parameter value you chose.
        8. Set metadata.confidence to a float 0–1 reflecting certainty.

        ════════════════════════════════════════════════════════════════
        CONTROL THEORY MAPPINGS
        ════════════════════════════════════════════════════════════════
        • "Damping ratio ζ" + "Natural frequency ωn"
            → SECOND_ORDER block with natural_frequency=ωn, damping_ratio=ζ
        • "Integrator" / "1/s"
            → INTEGRATOR block
        • "Gain K"
            → GAIN block with gain=K
        • "PID controller" with Kp, Ki, Kd
            → PID block
        • "Step input" / "unit step"
            → STEP block (amplitude=1, step_time=0)
        • "Transfer function H(s) = N(s)/D(s)"
            → TRANSFER_FUNCTION block (encode num/den coefficients)
        • "Closed-loop / feedback"
            → SUM block with signs=[1, -1] (positive reference, negative feedback)
        • "Sensor / measurement noise" → add SINE block with small amplitude
        • "Saturation / limiter" → SATURATION block

        ════════════════════════════════════════════════════════════════
        CLOSED-LOOP TEMPLATE (most common pattern)
        ════════════════════════════════════════════════════════════════
        Reference → SUM(+/-) → Controller → Plant → SCOPE
                        ↑___________________________|

        ════════════════════════════════════════════════════════════════
        OUTPUT CONTRACT
        ════════════════════════════════════════════════════════════════
        Return ONLY a JSON object. No markdown, no prose, no code fences.
        The JSON must be directly parseable by Python's json.loads().

        JSON schema (abbreviated):
        {{
          "id": "<uuid4>",
          "name": "<short human name>",
          "blocks": [
            {{
              "id": "<uuid4>",
              "type": "<BlockType>",
              "label": "<optional>",
              "parameters": {{"<param_name>": <float>, ...}},
              "position": {{"x": <float>, "y": <float>}}
            }}
          ],
          "connections": [
            {{
              "id": "<uuid4>",
              "source_block": "<block_id>",
              "source_port": <int>,
              "target_block": "<block_id>",
              "target_port": <int>
            }}
          ],
          "config": {{
            "final_time": <float>,
            "solver": "LSodar",
            "absolute_tolerance": 1e-6,
            "relative_tolerance": 1e-4,
            "max_step_size": 0.0
          }},
          "metadata": {{
            "intent": "<one-line description>",
            "explanation": "<detailed parameter justification>",
            "confidence": <0.0–1.0>
          }}
        }}
    """)


# ---------------------------------------------------------------------------
# SimulationArchitect
# ---------------------------------------------------------------------------


class SimulationArchitect:
    """
    Converts natural-language engineering prompts into validated
    ``SimulationModel`` objects.

    Parameters
    ----------
    client : Any
        An OpenAI-compatible client object that exposes
        ``client.chat.completions.create(**kwargs)``.
        Pass ``None`` to use the default ``openai.OpenAI()`` instance
        (reads ``OPENAI_API_KEY`` and ``OPENAI_BASE_URL`` from env).
    model : str
        LLM identifier (default: value of ``LLM_MODEL`` env var).
    temperature : float
        Sampling temperature.  Lower = more deterministic (recommended ≤ 0.3).
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        model: str = _DEFAULT_MODEL,
        temperature: float = _DEFAULT_TEMPERATURE,
    ) -> None:
        if client is None:
            import openai  # lazy import — only needed at runtime
            self._client = openai.OpenAI(
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get("OPENAI_BASE_URL"),
            )
        else:
            self._client = client

        self._model = model
        self._temperature = temperature
        self._system_prompt = _build_system_prompt()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(self, prompt: str) -> SimulationModel:
        """
        Generate a new SimulationModel from a free-form user prompt.

        The raw LLM output passes through Pydantic validation and then the
        ``ModelAutoFixer`` before being returned, so callers always receive
        a model that is as structurally sound as possible.

        Parameters
        ----------
        prompt : str
            Natural-language engineering description
            (e.g. "Second-order system, ωn=10 rad/s, ζ=0.7, unit step input").

        Returns
        -------
        SimulationModel
            Validated and auto-fixed Pydantic model ready for the ZCOS compiler.

        Raises
        ------
        ValueError
            If the LLM returns malformed JSON or the JSON fails Pydantic
            validation after ``_MAX_RETRIES`` attempts.
        """
        return self._invoke(
            messages=[
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": prompt},
            ],
            raw_prompt=prompt,
        )

    def refine(self, existing: SimulationModel, instruction: str) -> SimulationModel:
        """
        Modify an *existing* SimulationModel according to a natural-language
        instruction.

        The existing model is serialised to JSON and passed as context so the
        LLM can perform targeted edits (add/remove/rewire blocks) rather than
        regenerating from scratch.

        Parameters
        ----------
        existing : SimulationModel
            The current model displayed in the user's workspace.
        instruction : str
            Change instruction (e.g. "Add a low-pass filter to the output").

        Returns
        -------
        SimulationModel
            Updated and re-validated model.
        """
        existing_json = existing.model_dump_json(indent=2)
        messages = [
            {"role": "system", "content": self._system_prompt},
            {
                "role": "user",
                "content": (
                    "Here is the current simulation model:\n\n"
                    f"```json\n{existing_json}\n```\n\n"
                    f"Instruction: {instruction}\n\n"
                    "Return the COMPLETE updated model JSON."
                ),
            },
        ]
        return self._invoke(messages=messages, raw_prompt=instruction)

    def diagnose(self, model: SimulationModel, error: str) -> Dict[str, str]:
        """
        Ask the AI to explain why a simulation failed and suggest a specific fix.

        The response is always a ``dict`` with two string keys so callers never
        have to guard against missing keys.  If the LLM call itself fails, a
        static fallback message is returned — the method never raises.

        Parameters
        ----------
        model : SimulationModel
            The model that produced the error (used as context for the LLM).
        error : str
            The user-visible error message from the graph compiler or Scilab.

        Returns
        -------
        dict with keys "diagnosis" (root-cause explanation) and
        "suggestion" (actionable fix instruction).
        """
        model_json = model.model_dump_json(indent=2)
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a control-systems expert helping debug a simulation. "
                    "Given the model JSON and the error message below, explain the "
                    "root cause in plain English (1–3 sentences) and give one "
                    "specific, actionable suggestion to fix it. "
                    'Respond ONLY with valid JSON: {"diagnosis": "...", "suggestion": "..."}'
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Model:\n```json\n{model_json}\n```\n\n"
                    f"Error: {error}"
                ),
            },
        ]
        try:
            raw = self._call_llm(messages)
            data = json.loads(raw)
            return {
                "diagnosis": str(
                    data.get("diagnosis", "Unable to determine root cause.")
                ),
                "suggestion": str(
                    data.get(
                        "suggestion",
                        "Try simplifying the model or checking block connections.",
                    )
                ),
            }
        except Exception as exc:  # noqa: BLE001
            log.warning("Diagnosis LLM call failed: %s", exc)
            return {
                "diagnosis": f"Validation failed: {error}",
                "suggestion": (
                    "Ensure all input ports are connected, "
                    "at least one SCOPE block exists, "
                    "and all block parameters are within valid ranges."
                ),
            }

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    _MAX_RETRIES = 3

    def _invoke(
        self,
        messages: list[Dict[str, str]],
        raw_prompt: str,
    ) -> SimulationModel:
        """Call the LLM and parse the response, retrying on validation failure."""
        last_error: Optional[Exception] = None

        for attempt in range(1, self._MAX_RETRIES + 1):
            raw_json = ""  # initialised here so the except block can always reference it
            try:
                raw_json = self._call_llm(messages)
                data = json.loads(raw_json)

                # Inject runtime metadata that the LLM cannot know
                data.setdefault("id", str(uuid.uuid4()))
                if "metadata" not in data or data["metadata"] is None:
                    data["metadata"] = {}
                data["metadata"]["llm_model"] = self._model
                data["metadata"]["raw_prompt"] = raw_prompt

                model = SimulationModel.model_validate(data)

                # ── Auto-fix layer ────────────────────────────────────────
                # Deterministically repair common AI output mistakes
                # (wrong param names, missing params, absent SCOPE, etc.)
                # before the model ever reaches the graph compiler.
                model, fixes = ModelAutoFixer().fix(model)
                if fixes:
                    log.info(
                        "Auto-fixer applied %d correction(s) on attempt %d: %s",
                        len(fixes),
                        attempt,
                        fixes,
                    )

                log.info(
                    "SimulationModel validated: %d blocks, %d connections (attempt %d).",
                    len(model.blocks),
                    len(model.connections),
                    attempt,
                )
                log.debug("Generated IR JSON: %s", model.model_dump_json())
                return model

            except (json.JSONDecodeError, ValidationError, KeyError) as exc:
                last_error = exc
                log.warning(
                    "LLM output failed validation (attempt %d/%d): %s",
                    attempt,
                    self._MAX_RETRIES,
                    exc,
                )
                # Append the error as a correction request in the next attempt
                if attempt < self._MAX_RETRIES:
                    messages = messages + [
                        {
                            "role": "assistant",
                            "content": raw_json,
                        },
                        {
                            "role": "user",
                            "content": (
                                f"Your previous response failed validation with:\n{exc}\n\n"
                                "Please fix ONLY the validation error and return the "
                                "corrected complete JSON."
                            ),
                        },
                    ]

        raise ValueError(
            f"LLM failed to produce a valid SimulationModel after "
            f"{self._MAX_RETRIES} attempts. Last error: {last_error}"
        )

    def _call_llm(self, messages: list[Dict[str, str]]) -> str:
        """Send messages to the LLM and return the raw string response."""
        response = self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=self._temperature,
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content
        if content is None:
            raise ValueError("LLM returned an empty response.")
        return content
