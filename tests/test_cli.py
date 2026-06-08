"""Tests for deq CLI: _normalize_to_url, _parse_ref, and main()."""

from __future__ import annotations

import pytest

import deq.cli as cli_mod
import deq.sample_pack as sp
from deq.cli import _normalize_to_url, _parse_ref, main
from deq.sample_pack import DraftCard, DraftState

_DRAFT_ID = "9b74b1a5ea8349039dc532964dc89c91"
_BASE = f"https://www.17lands.com/draft/{_DRAFT_ID}"


class TestNormalizeToUrl:
    def test_full_url_passthrough(self):
        url = f"{_BASE}/1/2"
        assert _normalize_to_url(url, pack=1, pick=1) == url

    def test_draft_id_slash_pack_slash_pick(self):
        assert _normalize_to_url(f"{_DRAFT_ID}/2/3", pack=1, pick=1) == f"{_BASE}/2/3"

    def test_bare_draft_id_uses_pack_pick_args(self):
        assert _normalize_to_url(_DRAFT_ID, pack=2, pick=3) == f"{_BASE}/2/3"

    def test_bare_draft_id_defaults(self):
        assert _normalize_to_url(_DRAFT_ID, pack=1, pick=1) == f"{_BASE}/1/1"


class TestParseRef:
    def test_set_code_detected(self):
        assert _parse_ref("SOS", 1, 1) == {"kind": "set", "set_code": "SOS"}

    def test_set_code_with_digit(self):
        assert _parse_ref("OM1", 1, 1) == {"kind": "set", "set_code": "OM1"}

    def test_set_code_case_insensitive(self):
        assert _parse_ref("sos", 1, 1) == {"kind": "set", "set_code": "SOS"}

    def test_alias_maps_to_real_code(self):
        assert _parse_ref("PCube", 1, 1) == {"kind": "set", "set_code": "Cube+-+Powered"}

    def test_alias_case_insensitive(self):
        assert _parse_ref("pcube", 1, 1) == {"kind": "set", "set_code": "Cube+-+Powered"}

    def test_full_real_code(self):
        assert _parse_ref("Cube+-+Powered", 1, 1) == {"kind": "set", "set_code": "Cube+-+Powered"}

    def test_unknown_short_code_errors(self):
        with pytest.raises(SystemExit):
            _parse_ref("ZZZ", 1, 1)

    def test_unknown_six_char_code_errors(self):
        with pytest.raises(SystemExit):
            _parse_ref("ABCDEF", 1, 1)

    def test_full_url_is_pick(self):
        ref = _parse_ref(f"{_BASE}/1/2", 1, 1)
        assert ref["kind"] == "pick"
        assert ref["url"] == f"{_BASE}/1/2"

    def test_draft_id_is_pick(self):
        ref = _parse_ref(_DRAFT_ID, 2, 3)
        assert ref["kind"] == "pick"
        assert ref["url"] == f"{_BASE}/2/3"


class TestMain:
    @pytest.fixture(autouse=True)
    def _mock_fetch(self, monkeypatch: pytest.MonkeyPatch):
        pick = DraftState(
            set_code="TLA",
            draft_id=_DRAFT_ID,
            pack_num=1,
            pick_num=2,
            pick="Lightning Bolt",
            pack=[
                DraftCard(name="Lightning Bolt"),
                DraftCard(name="Counterspell"),
            ],
        )
        monkeypatch.setattr(cli_mod, "fetch_draft_pick", lambda url: pick)

    def test_set_code_outputs_set_url(self, capsys):
        main(["link", "SOS"])
        out = capsys.readouterr().out.strip()
        assert out == "https://magic-flea.com/on-draft/deq.html?set=SOS"

    def test_alias_outputs_real_code_in_url(self, capsys):
        main(["link", "PCube"])
        out = capsys.readouterr().out.strip()
        assert out == "https://magic-flea.com/on-draft/deq.html?set=Cube%2B-%2BPowered"

    def test_set_code_with_card_flag(self, capsys):
        main(["link", "SOS", "--card", "Lightning Bolt"])
        out = capsys.readouterr().out.strip()
        assert "set=SOS" in out
        assert "card=Lightning+Bolt" in out

    def test_pick_ref_outputs_pack_url(self, capsys):
        main(["link", f"{_BASE}/1/2"])
        out = capsys.readouterr().out.strip()
        assert out.startswith("https://magic-flea.com/on-draft/deq.html?")
        assert "set=TLA" in out
        assert "card=" not in out

    def test_card_flag_adds_card_param(self, capsys):
        main(["link", f"{_BASE}/1/2", "--card", "Lightning Bolt"])
        out = capsys.readouterr().out.strip()
        assert "card=Lightning+Bolt" in out

    def test_base_url_override(self, capsys):
        main(["link", f"{_BASE}/1/2", "--base-url", "http://localhost:8080/deq.html"])
        out = capsys.readouterr().out.strip()
        assert out.startswith("http://localhost:8080/deq.html?")

    def test_color_flag_prepended_to_q(self, capsys):
        main(["link", f"{_BASE}/1/2", "-c", "wb*"])
        out = capsys.readouterr().out.strip()
        assert "c%3Awb" in out  # c:wb encoded in q=

    def test_rarity_flag_prepended_to_q(self, capsys):
        main(["link", f"{_BASE}/1/2", "-r", "common"])
        out = capsys.readouterr().out.strip()
        assert "r%3Acommon" in out  # r:common encoded in q=

    def test_set_with_color_filter(self, capsys):
        main(["link", "SOS", "-c", "u/r"])
        out = capsys.readouterr().out.strip()
        assert "set=SOS" in out
        assert "q=c%3Au%2Fr" in out  # c:u/r encoded

    def test_set_with_rarity_filter(self, capsys):
        main(["link", "SOS", "-r", "common"])
        out = capsys.readouterr().out.strip()
        assert "set=SOS" in out
        assert "r%3Acommon" in out

    def test_set_no_filter_has_no_q(self, capsys):
        main(["link", "SOS"])
        out = capsys.readouterr().out.strip()
        assert "q=" not in out

    def test_bare_asc_defaults_sort_to_deq(self, capsys):
        main(["link", "SOS", "--asc"])
        out = capsys.readouterr().out.strip()
        assert "sort=deq%3Aasc" in out

    def test_sort_desc_default(self, capsys):
        main(["link", "SOS", "--sort", "adj"])
        out = capsys.readouterr().out.strip()
        assert "sort=adj%3Adesc" in out

    def test_sort_asc_flag(self, capsys):
        main(["link", "SOS", "--sort", "adj", "--asc"])
        out = capsys.readouterr().out.strip()
        assert "sort=adj%3Aasc" in out

    def test_no_sort_has_no_sort_param(self, capsys):
        main(["link", "SOS"])
        out = capsys.readouterr().out.strip()
        assert "sort=" not in out

    def test_k_adds_k_param(self, capsys):
        main(["link", "SOS", "-k", "2"])
        out = capsys.readouterr().out.strip()
        assert "k=2" in out

    def test_k_on_pack(self, capsys):
        main(["link", f"{_BASE}/1/2", "-k", "1"])
        out = capsys.readouterr().out.strip()
        assert "k=1" in out
