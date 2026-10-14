# -*- coding: utf-8 -*-
"""KML -> GPX 转换核心。

与 gpx2kml（Ruby）方向相反：读入 KML，输出 GPX 1.1。
支持的 KML 元素：

* ``Placemark/LineString``          -> ``trk/trkseg/trkpt``
* ``Placemark/Polygon/LinearRing``  -> 闭合的 ``trk``
* ``Placemark/Point``               -> ``wpt``
* ``Placemark/gx:Track``            -> ``trk``（带时间戳）
* ``MultiGeometry``                 -> 内部几何逐个展开
* ``Placemark`` 之外的层级（Folder / Document）会被递归展开

仅依赖标准库。
"""

import re
import xml.etree.ElementTree as ET
from collections import namedtuple
from datetime import datetime, timezone

from .simplify import DouglasPeucker

GPX_NS = "http://www.topografix.com/GPX/1/1"
XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
GPX_SCHEMA = "http://www.topografix.com/GPX/1/1/gpx.xsd"

#: 坐标点：经度、纬度、海拔（可为 None）、时间（datetime 或 None）
GeoPoint = namedtuple("GeoPoint", "lon lat alt time")

_TAG_RE = re.compile(r"<[^>]+>")
_HTML_ENTITIES = [
    ("&nbsp;", " "),
    ("&amp;", "&"),
    ("&lt;", "<"),
    ("&gt;", ">"),
    ("&quot;", '"'),
    ("&#39;", "'"),
]
_TIME_RE = re.compile(
    r"^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?"
    r"\s*(Z|z|[+-]\d{2}:?\d{2})?$"
)


# --------------------------------------------------------------------------
# XML 小工具
# --------------------------------------------------------------------------
def local_name(tag):
    """去掉 ``{namespace}`` 前缀，返回本地标签名。"""
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1]


def iter_nodes(node, name):
    """深度优先遍历 node 下所有本地名为 name 的后代（含自身）。"""
    for element in node.iter():
        if local_name(element.tag) == name:
            yield element


def find_child(node, name):
    """返回第一个本地名为 name 的直接子节点。"""
    if node is None:
        return None
    for child in node:
        if local_name(child.tag) == name:
            return child
    return None


def node_text(node):
    """取节点的全部文本内容（含 CDATA）。"""
    if node is None:
        return ""
    return "".join(node.itertext()).strip()


def clean_text(value, strip_html=True):
    """把 KML 的 HTML 描述整理成 GPX 可接受的纯文本。"""
    if value is None:
        return ""
    text = value.strip()
    if not text:
        return ""
    if strip_html and "<" in text and ">" in text:
        text = _TAG_RE.sub(" ", text)
        text = re.sub(r"\s+", " ", text).strip()
    return text


def unescape_text(value):
    for entity, char in _HTML_ENTITIES:
        value = value.replace(entity, char)
    return value


# --------------------------------------------------------------------------
# 坐标 / 时间解析
# --------------------------------------------------------------------------
def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid_lat_lon(lon, lat):
    return lon is not None and lat is not None and -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0


def parse_coordinates(text):
    """解析 KML ``<coordinates>`` 文本。

    支持 ``lon,lat[,alt]`` 形式，多个点之间以空白（空格/换行/制表符）分隔。
    """
    points = []
    for token in (text or "").split():
        if "," not in token:
            continue
        parts = token.split(",")
        lon = _to_float(parts[0])
        lat = _to_float(parts[1]) if len(parts) > 1 else None
        if not _valid_lat_lon(lon, lat):
            continue
        alt = _to_float(parts[2]) if len(parts) > 2 else None
        points.append(GeoPoint(lon, lat, alt, None))
    return points


def parse_coord_text(text):
    """解析 ``<gx:coord>`` 文本：``lon lat alt``（空格分隔，无逗号）。"""
    parts = (text or "").split()
    if len(parts) < 2:
        return None
    lon = _to_float(parts[0])
    lat = _to_float(parts[1])
    if not _valid_lat_lon(lon, lat):
        return None
    alt = _to_float(parts[2]) if len(parts) > 2 else None
    return GeoPoint(lon, lat, alt, None)


