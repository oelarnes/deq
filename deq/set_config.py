import datetime as dt
from dataclasses import dataclass


@dataclass
class Run:
    start_date: dt.date
    end_date: dt.date | None = None


@dataclass
class DEqConfig:
    runs: list[Run]
    is_pick_two: bool = False
    cube: bool = False
    # date the Contender Draft queue opens, if it does. 17lands' combined
    # Premier+Contender event type isn't queryable before this date, so it
    # must be a real (possibly future, pre-configured) date, not a blanket
    # flag. Once combined data exists it's a property of the set, not any
    # one run.
    contender_start: dt.date | None = None


def current_run(cfg: DEqConfig, as_of: dt.date) -> Run:
    """The run governing `as_of`: the most recently started run, or the
    earliest configured run if none have started yet, so a run defined ahead
    of time stays inert until its own start_date arrives."""
    started = [run for run in cfg.runs if run.start_date <= as_of]
    return max(started, key=lambda run: run.start_date) if started else cfg.runs[0]


def launch_date(cfg: DEqConfig) -> dt.date:
    """When the set first launched, regardless of any later runs.

    Used to rank/filter sets by how recently they debuted, so a set
    temporarily reactivated for a later run (e.g. a bring-back event) doesn't
    read as newer than sets that actually launched more recently.
    """
    return min(run.start_date for run in cfg.runs)


def is_contender(cfg: DEqConfig, as_of: dt.date) -> bool:
    """Whether 17lands' combined Premier+Contender event type is queryable as
    of `as_of`. The Contender Draft queue can open partway through a set's
    run, so this must be a real date check, not a blanket flag."""
    return cfg.contender_start is not None and as_of >= cfg.contender_start


# Sets included in the p1 strategy analysis (requires full public parquet data)
p1_sets = [
    "SOS",
    "EOE",
    "FIN",
    "TDM",
    "DFT",
    "PIO",
    "FDN",
    "DSK",
    "BLB",
    "MH3",
    "OTJ",
    "MKM",
    "KTK",
    "LCI",
    "WOE",
    "LTR",
    "MOM",
    "SIR",
    "ONE",
    "BRO",
    "DMU",
    "SNC",
    "NEO",
]

config = {
    "FRA": DEqConfig(
        runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 9))],
        contender_start=dt.date(2026, 10, 13),
    ),
    "HOB": DEqConfig(
        runs=[Run(dt.date(2026, 8, 11), dt.date(2026, 9, 29))],
        contender_start=dt.date(2026, 8, 11),
    ),
    "MSH": DEqConfig(runs=[Run(dt.date(2026, 6, 23), dt.date(2026, 8, 11))]),
    "SOS": DEqConfig(
        runs=[Run(dt.date(2026, 4, 21), dt.date(2026, 6, 23))],
        contender_start=dt.date(2026, 4, 21),
    ),
    "TMT": DEqConfig(runs=[Run(dt.date(2026, 3, 3), dt.date(2026, 4, 21))]),
    "ECL": DEqConfig(runs=[Run(dt.date(2026, 1, 20), dt.date(2026, 3, 2))]),
    "TLA": DEqConfig(runs=[Run(dt.date(2025, 11, 18), dt.date(2026, 6, 9))]),
    "Cube+-+Powered": DEqConfig(
        runs=[
            Run(dt.date(2025, 10, 28), dt.date(2026, 9, 28)),
            Run(dt.date(2026, 10, 20), dt.date(2026, 11, 9)),
        ],
        cube=True,
    ),
    "EOE": DEqConfig(runs=[Run(dt.date(2025, 7, 29), dt.date(2026, 8, 4))]),
    "FIN": DEqConfig(runs=[Run(dt.date(2025, 6, 10), dt.date(2026, 6, 23))]),
    "TDM": DEqConfig(runs=[Run(dt.date(2025, 4, 8), dt.date(2025, 10, 28))]),
    "DFT": DEqConfig(runs=[Run(dt.date(2025, 2, 11), dt.date(2026, 7, 21))]),
    "PIO": DEqConfig(runs=[Run(dt.date(2024, 12, 10), dt.date(2025, 2, 11))]),
    "FDN": DEqConfig(runs=[Run(dt.date(2024, 11, 12), dt.date(2024, 12, 10))]),
    "DSK": DEqConfig(runs=[Run(dt.date(2024, 9, 24), dt.date(2026, 7, 28))]),
    "BLB": DEqConfig(runs=[Run(dt.date(2024, 7, 30), dt.date(2026, 7, 2))]),
    "MH3": DEqConfig(runs=[Run(dt.date(2024, 6, 11), dt.date(2026, 9, 15))]),
    "OTJ": DEqConfig(
        runs=[
            Run(dt.date(2024, 4, 16), dt.date(2025, 11, 4)),
            Run(dt.date(2026, 9, 22), dt.date(2026, 9, 29)),
        ]
    ),
    "MKM": DEqConfig(runs=[Run(dt.date(2024, 2, 6), dt.date(2024, 4, 16))]),
    "LCI": DEqConfig(runs=[Run(dt.date(2023, 11, 14), dt.date(2024, 2, 6))]),
    "WOE": DEqConfig(runs=[Run(dt.date(2023, 9, 5), dt.date(2025, 9, 23))]),
    "LTR": DEqConfig(runs=[Run(dt.date(2023, 6, 20), dt.date(2023, 9, 5))]),
    "MOM": DEqConfig(runs=[Run(dt.date(2023, 4, 18), dt.date(2023, 6, 20))]),
    "ONE": DEqConfig(runs=[Run(dt.date(2023, 2, 7), dt.date(2023, 4, 18))]),
    "BRO": DEqConfig(runs=[Run(dt.date(2022, 11, 15), dt.date(2024, 7, 23))]),
    "DMU": DEqConfig(runs=[Run(dt.date(2022, 9, 1), dt.date(2026, 9, 22))]),
}
