"""Exact subject matching for known nested sources; no network or writes."""
import unittest

from api.intelligence.ticker_facts import _extract_for_ticker


class TickerFactsNestedSourcesTests(unittest.TestCase):
    def test_group_structures_plural(self):
        row = {'ticker': '000270', 'name': '기아', 'parent': '현대차'}
        self.assertEqual(_extract_for_ticker({'structures': {'000270': row}}, '000270'), row)
        self.assertIsNone(_extract_for_ticker({'structures': {'000270': row}}, '005930'))

    def test_all_three_perspectives_preserve_context_not_bucket_totals(self):
        row = {'ticker': '000270', 'name': '기아', 'revenue': 114140919000000}
        bucket = {'key': 'steady', 'label': '매출 꾸준', 'desc': '관측 분류',
                  'cap_sum': 779747649, 'leaders': [row, {'ticker': '005930'}]}
        doc = {'desire': {'tiers': [bucket]}, 'cycle': {'buckets': [bucket]},
               'buyback': {'buckets': [bucket]}}
        result = _extract_for_ticker(doc, '000270')
        self.assertEqual([r['perspective'] for r in result], ['desire', 'cycle', 'buyback'])
        for r in result:
            self.assertEqual(r['record'], row)
            self.assertEqual(r['bucket'], {'key': 'steady', 'label': '매출 꾸준', 'desc': '관측 분류'})
        self.assertIsNone(_extract_for_ticker(doc, '00027'))

    def test_malformed_nested_containers_are_ignored(self):
        docs = [{'desire': None}, {'desire': {'tiers': {}}},
                {'cycle': {'buckets': [None, {'leaders': None}, {'leaders': {}}]}},
                {'buyback': {'buckets': [{'leaders': [None, {}, {'ticker': None}]}]}}]
        for doc in docs:
            with self.subTest(doc=doc):
                self.assertIsNone(_extract_for_ticker(doc, '000270'))

    def test_etf_constituent_does_not_inherit_fund_flows(self):
        doc = {'etfs': [{'ticker': '102110', 'flow': 999,
                         'holdings': [{'t': '000270', 'weight': 2.75}]}]}
        self.assertIsNone(_extract_for_ticker(doc, '000270'))

    def test_receipt_substring_and_arbitrary_mentions_are_not_subjects(self):
        doc = {'feed': [{'ticker': '123456', 'receipt': '20261008000270'}],
               'notes': {'leaders': [{'ticker': '000270'}]}}
        self.assertIsNone(_extract_for_ticker(doc, '000270'))

    def test_existing_map_and_list_contract_unchanged(self):
        row = {'ticker': '000270', 'value': 1}
        for doc in [{'stocks': {'000270': row}}, {'000270': row},
                    {'structure': {'000270': row}}, {'by_ticker': {'000270': row}}]:
            self.assertEqual(_extract_for_ticker(doc, '000270'), row)
        for doc in [[row], {'stocks': [row]}]:
            self.assertEqual(_extract_for_ticker(doc, '000270'), [row])


if __name__ == '__main__':
    unittest.main()
