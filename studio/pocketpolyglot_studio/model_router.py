from __future__ import annotations

from dataclasses import dataclass

from .config import Settings


@dataclass(frozen=True)
class ModelChoice:
    model: str
    reasoning: str
    profile: str
    reason: str


PROFILE_REASONING = {
    "fast": "low",
    "balanced": "medium",
    "deep": "high",
    "ultra": "xhigh",
}


def choose_model(settings: Settings, message: str, profile: str = "auto") -> ModelChoice:
    if profile != "auto":
        reasoning = PROFILE_REASONING.get(profile, "low")
        return ModelChoice(settings.chat_model, reasoning, profile, f"Explicit {profile} profile")

    normalized = message.casefold()
    ultra_markers = (
        "final audit",
        "deep check",
        "prove correctness",
        "architecture review",
        "xhigh",
        "ultra",
    )
    deep_markers = (
        "debug",
        "root cause",
        "repair",
        "review",
        "overflow",
        "equation",
        "ocr error",
        "stalled",
    )
    if any(marker in normalized for marker in ultra_markers):
        return ModelChoice(settings.chat_model, "xhigh", "ultra", "Complex validation request")
    if any(marker in normalized for marker in deep_markers):
        return ModelChoice(settings.chat_model, "medium", "balanced", "Diagnostic request")
    return ModelChoice(settings.chat_model, settings.default_reasoning, "fast", "Default responsive chat")
