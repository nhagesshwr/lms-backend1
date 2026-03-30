"""
Bug Condition Exploration Test - Task 1

This test MUST FAIL on unfixed code. Failure confirms the bug exists.
DO NOT fix the code or the test when it fails.

Bug Condition:
  GET /favicon.ico returns 404 because no route is registered for it.

Expected Counterexample:
  GET /favicon.ico → 404 Not Found (instead of 200 OK with .ico content)

Validates: Requirements 1.1, 1.2
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_favicon_returns_200():
    """
    **Validates: Requirements 1.1, 1.2**

    Property 1: Bug Condition - Favicon Request Returns 200

    On UNFIXED code this test FAILS (returns 404), confirming the bug exists.
    Counterexample: GET /favicon.ico → 404 Not Found instead of 200 OK.
    """
    response = client.get("/favicon.ico")

    # This assertion FAILS on unfixed code (404 is returned instead of 200)
    assert response.status_code == 200, (
        f"BUG CONFIRMED: GET /favicon.ico returned {response.status_code} "
        f"instead of 200. Counterexample: no route registered for /favicon.ico."
    )

    # This assertion FAILS on unfixed code (content-type is not image/*)
    assert "image" in response.headers.get("content-type", ""), (
        f"BUG CONFIRMED: content-type is '{response.headers.get('content-type')}' "
        f"instead of an image type."
    )

    # This assertion FAILS on unfixed code (no body content)
    assert len(response.content) > 0, (
        "BUG CONFIRMED: response body is empty — no favicon content served."
    )