def parse_time(value):
    """解析 KML 时间字符串，返回 UTC 的 datetime；失败返回 None。"""
    if not value:
        return None
    match = _TIME_RE.match(value.strip())
    if not match:
        return None

    year, month, day, hour, minute, second, tz = match.groups()
    second = second or "00"
    stamp = "%s-%s-%sT%s:%s:%s" % (year, month, day, hour, minute, second)

    if tz in (None, "Z", "z"):
        tz = "+00:00"
    elif len(tz) == 5 and ":" not in tz:
        tz = tz[:3] + ":" + tz[3:]

    try:
        moment = datetime.fromisoformat(stamp + tz)
    except ValueError:
        return None

    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc)


def format_time(moment):
    """GPX 时间格式：UTC，秒精度。"""
    if moment is None:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --------------------------------------------------------------------------
# 转换器
# --------------------------------------------------------------------------
class Kml2Gpx(object):
    """把一个或多个 KML 文档转换成一个 GPX 1.1 文档。"""

    def __init__(self, creator="kml2gpx", epsilon=0.0, strip_html=True):
        self.creator = creator
        #: 抽稀容差（单位：度）。<= 0 表示保留全部点
        self.epsilon = float(epsilon or 0.0)
        self.strip_html = strip_html

        self.doc_name = ""
        self.doc_desc = ""
        self.tracks = []      # [{name, desc, points}]
        self.waypoints = []   # [{name, desc, points}]

    # -- 输入 ---------------------------------------------------------------
    def add_file(self, path):
        with open(path, "r") as handle:
            self.add_string(handle.read())

    def add_files(self, files):
        """兼容 gpx2kml 的写法，files 可以是列表或逗号分隔字符串。"""
        if isinstance(files, str):
            files = files.split(",")
        for path in files:
            path = path.strip()
            if path:
                self.add_file(path)

    def add_string(self, xml_text):
        self._read_kml(xml_text)

    # -- 解析 ---------------------------------------------------------------
    def _read_kml(self, xml_text):
        root = ET.fromstring(xml_text)

        document = find_child(root, "Document")
        container = document if document is not None else root

        self.doc_name = self.doc_name or clean_text(
            node_text(find_child(container, "name")), self.strip_html
        )
        self.doc_desc = self.doc_desc or clean_text(
            node_text(find_child(container, "description")), self.strip_html
        )

        for placemark in iter_nodes(root, "Placemark"):
            self._read_placemark(placemark)

    def _read_placemark(self, placemark):
        name = clean_text(node_text(find_child(placemark, "name")), self.strip_html)
        desc = clean_text(node_text(find_child(placemark, "description")), self.strip_html)
        moment = self._placemark_time(placemark)

        # gx:Track（历史轨迹点，自带 when 时间戳）
        for track in iter_nodes(placemark, "Track"):
            points = self._read_track(track, moment)
            if points:
                self.tracks.append({"name": name, "desc": desc, "points": points})

        # LineString -> 轨迹
        for line in iter_nodes(placemark, "LineString"):
            points = self._with_time(parse_coordinates(node_text(find_child(line, "coordinates"))), moment)
            if points:
                self.tracks.append({"name": name, "desc": desc, "points": points})

        # Polygon 的外环 -> 闭合轨迹
        for ring in iter_nodes(placemark, "LinearRing"):
            points = self._with_time(parse_coordinates(node_text(find_child(ring, "coordinates"))), moment)
            if points:
                self.tracks.append({"name": name, "desc": desc, "points": points})

        # Point -> 航点
        for point in iter_nodes(placemark, "Point"):
            coords = parse_coordinates(node_text(find_child(point, "coordinates")))
            if not coords:
                continue
            geo = coords[0]
            self.waypoints.append({
                "name": name,
                "desc": desc,
                "points": [GeoPoint(geo.lon, geo.lat, geo.alt, moment)],
            })

    @staticmethod
    def _with_time(points, moment):
        return [GeoPoint(p.lon, p.lat, p.alt, moment) for p in points]

    def _read_track(self, track, fallback_time):
        """解析 ``<gx:Track>``：gx:coord 与 when 按顺序一一对应。"""
        coord_nodes = list(iter_nodes(track, "coord"))
        when_nodes = list(iter_nodes(track, "when"))

        points = []
        for index, coord in enumerate(coord_nodes):
            geo = parse_coord_text(node_text(coord))
            if geo is None:
                continue
            moment = fallback_time
            if index < len(when_nodes):
                moment = parse_time(node_text(when_nodes[index])) or fallback_time
            points.append(GeoPoint(geo.lon, geo.lat, geo.alt, moment))
        return points

    def _placemark_time(self, placemark):
        stamp = find_child(placemark, "TimeStamp")
        moment = parse_time(node_text(find_child(stamp, "when")))
        if moment:
            return moment
        span = find_child(placemark, "TimeSpan")
        return parse_time(node_text(find_child(span, "begin")))

    # -- 输出 ---------------------------------------------------------------
    def build_gpx(self):
        """返回 GPX 的 ``ElementTree``。"""
        root = ET.Element("gpx", {
            "version": "1.1",
            "creator": self.creator,
            "xmlns": GPX_NS,
            "xmlns:xsi": XSI_NS,
            "xsi:schemaLocation": "%s %s" % (GPX_NS, GPX_SCHEMA),
        })

        if self.doc_name or self.doc_desc:
            metadata = ET.SubElement(root, "metadata")
            self._text_child(metadata, "name", self.doc_name)
            self._text_child(metadata, "desc", self.doc_desc)
            self._text_child(metadata, "time", format_time(datetime.now(timezone.utc)))

        simplifier = DouglasPeucker(self.epsilon)

        for waypoint in self.waypoints:
            root.append(self._build_wpt(waypoint))

        for track in self.tracks:
            root.append(self._build_trk(track, simplifier))

        return ET.ElementTree(root)

    def _build_wpt(self, waypoint):
        point = waypoint["points"][0]
        node = ET.Element("wpt", {"lat": self._fmt(point.lat), "lon": self._fmt(point.lon)})
        self._text_child(node, "ele", None if point.alt is None else self._fmt(point.alt))
        self._text_child(node, "time", format_time(point.time))
        self._text_child(node, "name", waypoint["name"])
        self._text_child(node, "desc", waypoint["desc"])
        return node

    def _build_trk(self, track, simplifier):
        node = ET.Element("trk")
        self._text_child(node, "name", track["name"])
        self._text_child(node, "desc", track["desc"])

        segment = ET.SubElement(node, "trkseg")
        for point in simplifier.simplify(track["points"]):
            trkpt = ET.SubElement(segment, "trkpt", {
                "lat": self._fmt(point.lat),
                "lon": self._fmt(point.lon),
            })
            if point.alt is not None:
                self._text_child(trkpt, "ele", self._fmt(point.alt))
            time_text = format_time(point.time)
            if time_text:
                self._text_child(trkpt, "time", time_text)
        return node

    def _text_child(self, parent, tag, value):
        if value is None or value == "":
            return None
        child = ET.SubElement(parent, tag)
        child.text = unescape_text(value)
        return child

    @staticmethod
    def _fmt(value):
        """去掉浮点噪声，最多保留 6 位小数（约 0.1 米）。"""
        text = "%.6f" % float(value)
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text or "0"

    def get_gpx(self, indent=2):
        """返回格式化后的 GPX 文本。"""
        tree = self.build_gpx()
        if indent and indent > 0:
            _indent(tree.getroot(), " " * int(indent))
        body = ET.tostring(tree.getroot(), encoding="unicode")
        return '<?xml version="1.0" encoding="UTF-8"?>\n' + body + "\n"

    def save(self, filename, indent=2):
        with open(filename, "w") as handle:
            handle.write(self.get_gpx(indent=indent))


def _indent(element, space, level=0):
    """给 ElementTree 加上缩进（Python 3.9 之前没有 ET.indent）。"""
    children = list(element)
    if children:
        if not element.text or not element.text.strip():
            element.text = "\n" + space * (level + 1)
        for child in children:
            _indent(child, space, level + 1)
        if not children[-1].tail or not children[-1].tail.strip():
            children[-1].tail = "\n" + space * level
    if not element.tail or not element.tail.strip():
        element.tail = "\n" + space * level


def convert(kml_path, gpx_path, epsilon=0.0, creator="kml2gpx", indent=2):
    """一步到位的便捷函数。"""
    converter = Kml2Gpx(creator=creator, epsilon=epsilon)
    converter.add_files(kml_path)
    converter.save(gpx_path, indent=indent)
    return converter
