"""Product model catalog; deployment limits must match the Oath runtime configuration."""

CONTEXT_WINDOWS = (128_000, 256_000, 512_000, 1_000_000)
MODEL_CONTEXT_WINDOWS = {
    "MiniMax-M2.7": 204_800,
    "MiniMax-M3": 1_000_000,
    "deepseek-flash": 1_048_576,
    "Qwen/Qwen3.8-27B": 262_144,
}


# Qwen explicitly supports a deployed extension; native capacity remains the default.
MODEL_MAX_CONTEXT_WINDOWS = {**MODEL_CONTEXT_WINDOWS, "Qwen/Qwen3.8-27B": 1_000_000}


def model_capacity(model: str, overrides=None) -> int:
    configured = (overrides or {}).get(model, MODEL_CONTEXT_WINDOWS.get(model, 128_000))
    return min(configured, MODEL_MAX_CONTEXT_WINDOWS.get(model, configured))


def effective_window(selected, model, overrides):
    return min(selected, model_capacity(model, overrides))
