"""Hand-written profiles for tests (no real people, no labels)."""

FULL_A = {
    "id": "a", "age": 30, "sex": "m", "orientation": "straight",
    "education": "graduated from college/university", "job": "science / tech / engineering",
    "religion": "agnosticism", "ethnicity": "white",
    "drinks": "socially", "drugs": "never", "smokes": "no", "diet": "mostly anything",
    "offspring": "doesn't have kids, but wants them", "pets": "likes dogs and likes cats",
    "height": 70, "body_type": "fit",
}
FULL_B = {
    "id": "b", "age": 28, "sex": "f", "orientation": "straight",
    "education": "graduated from college/university", "job": "computer / hardware / software",
    "religion": "agnosticism", "ethnicity": "white",
    "drinks": "socially", "drugs": "never", "smokes": "no", "diet": "anything",
    "offspring": "wants kids", "pets": "likes dogs",
    "height": 65, "body_type": "fit",
}


def variant(base, **changes):
    profile = dict(base)
    for key, value in changes.items():
        if value is None:
            profile.pop(key, None)
        else:
            profile[key] = value
    return profile


PARITY_PROFILES = [
    FULL_A,
    FULL_B,
    variant(FULL_B, id="c", age=45, sex="f", religion="christianity and very serious about it", ethnicity="black, white",
            job="medicine / health", education="working on masters program", offspring="doesn't want kids",
            drinks="very often", smokes="yes", diet="strictly vegan", pets="dislikes dogs and likes cats", height=59, body_type="curvy"),
    variant(FULL_A, id="d", age=34, sex="m", orientation="gay", job="artistic / musical / writer", height=74, body_type="jacked"),
    variant(FULL_B, id="e", age=26, sex="f", orientation="bisexual", job=None, religion=None, offspring=None, pets=None, height=None),
    {"id": "f", "age": 38, "sex": "f", "orientation": "straight"},
    {"id": "g", "age": 17, "sex": "f", "orientation": "straight", "height": 63},
    {"id": "h", "sex": "m", "orientation": "straight"},
]
