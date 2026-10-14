# -*- coding: utf-8 -*-
"""Ramer-Douglas-Peucker 抽稀算法。

与 gpx2kml 中的实现保持同样的思路：把经纬度当作平面坐标，
用点到首尾连线的垂直距离作为判据。这里改为迭代实现，
避免长轨迹递归过深导致栈溢出。
"""

from __future__ import division


class DouglasPeucker(object):
    """按给定容差 epsilon 抽稀点序列。"""

    def __init__(self, epsilon=1e-7):
        self.epsilon = float(epsilon)

    def simplify(self, points):
        """返回抽稀后的点列表。

        要求 points 中的对象至少具有 lon / lat 两个数值属性。
        epsilon <= 0 或点数不足 3 时原样返回。
        """
        points = list(points)
        if self.epsilon <= 0 or len(points) < 3:
            return points

        keep = [False] * len(points)
        keep[0] = True
        keep[-1] = True

        # 显式栈代替递归，栈元素为 (start, end) 闭区间
        stack = [(0, len(points) - 1)]
        while stack:
            start, end = stack.pop()
            if end - start < 2:
                continue

            dmax = 0.0
            index = start
            first = points[start]
            last = points[end]
            for i in range(start + 1, end):
                d = self.perpendicular_distance(points[i], first, last)
                if d > dmax:
                    dmax = d
                    index = i

            if dmax >= self.epsilon:
                keep[index] = True
                stack.append((start, index))
                stack.append((index, end))

        return [p for p, k in zip(points, keep) if k]

    @staticmethod
    def perpendicular_distance(point, line_start, line_end):
        """点到直线（平面近似）的垂直距离。"""
        x0, y0 = point.lon, point.lat
        x1, y1 = line_start.lon, line_start.lat
        x2, y2 = line_end.lon, line_end.lat

        numerator = abs((x2 - x1) * (y1 - y0) - (x1 - x0) * (y2 - y1))
        denominator = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if denominator == 0:
            return ((x0 - x1) ** 2 + (y0 - y1) ** 2) ** 0.5
        return numerator / denominator


def simplify(points, epsilon):
    """便捷函数：DouglasPeucker(epsilon).simplify(points)。"""
    return DouglasPeucker(epsilon).simplify(points)
