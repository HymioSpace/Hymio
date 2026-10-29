"""Human-facing context source identities; never expose connection IDs as labels."""

PROVIDERS = {
    "apple_health": "苹果健康",
    "apple_calendar": "苹果日历",
    "gmail": "Gmail",
    "dida": "滴答清单",
}


def provider_of(value):
    source = value.get("source") or {}
    namespace = source.get("namespace", "")
    provider = namespace.split(".", 1)[0]
    return provider if provider in PROVIDERS else source.get("kind", "legacy")


def health_summary(context):
    parts = []
    if context.get("steps") is not None:
        parts.append(f"步数 {context['steps']:,.0f} 步")
    if context.get("active_kcal") is not None:
        parts.append(f"活动能量 {context['active_kcal']:,.0f} 千卡")
    return " · ".join(parts) or "当天没有可分享的活动汇总"


def present_record(hit, value):
    provider = provider_of(value)
    context = value.get("context") or {}
    result = {"source_provider": provider}
    if provider == "apple_health":
        result.update(
            title="每日活动 · " + str(context.get("day", "")), preview=health_summary(context)
        )
    return result
