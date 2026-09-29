import random

from dadi import network
from dadi.tactics import TACTICS, TacticBandit


def test_bandit_learns_the_move_that_keeps_scammers_talking(tmp_path):
    bandit = TacticBandit(tmp_path / "b.json", rng=random.Random(0))
    for _ in range(60):
        bandit.update("digital_arrest", "long_story", continued=True)
        bandit.update("digital_arrest", "bad_connection", continued=False)
    picks = [bandit.choose("digital_arrest") for _ in range(200)]
    assert picks.count("long_story") > picks.count("bad_connection")
    assert set(picks) <= set(TACTICS)


def test_bandit_persists_and_shares_with_new_contexts(tmp_path):
    path = tmp_path / "b.json"
    b1 = TacticBandit(path)
    for _ in range(20):
        b1.update("kyc_bank", "ask_details", continued=True, new_intel=True)
    b2 = TacticBandit(path)
    assert b2.stats("kyc_bank")["ask_details"]["mean"] > 0.9
    # an unseen scam type borrows from the global posterior
    assert b2.stats("lottery_prize")["ask_details"]["mean"] > b2.stats("lottery_prize")["hold_on"]["mean"]


def test_exclude_prevents_repeating_last_move():
    bandit = TacticBandit(rng=random.Random(1))
    assert all(bandit.choose(None, exclude="mishear") != "mishear" for _ in range(50))


def _rec(cid, **intel):
    return {"id": cid, "scam_type": "digital_arrest", "wasted_s": 60, "intel": intel}


def test_calls_sharing_a_mule_account_form_a_ring():
    g = network.build([
        _rec("A", upi_ids=["mule@ybl"], phones=["9000000001"]),
        _rec("B", upi_ids=["mule@ybl"]),
        _rec("C", accounts=["123456789012"]),
    ])
    rings = network.rings(g)
    assert len(rings) == 1
    assert rings[0]["calls"] == ["A", "B"]
    assert rings[0]["shared_identifiers"] == ["UPI mule@ybl"]
    assert network.ring_of(g, "C") is None
