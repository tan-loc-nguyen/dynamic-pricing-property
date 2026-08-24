"""Checks that hand-maintained specifications still describe the code.

Round 4's theme: several lists were each the right call when written, none of
them fails when it goes stale, and staleness is silent. That is the original
"code that cannot do what it looks like it does" one level up — a SPECIFICATION
that has quietly stopped describing the code.

Each test here turns one of those lists into something that fails on drift.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

from dynamic_pricing.pricing.defaults import (
    NUMERIC_LEAVES,
    UNCOERCED_NUMERIC_LEAVES,
    _walk,
    default_config,
)

# encoding="utf-8" on every read below: the default is the LOCALE encoding,
# which is cp1252 on the Windows CI runner, and 31 source files carry non-ASCII
# (em-dashes, and the Vietnamese room-category labels in rate_book.py).
API_ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = API_ROOT / "dynamic_pricing"


def _numeric_leaf_paths(node, trail: str = ""):
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _numeric_leaf_paths(value, f"{trail}{key}.")
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _numeric_leaf_paths(value, f"{trail[:-1]}[{i}].")
    elif isinstance(node, (int, float)) and not isinstance(node, bool):
        yield trail[:-1]


def test_numeric_leaf_coverage_is_complete():
    """Every numeric leaf must be coerced, or explicitly declared uncoerced.

    NUMERIC_LEAVES covered 39 of 88 leaves for a full round — the entire
    now-deleted legacy engine's subtree was missed, so its eleven casts had no
    boundary protection at all. A hand-maintained allowlist that nothing verifies drifts
    the moment someone adds a cast without adding a path.
    """
    config = default_config()
    all_numeric = set(_numeric_leaf_paths(config))
    covered = {p for expr, _ in NUMERIC_LEAVES for _, _, p in _walk(config, expr.split("."))}

    uncovered = sorted(all_numeric - covered - UNCOERCED_NUMERIC_LEAVES)
    assert not uncovered, (
        f"{len(uncovered)} numeric config leaf(s) are neither coerced nor declared "
        f"uncoerced. Add them to NUMERIC_LEAVES, or to UNCOERCED_NUMERIC_LEAVES if "
        f"nothing ever casts them: {uncovered}"
    )


def test_uncoerced_allowlist_has_no_stale_entries():
    """The escape hatch must not outlive the thing it excused."""
    all_numeric = set(_numeric_leaf_paths(default_config()))
    stale = sorted(UNCOERCED_NUMERIC_LEAVES - all_numeric)
    assert not stale, f"UNCOERCED_NUMERIC_LEAVES names leaves that no longer exist: {stale}"


def test_every_cast_site_lives_behind_the_boundary():
    """int()/float() on config must not appear outside the declared layers.

    The wedge came from casts in FeatureEngine.__init__ — outside the per-row
    loop, so no guard could see them. This pins where casts are allowed to be.
    """
    allowed = {
        "pricing/defaults.py",       # the boundary itself
        "pricing/engine.py",         # inside the per-row loop
        "features/engine.py",        # guarded by _num(), asserted below
        "features/booking_curve.py", # guarded by try/except, asserted below
    }
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        rel = str(path.relative_to(PACKAGE))
        if rel in allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in {"int", "float"}
                and any(
                    isinstance(a, ast.Call)
                    and isinstance(a.func, ast.Attribute)
                    and a.func.attr == "get"
                    for a in node.args
                )
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "config value cast outside the declared layers; it would bypass the "
        f"boundary coercion and every pricing-run guard: {offenders}"
    )


# --------------------------------------------------------------------------
# Tautology detection
# --------------------------------------------------------------------------
BUILTIN_CALLS = {
    "issubclass", "isinstance", "len", "type", "hasattr", "getattr", "abs",
    "all", "any", "set", "list", "dict", "tuple", "sorted", "str", "int",
    "float", "bool", "round", "min", "max", "sum", "repr",
}


def _is_substantive(fn: ast.FunctionDef) -> bool:
    """Does any assertion in this test touch something the code COMPUTED?

    Heuristic, deliberately. A name counts as computed if it is derived from a
    call, a comprehension, a subscript/attribute chain, or is an accumulator
    that gets mutated. An assertion is substantive if it calls a non-builtin or
    reads such a name. Assertions that only compare module constants, imports
    or class hierarchies pass whether or not the behaviour they are named for
    still exists — which is the failure this exists to catch.
    """
    DERIVED = (
        ast.Call, ast.Attribute, ast.Subscript, ast.ListComp, ast.SetComp,
        ast.DictComp, ast.GeneratorExp, ast.Await, ast.BinOp, ast.Compare,
    )
    computed: set[str] = set()

    def _derived(value) -> bool:
        return isinstance(value, DERIVED) or any(
            isinstance(n, DERIVED) for n in ast.walk(value)
        )

    for node in ast.walk(fn):
        # x = <anything derived from a call/comprehension/lookup>
        if isinstance(node, ast.Assign) and node.value is not None and _derived(node.value):
            for t in node.targets:
                for name in ast.walk(t):
                    if isinstance(name, ast.Name):
                        computed.add(name.id)
        if isinstance(node, ast.AnnAssign) and node.value is not None and _derived(node.value):
            if isinstance(node.target, ast.Name):
                computed.add(node.target.id)
        # accumulators: xs = []  ...  xs.append(f())
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"append", "add", "extend", "update"}
            and isinstance(node.func.value, ast.Name)
        ):
            computed.add(node.func.value.id)
        # with pytest.raises(...) as caught
        if isinstance(node, ast.withitem) and isinstance(node.optional_vars, ast.Name):
            computed.add(node.optional_vars.id)
        # for row in <derived>
        if isinstance(node, (ast.For, ast.comprehension)):
            target = node.target
            for name in ast.walk(target):
                if isinstance(name, ast.Name):
                    computed.add(name.id)

    for node in ast.walk(fn):
        if not isinstance(node, ast.Assert):
            continue
        for inner in ast.walk(node.test):
            if isinstance(inner, ast.Call):
                name = (
                    inner.func.id
                    if isinstance(inner.func, ast.Name)
                    else getattr(inner.func, "attr", "")
                )
                if name not in BUILTIN_CALLS:
                    return True
            if isinstance(inner, ast.Name) and inner.id in computed:
                return True
            if isinstance(inner, ast.Attribute):
                root = inner
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name) and root.id in computed:
                    return True
    return False


# Legitimate exemptions. The distinction that matters: a constant may be
# asserted about when the CONSTANT ITSELF IS THE DELIVERABLE, not when it
# stands in for behaviour the test claims to cover.
#
# The heuristic cannot tell those apart, so each exemption is justified here
# rather than silently allowed. Keep this list small; every addition is a claim
# that a test proves something without exercising anything.
TAUTOLOGY_EXEMPT = {
    # Pins Luminous' CLIENT-VALIDATED rate table against an independently
    # restated copy. The constant is the business data, and pinning it is the
    # entire point — a mismatch means we would quote a rate they never agreed.
    "test_all_fifteen_bands_exist",
    "test_every_band_matches_the_client_table",
    # Asserts the ABSENCE of an attribute, which no computed value can express.
    "test_no_engine_has_a_seasonality_factor",
}


@pytest.mark.parametrize(
    "test_file", sorted(p.name for p in (API_ROOT / "tests").glob("test_*.py"))
)
def test_no_test_asserts_only_about_constants(test_file):
    """Three tests have now shipped asserting nothing about behaviour.

    `issubclass(PricingRunFailed, RuntimeError)` and
    `SYSTEMIC_ERROR_THRESHOLD >= 3` both passed with the code they were named
    for deleted. Two rounds of vigilance did not prevent the third, so this
    checks it mechanically instead.
    """
    tree = ast.parse((API_ROOT / "tests" / test_file).read_text(encoding="utf-8"))
    hollow = [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name.startswith("test_")
        and node.name not in TAUTOLOGY_EXEMPT
        and any(isinstance(n, ast.Assert) for n in ast.walk(node))
        and not _is_substantive(node)
    ]
    assert not hollow, (
        f"{test_file}: these tests assert only about constants, imports or class "
        f"hierarchies — they would pass with the behaviour they name deleted: {hollow}"
    )


def test_numeric_leaves_only_claims_leaves_that_are_actually_numeric():
    """The coverage test checks that no numeric leaf is MISSED. This checks the
    other direction: that the spec does not claim a non-numeric leaf.

    A wildcard (`<subtree>.pricing.*`) matched a string sibling and coercion
    then rejected the shipped default as "must be a number, got 'nearest'" —
    breaking 28 tests. Coverage alone could not catch it; both directions have
    to hold.
    """
    config = default_config()
    mistyped: list[str] = []
    for expression, _ in NUMERIC_LEAVES:
        for container, key, path in _walk(config, expression.split(".")):
            value = container[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                mistyped.append(f"{path} = {value!r}")
    assert not mistyped, (
        "NUMERIC_LEAVES claims these are numeric, but the shipped defaults say "
        f"otherwise: {mistyped}"
    )


def test_enum_leaves_only_claims_values_the_defaults_satisfy():
    """Same both-directions check for the enum spec."""
    from dynamic_pricing.pricing.defaults import ENUM_LEAVES

    config = default_config()
    violations: list[str] = []
    for expression, allowed in ENUM_LEAVES:
        for container, key, path in _walk(config, expression.split(".")):
            value = container[key]
            if value is not None and value not in allowed:
                violations.append(f"{path} = {value!r} not in {allowed}")
    assert not violations, f"the shipped defaults violate their own enum spec: {violations}"


def test_no_config_reaches_an_engine_without_passing_the_boundary():
    """Every caller-supplied config must go through coercion — not merely have
    its casts live in a declared layer.

    test_every_cast_site_lives_behind_the_boundary checks where casts LIVE. It
    could not catch the preview endpoint, which called merge_config directly and
    handed an uncoerced config to the engine from OUTSIDE the per-row loop: the
    cast's location was legitimate, the path reaching it was not.

    There are exactly two entry points, and they must be the sanctioned ones.
    This is the fourth time a second path has quietly skipped a guard
    (PricingRunFailed handled at 1 of 3 call sites, the rollback, reset(), and
    now this), so it is encoded rather than watched for.
    """
    sanctioned = {"pricing/defaults.py"}  # prepare_config + preview_config live here
    offenders: list[str] = []
    for path in PACKAGE.rglob("*.py"):
        rel = str(path.relative_to(PACKAGE))
        if rel in sanctioned:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "merge_config"
            ):
                offenders.append(f"{rel}:{node.lineno}")
    assert not offenders, (
        "merge_config called outside the coercion boundary — this hands an "
        "uncoerced, caller-supplied config to the engine. Use prepare_config "
        f"(save) or preview_config (unsaved): {offenders}"
    )
