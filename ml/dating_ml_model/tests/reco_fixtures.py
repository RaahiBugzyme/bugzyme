"""Hand-written TEST FIXTURES for the recommendation layer. They exercise mechanics only:
they are not training data, carry no real people, and no metrics are ever reported from them."""
from datetime import datetime, timedelta

NOW = datetime(2026, 10, 1, 12, 0, 0)
TECH, HEALTH = "science / tech / engineering", "medicine / health"


def man(pid, **kw):
    base = {"id": pid, "age": 30, "sex": "m", "orientation": "straight", "job": TECH,
            "education": "graduated from college/university", "religion": "agnosticism", "ethnicity": "white",
            "drinks": "socially", "smokes": "no", "drugs": "never", "height": 70, "body_type": "fit",
            "offspring": "wants kids", "pets": "likes dogs"}
    base.update(kw)
    return {k: v for k, v in base.items() if v is not None}


def woman(pid, **kw):
    kw.setdefault("sex", "f")
    return man(pid, **kw)


# --- focus users -----------------------------------------------------------------
U1 = woman("u1", age=29, city="Pune", state="Maharashtra", country="India", relationship_intention="long_term", height=65)
U2 = woman("u2", age=31, city="Mumbai", state="Maharashtra", country="India", relationship_intention="long_term", height=64)
U3 = woman("u3", age=28, height=66)                                  # no location at all
U1_PREFS = {"preferred_distance_km": 25, "criteria": {"profession_group": {"values": ["technology_science"], "hard": False}}}

# --- 20 men with a deterministic, alternating pattern -----------------------------
POOL = [man(f"m{i:02d}", age=26 + (i % 7), job=TECH if i % 2 else HEALTH,
            city=("Pune" if i % 3 == 0 else "Mumbai" if i % 3 == 1 else None),
            state=("Maharashtra" if i % 3 != 2 else None), country=("India" if i % 3 != 2 else None),
            relationship_intention=("long_term" if i % 4 else "casual")) for i in range(1, 21)]

# --- edge-case candidates for U1 ----------------------------------------------------
EDGE = [
    man("e_coords_near", latitude=18.53, longitude=73.86),
    man("e_no_location"),
    man("e_unresolved", city="Atlantis", country="Nowhere"),
    man("e_old", age=62),
    woman("e_same_sex", age=29),           # ineligible: orientation
    man("e_minor", age=16),                # ineligible: adult check
    {"id": "e_sparse", "age": 30, "sex": "m", "orientation": "straight"},
]

PROFILES = [U1, U2, U3] + POOL + EDGE


def _ev(user, cand, action, days_ago):
    return {"user_id": user, "candidate_id": cand, "action": action,
            "timestamp": (NOW - timedelta(days=days_ago)).isoformat() + "Z"}


# U2: 14 decisions (likes technology, passes health) -> enough evidence. U3: 2 decisions only.
INTERACTIONS = ([_ev("u2", f"m{i:02d}", "LIKE" if i % 2 else "PASS", 1 + i) for i in range(1, 15)]
                + [_ev("u2", "m02", "VIEW", 3)]
                + [_ev("u3", "m01", "LIKE", 2), _ev("u3", "m02", "PASS", 1)])
PREFERENCES = {"u1": U1_PREFS}
