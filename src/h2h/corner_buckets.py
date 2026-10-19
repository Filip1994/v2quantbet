"""Operator-selected Corner cubes, shared by Research and Operations.

Ranges are lower-inclusive/upper-exclusive, exactly as displayed by the
Research cube. This is an explicit seven-bucket selection, not auto-promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode


@dataclass(frozen=True)
class CornerBucket:
    bucket_id: str
    selection: str
    odds: tuple[str, str]
    probability: tuple[str, str]
    ev: tuple[str, str]
    gap: tuple[str, str]

    @property
    def label(self):
        return (f'Corner {self.selection} · odds {"–".join(self.odds)} · '
                f'P {"–".join(self.probability)} · EV {"–".join(self.ev)} · gap {"–".join(self.gap)}')

    @property
    def analytics_path(self):
        return '/research/analytics/corners?' + urlencode({'bucket_id': self.bucket_id}) + '#operations-corner-buckets'

    def matches(self, row):
        if str(row.get('market_key') or row.get('market') or '').upper() != 'TOTAL_CORNERS':
            return False
        if str(row.get('selection') or '').upper() != self.selection:
            return False
        try:
            # Always derive the gap from frozen source features when available.
            gap = (Decimal(str(row['expected_total_corners'])) - Decimal(str(row['line']))
                   if row.get('expected_total_corners') is not None and row.get('line') is not None
                   else Decimal(str(row['line_gap'])))
            values = (Decimal(str(row['odds'])), Decimal(str(row['model_probability'])),
                      Decimal(str(row['expected_value'])), gap)
            return all(v.is_finite() and Decimal(low) <= v < Decimal(high)
                       for v,(low,high) in zip(values,(self.odds,self.probability,self.ev,self.gap),strict=True))
        except (KeyError, InvalidOperation, TypeError, ValueError):
            return False


CORNER_OPERATIONS_BUCKETS = (
    CornerBucket('CORNER_CUBE_OVER_O150_175_P65_70_EV10_15_G1_2', 'OVER', ('1.5','1.75'),('.65','.70'),('.10','.15'),('1','2')),
    CornerBucket('CORNER_CUBE_UNDER_O175_200_P55_60_EV00_05_GM1_0', 'UNDER', ('1.75','2'),('.55','.60'),('0','.05'),('-1','0')),
    CornerBucket('CORNER_CUBE_OVER_O200_225_P50_55_EV10_15_G0_1', 'OVER', ('2','2.25'),('.50','.55'),('.10','.15'),('0','1')),
    CornerBucket('CORNER_CUBE_OVER_O200_225_P55_60_EV15_20_G0_1', 'OVER', ('2','2.25'),('.55','.60'),('.15','.20'),('0','1')),
    CornerBucket('CORNER_CUBE_OVER_O200_225_P50_55_EV00_05_G0_1', 'OVER', ('2','2.25'),('.50','.55'),('0','.05'),('0','1')),
    CornerBucket('CORNER_CUBE_OVER_O175_200_P55_60_EV05_10_G0_1', 'OVER', ('1.75','2'),('.55','.60'),('.05','.10'),('0','1')),
    CornerBucket('CORNER_CUBE_OVER_O200_225_P50_55_EV05_10_G0_1', 'OVER', ('2','2.25'),('.50','.55'),('.05','.10'),('0','1')),
)
CORNER_OPERATIONS_IDS = tuple(b.bucket_id for b in CORNER_OPERATIONS_BUCKETS)
CORNER_BUCKET_BY_ID = {b.bucket_id:b for b in CORNER_OPERATIONS_BUCKETS}


def corner_bucket_matches(row, bucket_id):
    return CORNER_BUCKET_BY_ID[bucket_id].matches(row)
