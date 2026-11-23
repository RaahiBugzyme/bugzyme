"""Phase 1 endpoint tests: /compatibility, /eligibility, /explanation.

Uses the real FastAPI app with TestClient. Registers test users, obtains JWT
tokens, and exercises the DatingML V3 endpoints with:
  - valid user IDs
  - nonexistent user IDs
  - unauthenticated requests
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def register_user(email, password, username=None):
    if username is None:
        username = email.split("@")[0]
    resp = client.post(
        "/register",
        json={"username": username, "email": email, "password": password},
    )
    if resp.status_code == 409:
        # User already exists from a previous test run — that's fine
        return None
    assert resp.status_code in (200, 201), f"Register failed: {resp.status_code} {resp.text}"
    return resp.json()


def login_user(email, password):
    resp = client.post(
        "/login",
        data={"username": email, "password": password},
    )
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    return resp.json()["access_token"]


def test_unauthenticated_endpoints_return_401():
    """All three DatingML endpoints require authentication."""
    for path in ["/compatibility", "/eligibility", "/explanation"]:
        resp = client.get(path, params={"user_id": 1})
        assert resp.status_code == 401, f"{path} should require auth, got {resp.status_code}"


def test_nonexistent_target_user_returns_404():
    """Requesting compatibility for a non-existent user returns 404."""
    register_user("phase1_nonexist_a@test.com", "Password123!", "nonexist_a")
    token = login_user("phase1_nonexist_a@test.com", "Password123!")

    for path in ["/compatibility", "/eligibility", "/explanation"]:
        resp = client.get(
            path,
            params={"user_id": 999999},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404, f"{path} should return 404 for nonexistent user, got {resp.status_code}: {resp.text}"


def test_valid_compatibility_endpoint():
    """Two registered users should get a compatibility result (no ImportError)."""
    register_user("phase1_valid_a@test.com", "Password123!", "valid_a")
    register_user("phase1_valid_b@test.com", "Password123!", "valid_b")

    token_a = login_user("phase1_valid_a@test.com", "Password123!")

    resp = client.get("/users", headers={"Authorization": f"Bearer {token_a}"})
    assert resp.status_code == 200
    users = resp.json()
    user_b = next(u for u in users if u["username"] == "valid_b")

    resp = client.get(
        "/compatibility",
        params={"user_id": user_b["id"]},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200, f"Compatibility failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "user_a" in data
    assert "user_b" in data
    assert "eligible" in data
    assert "eligibility_reason" in data
    assert data["user_a"] == "valid_a"
    assert data["user_b"] == "valid_b"
    print("  compatibility result:", data)


def test_valid_eligibility_endpoint():
    """Two registered users should get an eligibility result (no ImportError)."""
    token_a = login_user("phase1_valid_a@test.com", "Password123!")

    resp = client.get("/users", headers={"Authorization": f"Bearer {token_a}"})
    users = resp.json()
    user_b = next(u for u in users if u["username"] == "valid_b")

    resp = client.get(
        "/eligibility",
        params={"user_id": user_b["id"]},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200, f"Eligibility failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "user_a" in data
    assert "user_b" in data
    assert "eligible" in data
    assert "reason" in data
    print("  eligibility result:", data)


def test_valid_explanation_endpoint():
    """Two registered users should get an explanation result (no ImportError)."""
    token_a = login_user("phase1_valid_a@test.com", "Password123!")

    resp = client.get("/users", headers={"Authorization": f"Bearer {token_a}"})
    users = resp.json()
    user_b = next(u for u in users if u["username"] == "valid_b")

    resp = client.get(
        "/explanation",
        params={"user_id": user_b["id"]},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert resp.status_code == 200, f"Explanation failed: {resp.status_code} {resp.text}"
    data = resp.json()
    assert "user_a" in data
    assert "user_b" in data
    assert "decision" in data
    assert "summary" in data
    print("  explanation result:", data)


if __name__ == "__main__":
    test_unauthenticated_endpoints_return_401()
    print("  PASS: unauthenticated endpoints return 401")

    test_nonexistent_target_user_returns_404()
    print("  PASS: nonexistent target user returns 404")

    test_valid_compatibility_endpoint()
    print("  PASS: /compatibility returns 200 with valid users")

    test_valid_eligibility_endpoint()
    print("  PASS: /eligibility returns 200 with valid users")

    test_valid_explanation_endpoint()
    print("  PASS: /explanation returns 200 with valid users")

    print("\nALL PHASE 1 ENDPOINT TESTS PASSED")
