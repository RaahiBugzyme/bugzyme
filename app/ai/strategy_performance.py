"""Conservative strategy summaries based on explicit feedback only."""
from collections import defaultdict

MIN_OBSERVATIONS = 5

def summarize_strategy_performance(records: list[dict]) -> dict:
    buckets = defaultdict(lambda: {"helpful": 0, "not_helpful": 0})
    for item in records or []:
        strategy = item.get("strategy")
        rating = item.get("rating")
        if strategy and rating in {"helpful", "not_helpful"}:
            buckets[strategy][rating] += 1
    result = {}
    for strategy, counts in buckets.items():
        total = counts["helpful"] + counts["not_helpful"]
        result[strategy] = {**counts, "observations": total,
                            "confidence": "medium" if total >= MIN_OBSERVATIONS else "insufficient",
                            "avoid_for_now": total >= MIN_OBSERVATIONS and counts["not_helpful"] / total >= .8}
    return result
