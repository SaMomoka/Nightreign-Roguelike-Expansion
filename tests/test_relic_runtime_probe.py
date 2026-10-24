import struct
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"tools"))
from probe_relic_work_values import marker_matches


class WorkValueProbeTests(unittest.TestCase):
    markers=(1599843857,1599843858,1599843859,1599843860)

    def test_reports_packed_int_observation(self):
        data=b"pad"+struct.pack("<4i",*self.markers)+b"tail"
        self.assertIn((3,"<i",4),list(marker_matches(data,self.markers)))

    def test_partial_markers_do_not_identify_layout(self):
        data=struct.pack("<3i",*self.markers[:3])
        self.assertEqual(list(marker_matches(data,self.markers)),[])

    def test_float_rounding_cannot_fake_four_distinct_markers(self):
        data=struct.pack("<4f",*self.markers)
        self.assertEqual(list(marker_matches(data,self.markers)),[])

    def test_multiple_matches_remain_ambiguous_observations(self):
        block=struct.pack("<4i",*self.markers)
        matches=[m for m in marker_matches(block+b"X"*300+block,self.markers) if m[1:] == ("<i",4)]
        self.assertEqual([m[0] for m in matches],[0,316])
