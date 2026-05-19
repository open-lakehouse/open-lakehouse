"""Data quality chaos injection for realistic testing."""

import copy
import json
import random
from datetime import timedelta
from typing import List

from .config import ChaosConfig
from .events import Event


def apply_chaos(events: List[dict], config: ChaosConfig) -> List[dict]:
    """Apply data quality issues to a list of event dictionaries."""
    if not config.enabled:
        return events

    result = []

    for event in events:
        # Make a copy to avoid mutating original
        event = copy.deepcopy(event)

        # Null injection
        if random.random() < config.null_rate:
            event = inject_null(event)

        # Malformed JSON
        if random.random() < config.malformed_json_rate:
            event = inject_malformed_json(event)

        result.append(event)

        # Duplicate injection
        if random.random() < config.duplicate_rate:
            dup = copy.deepcopy(event)
            # Duplicates might have slightly different timestamps
            if random.random() < 0.5:
                dup["ts_seconds"] = dup.get("ts_seconds", 0) + random.randint(1, 10)
            result.append(dup)

    # Late event injection (out of order)
    if config.late_event_rate > 0:
        result = inject_late_events(result, config.late_event_rate)

    return result


def inject_null(event: dict) -> dict:
    """Randomly nullify one field in the event."""
    nullable_fields = ["location_id", "order_id", "body"]
    field = random.choice(nullable_fields)

    if field == "body":
        # Null a field inside the body JSON
        try:
            body = json.loads(event.get("body", "{}"))
            if body:
                key = random.choice(list(body.keys()))
                body[key] = None
                event["body"] = json.dumps(body)
        except (json.JSONDecodeError, TypeError):
            pass
    else:
        event[field] = None

    return event


def inject_malformed_json(event: dict) -> dict:
    """Corrupt the body JSON to be malformed."""
    body = event.get("body", "{}")

    corruption_type = random.choice([
        "truncate",
        "missing_brace",
        "missing_quote",
        "extra_comma",
    ])

    if corruption_type == "truncate":
        # Truncate the JSON
        if len(body) > 10:
            event["body"] = body[:len(body) // 2]
    elif corruption_type == "missing_brace":
        # Remove closing brace
        if body.endswith("}"):
            event["body"] = body[:-1]
    elif corruption_type == "missing_quote":
        # Remove a quote
        event["body"] = body.replace('"', '', 1)
    elif corruption_type == "extra_comma":
        # Add trailing comma
        if body.endswith("}"):
            event["body"] = body[:-1] + ",}"

    return event


def inject_late_events(events: List[dict], rate: float) -> List[dict]:
    """Shuffle some events to simulate out-of-order arrival."""
    if not events:
        return events

    num_late = int(len(events) * rate)
    if num_late == 0:
        return events

    # Select random events to make "late"
    late_indices = random.sample(range(len(events)), min(num_late, len(events)))

    # Move each late event forward in the list
    for idx in sorted(late_indices, reverse=True):
        if idx < len(events) - 1:
            event = events.pop(idx)
            # Insert 5-50 positions later
            new_pos = min(idx + random.randint(5, 50), len(events))
            events.insert(new_pos, event)

    return events


def inject_chaos_to_event(event: Event, config: ChaosConfig) -> Event:
    """Apply chaos to a single Event object (before serialization)."""
    if not config.enabled:
        return event

    # Late arrival simulation
    if random.random() < config.late_event_rate:
        delay_seconds = random.randint(60, 600)  # 1-10 minute delay
        event.ts = event.ts + timedelta(seconds=delay_seconds)

    # Null injection in body
    if random.random() < config.null_rate and event.body:
        keys = list(event.body.keys())
        if keys:
            key = random.choice(keys)
            event.body[key] = None

    return event


class ChaosMonkey:
    """Stateful chaos injector for streaming scenarios."""

    def __init__(self, config: ChaosConfig):
        self.config = config
        self.pending_duplicates: List[dict] = []
        self.delayed_events: List[dict] = []

    def process(self, event: dict) -> List[dict]:
        """Process an event and return resulting events (may be 0, 1, or more)."""
        if not self.config.enabled:
            return [event]

        results = []

        # First, check if any delayed events should now be released
        current_ts = event.get("ts_seconds", 0)
        ready_delayed = [
            e for e in self.delayed_events
            if e.get("_release_at", 0) <= current_ts
        ]
        for e in ready_delayed:
            self.delayed_events.remove(e)
            del e["_release_at"]
            results.append(e)

        # Process current event
        event = copy.deepcopy(event)

        # Maybe delay this event
        if random.random() < self.config.late_event_rate:
            delay_seconds = random.randint(60, 300)
            event["_release_at"] = current_ts + delay_seconds
            self.delayed_events.append(event)
        else:
            # Apply other chaos
            if random.random() < self.config.null_rate:
                event = inject_null(event)
            if random.random() < self.config.malformed_json_rate:
                event = inject_malformed_json(event)

            results.append(event)

            # Maybe duplicate
            if random.random() < self.config.duplicate_rate:
                dup = copy.deepcopy(event)
                results.append(dup)

        return results

    def flush(self) -> List[dict]:
        """Flush any remaining delayed events."""
        results = []
        for e in self.delayed_events:
            if "_release_at" in e:
                del e["_release_at"]
            results.append(e)
        self.delayed_events.clear()
        return results
