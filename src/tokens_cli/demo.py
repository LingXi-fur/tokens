"""Deterministic synthetic data for the first-run Dashboard demo."""
import math
import random
from datetime import date, datetime, time, timedelta

from . import config


DEMO_DAYS = 91
DEMO_SEED = 0x70C3A
DEMO_SOURCES = ("claude", "gemini", "codex")

_MODELS = {
    "claude": ("claude-sonnet-4-5", "claude-opus-4-1"),
    "gemini": ("gemini-2.5-pro", "gemini-2.5-flash"),
    "codex": ("gpt-5-codex", "gpt-5-mini"),
}
_PROJECTS = (
    "pixel-garden",
    "orbit-notes",
    "quiet-api",
    "lantern-docs",
    "tiny-compiler",
    "weekend-lab",
)
_SESSION_TITLES = (
    "Shape the onboarding story",
    "Trace a stubborn regression",
    "Refactor the data pipeline",
    "Polish the local Dashboard",
    "Write the release checklist",
    "Explore a faster parser",
    "Review accessibility details",
    "Prototype a sharing flow",
    "Tighten privacy boundaries",
    "Document the CLI journey",
    "Reduce cold-start friction",
    "Test the cross-platform build",
    "Simplify the aggregation core",
    "Tune the cache strategy",
    "Audit empty states",
    "Design a useful demo",
    "Map the next growth sprint",
    "Close the final edge cases",
)


def build_demo(today=None, sources=None):
    """Return stable, timezone-aware synthetic records anchored to one day."""
    today = today or datetime.now(config.TZ).date()
    selected = tuple(sources or DEMO_SOURCES)
    unknown = sorted(set(selected) - set(DEMO_SOURCES))
    if unknown:
        raise ValueError("unsupported demo source: " + ", ".join(unknown))

    rng = random.Random(DEMO_SEED + today.toordinal())
    generated_at = datetime.combine(today, time(12, 0), tzinfo=config.TZ)
    first_day = today - timedelta(days=DEMO_DAYS - 1)
    records = []
    session_titles = {
        f"demo-session-{index:02d}": title
        for index, title in enumerate(_SESSION_TITLES, 1)
    }

    for day_offset in range(DEMO_DAYS):
        current_day = first_day + timedelta(days=day_offset)
        progress = day_offset / max(1, DEMO_DAYS - 1)
        wave = 1 + 0.22 * math.sin(day_offset / 4.7)
        weekend = 0.72 if current_day.weekday() >= 5 else 1.0
        spike = 1.65 if day_offset in (20, 47, 75, 88) else 1.0
        daily_scale = (0.72 + progress * 0.76) * wave * weekend * spike
        call_count = 3 + rng.randrange(4)

        for call_index in range(call_count):
            source = selected[(day_offset + call_index) % len(selected)]
            models = _MODELS[source]
            model = models[(day_offset // 5 + call_index) % len(models)]
            project_index = (day_offset * 3 + call_index * 5) % len(_PROJECTS)
            project = _PROJECTS[project_index]
            session_index = (project_index * 3 + day_offset // 6 + call_index) % len(_SESSION_TITLES)
            session = f"demo-session-{session_index + 1:02d}"

            hour_pattern = (8, 10, 14, 17, 21, 1)
            hour = hour_pattern[(day_offset + call_index) % len(hour_pattern)]
            if current_day == today:
                hour = (7, 8, 9, 10, 11, 11)[call_index]
            minute = (day_offset * 11 + call_index * 17) % 60
            timestamp = datetime.combine(
                current_day,
                time(hour, minute),
                tzinfo=config.TZ,
            )

            model_scale = 1.18 if model in ("claude-opus-4-1", "gemini-2.5-pro") else 0.9
            jitter = 0.82 + rng.random() * 0.38
            base = int(92000 * daily_scale * model_scale * jitter)
            output = max(1800, int(base * (0.12 + rng.random() * 0.07)))
            cache_read = max(0, int(base * (0.34 + rng.random() * 0.24)))
            cache_write = max(0, int(base * (0.05 + rng.random() * 0.06)))
            fresh_input = max(5000, base - output - cache_read - cache_write)
            if source == "codex":
                input_tokens = fresh_input + cache_read
                total = input_tokens + output + cache_write
            else:
                input_tokens = fresh_input
                total = input_tokens + output + cache_read + cache_write

            records.append({
                "source": source,
                "ts": timestamp.isoformat(),
                "date": current_day.isoformat(),
                "model": model,
                "input": input_tokens,
                "output": output,
                "cache_read": cache_read,
                "cache_write": cache_write,
                "total": total,
                "session": session,
                "cwd": f"/synthetic/{project}",
            })

    return {
        "records": records,
        "generated_at": generated_at,
        "since": first_day.isoformat(),
        "until": today.isoformat(),
        "sources": list(selected),
        "session_titles": session_titles,
    }
