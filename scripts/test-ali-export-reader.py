import unittest, sys, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
import ali_export_reader as a

class ExportReaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows=a.read_xlsx(Path('K:/CRA客户项目/records/chat-signal/ali-orders-export-original-2026-10-12.xlsx'))

    def test_full_long_ids_and_bad_dimensions(self):
        self.assertEqual(len(self.rows),13)
        self.assertEqual(self.rows[0]['订单编号(Order Number)'],'318659674001022131')
        self.assertEqual(len(a.aggregate(self.rows)),12)

    def test_repeated_order_money_once(self):
        orders=a.aggregate(self.rows)
        mehis=orders['33277284501047472']
        self.assertEqual(len(mehis['items']),2)
        self.assertEqual(mehis['goods'],a.decimal.Decimal('140.53'))
        self.assertEqual(sum(o['total'] for o in orders.values()),a.decimal.Decimal('11832.76'))

    def test_conflicting_order_fields_rejected(self):
        rows=copy.deepcopy(self.rows)
        rows[4]['订单总价(Order Amount)']='999'
        with self.assertRaises(ValueError): a.aggregate(rows)

    def test_no_receipt_or_business_state_override(self):
        orders=a.aggregate([self.rows[2]])
        person={'id':'p','nameFirstName':'美国｜Zoe Keyreli','nameLastName':'','emailsPrimaryEmail':''}
        crm={'people':[person],'orders':[{'id':'o','aLiDingDanHao':'317277927001023621','keHuId':'p',
            'yuanDingDanJinEAmountMicros':'3002000000','lieBiaoShangPinJinEAmountMicros':'3000000000',
            'shiJiLuYueZhuangTai':'DAI_FU_KUAN','yiShouJinEAmountMicros':'0'}]}
        p=a.plan(orders,crm,'test')
        self.assertNotIn('yiShouJinE',p['orders'][0]['fields'])
        self.assertNotIn('shiJiLuYueZhuangTai',p['orders'][0]['fields'])
        self.assertEqual(p['crm_writes'],0)

    def test_ambiguous_existing_orders_blocked(self):
        orders=a.aggregate([self.rows[0]])
        p=a.plan(orders,{'people':[],'orders':[{'aLiDingDanHao':next(iter(orders))}]*2},'test')
        self.assertEqual(p['orders'],[])
        self.assertTrue(p['issues'])

    def test_scientific_notation_not_accepted(self):
        rows=copy.deepcopy(self.rows[:1]); rows[0]['订单编号(Order Number)']='3.1866E+17'
        with self.assertRaises(ValueError): a.aggregate(rows)

if __name__=='__main__': unittest.main()
