"""
Preservation Property Tests - Task 2

These tests MUST PASS on unfixed code. Passing confirms the baseline behavior
that must be preserved after the fix is applied.

Property 2: Preservation - Existing Routes Unaffected
  For all requests where isBugCondition is false (path != /favicon.ico),
  the response is identical before and after the fix.

Validates: Requirements 3.1, 3.2, 3.3
"""

import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app, raise_server_exceptions=False)


def is_bug_condition(path: str, method: str = "GET") -> bool:
    """Returns True only for the specific bug condition: GET /favicon.ico"""
    return method.upper() == "GET" and path == "/favicon.ico"


# ---------------------------------------------------------------------------
# Concrete test: root endpoint
# ---------------------------------------------------------------------------

def test_root_returns_expected_message():
    """
    **Validates: Requirements 3.1**

    Concrete baseline: GET / must return the exact root message.
    This must be preserved after the fix.
    """
    assert not is_bug_condition("/")
    response = client.get("/")
    assert response.status_code == 200
    assert response.json() == {"message": "Company LMS API is running 🚀"}


# ---------------------------------------------------------------------------
# Router reachability checks
# ---------------------------------------------------------------------------

ROUTER_PREFIXES = [
    "/auth",
    "/courses",
    "/employees",
    "/departments",
    "/lessons",
    "/enrollments",
    "/quizzes",
    "/assignments",
    "/certificates",
    "/messages",
    "/doubts",
]


@pytest.mark.parametrize("prefix", ROUTER_PREFIXES)
def test_router_prefix_reachable_non_500(prefix):
    """
    **Validates: Requirements 3.2**

    Each registered router prefix must respond without a 500 Internal Server Error.
    A 401/403/404/405/422 is acceptable — it means the route exists and is handled.
    A 500 would indicate a regression introduced by the fix.
    """
    assert not is_bug_condition(prefix)
    response = client.get(prefix)
    assert response.status_code != 500, (
        f"Router prefix {prefix!r} returned 500 — possible regression."
    )


# ---------------------------------------------------------------------------
# Property-based test: non-favicon paths are unaffected
# ---------------------------------------------------------------------------

NON_FAVICON_PATHS = [
    "/",
    "/auth",
    "/auth/login",
    "/auth/register",
    "/courses",
    "/employees",
    "/departments",
    "/lessons",
    "/enrollments",
    "/quizzes",
    "/assignments",
    "/certificates",
    "/messages",
    "/doubts",
    "/nonexistent-path-xyz",
]


@pytest.mark.parametrize("path", NON_FAVICON_PATHS)
def test_non_favicon_paths_not_bug_condition(path):
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Property 2: Preservation - for all paths where isBugCondition is false,
    the response must not be a 500 error and the path must not be the bug condition.

    On unfixed code these paths all behave correctly; the fix must not change them.
    """
    assert not is_bug_condition(path), (
        f"Path {path!r} was incorrectly classified as the bug condition."
    )
    response = client.get(path)
    # Must not be a server error — any 1xx/2xx/3xx/4xx is acceptable
    assert response.status_code < 500, (
        f"GET {path} returned {response.status_code} — unexpected server error."
    )


def test_root_response_is_stable():
    """
    **Validates: Requirements 3.1**

    Calling GET / multiple times must always return the same response,
    confirming the root handler is stable and deterministic.
    """
    expected = {"message": "Company LMS API is running 🚀"}
    for _ in range(3):
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == expected


def test_favicon_path_is_only_bug_condition():
    """
    **Validates: Requirements 3.1, 3.2, 3.3**

    Confirms that isBugCondition is true ONLY for GET /favicon.ico,
    and false for all other paths tested in this suite.
    """
    assert is_bug_condition("/favicon.ico", "GET")
    assert not is_bug_condition("/favicon.ico", "POST")
    assert not is_bug_condition("/", "GET")
    assert not is_bug_condition("/auth", "GET")
    assert not is_bug_condition("/courses", "GET")
