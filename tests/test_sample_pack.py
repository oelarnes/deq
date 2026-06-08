"""Tests for DraftState.deq_query_str and fetch_draft_pick."""

from __future__ import annotations

import pytest

import deq.sample_pack as sp
from deq.sample_pack import DraftCard, DraftState, fetch_draft_pick


def _card(name: str) -> DraftCard:
    return DraftCard(name=name)


class TestDraftStateDeqQueryStr:
    def _pick(self, *names: str) -> DraftState:
        return DraftState(
            set_code="SOS", draft_id="abc", pack_num=1, pick_num=1,
            pick=names[0], pack=[_card(n) for n in names],
        )

    def test_no_card_name_returns_url_with_set_and_q(self):
        pick = self._pick("Lightning Bolt", "Counterspell", "Dark Ritual")
        url = pick.deq_query_str()
        assert url.startswith("https://magic-flea.com/on-draft/deq.html?")
        assert "set=SOS" in url
        assert "%22Lightning+Bolt%22" in url  # all names quoted
        assert "card=" not in url

    def test_all_names_quoted_in_q(self):
        pick = self._pick("Counterspell", "Fire // Ice")
        url = pick.deq_query_str()
        assert "%22Counterspell%22" in url      # single-word names quoted too
        assert "%22Fire+%2F%2F+Ice%22" in url  # split card quoted

    def test_with_card_name_adds_card_param(self):
        pick = self._pick("Lightning Bolt", "Counterspell")
        url = pick.deq_query_str(card_name="Lightning Bolt")
        assert url.startswith("https://magic-flea.com/on-draft/deq.html?")
        assert "set=SOS" in url
        assert "card=Lightning+Bolt" in url
        assert "q=" in url


class TestFetchDraftPick:
    def test_parses_url_and_builds_pick(self, monkeypatch: pytest.MonkeyPatch):
        fake_data = {
            "expansion": "TLA",
            "num_seats": 8,
            "picks": [
                {
                    "pack_number": 0,
                    "pick_number": 1,
                    "pick": {"name": "Lightning Bolt", "image_url": "bolt.jpg"},
                    "available": [
                        {"name": "Lightning Bolt", "image_url": "bolt.jpg"},
                        {"name": "Counterspell", "image_url": "counter.jpg"},
                    ],
                }
            ],
        }

        class _FakeResp:
            def json(self):
                return fake_data

        monkeypatch.setattr(sp.requests, "get", lambda url: _FakeResp())

        pick = fetch_draft_pick("https://www.17lands.com/draft/abc123/1/2")

        assert pick.set_code == "TLA"
        assert pick.draft_id == "abc123"
        assert pick.pack_num == 1
        assert pick.pick_num == 2
        assert pick.pick == "Lightning Bolt"
        assert [c.name for c in pick.pack] == ["Lightning Bolt", "Counterspell"]
        # the draft environment is not attached to individual cards
        assert all(c.set_code is None for c in pick.pack)

    def test_draft_link_roundtrips(self, monkeypatch: pytest.MonkeyPatch):
        url = "https://www.17lands.com/draft/abc123/1/2"
        fake_data = {
            "expansion": "TLA",
            "num_seats": 8,
            "picks": [{
                "pack_number": 0, "pick_number": 1,
                "pick": {"name": "X", "image_url": ""},
                "available": [{"name": "X", "image_url": ""}],
            }],
        }

        class _FakeResp:
            def json(self):
                return fake_data

        monkeypatch.setattr(sp.requests, "get", lambda url: _FakeResp())
        pick = fetch_draft_pick(url)
        assert pick.draft_link() == url
