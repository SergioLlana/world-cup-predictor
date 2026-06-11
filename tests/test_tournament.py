"""Checks for the full-tournament simulator (`wcpred/tournament.py`).

No pytest required: run directly with `python3 tests/test_tournament.py`
(also collectable by pytest if available).
"""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wcpred.thirds_table import THIRD_PLACE_ALLOCATION
from wcpred.tournament import (COMBO_MASKS, GROUP_IDX, SLOT_GROUP, THIRD_SLOTS,
                               OFFICIAL_GROUPS, _simulate_bracket)


def test_official_groups_well_formed():
    """12 groups of 4, 48 distinct teams."""
    assert list(OFFICIAL_GROUPS) == list("ABCDEFGHIJKL")
    teams = [t for ts in OFFICIAL_GROUPS.values() for t in ts]
    assert len(teams) == 48 and len(set(teams)) == 48
    assert all(len(ts) == 4 for ts in OFFICIAL_GROUPS.values())


def test_thirds_table_structure():
    """495 combos, each a sorted 8-subset of A..L, each a slot->group bijection."""
    assert len(THIRD_PLACE_ALLOCATION) == 495
    seen = set()
    for combo, slots in THIRD_PLACE_ALLOCATION.items():
        assert combo not in seen
        seen.add(combo)
        assert len(combo) == 8 and sorted(combo) == list(combo)
        assert set(combo) <= set("ABCDEFGHIJKL")
        assert set(slots) == set(THIRD_SLOTS)
        # the 8 assigned thirds are exactly the 8 qualified groups
        assert sorted(slots.values()) == sorted(combo)
    # spot-check the published row 1 (groups E..L)
    assert THIRD_PLACE_ALLOCATION[("E", "F", "G", "H", "I", "J", "K", "L")] == {
        "M79": "E", "M85": "J", "M81": "I", "M74": "F",
        "M82": "H", "M77": "G", "M87": "L", "M80": "K"}


def test_compiled_table_matches_dict():
    """COMBO_MASKS is sorted and SLOT_GROUP agrees with the source dict."""
    assert len(COMBO_MASKS) == 495
    assert np.all(np.diff(COMBO_MASKS) > 0)             # sorted, unique
    for combo, slots in THIRD_PLACE_ALLOCATION.items():
        mask = sum(1 << GROUP_IDX[g] for g in combo)
        row = int(np.searchsorted(COMBO_MASKS, mask))
        for c, m in enumerate(THIRD_SLOTS):
            assert SLOT_GROUP[row, c] == GROUP_IDX[slots[m]]


def test_played_knockout_is_forced():
    """A real knockout result overrides the sampled winner everywhere it occurs.

    Deterministic groups: group g (0..11) holds teams [4g..4g+3] with winner=4g,
    runner=4g+1, third=4g+2. Thirds of groups A..H qualify. Match 73 is
    Runner-up A (id 1) vs Runner-up B (id 5); we force id 1 to win it."""
    n_sims, n_teams = 2000, 48
    cols = np.arange(12)
    winner = np.tile(4 * cols, (n_sims, 1)).astype(np.int32)
    runner = np.tile(4 * cols + 1, (n_sims, 1)).astype(np.int32)
    third = np.tile(4 * cols + 2, (n_sims, 1)).astype(np.int32)
    qualifies = np.zeros((n_sims, 12), bool)
    qualifies[:, :8] = True                            # groups A..H thirds qualify
    combo_mask = np.full(n_sims, sum(1 << i for i in range(8)))
    W = np.full((n_teams, n_teams), 0.5)               # every tie a coin flip
    np.fill_diagonal(W, 0.0)
    rng = np.random.default_rng(0)

    reach = _simulate_bracket(winner, runner, third, qualifies, combo_mask, W,
                              ko_pairs=[(1, 5)], rng=rng, n_teams=n_teams)
    # forced winner of M73 always advances out of the Round of 32...
    assert reach["r16"][:, 1].all()
    # ...and its forced loser never does (id 5 only appears in M73).
    assert reach["r16"][:, 5].sum() == 0
    # combinatorial invariants still hold
    assert np.all(reach["r32"].sum(1) == 32)
    assert np.all(reach["champion"].sum(1) == 1)


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tournament checks passed")
