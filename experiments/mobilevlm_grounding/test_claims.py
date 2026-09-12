"""Boundary tests: positive detection is not grip evidence; uncertainty persists."""
import unittest
from claims import check


class ClaimBoundaries(unittest.TestCase):
    def setUp(self):
        self.e=dict(frame_id='frame-a',source_pts_seconds=3,pair_skew_ms=0,
            detections=[dict(label='person',confidence=.9),dict(label='remote',confidence=.99)])

    def test_remote_detection_cannot_authorize_holding(self):
        self.assertTrue(check('The person is holding a remote.',self.e,'frame-a',3)['all_withdrawn'])

    def test_no_detection_cannot_prove_absence(self):
        self.e['detections']=[]
        r=check('No objects are present.',self.e,'frame-a',3)
        self.assertEqual(r['verified_claim_count'],0)
        self.assertTrue(r['all_withdrawn'])

    def test_misaligned_data_invalidates_confirmation(self):
        self.assertTrue(check('A person is present.',self.e,'frame-b',3)['all_withdrawn'])
        self.assertTrue(check('A person is present.',self.e,'frame-a',4)['all_withdrawn'])

    def test_retained_posture_is_not_promoted_to_verified(self):
        r=check('The person is sitting down and looking at a computer screen.',self.e,'frame-a',3)
        self.assertEqual(r['verified_claim_count'],0)
        self.assertEqual(len(r['retained_claims']),1)
        self.assertEqual(r['retained_claims'][0]['status'],'image_only_unverified')
        self.assertEqual(len(r['withdrawn_claims']),1)

    def test_truncated_output_is_not_admitted(self):
        self.assertTrue(check('The person is sitting',self.e,'frame-a',3,False)['all_withdrawn'])

    def test_raised_own_hands_are_not_held_objects(self):
        r=check('The person is holding their hands up.',self.e,'frame-a',3)
        self.assertFalse(r['all_withdrawn'])
        self.assertEqual(r['verified_claim_count'],0)

    def test_put_substring_is_not_put_action(self):
        r=check('A computer is present.',self.e,'frame-a',3)
        self.assertEqual(r['claims'][0]['reason'],'unparsed_or_unverified_specific_claim')


if __name__=='__main__':unittest.main()
