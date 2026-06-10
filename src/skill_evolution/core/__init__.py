"""Core evolution engine — explorer, comparator, auditor, patcher, pipeline."""


def __getattr__(name: str):
    if name == "EvolutionPipeline":
        from skill_evolution.core.pipeline import EvolutionPipeline
        return EvolutionPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["EvolutionPipeline"]
