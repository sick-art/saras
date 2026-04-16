"""Built-in preset metric definitions.

Each preset is a MetricDefinition with a stable key. Users reference presets by
key in their metric set YAML (e.g. ``- preset: goal_completion``), optionally
overriding fields like ``threshold``.

LLM-judge presets include a rubric that is injected into the judge prompt.
Deterministic presets have type="deterministic" and are handled in metrics.py.
"""

from __future__ import annotations

from saras.evals.schemas import MetricDefinition

# ── Preset registry ────────────────────────────────────────────────────────────

PRESET_METRICS: dict[str, MetricDefinition] = {
    # ── LLM-judge presets (whole_conversation) ─────────────────────────────
    "goal_completion": MetricDefinition(
        name="Goal Completion",
        type="llm_judge",
        scope="whole_conversation",
        preset="goal_completion",
        description="Did the agent fully achieve the user's stated goal by the end of the conversation?",
        rubric="""\
1 - Goal not addressed or agent failed entirely
2 - Agent attempted but missed key steps or gave wrong information
3 - Goal partially complete — main intent addressed but gaps remain
4 - Goal complete with only minor gaps or unnecessary friction
5 - Goal fully and gracefully achieved, user would leave satisfied""",
    ),

    # ── LLM-judge presets (per_turn) ───────────────────────────────────────
    "hallucination_detection": MetricDefinition(
        name="Hallucination Detection",
        type="llm_judge",
        scope="per_turn",
        preset="hallucination_detection",
        description=(
            "Did the agent state anything not grounded in tool results, the agent schema, "
            "or information the user explicitly provided?"
        ),
        rubric="""\
1 - Clear hallucination: agent stated fabricated facts not grounded in any available source
2 - Likely hallucination: agent stated specific claims with no apparent grounding
3 - Uncertain: response contains claims that could be inferred but aren't clearly grounded
4 - Mostly grounded: minor extrapolation but no clear fabrication
5 - Fully grounded: every claim is traceable to tool results, the agent schema, or user input""",
    ),

    "context_precision": MetricDefinition(
        name="Context Precision",
        type="llm_judge",
        scope="per_turn",
        preset="context_precision",
        description=(
            "Did the agent use only relevant context in its response? "
            "Penalises injecting irrelevant information or confusing the user with unrelated topics."
        ),
        rubric="""\
1 - Response dominated by irrelevant context or the wrong topic entirely
2 - Significant irrelevant content mixed with relevant
3 - Mostly relevant with one or two unnecessary diversions
4 - Highly relevant with only minor tangents
5 - Perfectly precise: only relevant context, nothing extraneous""",
    ),

    "context_recall": MetricDefinition(
        name="Context Recall",
        type="llm_judge",
        scope="per_turn",
        preset="context_recall",
        description=(
            "Did the agent include all relevant information it had access to "
            "(from tool results, prior slots, agent knowledge) in its response?"
        ),
        rubric="""\
1 - Critical information omitted — user is left without key details they need
2 - Several important pieces of available information were not surfaced
3 - Most relevant info included but one notable gap
4 - Nearly complete — only minor details omitted
5 - Comprehensive: agent surfaced all relevant available information""",
    ),

    "tone_consistency": MetricDefinition(
        name="Tone Consistency",
        type="llm_judge",
        scope="per_turn",
        preset="tone_consistency",
        description="Does the agent's response match the tone and persona defined in its configuration?",
        rubric="""\
1 - Completely off-tone or out of character
2 - Noticeably inconsistent with defined persona/tone
3 - Generally appropriate but a few phrases feel off
4 - Consistent tone with only very minor lapses
5 - Perfectly on-tone throughout""",
    ),

    "helpfulness": MetricDefinition(
        name="Helpfulness",
        type="llm_judge",
        scope="per_turn",
        preset="helpfulness",
        description="Did the agent help the user accomplish their intent? Considers clarity, completeness, and proactiveness.",
        rubric="""\
1 - Actively unhelpful or misleading — the response makes the user's situation worse
2 - Mostly unhelpful — the response is tangential, evasive, or misses the user's intent
3 - Somewhat helpful — partial answer but lacks completeness or clarity
4 - Very helpful — addresses the user's need clearly and thoroughly
5 - Proactively helpful — not only answers the question but anticipates follow-up needs""",
    ),

    # ── Deterministic presets ──────────────────────────────────────────────
    "tool_call_accuracy": MetricDefinition(
        name="Tool Call Accuracy",
        type="deterministic",
        scope="tool_call",
        preset="tool_call_accuracy",
        description=(
            "Were the correct tools called with the correct required arguments? "
            "Compares actual tool calls in each turn against the expected tools in the dataset item."
        ),
    ),

    "slot_fill_efficiency": MetricDefinition(
        name="Slot Fill Efficiency",
        type="deterministic",
        scope="per_turn",
        preset="slot_fill_efficiency",
        description=(
            "Did the agent ask for slots it already had confirmed? "
            "Did it ask for required slots when they were genuinely missing? "
            "Penalises redundant slot questions and missed required slots."
        ),
    ),

    "semantic_similarity": MetricDefinition(
        name="Semantic Similarity",
        type="deterministic",
        scope="per_turn",
        preset="semantic_similarity",
        description=(
            "Cosine similarity between the agent's response and the expected output "
            "stored in the dataset item. Requires a golden expected_output."
        ),
    ),

    "rouge_l": MetricDefinition(
        name="ROUGE-L",
        type="deterministic",
        scope="per_turn",
        preset="rouge_l",
        description=(
            "ROUGE-L F1 score (longest common subsequence) between the agent response "
            "and the expected output. Requires a golden expected_output."
        ),
    ),

    "bleu": MetricDefinition(
        name="BLEU-4",
        type="deterministic",
        scope="per_turn",
        preset="bleu",
        description=(
            "BLEU-4 n-gram precision between the agent response and the expected output. "
            "Requires a golden expected_output."
        ),
    ),
}


def resolve_metric(raw: dict) -> MetricDefinition:
    """Merge a raw metric dict (from YAML) with its preset defaults.

    If the dict has a ``preset`` key, start from the preset definition and
    overlay any user-provided fields (e.g. ``threshold``, ``name``).
    If no preset, treat it as a fully custom metric.
    """
    preset_key: str | None = raw.get("preset")
    if preset_key:
        base = PRESET_METRICS.get(preset_key)
        if base is None:
            raise ValueError(
                f"Unknown preset '{preset_key}'. "
                f"Available presets: {', '.join(PRESET_METRICS)}"
            )
        # Build merged dict: preset defaults + user overrides
        merged = base.model_dump()
        for field in ("name", "description", "rubric", "threshold"):
            if field in raw and raw[field] is not None:
                merged[field] = raw[field]
        return MetricDefinition(**merged)

    # Fully custom metric — must have all required fields
    return MetricDefinition(**raw)


def list_presets() -> list[dict]:
    """Return preset metadata for the UI picker (name, key, scope, description)."""
    return [
        {
            "key": key,
            "name": m.name,
            "type": m.type,
            "scope": m.scope,
            "description": m.description,
        }
        for key, m in PRESET_METRICS.items()
    ]
