"""Boundary tests using synthetic observations, not model-accuracy evidence."""
import unittest
from fusion import Fusion

def observation(x=.4, hands=True, faces=1):
    return dict(faces=[dict(center=[.5,.4],width=.2,height=.4,chin_y=.6)]*faces,
                hands=[dict(palm=[x,.85],open_fingers=4,mouth_distance_face_width=1)] if hands else [],pose=[])

class Boundaries(unittest.TestCase):
    def test_static_hand_is_not_wave(self):
        f=Fusion(); out=[f.update(i/10,observation()) for i in range(40)]
        self.assertEqual(out[-1]['state'],'open_hand_visible')
        self.assertFalse(any(r['wave_motion'] for r in out))

    def test_chest_height_wave_does_not_require_palm_above_chin(self):
        f=Fusion(); out=[f.update(i/10,observation(x)) for i,x in enumerate([.3,.4,.5,.4,.3,.4,.5])]
        self.assertTrue(any(r['wave_motion'] for r in out))

    def test_missing_hand_does_not_mean_lowering(self):
        f=Fusion(); [f.update(i/10,observation()) for i in range(10)]
        out=[f.update(i/10,observation(hands=False)) for i in range(10,20)]
        self.assertEqual(out[-1]['state'],'unknown')
        self.assertIn('hand_observation_lost',[e['type'] for r in out for e in r['events']])
        self.assertNotIn('hand_lowered',[e['type'] for r in out for e in r['events']])

    def test_gap_does_not_bridge_wave_or_debounce(self):
        f=Fusion(); f.update(0,observation(.3)); f.update(.1,observation(.5))
        r=f.update(2,observation(.3))
        self.assertEqual(r['state'],'unknown');self.assertFalse(r['wave_motion'])

    def test_ambiguous_person_does_not_keep_hand_association(self):
        f=Fusion(); [f.update(i/10,observation()) for i in range(10)]
        out=[f.update(i/10,observation(faces=2)) for i in range(10,16)]
        self.assertEqual(out[-1]['state'],'unknown');self.assertFalse(out[-1]['wave_motion'])
        self.assertEqual(out[-1]['quality'],'multiple_faces_ambiguous')

    def test_new_local_track_requires_fresh_evidence(self):
        f=Fusion(); [f.update(i/10,observation()) for i in range(10)]
        o=observation(.8);o['faces'][0]['center']=[.9,.4]
        r=f.update(1,o);self.assertEqual(r['state'],'unknown')

    def test_time_must_increase(self):
        f=Fusion();f.update(1,observation())
        with self.assertRaises(ValueError):f.update(1,observation())

if __name__=='__main__':unittest.main()
