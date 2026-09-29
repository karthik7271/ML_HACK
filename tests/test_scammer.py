import asyncio
import random

from dadi.llm import LLM
from dadi.scammer import SCENARIO, ScammerBot


def no_llm(monkeypatch):
    monkeypatch.setenv("DADI_LLM_ORDER", "none")
    return LLM()


def test_scripted_scammer_walks_through_its_script_with_fake_details(monkeypatch):
    bot = ScammerBot(no_llm(monkeypatch), rng=random.Random(0), scam_type="digital_arrest")
    lines = [asyncio.run(bot.next_line([])) for _ in range(5)]
    assert all(lines) and "{" not in "".join(lines)
    assert bot.turn == 5


def test_random_scenario_is_a_known_script(monkeypatch):
    assert ScammerBot(no_llm(monkeypatch), rng=random.Random(1)).scam_type in SCENARIO
