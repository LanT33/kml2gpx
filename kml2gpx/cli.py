# -*- coding: utf-8 -*-
"""命令行入口：kml2gpx。"""

import argparse
import sys

from . import __version__
from .converter import Kml2Gpx


def build_parser():
    parser = argparse.ArgumentParser(
        prog="kml2gpx",
        description="把 KML 文件转换成 GPX 1.1 文件（gpx2kml 的反向工具）",
    )
    parser.add_argument(
        "-i", "--input", action="append", required=True, metavar="FILE",
        help="输入 KML 文件，可用逗号分隔多个，也可重复使用该选项",
    )
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help="输出 GPX 文件；省略时输出到标准输出",
    )
    parser.add_argument(
        "-e", "--epsilon", default="0", metavar="FLOAT",
        help="Douglas-Peucker 抽稀容差（单位：度），默认 0 表示不抽稀",
    )
    parser.add_argument(
        "-c", "--creator", default="kml2gpx", metavar="NAME",
        help="写入 GPX creator 属性的名字，默认 kml2gpx",
    )
    parser.add_argument(
        "--indent", type=int, default=2, metavar="N",
        help="缩进空格数，0 表示压缩输出，默认 2",
    )
    parser.add_argument(
        "--keep-html", action="store_true",
        help="保留描述中的 HTML 标签（默认会剥离）",
    )
    parser.add_argument("-v", "--version", action="version", version="kml2gpx %s" % __version__)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)

    files = []
    for item in args.input:
        files.extend(part.strip() for part in item.split(",") if part.strip())

    try:
        converter = Kml2Gpx(
            creator=args.creator,
            epsilon=float(args.epsilon),
            strip_html=not args.keep_html,
        )
        converter.add_files(files)
    except (IOError, OSError) as exc:
        sys.stderr.write("读取失败：%s\n" % exc)
        return 1
    except Exception as exc:  # noqa: BLE001 - 解析错误统一提示
        sys.stderr.write("解析 KML 失败：%s\n" % exc)
        return 1

    text = converter.get_gpx(indent=args.indent)
    if args.output:
        try:
            with open(args.output, "w") as handle:
                handle.write(text)
        except (IOError, OSError) as exc:
            sys.stderr.write("写入失败：%s\n" % exc)
            return 1
        sys.stderr.write(
            "已生成 %s：%d 条轨迹，%d 个航点\n"
            % (args.output, len(converter.tracks), len(converter.waypoints))
        )
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
