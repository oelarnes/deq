"""Tests for how the site build handles a set it can't compute."""

from __future__ import annotations

import datetime as dt
import json
import shutil
from pathlib import Path

import polars as pl
import pytest

from spells import TimePeriod

from deq import site
from deq.main import DeqData

TEMPLATE = Path(__file__).parent.parent / "deq_site_template.html"


def fake_deq_data(code: str, n_cards: int = 10) -> DeqData:
    df = pl.DataFrame(
        {
            "deq_grade": ["B"] * n_cards,
            "name": [f"Card {i}" for i in range(n_cards)],
            "color": ["W"] * n_cards,
            "rarity": ["common"] * n_cards,
            "deq": [0.001 * i for i in range(n_cards)],
            "mwr": [0.01] * n_cards,
            "pick_equity": [0.01] * n_cards,
            "deq_bias_adj": [0.0] * n_cards,
            "deq_meta_adj": [0.0] * n_cards,
            "npr": [0.0] * n_cards,
            "pct_top": [0.5] * n_cards,
            "pct_gp": [0.5] * n_cards,
            "image_url": [""] * n_cards,
        }
    )
    return DeqData(
        df=df,
        set_code=code,
        time_period=TimePeriod.ALL_EXCEPT_FIRST_WEEK,
        start_date=dt.date(2026, 10, 6),
        end_date=dt.date(2026, 11, 10),
    )


@pytest.fixture
def site_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A build in tmp_path, with FRA and TRK available and nothing published."""
    monkeypatch.chdir(tmp_path)
    shutil.copy(TEMPLATE, tmp_path / TEMPLATE.name)
    (tmp_path / "docs" / "_build" / "html" / "_static").mkdir(parents=True)
    (tmp_path / "docs" / "_static").mkdir()

    published = tmp_path / "published"
    published.mkdir()
    monkeypatch.setattr(site, "PUBLISHED_DATA_DIR", published)
    monkeypatch.setattr(site, "available_sets", lambda: ["TRK", "FRA"])
    monkeypatch.setattr(site, "current_set", lambda: "TRK")
    return tmp_path


def failing_for(*codes: str):
    def fake_deq(code):
        if code in codes:
            raise ValueError(f"Empty card ratings response for {code}")
        return fake_deq_data(code)

    return fake_deq


def built_sets(root: Path) -> set[str]:
    return {p.stem for p in (root / "docs" / "_build" / "html" / "data").glob("*.json")}


def test_a_set_without_data_is_left_off_and_the_next_becomes_default(
    site_env, monkeypatch
):
    monkeypatch.setattr(site, "deq", failing_for("TRK"))
    site.main()

    assert built_sets(site_env) == {"FRA"}
    html = (site_env / "docs" / "_build" / "html" / "deq.html").read_text()
    assert '<option value="FRA" selected>' in html
    assert 'value="TRK"' not in html


def test_a_failing_set_keeps_its_published_data(site_env, monkeypatch):
    published = site.set_payload(fake_deq_data("TRK"))
    (site.PUBLISHED_DATA_DIR / "TRK.json").write_text(json.dumps(published))
    monkeypatch.setattr(site, "deq", failing_for("TRK"))
    site.main()

    assert built_sets(site_env) == {"FRA", "TRK"}
    kept = json.loads(
        (site_env / "docs" / "_build" / "html" / "data" / "TRK.json").read_text()
    )
    assert kept == published


def test_the_build_fails_when_no_set_can_be_published(site_env, monkeypatch):
    monkeypatch.setattr(site, "deq", failing_for("TRK", "FRA"))
    with pytest.raises(RuntimeError):
        site.main()


def test_a_large_drop_in_rated_cards_from_the_published_data_is_rejected(site_env):
    published = site.set_payload(fake_deq_data("FRA", n_cards=10))
    (site.PUBLISHED_DATA_DIR / "FRA.json").write_text(json.dumps(published))

    with pytest.raises(ValueError, match="rated cards dropped"):
        site.sanity_check(fake_deq_data("FRA", n_cards=5))
