# -*- coding: utf-8 -*-
"""kml2gpx：把 KML 文件转换成 GPX 1.1 文件的轻量工具。"""

from .converter import (  # noqa: F401
    Kml2Gpx,
    convert,
    format_time,
    parse_coordinates,
    parse_time,
)
from .simplify import DouglasPeucker, simplify  # noqa: F401

__version__ = "0.1.0"
__all__ = [
    "Kml2Gpx",
    "DouglasPeucker",
    "simplify",
    "convert",
    "format_time",
    "parse_time",
    "parse_coordinates",
    "__version__",
]
