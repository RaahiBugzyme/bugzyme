import math


def assert_same(x, y, path="root", tol=1e-4):
    if isinstance(x, dict):
        assert isinstance(y, dict) and x.keys() == y.keys(), f"{path}: keys differ {sorted(set(x) ^ set(y))}"
        for k in x:
            assert_same(x[k], y[k], f"{path}.{k}", tol)
    elif isinstance(x, list):
        assert isinstance(y, list) and len(x) == len(y), f"{path}: length differs"
        for i, (p, q) in enumerate(zip(x, y)):
            assert_same(p, q, f"{path}[{i}]", tol)
    elif isinstance(x, float) or isinstance(y, float):
        assert x is not None and y is not None and math.isclose(x, y, abs_tol=tol), f"{path}: {x} != {y}"
    else:
        assert x == y, f"{path}: {x!r} != {y!r}"
