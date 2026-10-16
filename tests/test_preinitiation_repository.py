"""内存 Repository 保证范围与进程内防重测试（03 §4.7/§7）。"""
import unittest

from src.modules.preinitiation.repository import GUARANTEE, DuplicatePendingProductError, InMemoryRepository


class TestGuaranteeBoundary(unittest.TestCase):
    def test_guarantee_explicitly_documented(self):
        """内存实现的保证范围有明确说明：无持久化/无并发保障/不得用于生产。"""
        repo = InMemoryRepository()
        self.assertEqual(repo.guarantee, GUARANTEE)
        for keyword in ('持久化', '并发', '生产', '不得用于生产或真实决策'):
            self.assertIn(keyword, GUARANTEE)
        # 保证范围同时声明了"保证什么"
        self.assertIn('单进程内状态一致', GUARANTEE)
        self.assertIn('四元组进程内防重', GUARANTEE)


class TestFourTupleDedup(unittest.TestCase):
    def test_four_tuple_dedup_in_process(self):
        """四元组 (task, asin, offer, sku) 进程内防重（03 §4.7 保证边界）。"""
        repo = InMemoryRepository()
        repo.add_pending_product('t1', 'a1', 'o1', 's1', 'snap-1', 'user')
        with self.assertRaises(DuplicatePendingProductError):
            repo.add_pending_product('t1', 'a1', 'o1', 's1', 'snap-2', 'user')
        # 不同 SKU 不受影响
        repo.add_pending_product('t1', 'a1', 'o1', 's2', 'snap-3', 'user')
        self.assertEqual(len(repo.pending_products()), 2)


if __name__ == '__main__':
    unittest.main()
