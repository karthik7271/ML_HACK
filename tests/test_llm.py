import asyncio

import pytest

from dadi.llm import LLM, Provider
from dadi.persona import clean_line


class FakeClient:
    def __init__(self, reply=None, error=None):
        self.reply, self.error, self.calls = reply, error, 0
        self.chat = self
        self.completions = self

    async def create(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error

        class Msg:
            content = self.reply

        class Choice:
            message = Msg

        class Resp:
            choices = [Choice]

        return Resp


def chain(*clients):
    llm = LLM.__new__(LLM)
    llm.providers = [(Provider(f"p{i}", "", "m", None), c) for i, c in enumerate(clients)]
    llm._benched_until = {}
    return llm


def test_falls_through_to_next_provider_and_benches_the_failed_one():
    bad, good = FakeClient(error=TimeoutError("slow")), FakeClient(reply="Haan beta")
    llm = chain(bad, good)
    assert asyncio.run(llm.complete([])) == ("Haan beta", "p1")
    asyncio.run(llm.complete([]))
    assert bad.calls == 1  # benched after failing, not retried on the next turn
    assert good.calls == 2


def test_raises_when_every_provider_fails():
    with pytest.raises(RuntimeError):
        asyncio.run(chain(FakeClient(error=ValueError("429"))).complete([]))


def test_no_providers_when_order_is_empty(monkeypatch):
    monkeypatch.setenv("DADI_LLM_ORDER", "none")
    assert not LLM().available


def test_clean_line_strips_labels_directions_and_rambling():
    raw = 'Dadi: "Arre beta *adjusts glasses* ruko. Chashma kahan hai? Mil gaya. Ab bolo. Aur kya?"'
    assert clean_line(raw) == "Arre beta ruko. Chashma kahan hai? Mil gaya."


def test_clean_line_drops_emoji_and_repeated_sentence():
    assert clean_line("Namaste beta! 🌸 Kaise ho?Kaise ho?") == "Namaste beta! Kaise ho?"
