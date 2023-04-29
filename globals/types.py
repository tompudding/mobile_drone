import math
import os
from functools import total_ordering
import pymunk


class Point(object):
    def __init__(self, x=None, y=None):
        self.x = x
        self.y = y
        self.iter_pos = 0

    def __add__(self, other_point):
        return Point(self.x + other_point.x, self.y + other_point.y)

    def __sub__(self, other_point):
        return Point(self.x - other_point.x, self.y - other_point.y)

    def __mul__(self, other_point):
        if isinstance(other_point, Point):
            return Point(self.x * other_point.x, self.y * other_point.y)
        else:
            return Point(self.x * other_point, self.y * other_point)

    def __div__(self, factor):
        try:
            return Point(self.x / factor.x, self.y / factor.y)
        except AttributeError:
            return Point(self.x / factor, self.y / factor)

    def __truediv__(self, factor):
        try:
            return Point(self.x / factor.x, self.y / factor.y)
        except AttributeError:
            return Point(self.x / factor, self.y / factor)

    def __getitem__(self, index):
        return (self.x, self.y)[index]

    def __setitem__(self, index, value):
        setattr(self, ("x", "y")[index], value)

    def __iter__(self):
        return self

    def __repr__(self):
        return str(self)

    def __str__(self):
        return "(%.2f,%.2f)" % (self.x, self.y)

    def __len__(self):
        return 2

    @total_ordering
    def __lt__(self, other):
        try:
            if other.x < self.x:
                return True
            return other.y < self.y
        except AttributeError:
            raise TypeError(f"'<' not supported between instances of {type(self)} and {type(other)}")

    def __eq__(self, other):
        try:
            return self.x == other.x and self.y == other.y
        except AttributeError:
            return False

    def __hash__(self):
        return int(self.x) << 16 | int(self.y)

    def to_float(self):
        return Point(float(self.x), float(self.y))

    def to_int(self):
        return Point(int(self.x), int(self.y))

    def __next__(self):
        try:
            out = (self.x, self.y)[self.iter_pos]
            self.iter_pos += 1
        except IndexError:
            self.iter_pos = 0
            raise StopIteration
        return out

    def length(self):
        return math.sqrt(self.x ** 2 + self.y ** 2)

    def distance_heuristic(self, other):
        # return (other-self).diaglength()
        diff = other - self
        return (abs(diff.x) + abs(diff.y)) * 20
        # return diff.x**2 + diff.y**2

    def diaglength(self):
        return max(abs(self.x), abs(self.y))


class Directories:
    def __init__(self, base):
        self.resource = base
        for name in "sprites", "foreground", "computer", "cursor":
            setattr(self, name, os.path.join(base, name))


class Segment(pymunk.Segment):
    def __init__(self, body, a, b, radius):
        super().__init__(body, tuple(a), tuple(b), radius)


class Body(pymunk.Body):
    @property
    def position(self):
        return super().position

    @position.setter
    def position(self, a):
        super(Body, self.__class__).position.fset(self, tuple(a))

    def apply_impulse_at_local_point(self, direction):
        return super().apply_impulse_at_local_point(tuple(direction))


# def create_segment(body, a, b, radius):
#     # The newest version of pymunk seems to insist on args being tuples
#     return seg_wrapper(pymunk.Segment(body, tuple(a), tuple(b), radius)
