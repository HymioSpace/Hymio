from hymio_backend.context.browse import browse, card
from hymio_backend.context.presentation import present_record, provider_of


def test_provider_labels_never_use_connection_identifiers():
    value = {
        "source": {"kind": "connector", "namespace": "apple_health.private-connection"},
        "context": {"day": "2026-01-01", "steps": 4200, "active_kcal": 220},
    }
    card = present_record({}, value)
    assert card["source_provider"] == "apple_health"
    assert card["title"] == "每日活动 · 2026-01-01"
    assert "4,200" in card["preview"]
    assert "private-connection" not in str(card)
    assert provider_of({"source": {"kind": "connector", "namespace": "unknown.id"}}) == "connector"


def test_legacy_category_never_becomes_an_invented_browsing_label():
    value = card(
        {"id": "legacy", "kind": "artifact", "topics": []},
        {"fields": {"category": "work", "title": "Old card"}},
    )
    assert value["category"] == "work"
    assert value["labels"] == []


def test_missing_labels_use_nostalgia_topics_without_builtin_dictionary_terms():
    value = card(
        {"id": "topic", "kind": "artifact", "topics": ["晚饭安排"]},
        {"fields": {"category": "life", "title": "晚饭"}},
    )
    assert value["labels"] == ["晚饭安排"]


def test_default_feed_skips_sensor_body_reads_and_provider_filter_is_specific():
    class Context:
        reads = []

        def call(self, uid, action, **kwargs):
            if action == "search":
                return {
                    "data": {
                        "items": [
                            {
                                "id": "health",
                                "kind": "record",
                                "source": {"kind": "connector", "namespace": "apple_health.x"},
                            },
                            {
                                "id": "calendar",
                                "kind": "record",
                                "source": {"kind": "connector", "namespace": "apple_calendar.y"},
                            },
                        ],
                        "next_cursor": None,
                    }
                }
            self.reads.append(kwargs["item_id"])
            return {
                "data": {
                    "context": {"title": "Plan"},
                    "source": {"kind": "connector", "namespace": "apple_calendar.y"},
                }
            }

    client = Context()
    page = browse(client, "u", {"target": "records"})
    assert [c["id"] for c in page["items"]] == ["calendar"]
    assert client.reads == ["calendar"]
    page = browse(client, "u", {"target": "records", "source_kind": "apple_calendar"})
    assert [c["id"] for c in page["items"]] == ["calendar"]
