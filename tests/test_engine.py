import unittest
from engine import TOTAL_CONFIGURATIONS, config_at, config_hash, PaperAccount, should_enter

class EngineTests(unittest.TestCase):
    def test_count_and_uniqueness_sample(self):
        self.assertEqual(TOTAL_CONFIGURATIONS,1_000_000)
        ids=[config_hash(i) for i in range(0,TOTAL_CONFIGURATIONS,997)]
        self.assertEqual(len(ids),len(set(ids)))
        self.assertNotEqual(config_at(0),config_at(999999))
    def test_bounds(self):
        with self.assertRaises(IndexError): config_at(1_000_000)
    def test_costs(self):
        a=PaperAccount()
        self.assertTrue(a.buy(1,100))
        self.assertTrue(a.sell(1,101))
        self.assertAlmostEqual(a.cash,9.801,places=5)
        self.assertLess(a.realized,0)
    def test_wins(self):
        a=PaperAccount()
        a.buy(1,100)
        a.sell(2,101)
        self.assertEqual(a.wins,1)
    def test_signal(self):
        c=config_at(0)
        self.assertTrue(should_enter(c,3,10))
        self.assertFalse(should_enter(c,-3,10))
if __name__ == "__main__": unittest.main()
