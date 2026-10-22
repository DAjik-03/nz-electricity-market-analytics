import sys
import gzip
import unittest
from pathlib import Path
from decimal import Decimal

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from historical.daily_final import parse_prices,compare_populations,constituent_identity,build_aggregate,HEADER


def payload(rows):
    return (','.join(HEADER)+'\n'+'\n'.join(','.join(map(str,r)) for r in rows)+'\n').encode()


class DailyFinalTests(unittest.TestCase):
    def test_aggregate_roundtrip_and_constituent_revision(self):
        values={('2025-12-01',2,'X'):Decimal('2.00'),('2025-12-01',1,'X'):Decimal('-1.25')}
        source=dict(trading_date='2025-12-01',filename='a.csv',source_url='https://official/a',sha256='a'*64,price_status='final')
        identity,artifact=build_aggregate(values,[source])
        self.assertEqual(parse_prices(gzip.decompress(artifact)),values)
        self.assertEqual((identity,artifact),build_aggregate(dict(reversed(list(values.items()))),[source]))
        revised_id,revised_bytes=build_aggregate(values,[dict(source,sha256='b'*64)])
        self.assertNotEqual(identity,revised_id)
        self.assertNotEqual(artifact,revised_bytes)
        self.assertEqual(gzip.decompress(artifact),gzip.decompress(revised_bytes))

    def test_daily_calendar_accepts_real_dst_lengths(self):
        for day,count in [('2025-09-28',46),('2026-04-05',50)]:
            raw=payload([(day,p,'X','1') for p in range(1,count+1)])
            self.assertEqual(len(parse_prices(raw,day,expected_month=day[:7],require_complete=True)),count)

    def test_complete_daily_schema_and_keys(self):
        rows=[('2025-12-01',p,'ABC0111','12.34') for p in range(1,49)]
        parsed=parse_prices(payload(rows),'2025-12-01',require_complete=True)
        self.assertEqual(len(parsed),48)
        self.assertEqual(parsed[('2025-12-01',1,'ABC0111')],Decimal('12.34'))

    def test_schema_drift_rejected(self):
        with self.assertRaisesRegex(ValueError,'schema'):
            parse_prices(b'Date,TP,POC,Price\n2025-12-01,1,X,2\n')

    def test_wrong_daily_date_rejected(self):
        with self.assertRaisesRegex(ValueError,'stated daily date'):
            parse_prices(payload([('2025-12-02',1,'X',2)]),'2025-12-01')

    def test_duplicate_key_rejected(self):
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            parse_prices(payload([('2025-12-01',1,'X',2)]*2))

    def test_invalid_tp_and_missing_period_rejected(self):
        with self.assertRaisesRegex(ValueError,'calendar'):
            parse_prices(payload([('2025-12-01',49,'X',2)]))
        with self.assertRaisesRegex(ValueError,'Missing expected'):
            parse_prices(payload([('2025-12-01',1,'X',2)]),'2025-12-01',require_complete=True)

    def test_overlap_comparison_uses_exact_decimal(self):
        key=('2025-12-01',1,'X')
        equal=compare_populations({key:Decimal('1.00')},{key:Decimal('1')})
        self.assertEqual(equal['mismatching_overlap_values'],0)
        conflict=compare_populations({key:Decimal('1.000000001')},{key:Decimal('1')})
        self.assertEqual(conflict['mismatching_overlap_values'],1)

    def test_difference_populations_reported(self):
        a={('2025-12-01',1,'A'):Decimal(1),('2025-12-02',1,'B'):Decimal(2)}
        b={('2025-12-01',1,'A'):Decimal(1)}
        r=compare_populations(a,b)
        self.assertEqual((r['overlap_keys'],r['only_daily']['key_count'],r['only_incomplete_monthly']['key_count']),(1,1,0))
        self.assertEqual(r['exclusively_daily_dates'],['2025-12-02'])
        self.assertEqual(r['exclusively_daily_pocs'],['B'])

    def test_identity_order_independent_and_content_sensitive(self):
        a=dict(trading_date='2025-12-01',filename='a.csv',source_url='https://official/a',sha256='a'*64,price_status='final')
        b=dict(a,trading_date='2025-12-02',filename='b.csv',sha256='b'*64)
        identity=constituent_identity([a,b])
        self.assertEqual(identity,constituent_identity([b,a]))
        self.assertNotEqual(identity,constituent_identity([a,dict(b,sha256='c'*64)]))
        with self.assertRaises(ValueError): constituent_identity([dict(a,price_status='interim')])


if __name__=='__main__': unittest.main()
