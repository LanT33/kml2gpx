# -*- coding: utf-8 -*-
"""kml2gpx 单元测试：python -m unittest discover -s tests"""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from kml2gpx import Kml2Gpx, DouglasPeucker, convert, parse_coordinates, parse_time

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLE = os.path.join(HERE, os.pardir, "examples", "example.kml")

KML_SIMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
  <Document>
    <name>doc</name>
    <Placemark>
      <name>track A</name>
      <LineString><coordinates>
        116.1,39.1,10
        116.2,39.2,11
      </coordinates></LineString>
    </Placemark>
    <Placemark>
      <name>point B</name>
      <Point><coordinates>116.3,39.3,12</coordinates></Point>
    </Placemark>
  </Document>
</kml>
"""


GPX_NS = "{http://www.topografix.com/GPX/1/1}"


def gpx_root(text):
    return ET.fromstring(text)


def find(root, path):
    """按 GPX 命名空间查找单个节点。"""
    return root.find("/".join(GPX_NS + part for part in path.split("/")))


def findall(root, path):
    """按 GPX 命名空间查找节点列表。"""
    return root.findall("/".join(GPX_NS + part for part in path.split("/")))


class TestParse(unittest.TestCase):
    def test_parse_coordinates(self):
        points = parse_coordinates("1.0,2.0,3.0 4.0,5.0\n6.0,7.0,8.0")
        self.assertEqual(len(points), 3)
        self.assertEqual((points[0].lat, points[0].lon, points[0].alt), (2.0, 1.0, 3.0))
        self.assertIsNone(points[1].alt)

    def test_parse_coordinates_skips_invalid(self):
        self.assertEqual(parse_coordinates("abc,def"), [])
        self.assertEqual(parse_coordinates(""), [])
        # 纬度超范围
        self.assertEqual(parse_coordinates("10.0,120.0"), [])

    def test_parse_time_utc(self):
        moment = parse_time("2024-05-01T06:30:00Z")
        self.assertEqual(moment.isoformat(), "2024-05-01T06:30:00+00:00")

    def test_parse_time_with_offset(self):
        moment = parse_time("2024-05-01T14:30:00+08:00")
        self.assertEqual(moment.isoformat(), "2024-05-01T06:30:00+00:00")

    def test_parse_time_invalid(self):
        self.assertIsNone(parse_time("not a time"))
        self.assertIsNone(parse_time(""))


class TestSimplify(unittest.TestCase):
    def test_epsilon_zero_keeps_all(self):
        points = parse_coordinates("0,0 1,0.000001 2,0")
        self.assertEqual(len(DouglasPeucker(0).simplify(points)), 3)

    def test_simplify_removes_collinear(self):
        points = parse_coordinates("0,0 1,0 2,0 3,0 4,0")
        result = DouglasPeucker(1e-6).simplify(points)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].lon, 0.0)
        self.assertEqual(result[-1].lon, 4.0)

    def test_simplify_keeps_outlier(self):
        points = parse_coordinates("0,0 1,0.5 2,0")
        result = DouglasPeucker(1e-6).simplify(points)
        self.assertEqual(len(result), 3)


class TestConvert(unittest.TestCase):
    def test_simple_document(self):
        converter = Kml2Gpx()
        converter.add_string(KML_SIMPLE)
        root = gpx_root(converter.get_gpx())

        self.assertEqual(root.get("version"), "1.1")
        self.assertEqual(find(root, "metadata/name").text, "doc")
        self.assertEqual(len(findall(root, "trk")), 1)
        self.assertEqual(len(findall(root, "wpt")), 1)

        trkpt = findall(root, "trk/trkseg/trkpt")
        self.assertEqual(len(trkpt), 2)
        self.assertEqual(trkpt[0].get("lat"), "39.1")
        self.assertEqual(trkpt[0].get("lon"), "116.1")
        self.assertEqual(find(trkpt[0], "ele").text, "10")

        wpt = find(root, "wpt")
        self.assertEqual(wpt.get("lat"), "39.3")
        self.assertEqual(find(wpt, "name").text, "point B")

    def test_example_file(self):
        if not os.path.exists(EXAMPLE):
            self.skipTest("缺少示例文件")
        converter = Kml2Gpx()
        converter.add_file(EXAMPLE)

        # LineString + gx:Track + Polygon 外环 = 3 条轨迹
        self.assertEqual(len(converter.tracks), 3)
        self.assertEqual(len(converter.waypoints), 1)

        root = gpx_root(converter.get_gpx())
        times = [t.text for t in findall(root, "trk/trkseg/trkpt/time")]
        self.assertIn("2024-05-01T06:30:00Z", times)
        self.assertIn("2024-05-02T09:00:10Z", times)

    def test_html_description_is_stripped(self):
        converter = Kml2Gpx()
        converter.add_file(EXAMPLE)
        root = gpx_root(converter.get_gpx())
        names = [n.text for n in findall(root, "trk/name")]
        descs = [d.text for d in findall(root, "trk/desc")]
        self.assertIn("Morning run", names)
        self.assertNotIn("<p>", " ".join(descs))

    def test_epsilon_applied(self):
        kml = KML_SIMPLE.replace(
            "        116.1,39.1,10\n        116.2,39.2,11\n",
            "        116.1,39.1,10\n        116.2,39.1,11\n        116.3,39.1,12\n",
        )
        converter = Kml2Gpx(epsilon=1e-6)
        converter.add_string(kml)
        root = gpx_root(converter.get_gpx())
        self.assertEqual(len(findall(root, "trk/trkseg/trkpt")), 2)

    def test_roundtrip_file(self):
        if not os.path.exists(EXAMPLE):
            self.skipTest("缺少示例文件")
        handle, path = tempfile.mkstemp(suffix=".gpx")
        os.close(handle)
        try:
            convert(EXAMPLE, path)
            with open(path) as fp:
                text = fp.read()
            self.assertTrue(text.startswith('<?xml version="1.0" encoding="UTF-8"?>'))
            self.assertTrue(len(findall(ET.fromstring(text), "trk")) > 0)
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
