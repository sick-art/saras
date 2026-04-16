"""Metric registry and factory.

Metrics self-register via the ``@register`` decorator. The ``build_metric``
factory instantiates the correct class from a ``MetricDefinition``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from saras.evals.schemas import MetricDefinition

if TYPE_CHECKING:
    from saras.evals.metrics.base import BaseMetric

log = structlog.get_logger()

# preset key → metric class
METRIC_REGISTRY: dict[str, type[BaseMetric]] = {}


def register(preset_key: str):
    """Class decorator that registers a metric under *preset_key*."""

    def decorator(cls: type[BaseMetric]) -> type[BaseMetric]:
        if preset_key in METRIC_REGISTRY:
            log.warning(
                "registry.overwrite",
                preset=preset_key,
                existing=METRIC_REGISTRY[preset_key].__name__,
                new=cls.__name__,
            )
        METRIC_REGISTRY[preset_key] = cls
        return cls

    return decorator


def build_metric(
    definition: MetricDefinition,
    **kwargs: object,
) -> BaseMetric:
    """Factory: instantiate the right metric class for a ``MetricDefinition``.

    ``judge_model`` (and any other LLM-judge-specific kwargs) are forwarded
    only to classes that accept them (i.e. LLMJudgeMetric subclasses).
    Deterministic metrics receive only ``definition``.
    """
    preset = definition.preset
    if preset is None or preset not in METRIC_REGISTRY:
        raise ValueError(
            f"No metric class registered for preset '{preset}'. "
            f"Available: {sorted(METRIC_REGISTRY.keys())}"
        )
    cls = METRIC_REGISTRY[preset]

    # Only pass extra kwargs (e.g. judge_model) to LLM judge subclasses.
    # Import here to avoid a circular dependency at module level.
    from saras.evals.metrics.llm_judge import LLMJudgeMetric  # noqa: PLC0415

    if issubclass(cls, LLMJudgeMetric):
        return cls(definition, **kwargs)
    return cls(definition)
