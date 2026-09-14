"""Check handoff coverage and explicit capacity overflow without camera hardware."""
import threading
import unittest
from live_capture import Buffer


class HandoffTests(unittest.TestCase):
    def test_concurrent_handoffs_preserve_every_sequence_once(self):
        state = Buffer(2000)
        def produce():
            for i in range(1000):
                state.append(dict(seq=i))
        thread = threading.Thread(target=produce)
        thread.start()
        batches = []
        while thread.is_alive():
            batches.append(state.take())
        thread.join()
        batches.append(state.take())
        rows = [r for b in batches for r in b['frames']]
        self.assertEqual([r['seq'] for r in rows], list(range(1000)))
        for b in batches:
            self.assertTrue(all(b['start'] <= r['mono'] <= b['end'] for r in b['frames']))
        for a,b in zip(batches,batches[1:]):
            self.assertEqual(a['end'],b['start'])

    def test_overflow_is_reported_not_silent(self):
        state = Buffer(3)
        for i in range(5):
            state.append(dict(seq=i))
        batch = state.take()
        self.assertEqual(batch['overflow'],2)
        self.assertEqual([r['seq'] for r in batch['frames']],[2,3,4])
        self.assertEqual(state.take()['frames'],[])


if __name__ == '__main__':
    unittest.main()
