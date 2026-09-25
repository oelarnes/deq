import datetime as dt
from dataclasses import dataclass


@dataclass
class Run:
    start_date: dt.date
    # the changeover day: the next set's launch, or the day after the last day of play
    end_date: dt.date | None = None


@dataclass
class DEqConfig:
    runs: list[Run]
    is_pick_two: bool = False
    cube: bool = False
    # 17lands only serves the combined Premier+Contender event type from here on
    contender_start: dt.date | None = None


def current_run(cfg: DEqConfig, as_of: dt.date) -> Run:
    """The run in effect on `as_of`: the latest one started, or the first if none has."""
    started = [run for run in cfg.runs if run.start_date <= as_of]
    return max(started, key=lambda run: run.start_date) if started else cfg.runs[0]


def launch_date(cfg: DEqConfig) -> dt.date:
    """When the set first launched; a later run doesn't make a set newer."""
    return min(run.start_date for run in cfg.runs)


def is_contender(cfg: DEqConfig, as_of: dt.date) -> bool:
    """Whether 17lands has combined Premier+Contender data as of `as_of`, a day behind play."""
    return cfg.contender_start is not None and as_of > cfg.contender_start


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
        runs=[Run(dt.date(2026, 9, 29), dt.date(2026, 11, 10))],
        contender_start=dt.date(2026, 10, 13),
    ),
    "HOB": DEqConfig(
        runs=[Run(dt.date(2026, 8, 11), dt.date(2026, 9, 29))],
        contender_start=dt.date(2026, 8, 24),
    ),
    # contender_start (7/7) waits on a 17lands backfill of MSH's combined data
    "MSH": DEqConfig(runs=[Run(dt.date(2026, 6, 23), dt.date(2026, 8, 11))]),
    "SOS": DEqConfig(
        runs=[Run(dt.date(2026, 4, 21), dt.date(2026, 6, 23))],
        contender_start=dt.date(2026, 5, 22),
    ),
    "TMT": DEqConfig(runs=[Run(dt.date(2026, 3, 3), dt.date(2026, 4, 21))]),
    "ECL": DEqConfig(runs=[Run(dt.date(2026, 1, 20), dt.date(2026, 3, 2))]),
    "TLA": DEqConfig(
        runs=[
            Run(dt.date(2025, 11, 18), dt.date(2026, 1, 20)),
            Run(dt.date(2026, 6, 2), dt.date(2026, 6, 9)),
        ]
    ),
    "Cube+-+Powered": DEqConfig(
        runs=[
            Run(dt.date(2025, 10, 28), dt.date(2025, 11, 18)),
            Run(dt.date(2026, 6, 2), dt.date(2026, 6, 23)),
            Run(dt.date(2026, 9, 8), dt.date(2026, 9, 29)),
            Run(dt.date(2026, 10, 20), dt.date(2026, 11, 10)),
        ],
        cube=True,
    ),
    "EOE": DEqConfig(
        runs=[
            Run(dt.date(2025, 7, 29), dt.date(2025, 9, 23)),
            Run(dt.date(2026, 7, 28), dt.date(2026, 8, 4)),
        ]
    ),
    "FIN": DEqConfig(
        runs=[
            Run(dt.date(2025, 6, 10), dt.date(2025, 7, 29)),
            Run(dt.date(2026, 6, 16), dt.date(2026, 6, 23)),
        ]
    ),
    "TDM": DEqConfig(runs=[Run(dt.date(2025, 4, 8), dt.date(2025, 10, 28))]),
    "DFT": DEqConfig(
        runs=[
            Run(dt.date(2025, 2, 11), dt.date(2025, 4, 8)),
            Run(dt.date(2026, 7, 14), dt.date(2026, 7, 21)),
        ]
    ),
    "PIO": DEqConfig(
        runs=[
            Run(dt.date(2024, 12, 10), dt.date(2025, 2, 11)),
            Run(dt.date(2026, 11, 3), dt.date(2026, 11, 11)),
        ]
    ),
    "FDN": DEqConfig(runs=[Run(dt.date(2024, 11, 12), dt.date(2024, 12, 10))]),
    "DSK": DEqConfig(
        runs=[
            Run(dt.date(2024, 9, 24), dt.date(2024, 11, 12)),
            Run(dt.date(2026, 7, 21), dt.date(2026, 7, 28)),
        ]
    ),
    "BLB": DEqConfig(
        runs=[
            Run(dt.date(2024, 7, 30), dt.date(2024, 9, 24)),
            Run(dt.date(2026, 6, 23), dt.date(2026, 7, 2)),
        ]
    ),
    "MH3": DEqConfig(
        runs=[
            Run(dt.date(2024, 6, 11), dt.date(2024, 7, 30)),
            Run(dt.date(2026, 9, 8), dt.date(2026, 9, 16)),
        ]
    ),
    "OTJ": DEqConfig(
        runs=[
            Run(dt.date(2024, 4, 16), dt.date(2025, 11, 4)),
            Run(dt.date(2026, 9, 22), dt.date(2026, 9, 29)),
        ]
    ),
    "MKM": DEqConfig(runs=[Run(dt.date(2024, 2, 6), dt.date(2024, 4, 16))]),
    "LCI": DEqConfig(runs=[Run(dt.date(2023, 11, 14), dt.date(2024, 2, 6))]),
    "WOE": DEqConfig(runs=[Run(dt.date(2023, 9, 5), dt.date(2025, 9, 23))]),
    "LTR": DEqConfig(
        runs=[
            Run(dt.date(2023, 6, 20), dt.date(2023, 9, 5)),
            Run(dt.date(2026, 8, 25), dt.date(2026, 9, 8)),
        ]
    ),
    "MOM": DEqConfig(runs=[Run(dt.date(2023, 4, 18), dt.date(2023, 6, 20))]),
    "ONE": DEqConfig(runs=[Run(dt.date(2023, 2, 7), dt.date(2023, 4, 18))]),
    "BRO": DEqConfig(runs=[Run(dt.date(2022, 11, 15), dt.date(2024, 7, 23))]),
    "DMU": DEqConfig(
        runs=[
            Run(dt.date(2022, 9, 1), dt.date(2022, 11, 15)),
            Run(dt.date(2026, 9, 16), dt.date(2026, 9, 22)),
        ]
    ),
}
