from typing import Any
from src.models.events import EventModel

def preprocess_event_data(raw_events: list[dict[str, Any]]) -> list[EventModel]:
    return [EventModel.model_validate(event) for event in raw_events]