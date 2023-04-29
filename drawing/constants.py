import numpy
import math


class DrawLevels:
    grid = 0
    ui = 4000
    text = 5000


full_tc = numpy.array([(0, 0), (0, 1), (1, 1), (1, 0)], numpy.float32)


class colours:
    dark_green = (0, 0.5, 0, 1)
    light_green = (0.5, 1, 0.5, 1)
    white = (1, 1, 1, 1)
    red = (1, 0, 0, 1)
    green = (0, 1, 0, 1)
    blue = (0, 1, 1, 1)
    yellow = (1, 1, 0, 1)

    class c64:
        foreground = (0.625, 0.625, 1.0, 1)
        background = (0.25, 0.25, 0.875, 1)


def daylight(t):
    # Direction will be
    r = 10
    b = math.pi * 3 / 8
    t = float(t % 10000) / 10000
    if t < 0.5:
        a = t * math.pi * 2
        z = math.sin(a) * r
        p = math.cos(a) * r
        x = math.cos(b) * p
        y = math.sin(b) * p
        r, g, b = (0.7 * math.sin(20 * t / math.pi) for i in (0, 1, 2))
    else:
        x, y, z = (1, 1, 1)
        r, g, b = (0, 0, 0)

    return (-x, -y, -z), (r, g, b)


def nightlight(t):
    # Direction will be

    return (1, 3, -1), (0.25, 0.25, 0.4)
