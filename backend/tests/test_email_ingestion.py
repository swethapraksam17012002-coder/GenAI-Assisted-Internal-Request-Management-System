from app.services.email_ingestion import _build_request_payload_from_email, _extract_message_body


def test_extract_message_body_prefers_plain_text():
    payload = {
        "mimeType": "multipart/alternative",
        "parts": [
            {"mimeType": "text/html", "body": {"data": "PHA+SGVsbG88L3A+"}},
            {"mimeType": "text/plain", "body": {"data": "SGVsbG8gZnJvbSBHbWFpbA"}},
        ],
    }

    body = _extract_message_body(payload)
    assert body == "Hello from Gmail"


def test_build_request_payload_from_email_maps_headers_and_body():
    message = {
        "id": "gmail-message-1",
        "threadId": "gmail-thread-1",
        "payload": {
            "headers": [
                {"name": "From", "value": "Suresh <suresh@example.com>"},
                {"name": "Subject", "value": "VPN access required"},
            ],
            "mimeType": "text/plain",
            "body": {"data": "UGxlYXNlIGdyYW50IFZQTiBhY2Nlc3MgZm9yIHByb2R1Y3Rpb24gc3VwcG9ydC4"},
        },
    }

    payload = _build_request_payload_from_email(message)

    assert payload["gmail_message_id"] == "gmail-message-1"
    assert payload["gmail_thread_id"] == "gmail-thread-1"
    assert payload["requestor_name"] == "Suresh"
    assert payload["requestor_email"] == "suresh@example.com"
    assert payload["source_channel"] == "Email"
    assert "VPN access required" in payload["raw_description"]
