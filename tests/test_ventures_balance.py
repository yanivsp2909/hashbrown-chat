"""⚖️ The balance simulation (chatserver/ventures_balance.py): 20 seasons of 20 bot companies (4 kinds of players,
all 5 sectors) for a whole season (SEASON_TICKS game days), with the real formulas and the formula investor. Is the game fair, and does the token
economy stay sane? Run `python3 -m chatserver.ventures_balance` to see the numbers."""
import pytest

from chatserver import config, ventures_balance


@pytest.fixture(scope="module")
def result():
    return ventures_balance.summary(seeds=20, companies=20)   # (a whole season: SEASON_TICKS game days)


def test_some_companies_die(result):
    assert 0.20 <= result["death_rate"] <= 0.50


def test_at_least_half_raise_a_seed_round(result):
    assert result["seed_rate"] >= 0.50


def test_about_one_ipo_a_season(result):
    assert 0.5 <= result["ipos_per_season"] <= 1.5


def test_nobody_gets_infinite_money(result):
    assert result["max_cash"] < 5_000_000_000


def test_exits_stay_under_the_season_cap(result):
    # what the busiest season would need in NEW tokens (before the cap clamps it) fits under the cap
    assert result["mint_need_max"] <= config.VENTURES_MINT_SEASON_CAP
    assert result["waiting_max"] == 0


def test_careful_players_do_better_than_reckless_or_idle_ones(result):
    def ended(strategy, outcome):
        return sum(r["by_strategy"][strategy].count(outcome) for r in result["runs"])
    assert ended("careful", "dead") < ended("hirer", "dead")
    assert ended("careful", "public") >= ended("idle", "public")
    assert ended("idle", "dead") > ended("careful", "dead")


def test_the_report_prints():
    assert "IPOs per season" in ventures_balance.report()


def test_every_kind_of_exit_happens(result):
    assert result["acquisitions_per_season"] > 0
    assert result["paid_ipo"] > 0 and result["paid_buys"] > 0 and result["paid_season_end"] > 0
