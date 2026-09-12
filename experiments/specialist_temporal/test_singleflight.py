import unittest
from singleflight import Scheduler

class SingleflightTests(unittest.TestCase):
    def test_pending_deduplicates_and_retains_latest(self):
        s=Scheduler();s.observe(0,'A',0);j=s.dispatch(0)
        for i in range(1,21):
            s.observe(i/10,'A',i);self.assertIsNone(s.dispatch(i/10))
        self.assertEqual(s.payload,20);self.assertEqual(s.serial,1)
        self.assertTrue(s.complete(j['id'],2,'phone'))
        self.assertIsNone(s.dispatch(2))

    def test_changed_target_discards_old_result_and_dispatches_latest(self):
        s=Scheduler();s.observe(0,'A',0);j=s.dispatch(0)
        s.observe(1,'B',1);s.observe(2,'C',2)
        self.assertIsNone(s.dispatch(2));self.assertFalse(s.complete(j['id'],2,'old phone'))
        nxt=s.dispatch(2);self.assertEqual(nxt['key'],'C');self.assertEqual(nxt['payload'],2)

    def test_disappearance_and_reentry_do_not_reuse_identity(self):
        s=Scheduler();s.observe(0,'track1:r1');j=s.dispatch(0);s.observe(.1,None)
        self.assertFalse(s.complete(j['id'],.2,'phone'))
        s.observe(.3,'track2:r1');self.assertIsNotNone(s.dispatch(.3))

    def test_unknown_reply_cools_down_without_retry_loop(self):
        s=Scheduler();s.observe(0,'A');j=s.dispatch(0);s.observe(1,'A')
        s.complete(j['id'],1,'unclear',usable=False)
        s.observe(2,'A');self.assertIsNone(s.dispatch(2))
        s.observe(3,'A');self.assertIsNotNone(s.dispatch(3))

    def test_success_cache_expires(self):
        s=Scheduler();s.observe(0,'A');j=s.dispatch(0);s.observe(1,'A');s.complete(j['id'],1,'phone')
        s.observe(10,'A');self.assertIsNone(s.dispatch(10))
        s.observe(11,'A');self.assertIsNotNone(s.dispatch(11))

    def test_late_result_never_overlaps_another_backend_request(self):
        s=Scheduler();s.observe(0,'A');j=s.dispatch(0);s.observe(6,'A')
        self.assertIsNone(s.dispatch(6));self.assertFalse(s.complete(j['id'],6,'late'))
        self.assertIsNotNone(s.dispatch(6))

    def test_known_or_missing_observation_does_not_trigger(self):
        s=Scheduler();s.observe(0,None);self.assertIsNone(s.dispatch(0))
        s.observe(1,'A',unknown=False);self.assertIsNone(s.dispatch(1))
        s.observe(2,'A');self.assertIsNone(s.dispatch(3))

    def test_unmatched_completion_cannot_overwrite_current_job(self):
        s=Scheduler();s.observe(0,'A');j=s.dispatch(0)
        self.assertFalse(s.complete(999,.1,'wrong'));self.assertEqual(s.pending['id'],j['id'])

if __name__=='__main__':unittest.main()
