import datetime as dt
from dataclasses import dataclass


@dataclass
class DEqConfig:
    start_date: dt.date
    end_date: dt.date | None = None
    is_pick_two: bool = False
    cube: bool = False


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

# Per-set configuration for DEq daily calculations
# TEMPORARY (spells 0.14.0 migration verification): everything but MSH is
# commented out. Add sets back one at a time once things look good.
config = {
    "MSH": DEqConfig(start_date=dt.date(2026, 6, 23)),
    "SOS": DEqConfig(start_date=dt.date(2026, 4, 21), end_date=dt.date(2026, 6, 23)),
    "TMT": DEqConfig(start_date=dt.date(2026, 3, 3), end_date=dt.date(2026, 4, 21)),
    "ECL": DEqConfig(start_date=dt.date(2026, 1, 20), end_date=dt.date(2026, 3, 2)),
    "TLA": DEqConfig(start_date=dt.date(2025, 11, 18), end_date=dt.date(2026, 6, 9)),
    "Cube+-+Powered": DEqConfig(
        start_date=dt.date(2025, 10, 28), end_date=dt.date(2026, 6, 23), cube=True
    ),
    "EOE": DEqConfig(start_date=dt.date(2025, 7, 29), end_date=dt.date(2025, 9, 23)), # scheduled w/o 7/28/26
    "FIN": DEqConfig(start_date=dt.date(2025, 6, 10), end_date=dt.date(2026, 6, 23)),
    "TDM": DEqConfig(start_date=dt.date(2025, 4, 8), end_date=dt.date(2025, 10, 28)),
    "DFT": DEqConfig(start_date=dt.date(2025, 2, 11), end_date=dt.date(2026, 7, 21)),
    "PIO": DEqConfig(start_date=dt.date(2024, 12, 10), end_date=dt.date(2025, 2, 11)),
    "FDN": DEqConfig(start_date=dt.date(2024, 11, 12), end_date=dt.date(2024, 12, 10)),
    "DSK": DEqConfig(start_date=dt.date(2024, 9, 24), end_date=dt.date(2026, 7, 28)),
    "BLB": DEqConfig(start_date=dt.date(2024, 7, 30), end_date=dt.date(2026, 7, 2)),
    "MH3": DEqConfig(start_date=dt.date(2024, 6, 11), end_date=dt.date(2025, 10, 21)),
    "OTJ": DEqConfig(start_date=dt.date(2024, 4, 16), end_date=dt.date(2025, 11, 4)),
    "MKM": DEqConfig(start_date=dt.date(2024, 2, 6), end_date=dt.date(2024, 4, 16)),
    # "LCI": DEqConfig(start_date=dt.date(2023, 11, 14), end_date=dt.date(2024, 2, 6)),
    # "WOE": DEqConfig(start_date=dt.date(2023, 9, 5), end_date=dt.date(2025, 9, 23)),
    # "LTR": DEqConfig(start_date=dt.date(2023, 6, 20), end_date=dt.date(2023, 9, 5)),
    # "MOM": DEqConfig(start_date=dt.date(2023, 4, 18), end_date=dt.date(2023, 6, 20)),
}
