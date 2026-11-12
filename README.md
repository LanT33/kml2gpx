# kml2gpx

用于转换地图轨迹文件格式.越野跑真好玩

把 KML 文件转换成 GPX 1.1 文件的命令行 / 库工具，根据 [gpx2kml](https://github.com/shakaman/gpx2kml) 编写的反向版本。

* 支持 `LineString`、`Point`、`Polygon/LinearRing`、`gx:Track`、`MultiGeometry`，`Folder` 层级会被自动展开
* 支持命名空间（KML 2.2 / 2.1 / Google 扩展 `gx:`），无需预处理
* 保留 `name`、`description`、海拔 `ele`、时间（`TimeStamp` / `TimeSpan` / `gx:Track` 的 `when`），时间统一转为 UTC
* 可选 Douglas-Peucker 抽稀，压缩轨迹点数
* 支持合并多个 KML 到同一个 GPX

## 安装

```bash
cd kml2gpx
pip install .          # 安装后可直接用 kml2gpx 命令
# 或者不安装，直接用源码运行：
PYTHONPATH=. python3 -m kml2gpx -i input.kml -o output.gpx
```

## 命令行用法

```bash
kml2gpx -i 输入.kml -o 输出.gpx [选项]
```

| 选项 | 说明 |
| --- | --- |
| `-i, --input FILE` | 输入 KML，可用逗号分隔多个，也可重复传入；必填 |
| `-o, --output FILE` | 输出 GPX；省略时打印到标准输出 |
| `-e, --epsilon FLOAT` | Douglas-Peucker 抽稀容差（单位：度），默认 `0` 表示不抽稀 |
| `-c, --creator NAME` | 写入 `gpx@creator`，默认 `kml2gpx` |
| `--indent N` | 缩进空格数，`0` 表示紧凑输出，默认 `2` |
| `--keep-html` | 保留描述里的 HTML 标签（默认剥离） |
| `-v, --version` | 打印版本 |

示例：

```bash
# 基本转换
kml2gpx -i examples/example.kml -o example.gpx

# 多个输入合并，并按 0.0001 度容差抽稀
kml2gpx -i a.kml,b.kml -i c.kml -o merged.gpx -e 0.0001

# 输出到标准输出
kml2gpx -i track.kml
```

> 容差参考：1e-5 度约 1 米，1e-4 度约 10 米。

## 作为库使用

```python
from kml2gpx import Kml2Gpx, convert

# 一步到位
convert("input.kml", "output.gpx", epsilon=0.0001)

# 或者自己控制
converter = Kml2Gpx(creator="my-app", epsilon=0.0)
converter.add_file("input.kml")
converter.add_string(open("other.kml").read())
print("轨迹数:", len(converter.tracks), "航点数:", len(converter.waypoints))
converter.save("output.gpx")
```

`converter.tracks` 是 `[{name, desc, points}]`，`points` 为 `GeoPoint(lon, lat, alt, time)` 命名元组；
`converter.waypoints` 结构相同，每条只含一个点。

## 转换映射

| KML | GPX |
| --- | --- |
| `Document/name`、`description` | `metadata/name`、`metadata/desc` |
| `Placemark/LineString` | `trk/trkseg/trkpt` |
| `Placemark/Polygon/outerBoundaryIs/LinearRing` | `trk/trkseg/trkpt`（闭合） |
| `Placemark/gx:Track`（`gx:coord` + `when`） | `trk/trkseg/trkpt`（带时间） |
| `Placemark/Point` | `wpt` |
| `Placemark/TimeStamp/when`、`TimeSpan/begin` | `trkpt/time`、`wpt/time`（UTC） |

## 与 gpx2kml 的差异

| | gpx2kml (Ruby) | kml2gpx (Python) |
| --- | --- | --- |
| 方向 | GPX -> KML | KML -> GPX |
| 依赖 | nokogiri、mini_exiftool | 无（标准库） |
| 抽稀 | 默认 30e-5，递归实现 | 默认关闭（`-e` 开启），迭代实现避免深递归 |
| 照片 | 读取 EXIF 生成 Placemark | 不支持 |

## 项目结构

```
kml2gpx/
├── kml2gpx/
│   ├── __init__.py     # 对外 API
│   ├── __main__.py     # python -m kml2gpx
│   ├── cli.py          # 命令行参数
│   ├── converter.py    # KML 解析 + GPX 生成
│   └── simplify.py     # Douglas-Peucker 抽稀
├── examples/example.kml
├── tests/test_converter.py
├── pyproject.toml
└── README.md
```

## 测试

```bash
cd kml2gpx
PYTHONPATH=. python3 -m unittest discover -s tests -v
```

## 许可

MIT，见 `LICENSE`。
