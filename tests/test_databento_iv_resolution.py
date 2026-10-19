"""No invented IV: retain timed observations or preserve unpriced quantity."""
import copy
import unittest
from datetime import datetime, timezone

from gex_terminal.adapters.databento import DatabentoAdapter
from gex_terminal.american_futures import american_futures_option_price
from gex_terminal.contracts import canonical_option_contract
from gex_terminal.market_data_adapter import validate_normalized_message
from tests.test_databento_regressions import adapter_for, definition, quote, trade, statistics


def priced_trade(**updates):
    result = trade(**updates)
    result.pop('iv', None)
    return result


class IVResolutionTests(unittest.IsolatedAsyncioTestCase):
    async def feed(self, adapter, *records):
        for record in records:
            await adapter._handle_live_record(record)

    async def test_no_observation_keeps_volume_without_configured_iv(self):
        adapter, consumer = adapter_for()
        await self.feed(adapter, definition(), quote(), priced_trade(price=99999, sequence=1))
        state = consumer.contract_state[('databento','101','trade_volume')]
        self.assertIsNone(state['iv'])
        self.assertEqual(state['iv_source'], 'unavailable')
        self.assertEqual(state['accumulated_volume'], 7)
        self.assertFalse(adapter._last_observed_ivs)
        provenance=state['iv_provenance']
        self.assertEqual(provenance['status'], 'outside_no_arbitrage_bounds')
        self.assertEqual(provenance['option_price'], 99999)
        self.assertEqual(provenance['underlying_price'], 6000)
        self.assertIn('lower_bound', provenance)
        result=await consumer.process_latest_snapshot(14)
        self.assertEqual(result['status'], 'no_data')
        self.assertEqual(result['pricing_coverage']['unpriced_quantity'], 7)
        await self.feed(adapter, priced_trade(sequence=2, ts_event='2026-08-06T16:00:00.5Z'))
        recovered=consumer.contract_state[('databento','101','trade_volume')]
        self.assertEqual(recovered['iv_source'], 'black_76_inverted')
        self.assertEqual(recovered['accumulated_volume'], 14)

    async def test_failed_premium_retains_only_the_earlier_observed_contract_iv(self):
        adapter, consumer=adapter_for()
        await self.feed(adapter,definition(),quote(),priced_trade(sequence=1))
        observed=copy.deepcopy(adapter._last_observed_ivs[101])
        await self.feed(adapter,priced_trade(price=99999, sequence=2, ts_event='2026-08-06T16:00:00.5Z'))
        state=consumer.contract_state[('databento','101','trade_volume')]
        self.assertEqual(state['iv_source'],'prior_valid')
        self.assertEqual(state['iv'],observed['iv'])
        self.assertEqual(state['accumulated_volume'],14)
        self.assertEqual(state['iv_provenance']['prior_iv_age_ms'],500)
        self.assertEqual(adapter._last_observed_ivs[101],observed)
        self.assertEqual(adapter.diagnostics()['model_inputs']['prior_valid_iv_ticks'],1)

    async def test_rejected_sequence_does_not_refresh_the_iv_observation_cache(self):
        adapter,consumer=adapter_for()
        await self.feed(adapter,definition(),quote(),trade(sequence=10))
        observed=copy.deepcopy(adapter._last_observed_ivs[101])
        await self.feed(adapter,trade(sequence=9,iv=.8,ts_event='2026-08-06T16:00:00.1Z'))
        self.assertEqual(adapter._last_observed_ivs[101],observed)
        await self.feed(adapter,priced_trade(price=99999,sequence=11,ts_event='2026-08-06T16:00:00.5Z'))
        state=consumer.contract_state[('databento','101','trade_volume')]
        self.assertEqual(state['iv'],.22)
        self.assertEqual(state['accumulated_volume'],14)

    def test_retention_rejects_future_stale_or_different_model_observations(self):
        metadata=DatabentoAdapter._normalize_definition_record(definition())
        previous={'iv':.22,'source':'black_76_inverted','event_time':'2026-08-06T15:59:59Z',
                  'pricing_model':'black_76','expiry_timestamp':metadata['expiry_timestamp'],'risk_free_rate':.045}
        for changes in ({'event_time':'2026-08-06T16:00:01Z'},
                        {'event_time':'2026-08-06T15:54:59Z'},
                        {'pricing_model':'american_futures_crr'}, {'source':'prior_valid'},
                        {'expiry_timestamp':'2026-08-21T20:00:00Z'}):
            with self.subTest(changes=changes):
                message=DatabentoAdapter._normalize_option_trade_record(priced_trade(price=99999),{101:metadata},
                    underlying_price=6000,underlying_event_time='2026-08-06T16:00:00Z',
                    previous_valid_iv={**previous,**changes})
                self.assertIsNone(message['iv'])
                self.assertEqual(message['iv_source'],'unavailable')
                validate_normalized_message(message)

    async def test_native_american_style_selects_american_inversion_and_gamma(self):
        adapter,consumer=adapter_for()
        years=(datetime(2026,8,20,20,tzinfo=timezone.utc)-datetime(2026,8,6,16,tzinfo=timezone.utc)).total_seconds()/(365*86400)
        premium=american_futures_option_price(futures_price=6000,strike=6000,time_to_expiry_years=years,
            risk_free_rate=.045,volatility=.22,option_type='C')
        await self.feed(adapter,definition(cfi='OCAFPS'),quote(),priced_trade(price=premium,sequence=1))
        state=consumer.contract_state[('databento','101','trade_volume')]
        self.assertEqual(state['pricing_model'],'american_futures_crr')
        self.assertEqual(state['iv_source'],'american_futures_inverted')
        self.assertAlmostEqual(state['iv'],.22,places=7)
        self.assertTrue(state['iv_provenance']['early_exercise_modeled'])
        self.assertEqual(state['iv_provenance']['tree_steps'],512)
        self.assertEqual(adapter.diagnostics()['model_inputs']['american_futures_inverted_ticks'],1)

    def test_null_iv_and_retained_provenance_fail_closed(self):
        metadata=DatabentoAdapter._normalize_definition_record(definition())
        unknown=DatabentoAdapter._normalize_option_trade_record(priced_trade(price=99999),{101:metadata})
        for change in ({'iv':.15},{'iv_source':'provider'},{'iv_provenance':{'status':'converged'}}):
            with self.subTest(change=change),self.assertRaises(ValueError):
                validate_normalized_message({**unknown,**change})
        observed={'iv':.22,'source':'provider','event_time':'2026-08-06T15:59:59Z','pricing_model':'black_76',
                  'expiry_timestamp':metadata['expiry_timestamp'],'risk_free_rate':.045}
        retained=DatabentoAdapter._normalize_option_trade_record(priced_trade(price=99999),{101:metadata},previous_valid_iv=observed)
        validate_normalized_message(retained)
        for key,value in [('prior_iv_event_time','2026-08-06T16:00:01Z'),('prior_iv_age_ms',.01),('prior_iv',.3),('prior_iv_source','configured_default')]:
            bad=copy.deepcopy(retained);bad['iv_provenance'][key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):validate_normalized_message(bad)

    def test_legacy_selected_black76_model_is_not_silently_upgraded(self):
        metadata=DatabentoAdapter._normalize_definition_record(definition(cfi='OCAFPS'))
        new=DatabentoAdapter._normalize_option_trade_record(trade(),{101:metadata})
        old={**new,'pricing_model':'black_76','iv_source':'provider'}
        validate_normalized_message(old)
        self.assertEqual(canonical_option_contract(old,target_underlying='ES')['pricing_model'],'black_76')
        wrong={**new,'exercise_style':'european','exercise_style_source':'provider','provider_cfi':'OCEFPS'}
        with self.assertRaises(ValueError):validate_normalized_message(wrong)

    def test_statistics_without_observed_iv_does_not_invent_it(self):
        metadata=DatabentoAdapter._normalize_definition_record(definition())
        message=DatabentoAdapter._normalize_statistics_record(statistics(),{101:metadata})
        self.assertIsNone(message['iv'])
        self.assertEqual(message['iv_source'],'unavailable')
        validate_normalized_message(message)

if __name__=='__main__':unittest.main()
