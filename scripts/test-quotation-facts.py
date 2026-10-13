import copy
import unittest
from quotation_facts import validate, sent_evidence_ready, QuoteNeedsConfirmation

def sample():
    return {'currency':'USD','items':[{'product':'DEMO RC','model':'DEMO-1','quantity':'3','unit_price':'12.50','subtotal':'37.50'}],
            'goods_total':'37.50','shipping':None,'paid':'37.50','uncertainties':[]}

class QuoteFactsTests(unittest.TestCase):
    def test_unknown_shipping_does_not_become_zero_or_total(self):
        result=validate(sample())
        self.assertIsNone(result['quoted_shipping'])
        self.assertIsNone(result['quotation_total'])

    def test_shipping_separate_from_goods(self):
        raw=sample();raw['shipping']='5.00'
        result=validate(raw)
        self.assertEqual((result['goods_total'],result['quoted_shipping'],result['quotation_total']),('37.50','5.00','42.50'))

    def test_quote_never_proves_payment_or_shipment(self):
        result=validate(sample())
        self.assertFalse(result['payment_verified'])
        self.assertFalse(result['shipment_verified'])

    def test_line_conflict_requires_confirmation(self):
        raw=sample();raw['items'][0]['subtotal']='30.00'
        with self.assertRaisesRegex(QuoteNeedsConfirmation,'line_amount_conflict'):validate(raw)

    def test_total_conflict_requires_confirmation(self):
        raw=sample();raw['goods_total']='42.50'
        with self.assertRaisesRegex(QuoteNeedsConfirmation,'goods_total_conflict'):validate(raw)

    def test_wrong_currency_rejected(self):
        raw=sample();raw['currency']='CNY'
        with self.assertRaises(QuoteNeedsConfirmation):validate(raw)

    def test_invalid_decimal_never_partially_parsed(self):
        for number in ('1,000','-1','NaN','1e3', True, 12.5):
            raw=sample();raw['items'][0]['unit_price']=number
            with self.assertRaises(QuoteNeedsConfirmation):validate(raw)

    def test_missing_line_values_remain_unknown(self):
        raw=sample();raw['items'][0].update(quantity=None,unit_price=None,subtotal=None);raw['goods_total']=None
        result=validate(raw)
        self.assertIsNone(result['items'][0]['subtotal'])
        self.assertIsNone(result['goods_total'])

    def test_draft_unknown_customer_and_historical_do_not_start_followup(self):
        source={'direction':'outbound','person_id':'p1','occurred_at':'2026-10-12T01:00:00+00:00',
                'identity_verified':True,'actual_send_verified':True,'procurement_link_verified':True,
                'opportunity_id':'o1','classification':'quotation','content_hash':'hash','historical_only':False}
        self.assertTrue(sent_evidence_ready(source,'p1'))
        for key,value in [('direction','inbound'),('actual_send_verified',False),('procurement_link_verified',False),
                          ('occurred_at',None),('historical_only',True),('classification','not_quotation')]:
            changed=copy.copy(source);changed[key]=value
            self.assertFalse(sent_evidence_ready(changed,'p1'))
        self.assertFalse(sent_evidence_ready(source,'other'))

if __name__=='__main__':unittest.main()
