import ui
import globals
from globals.types import Point, Segment, Body
import drawing
import pymunk
import cmath
import math
import pygame
import traceback
import random
import enum
import itertools
import os
from dataclasses import dataclass

box_level = 7
ground_level = 2
squirt_level = 3
house_level = 4
drone_level = 8
sf = 1
debug_sprite_name = "resource/sprites/box.png"
phys_scale = 1

offset = 0


def to_world_coords(p):
    return p / globals.scale


def to_screen_coords(p):
    return p * globals.scale


def to_phys_coords(p):
    return p / phys_scale


def from_phys_coords(p):
    return p * phys_scale


class CollisionTypes:
    DRONE = 1
    BOTTOM = 2
    BOX = 3
    WALL = 4
    RECEIVER = 5
    CHARGER = 6


class Directions(enum.IntFlag):
    UP = enum.auto()
    DOWN = enum.auto()
    LEFT = enum.auto()
    RIGHT = enum.auto()


class ViewPos(object):
    follow_threshold = 0
    max_away = Point(100, 20)
    shake_radius = 10

    def __init__(self, point):
        self._pos = point - (globals.screen / globals.scale) * 0.5
        self.no_target()
        self.follow = None
        self.follow_locked = False
        self.t = 0
        self.shake_end = None
        self.shake_duration = 1
        self.shake = Point(0, 0)
        self.last_update = None

    def no_target(self):
        self.target = None
        self.target_change = None
        self.start_point = None
        self.target_time = None
        self.start_time = None

    @property
    def pos(self):
        return self._pos + self.shake

    def set(self, point):
        self._pos = point.to_int()
        self.no_target()

    def screen_shake(self, duration):
        self.shake_end = globals.game_time + duration
        self.shake_duration = float(duration)

    def set_target(self, point, rate=2, callback=None):
        # Don't fuck with the view if the player is trying to control it
        rate /= 4.0
        self.follow = None
        self.follow_start = 0
        self.follow_locked = False
        self.target = point.to_int()
        self.target_change = self.target - self._pos
        self.start_point = self._pos
        self.start_time = globals.game_time
        self.duration = self.target_change.length() / rate
        self.callback = callback
        if self.duration < 200:
            self.duration = 200
        self.target_time = self.start_time + self.duration

    def set_follow_target(self, actor):
        """
        Follow the given actor around.
        """
        self.follow = actor
        self.follow_start = globals.game_time
        self.follow_locked = False

    def has_target(self):
        return self.target is not None

    def skip(self):
        self._pos = self.target
        self.no_target()
        if self.callback:
            self.callback(self.t)
            self.callback = None

    def update(self):
        try:
            return self.update()
        finally:
            self._pos = self._pos.to_int()

    def update(
        self,
    ):
        if self.last_update is None:
            self.last_update = globals.game_time
            return
        self.t = globals.game_time
        elapsed = globals.game_time - self.last_update
        self.last_update = globals.game_time
        t = globals.game_time

        if self.shake_end:
            if globals.game_time >= self.shake_end:
                self.shake_end = None
                self.shake = Point(0, 0)
            else:
                left = (self.shake_end - t) / self.shake_duration
                radius = left * self.shake_radius
                self.shake = Point(random.random() * radius, random.random() * radius)

        if self.follow:
            # We haven't locked onto it yet, so move closer, and lock on if it's below the threshold
            fpos = from_phys_coords(self.follow.body.position) - globals.screen * Point(0, 0.03)
            if not fpos:
                return
            target = fpos - (globals.screen / globals.scale) * 0.5
            diff = Point(*(target - self._pos))
            # print diff.SquareLength(),self.follow_threshold
            direction = diff.direction()

            if abs(diff.x) < self.max_away.x and abs(diff.y) < self.max_away.y:
                adjust = diff * 0.02 * elapsed * 0.06
            else:
                adjust = diff * 0.03 * elapsed * 0.06
            # adjust = adjust.to_int()
            if adjust.x == 0 and adjust.y == 0:
                adjust = direction
            self._pos += adjust
            return

        elif self.target:
            if t >= self.target_time:
                self._pos = self.target
                self.no_target()
                if self.callback:
                    self.callback(t)
                    self.callback = None
            elif t < self.start_time:  # I don't think we should get this
                return
            else:
                partial = float(t - self.start_time) / self.duration
                partial = partial * partial * (3 - 2 * partial)  # smoothstep
                self._pos = (self.start_point + (self.target_change * partial)).to_int()


class Box(object):
    sprite_name = "resource/sprites/box.png"
    mass = 0.01
    density = 12 / 100000
    is_package = False
    receive_time = 5000
    collision_type = CollisionTypes.BOX
    body_type = None
    hack_factor = 0.99

    def __init__(self, parent, bl, tr, density_factor=1):
        self.parent = parent
        # bl, tr = (to_world_coords(x) for x in (bl, tr))
        self.quad = drawing.Quad(globals.quad_buffer)
        self.quad.set_vertices(bl, tr, box_level)
        self.normal_tc = parent.atlas.texture_coords(self.sprite_name)

        self.quad.set_texture_coordinates(self.normal_tc)

        centre = self.quad.get_centre()
        vertices = [tuple(to_phys_coords(Point(*v[:2]) - centre)) for v in self.quad.vertex[:4]]
        # vertices = [vertices[2],vertices[3],vertices[0],vertices[1]]
        self.moment = pymunk.moment_for_poly(self.mass, vertices)
        if self.body_type is None:
            self.body = Body(moment=self.moment)
        else:
            self.body = Body(moment=self.moment, body_type=self.body_type)
        self.body.position = to_phys_coords(self.quad.get_centre().to_float())
        self.body.force = 0, 0
        self.body.torque = 0
        self.body.velocity = 0, 0
        self.body.angular_velocity = 0
        # print(self.body.position,self.body.velocity)
        # print(vertices)
        self.shape = pymunk.Poly(self.body, vertices)
        self.shape.density = self.density * density_factor
        self.shape.friction = 0.2
        self.shape.elasticity = 0.5
        self.shape.collision_type = self.collision_type
        self.shape.parent = self
        globals.space.add(self.body, self.shape)
        self.in_world = True

    def update(self):
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(self.shape.get_vertices()):
            vertices[(4 - i) & 3] = from_phys_coords(v.rotated(self.body.angle) + self.body.position)

        self.quad.set_all_vertices(vertices, box_level)

    def delete(self):
        self.quad.delete()
        globals.space.remove(self.body, self.shape)
        self.in_world = False


class Package(Box):
    is_package = True
    collision_type = CollisionTypes.BOX
    max_damage = 100
    explosive = False

    sprite_size_lookup = {
        Point(40, 40): "box_40_40.png",
        Point(50, 10): "box_50_10.png",
        Point(50, 50): "box_50_50.png",
        Point(30, 30): "box_30_30.png",
    }

    def __init__(self, parent, bl, tr, info):
        size = tr - bl
        try:
            sprite_name = self.sprite_size_lookup[size]
        except KeyError:
            print("No box for size", size)
            sprite_name = self.sprite_size_lookup[Point(40, 40)]

        self.sprite_name = f"resource/sprites/{sprite_name}"
        super().__init__(parent, bl, tr, density_factor=info.density)
        self.id = info.target
        self.fragility = info.fragility
        self.max_speed = info.max_speed
        self.contents = info.contents
        self.collision_impulse = Point(0, 0)
        self.on_receiver = None
        self.last_update = None
        self.damage = 0
        self.highlights = [drawing.Line(globals.line_buffer_highlights) for i in range(4)]
        for line in self.highlights:
            line.set_colour((1, 1, 0, 1))
            line.disable()
        # self.last_package_start = 0
        self.highlighted = False

    def set_highlight(self, value):
        if self.highlighted == value:
            return

        self.highlighted = value
        for line in self.highlights:
            line.enable() if value else line.disable()

    def jostle(self, amount):
        self.damage += amount * self.fragility * 2
        if self.damage > self.max_damage and self.explosive:
            # TODO: Something for explosive boxes?
            pass

        self.parent.update_jostle(self)

    def jostle_amount(self):
        return min(self.damage / self.max_damage, 1)

    def anchor_points(self):
        orig_vertices = self.shape.get_vertices()
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(orig_vertices):
            vertices[i] = (i, v.rotated(self.body.angle) + self.body.position)

        # We want the one that's most left and most up, and the one that's most right and most up
        vertices.sort(key=lambda x: -x[1][1])
        output = [orig_vertices[vertices[0][0]], orig_vertices[vertices[1][0]]]
        output = [p * 0.8 for p in output]

        if vertices[0][1][0] < vertices[1][1][0]:
            self._anchor_points = output
        else:
            self._anchor_points = output[::-1]
        return self._anchor_points

    def mark_on_receiver(self, on_receiver):
        if not on_receiver:
            if self.on_receiver is not None:
                # We should credit the player with any time it's spent on this receiver
                receive_time = globals.game_time - self.on_receiver
                if self.parent.package_start:
                    self.parent.package_start += receive_time

            self.on_receiver = None

            return

        if self.on_receiver is None:
            self.on_receiver = globals.game_time

    def get_speed(self):
        # return self.body.velocity.length

        return 1000 * ((self.body.velocity.length / 1000) ** 2)

    def update(self):
        if self.last_update is None:
            self.last_update = globals.game_time
            return

        super().update()

        if self.highlighted:
            orig_vertices = self.shape.get_vertices()
            vertices = [0, 0, 0, 0]
            for i, v in enumerate(orig_vertices):
                vertices[i] = v.rotated(self.body.angle) + self.body.position

            for i in range(len(vertices)):
                self.highlights[i].set_vertices(vertices[i], vertices[(i + 1) % 4], 8)

        if self.on_receiver is not None:
            receive_time = globals.game_time - self.on_receiver
            if receive_time > self.receive_time:
                self.parent.package_delivered(self)
                self.on_receiver = None

            # else:
            # We don't count the time that the package is on the right receiver toward the delivery time
            # if self.parent.package_start is not None:
            #    extra = receive_time - self.last_package_start
            #    self.last_package_start = receive_time
            #    self.parent.package_start += extra

    def delete(self):
        super().delete()
        for line in self.highlights:
            line.delete()

    def enable(self):
        super().enable
        if self.highlighted:
            for line in self.highlights:
                line.enable()

    def disable(self):
        for line in self.highlights:
            line.disable()


class Receiver(Box):
    sprite_name = "resource/sprites/receiver.png"
    name_name = "resource/sprites/receiver_%d.png"
    mass = 0.01
    density = 12 / 100000
    is_package = False
    collision_type = CollisionTypes.RECEIVER
    body_type = pymunk.Body.STATIC

    def __init__(self, parent, pos, id):
        bl = Point(pos, 0)
        tr = bl + Point(40, 10)

        super().__init__(parent, bl, tr)

        self.id = id


class Charger(Box):
    sprite_name = "resource/sprites/charger.png"
    mass = 0.01
    density = 12 / 100000
    is_package = False
    collision_type = CollisionTypes.CHARGER
    body_type = pymunk.Body.STATIC

    def __init__(self, parent, pos, id):
        bl = Point(pos, 0)
        tr = bl + Point(40, 10)

        super().__init__(parent, bl, tr)

        self.id = id


class StaticBox(Box):
    mass = 0.01
    density = 12 / 100000
    is_package = False
    body_type = pymunk.Body.STATIC
    size = None

    def __init__(self, parent, pos, y=0):
        bl = Point(pos, y)
        tr = bl + self.size
        super().__init__(parent, bl, tr)


class Fence(StaticBox):
    sprite_name = "resource/sprites/fence.png"
    size = Point(8, 120)


class House(Box):
    sprite_name = "resource/sprites/house.png"
    size = Point(192, 192)

    mass = 0.01
    density = 12 / 100000
    is_package = False
    collision_type = CollisionTypes.WALL
    body_type = pymunk.Body.STATIC
    hack_factor = 0.95

    parts = [
        (Point(0, -60), Point(175, 81), 0),
        (Point(-10, 50), Point(135, 8), math.pi * 0.25),
        (Point(10, 50), Point(135, 8), -math.pi * 0.25),
    ]
    light_data = [(Point(-90, -20), math.pi * 1.2), (Point(90, -20), -math.pi * 0.2)]

    def __init__(self, parent, pos, y=0, hack_factor=0.95):
        bl = Point(pos, y)
        tr = bl + self.size
        self.parent = parent
        density_factor = 1
        # bl, tr = (to_world_coords(x) for x in (bl, tr))
        self.quad = drawing.Quad(globals.quad_buffer)
        self.quad.set_vertices(bl, tr, house_level)
        self.normal_tc = parent.atlas.texture_coords(self.sprite_name)
        hack_fix_tc(self.normal_tc, hack_factor)

        self.quad.set_texture_coordinates(self.normal_tc)

        centre = self.quad.get_centre()
        vertices = [tuple(to_phys_coords(Point(*v[:2]) - centre)) for v in self.quad.vertex[:4]]

        self.bodies = []
        self.moments = []
        self.shapes = []
        self.lights = []
        self.pos = centre

        for pos, size, angle in self.parts:
            bl = pos - size * 0.5
            tr = bl + size

            vertices = [
                pymunk.Vec2d(bl.x, bl.y).rotated(angle),
                pymunk.Vec2d(bl.x, tr.y).rotated(angle),
                pymunk.Vec2d(tr.x, tr.y).rotated(angle),
                pymunk.Vec2d(tr.x, bl.y).rotated(angle),
            ]
            # print(vertices)
            # raise SystemExit()

            moment = pymunk.moment_for_poly(self.mass, vertices)
            if self.body_type is None:
                body = Body(moment=moment)
            else:
                body = Body(moment=moment, body_type=self.body_type)
            body.position = to_phys_coords(self.quad.get_centre().to_float())
            body.force = 0, 0
            body.torque = 0
            body.velocity = 0, 0
            body.angular_velocity = 0

            shape = pymunk.Poly(body, vertices)
            shape.density = self.density * density_factor
            shape.friction = 0.2
            shape.elasticity = 0.5
            shape.collision_type = self.collision_type
            shape.parent = self
            globals.space.add(body, shape)
            self.bodies.append(body)
            self.shapes.append(shape)
            self.moments.append(moment)

        for pos, angle in self.light_data:
            self.lights.append(FixedConeLight(self.pos + pos, angle, 0.7, (1, 1, 1)))

        self.in_world = True

    def update(self):
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(self.shape.get_vertices()):
            vertices[(4 - i) & 3] = from_phys_coords(v.rotated(self.body.angle) + self.body.position)

        self.quad.set_all_vertices(vertices, box_level)

    def delete(self):
        self.quad.delete()
        for body, shape in zip(self.bodies, self.shapes):
            globals.space.remove(body, shape)
        self.in_world = False
        for light in self.lights:
            light.delete()


class Mailbox(House):
    sprite_template = "resource/sprites/mailbox_{num}{flag}.png"
    size = Point(32, 64)
    hack_factor = None

    parts = [
        (Point(0, -16), Point(4, 31), 0),
        (Point(0, 8), Point(15, 6), 0),
    ]
    light_data = []

    def __init__(self, parent, box_num, pos, y=0):
        self.sprite_name = self.sprite_template.format(num=box_num, flag="")
        self.id = box_num
        super().__init__(parent, pos, y, hack_factor=None)

        self.normal_tc = parent.atlas.texture_coords(self.sprite_name)
        self.quad.set_texture_coordinates(self.normal_tc)

        # I can't seem to make it accept my hack factor. So hack the hack!

        self.flag_tc = parent.atlas.texture_coords(self.sprite_template.format(num=box_num, flag=f"_flag"))
        self.current = self.normal_tc
        self.last_flag = globals.time

    def set_flag(self, flag):

        tc = self.flag_tc if flag else self.normal_tc

        if tc is not self.current:
            if globals.game_time - self.last_flag >= 500:
                if flag:
                    globals.sounds.flag.play()
                else:
                    globals.sounds.flag_down.play()
            self.quad.set_texture_coordinates(tc)
            self.current = tc
            self.last_flag = globals.game_time


class Ground(object):
    sprite_name = "resource/sprites/ground.png"

    def __init__(self, parent, height):
        self.parent = parent
        self.height = height

        self.bottom_left = Point(-300, -self.height)
        self.top_right = Point(128 * 100, 0)
        self.top_left = Point(self.bottom_left.x, 0)
        self.bottom_right = Point(self.top_right.x, self.bottom_left.y)
        self.size = self.top_right - self.bottom_left

        self.ceiling_left = self.top_left + Point(0, 1000)
        self.ceiling_right = self.top_right + Point(0, self.ceiling_left.y)

        # Typically we'd do this with a single quad and adjust the texture coords for a repeat, but that gets
        # a bit more complicated with the lighting, so for speed lets just make a quad for each repeat, there won't be that many
        subimage = parent.atlas.subimage(self.sprite_name)
        tc = parent.atlas.texture_coords(self.sprite_name)

        pos = Point(*self.bottom_left)
        self.quads = []

        quad_size = Point(subimage.size.x, self.height)

        while pos.x < self.top_right.x:
            quad = drawing.Quad(globals.quad_buffer, tc=tc)
            quad.set_vertices(pos, pos + quad_size, ground_level)
            self.quads.append(quad)

            pos.x += subimage.size.x - 1

        # The ground is a simple static horizontal line (for now)

        self.segment = Segment(
            globals.space.static_body,
            to_phys_coords(self.top_left),
            to_phys_coords(self.top_right),
            0.0,
        )
        # bottom.sensor = True
        self.segment.collision_type = CollisionTypes.BOTTOM
        self.segment.friction = 1
        self.segment.parent = self
        self.elasticity = 0.3

        globals.space.add(self.segment)
        self.segments = [self.segment]

        for (start, end) in (
            (self.bottom_left + Point(300, 0), self.ceiling_left),
            (self.ceiling_left, self.ceiling_right),
            (self.ceiling_right, self.bottom_right),
        ):
            # We'll also add a wall to the left
            segment = Segment(
                globals.space.static_body,
                to_phys_coords(start),
                to_phys_coords(end),
                0.0,
            )

            segment.collision_type = CollisionTypes.WALL
            segment.friction = 1
            segment.elasticity = 0.5
            segment.parent = self
            globals.space.add(segment)
            self.segments.append(segment)

    def delete(self):
        for segment in self.segments:
            globals.space.remove(segment)


class Sky(object):
    sprite_name = "resource/sprites/sky.png"

    def __init__(self, parent):
        self.parent = parent

        self.bottom_left = Point(-300, 0)
        self.top_right = Point(128 * 100, 1000)
        self.top_left = Point(self.bottom_left.x, 1000)
        self.bottom_right = Point(self.top_right.x, self.bottom_left.y)
        self.size = self.top_right - self.bottom_left

        # Typically we'd do this with a single quad and adjust the texture coords for a repeat, (it really
        # ought to get drawn first too otherwise it's going to look really weird with the lighting, TODO)

        subimage = parent.atlas.subimage(self.sprite_name)
        tc = parent.atlas.texture_coords(self.sprite_name)

        pos = Point(*self.bottom_left)
        self.quads = []

        quad_size = Point(subimage.size.x, self.size.y)

        while pos.x < self.top_right.x:
            quad = drawing.Quad(globals.quad_buffer, tc=tc)
            quad.set_vertices(pos, pos + quad_size, ground_level)
            self.quads.append(quad)

            pos.x += subimage.size.x

        # The ground is a simple static horizontal line (for now)


class Light(object):
    z = 80

    def __init__(self, pos, radius=400, intensity=1):
        self.radius = radius
        self.width = self.height = radius
        self.quad_buffer = drawing.QuadBuffer(4)
        self.quad = drawing.Quad(self.quad_buffer)
        self.shadow_quad = globals.shadow_quadbuffer.new_light()
        self.shadow_index = self.shadow_quad.shadow_index
        self.colour = (1, 1, 1)
        self.intensity = float(intensity)
        self.set_pos(pos)
        self.on = True
        self.append_to_list()

    def append_to_list(self):
        globals.lights.append(self)

    def set_pos(self, pos):
        self.world_pos = pos
        pos = pos
        self.pos = (pos.x, pos.y, self.z)
        box = globals.tile_scale * Point(self.width, self.height)
        bl = Point(*self.pos[:2]) - box * 0.5
        tr = bl + box
        bl = bl.to_int()
        tr = tr.to_int()
        self.quad.SetVertices(bl, tr, 4)

    def update(self, t):
        pass

    @property
    def screen_pos(self):
        p = self.pos
        return (
            (p[0] - globals.game_view.viewpos.full_pos.x) * globals.scale.x,
            (p[1] - globals.game_view.viewpos.full_pos.y) * globals.scale.y,
            self.z,
        )


class NonShadowLight(Light):
    def append_to_list(self):
        globals.non_shadow_lights.append(self)


class ActorLight(object):
    z = 20

    def __init__(self, parent):
        self.parent = parent
        self.quad_buffer = drawing.QuadBuffer(4)
        self.quad = drawing.Quad(self.quad_buffer)
        self.colour = (1, 1, 1)
        self.radius = 10
        self.intensity = 1
        self.on = True
        globals.non_shadow_lights.append(self)

    def Update(self):
        t = globals.time
        self.vertices = [((self.parent.pos + corner * 2)).to_int() for corner in self.parent.corners_euclid]
        self.quad.set_all_vertices(self.vertices, 0)

    @property
    def pos(self):
        return (self.parent.pos.x, self.parent.pos.y, self.z)


class FixedLight(object):
    z = 6

    def __init__(self, pos, size):
        # self.world_pos = pos
        self.pos = pos
        self.size = size
        self.quad_buffer = drawing.QuadBuffer(4)
        self.quad = drawing.Quad(self.quad_buffer)
        self.colour = (0.2, 0.2, 0.2)
        self.on = True
        globals.uniform_lights.append(self)
        self.pos = (self.pos.x, self.pos.y, self.z)
        box = self.size
        bl = Point(*self.pos[:2])
        tr = bl + box
        bl = bl.to_int()
        tr = tr.to_int()
        self.quad.set_vertices(bl, tr, 4)


class ConeLight(object):
    width = 700
    height = 700
    z = 60

    def __init__(self, parent, pos, angle, width, colour):
        self.parent = parent
        self.quad_buffer = drawing.QuadBuffer(4)
        self.quad = drawing.Quad(self.quad_buffer)
        self.shadow_quad = globals.shadow_quadbuffer.new_light()
        self.shadow_index = self.shadow_quad.shadow_index
        self.colour = colour
        self.initial_angle = angle
        self.angle = angle
        self.angle_width = width
        self.on = True
        pos = pos
        self.world_pos = pos
        self.pos = (self.parent.pos.x, self.parent.pos.y, self.z)
        self.refresh()
        globals.cone_lights.append(self)

    def refresh(self):
        box = globals.scale * Point(self.width, self.height)
        bl = Point(*self.pos[:2]) - box * 0.5
        tr = bl + box
        bl = bl.to_int()
        tr = tr.to_int()
        self.quad.set_vertices(bl, tr, 4)

    @property
    def screen_pos(self):
        p = self.parent.pos
        out = (
            (p[0] - globals.game_view.viewpos.pos.x) * globals.scale.x,
            (p[1] - globals.game_view.viewpos.pos.y) * globals.scale.y,
            self.z,
        )
        return out

    def update(self):
        self.pos = self.parent.pos

        self.angle = pymunk.Vec2d(*(globals.mouse_world - self.pos)).angle

        self.refresh()

    def delete(self):
        self.quad.delete()
        globals.cone_lights = [light for light in globals.cone_lights if light is not self]


# This shouldn't be necessary but I don't have time to debug the other lights and the cone light seems to work
class FixedConeLight:
    width = 700
    height = 700
    z = 60

    def __init__(self, pos, angle, width, colour):
        self.quad_buffer = drawing.QuadBuffer(4)
        self.quad = drawing.Quad(self.quad_buffer)
        self.shadow_quad = globals.shadow_quadbuffer.new_light()
        self.shadow_index = self.shadow_quad.shadow_index
        self.colour = colour
        self.initial_angle = angle
        self.angle = angle
        self.angle_width = width
        self.on = True
        self.pos = pos
        self.world_pos = pos
        self.refresh()
        globals.cone_lights.append(self)

    def refresh(self):
        box = globals.scale * Point(self.width, self.height)
        bl = Point(*self.pos[:2]) - box * 0.5
        tr = bl + box
        bl = bl.to_int()
        tr = tr.to_int()
        self.quad.set_vertices(bl, tr, 4)

    @property
    def screen_pos(self):
        p = self.pos
        out = (
            (p[0] - globals.game_view.viewpos.pos.x) * globals.scale.x,
            (p[1] - globals.game_view.viewpos.pos.y) * globals.scale.y,
            self.z,
        )
        return out

    def update(self):
        pass

    def delete(self):
        self.quad.delete()
        globals.cone_lights = [light for light in globals.cone_lights if light is not self]


def hack_fix_tc(tc, hack_factor):
    x_low = min(vertex[0] for vertex in tc)
    x_high = max(vertex[0] for vertex in tc)
    y_low = min(vertex[1] for vertex in tc)
    y_high = max(vertex[1] for vertex in tc)
    for vertex in tc:
        if vertex[0] == x_low:
            vertex[0] *= 1.01
        elif vertex[0] == x_high:
            vertex[0] *= 0.99
        if vertex[1] == y_low:
            vertex[1] *= 1.01
        elif vertex[1] == y_high:
            vertex[1] *= 0.99


class Squirt(object):
    sprite_name = f"resource/sprites/squirt.png"

    def __init__(self, parent, start, vector, duration):
        self.parent = parent
        self.start_pos = start
        self.vector = vector
        self.duration = duration
        self.start_time = globals.time
        self.end_time = self.start_time + duration
        tc = parent.atlas.texture_coords(self.sprite_name)
        hack_fix_tc(tc, 0.99)

        self.quad = drawing.Quad(globals.quad_buffer, tc=tc)

    def update(self):
        if globals.time > self.end_time:
            self.quad.delete()
            return False
        partial = float(globals.time - self.start_time) / self.duration
        vector = self.vector * partial
        size = Point(32.0, 32.0) * partial
        bl = self.start_pos + vector - (size * 0.5)

        # If we're going to go beneath the side
        if bl.y < 0:
            if self.vector.x > 0:
                bl.x -= bl.y
            else:
                bl.x += bl.y
            bl.y = 0

        tr = bl + size
        self.quad.set_vertices(bl, tr, squirt_level)
        self.quad.set_colour((1, 1, 1, 1 - partial ** 2))
        return True

    def delete(self):
        self.quad.delete()


class Drone(object):
    sprite_names = [f"resource/sprites/drone_{i}.png" for i in range(4)]
    up_keys = {pygame.locals.K_w, pygame.locals.K_UP}
    down_keys = {pygame.locals.K_s, pygame.locals.K_DOWN}
    left_keys = {pygame.locals.K_a, pygame.locals.K_LEFT}
    right_keys = {pygame.locals.K_d, pygame.locals.K_RIGHT}
    key_map = {}

    for key in up_keys:
        key_map[key] = Directions.UP

    for key in down_keys:
        key_map[key] = Directions.DOWN

    for key in left_keys:
        key_map[key] = Directions.LEFT

    for key in right_keys:
        key_map[key] = Directions.RIGHT

    vectors = {
        Directions.UP: Point(0, 1),
        Directions.DOWN: Point(0, -1),
        Directions.LEFT: Point(-1, 0),
        Directions.RIGHT: Point(1, 0),
    }
    desired_speed = 50
    max_desired = 20
    min_desired = 3
    grab_range = 20
    power_consumption = 0.01
    charge_rate = 0.01
    power_max = 100
    fps = 25
    frame_delta = 1000 / fps
    min_squirt_distance = 30
    squirt_distance = 80
    max_squirters = 100
    squirt_range = 0.6
    sound_thresh = 100

    def __init__(self, parent, pos):
        self.parent = parent
        self.quad = drawing.Quad(globals.quad_buffer)
        self.tcs = [parent.atlas.texture_coords(sprite_name) for sprite_name in self.sprite_names]

        self.size = parent.atlas.subimage(self.sprite_names[0]).size
        # pos = to_world_coords(pos)
        self.bottom_left = pos
        self.top_right = pos + self.size
        self.turning_enabled = True
        self.grabbed = None
        self.power = 100
        self.on_ground = None
        self.on_charger = None
        self.start_power = 0
        self.thrust = self.max_desired
        self.quad.set_texture_coordinates(self.tcs[0])
        self.left_squirters = []
        self.right_squirters = []
        self.last_squirt = [0, 0]
        self.squirt_delay = [0, 0]
        self.last_sound_change = 0

        self.quad.set_vertices(self.bottom_left, self.top_right, drone_level)

        self.pos = centre = self.quad.get_centre()
        self.lights = [
            # ConeLight(self, pos, 0, 0.7, (0.6, 0.6, 0.6)),
            ConeLight(self, pos, 0, math.pi * 2, (0.4, 0.4, 0.4)),
        ]
        vertices = [tuple(to_phys_coords(Point(*v[:2]) - centre)) for v in self.quad.vertex[:4]]

        self.mass = 0.08
        self.highlighted = None
        self.moment = pymunk.moment_for_poly(self.mass, vertices)
        self.body = Body(mass=self.mass, moment=self.moment)
        self.body.position = to_phys_coords(self.quad.get_centre().to_float())
        self.body.force = 0, 0
        self.body.torque = 0
        self.body.velocity = 0, 0
        self.body.angular_velocity = 0
        # print(self.body.position,self.body.velocity)
        self.shape = pymunk.Poly(self.body, vertices)
        self.shape.friction = 0.5
        self.shape.elasticity = 0.3
        self.shape.collision_type = CollisionTypes.DRONE
        self.shape.parent = self
        globals.space.add(self.body, self.shape)
        self.rotor_sound = None
        self.charge_played = False

        # self.polar_vertices = [cmath.polar(v[0] + v[1] * 1j) for v in self.vertices]

        # For debugging we'll draw a box around the desired pos
        self.desired_quad = drawing.Quad(
            globals.quad_buffer, tc=parent.atlas.texture_coords(debug_sprite_name)
        )
        self.desired_quad.disable()

        # Also for debugging we'll draw some lines for the jet forces
        # self.jet_lines = [Line(self, Point(0, 0), Point(300, 3000)) for i in (0, 1)]
        self.jet_lines = []

        self.desired_shift = Point(0, 0)
        self.desired_pos = from_phys_coords(self.body.position)
        self.desired_field = 0
        self.desired_vector = Point(0, 0)
        self.last_update = None
        self.jets = self.shape.get_vertices()[:2]
        self.reset_forces()
        self.target_rotation = 0
        self.engine = True
        self.soft_off = False
        self.anchors = []
        # Our anchor points are our bottom left and our bottom right

        self.anchor_points = [jet * 0.9 for jet in self.jets]

    def disable_turning(self):
        self.turning_enabled = False
        self.update_desired_vector()
        self.desired_shift[0] = 0
        self.desired_pos = (0, self.desired_pos[1])
        print("YO")

    def in_grab_range(self, distance):
        return distance < self.grab_range

    def grab(self, item):
        self.grabbed = item
        self.anchors = []
        self.joints = []
        for our_anchor, item_anchor in zip(self.anchor_points, item.anchor_points()):
            joint = pymunk.SlideJoint(
                self.body, item.body, anchor_a=our_anchor, anchor_b=item_anchor, min=0, max=self.grab_range
            )
            self.joints.append(joint)
            globals.space.add(joint)
            self.anchors.append(
                Line(
                    self,
                    from_phys_coords(self.body.local_to_world(our_anchor)),
                    from_phys_coords(item.body.local_to_world(item_anchor)),
                    colour=(1, 1, 1, 1),
                )
            )
            globals.sounds.anchor.play()
        # We also add an unseen stabilization joint
        # stable = pymunk.SlideJoint(self.body, item.body, (0, 0), (0, 0), 0, self.grab_range)
        # self.joints.append(stable)
        # globals.space.add(stable)

    def release(self):
        if not self.grabbed:
            return
        for joint in self.joints:
            globals.space.remove(joint)
        for anchor in self.anchors:
            anchor.delete()

        self.anchors = []
        self.grabbed = None
        self.joints = []
        self.parent.release(self)
        globals.sounds.release.play()

    def enable_turning(self):
        self.turning_enabled = True
        self.update_desired_vector()

    def select_rotor_sound(self):
        if globals.game_time - self.last_sound_change < self.sound_thresh:
            return
        sound = None
        if self.engine:
            # speed = self.body.velocity.length
            # if speed > 140:
            #     sound = globals.sounds.rotors_fast
            # elif speed > 80:
            #     sound = globals.sounds.rotors_normal
            # else:
            sound = globals.sounds.rotors_slow

        if sound is not self.rotor_sound:
            if self.rotor_sound:
                self.rotor_sound.stop()
            self.rotor_sound = sound
            if self.rotor_sound:
                self.rotor_sound.play(loops=-1)
            self.last_sound_change = globals.game_time

    def update(self):
        self.pos = self.quad.get_centre()

        for light in self.lights:
            light.update()
        if self.last_update is None:
            self.last_update = globals.game_time
            return

        self.select_rotor_sound()
        if self.engine:
            for light in self.lights:
                light.on = True
            tc = int((globals.game_time // self.frame_delta) % len(self.tcs))

            tc = self.tcs[tc]
            self.quad.set_texture_coordinates(tc)

            # We also squirt air out

            for i in range(2):
                squirter_list = (self.left_squirters, self.right_squirters)[i]
                jet = self.anchor_points[i]
                last_squirt = self.last_squirt[i]
                squirt_delay = self.squirt_delay[i]

                if (
                    len(squirter_list) < self.max_squirters
                    and (globals.game_time - last_squirt) > squirt_delay
                ):
                    jet_world = from_phys_coords(self.body.local_to_world(jet))
                    angle = self.body.angle - (math.pi * 0.5) + (random.random() - 0.5) * self.squirt_range
                    distance = random.random() * self.squirt_distance + self.min_squirt_distance
                    vector = cmath.rect(distance, angle)
                    vector = Point(vector.real, vector.imag)
                    start = Point(*jet_world)
                    squirter_list.append(Squirt(self.parent, start, vector, 1000))
                    self.last_squirt[i] = globals.game_time

        self.left_squirters = [squirt for squirt in self.left_squirters if squirt.update() == True]
        self.right_squirters = [squirt for squirt in self.right_squirters if squirt.update() == True]

        if self.on_ground is not None:
            on_ground_time = globals.game_time - self.on_ground
            if on_ground_time > 1000:
                self.engine = False
                self.on_ground = None
                self.soft_off = True

        vertices = [0, 0, 0, 0]
        for i, v in enumerate(self.shape.get_vertices()):
            vertices[(4 - i) & 3] = from_phys_coords(v.rotated(self.body.angle) + self.body.position)

        if self.forces is not None:
            # Debug draw the lines
            # for force, jet, line in zip(self.forces, vertices[::3], self.jet_lines):
            #    line.set(start=jet, end=jet - force)
            # Instead of debug lines we'll set the rate of squirts
            for i, force in enumerate(self.forces):
                length = pymunk.Vec2d(*force).length
                # Also factor in the thrust
                thrust_ratio = 0.1 + (self.thrust / 20) * 0.9
                length *= thrust_ratio
                if length == 0:
                    length = 1
                try:
                    self.squirt_delay[i] = 200 / length
                except ZeroDivisionError:
                    self.squirt_delay[i] = 200

        self.quad.set_all_vertices(vertices, box_level)

        elapsed = (globals.game_time - self.last_update) * globals.time_step
        self.last_update = globals.game_time

        if self.grabbed:
            # show the current package speed
            # speed = min(self.grabbed.avg_speed() / self.grabbed.max_speed, 1)
            speed = min(self.grabbed.get_speed() / self.grabbed.max_speed, 1)
            # speed = min(self.grabbed.body.velocity.length / self.grabbed.max_speed, 1)
            self.parent.top_bar.max_speed_bar.set_bar_level(speed)

            overspeed = self.grabbed.get_speed() - self.grabbed.max_speed
            if overspeed > 0:
                self.grabbed.jostle(overspeed * 5 * elapsed / 1000)
        else:
            # We can check all the extant packages to see if they need highlighting
            self.highlighted = None
            for package in self.parent.packages:
                # It must be directly beneath us
                diff = from_phys_coords(self.body.world_to_local(tuple(package.body.position)))
                if abs(diff.x) < self.size.x * 0.5 and diff.y < 0:
                    # We're pointed at it, but how close are we? We'll test the point that's from the drone's
                    # centre and steps grab_distance toward the package
                    diff = (package.body.position - self.body.position).scale_to_length(self.grab_range)
                    point = diff + self.body.position

                    info = package.shape.point_query(point)
                    if info.distance < 0:
                        self.highlighted = package
                        break
            for package in self.parent.packages:
                package.set_highlight(True if package is self.highlighted else False)

        if self.on_charger is not None:
            charge_time = globals.game_time - self.on_charger - 1000
            if charge_time > 0:
                if not self.charge_played:
                    globals.sounds.charging.play()
                    self.charge_played = True
                charge_amount = charge_time * self.charge_rate
                new_power = self.start_power + charge_amount
                self.add_power(new_power - self.power)

        if self.desired_field == 0:
            # decay the desired pos
            self.desired_vector = Point(0, 0)
            if self.desired_shift.length() > self.min_desired:
                self.desired_vector = self.desired_shift * -0.2
            else:
                self.desired_shift = Point(0, 0)

        self.desired_shift += self.desired_vector * self.desired_speed * (elapsed / 1000)
        desired_length = self.desired_shift.length()
        if self.desired_shift.length() > self.thrust:
            scale_factor = self.thrust / desired_length
            self.desired_shift *= scale_factor
        self.desired_pos = from_phys_coords(self.body.position) + self.desired_shift
        self.desired_quad.set_vertices(
            self.desired_pos - Point(4, 4), self.desired_pos + Point(4, 4), drone_level + 1
        )

        # pay for our fuel
        fuel = Point(*self.force).length() * (elapsed / 1000)
        self.add_power(-fuel * self.power_consumption)

        self.reset_forces()

        if not self.turning_enabled and self.body.position[1] > 100:
            self.enable_turning()

        if self.grabbed:
            for our_anchor, item_anchor, anchor in zip(
                self.anchor_points, self.grabbed._anchor_points, self.anchors
            ):
                anchor.set(
                    from_phys_coords(self.body.local_to_world(our_anchor)),
                    from_phys_coords(self.grabbed.body.local_to_world(item_anchor)),
                )

    def mark_on_charger(self, on_charger):
        if not on_charger:
            self.on_charger = None
            if self.charge_played:
                globals.sounds.charging.stop()
                self.charge_played = False
            return

        if self.on_charger is None:
            self.on_charger = globals.game_time
            self.start_power = self.power

    def add_power(self, amount):
        self.power += amount
        if self.power <= 0:
            self.power = 0
            for light in self.lights:
                light.on = False
            self.engine = False
        if self.power > self.power_max:
            self.power = self.power_max
        self.parent.top_bar.power_bar.set_bar_level(self.power / self.power_max)

    def calculate_forces(self):
        if not self.engine:
            self.forces = ((0, 0), (0, 0))
            self.force = (0, 0)
            return

        mass = self.body.mass
        anti_grav = -globals.space.gravity * mass * 0.5
        if 0 and self.grabbed:
            # We also have to work out the gravity on the grabbed object
            anti_grabbed = -globals.space.gravity * self.grabbed.body.mass * 0.5
            try:
                magnitude = self.grabbed.collision_impulse.length() / globals.dt
            except TypeError:
                magnitude = self.grabbed.collision_impulse.length / globals.dt

            anti_grabbed -= (self.grabbed.collision_impulse / globals.dt) * 0.5
            # HAX: this magnitude can grow too large sometimes
            if magnitude < 15:
                anti_grav += anti_grabbed
            self.grabbed.collision_impulse = Point(0, 0)

        desired = self.desired_shift - self.body.velocity * 0.1 / phys_scale

        # If we want to go horizontal, we're going to have to try to get a rotation to make that happen
        # We choose the amount of rotation based on how fast they want to go, with a max of 45 degrees
        self.target_rotation = math.pi * 0.5 * (desired.x / self.max_desired)

        # Then the differential in our jets is based on the size of the difference between the target rotation and our current rotation

        desired_rotation = self.target_rotation - self.body.angle

        coeff_range = 0.3
        coeff = 1 + (coeff_range * desired_rotation) / (math.pi * 0.5)

        self.forces = [coeff, 2 - coeff]

        jet_dir = pymunk.Vec2d(0, -1).rotated(self.body.angle)

        # We know that the sum in the y direction of our jets has to be equal to anti_grav + desired

        for i, jet in enumerate(self.jets):
            # That means to choose this force, we need the total force which makes our y component what we want
            magnitude = ((anti_grav + desired)[1]) / jet_dir[1]
            force = jet_dir * magnitude
            self.forces[i] = force * self.forces[i]

        # For the real forces we're going to simply apply two orthoganal forces to the centre of the object to simulate things
        # First the gravity force
        anti_grav *= 2
        grab_factor = 5 if not self.grabbed else 10
        self.force = (desired[0], (anti_grav + desired * grab_factor)[1])

    def reset_forces(self):
        self.forces = None
        self.force = None

        # for line in self.jet_lines:
        #    line.disable()

    def apply_forces(self):
        if self.force is None:
            self.calculate_forces()
        if not self.engine:
            # This might just be turned off for power saving reasons. If it's a soft_off and we're trying to move, turn it back on
            if self.soft_off and self.desired_field != 0 and self.power > 0:
                self.soft_off = False
                self.engine = True
            else:
                return

        force = pymunk.Vec2d(*self.force).rotated(-self.body.angle)
        self.body.apply_force_at_local_point(force, (0, 0))
        elapsed = globals.dt
        desired_angle = -0.5 * ((math.pi * 0.5 * (self.desired_shift.x / self.max_desired)))

        desired_angular_velocity = (desired_angle - self.body.angle) * elapsed * 4000
        if abs(desired_angular_velocity) < 0.05:
            desired_angular_velocity = 0

        self.body.angular_velocity = desired_angular_velocity  # torque

    def update_desired_vector(self):
        self.desired_vector = Point(0, 0)
        if self.desired_field == 0:
            return

        for direction in Directions:
            if self.desired_field & direction:
                vector = self.vectors[direction]
                if not self.turning_enabled:
                    vector.x = 0
                self.desired_vector += vector

    def flying(self):
        return self.desired_field != 0

    def landed(self):
        orig_vertices = self.shape.get_vertices()
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(orig_vertices):
            vertices[i] = v.rotated(self.body.angle) + self.body.position

        # We want the one that's most left and most up, and the one that's most right and most up
        vertices.sort(key=lambda x: x[1])

        return all(vertex[1] < 12 for vertex in vertices[:2])

    def key_down(self, key):
        try:
            direction = self.key_map[key]
        except KeyError:
            return

        self.desired_field |= direction
        self.update_desired_vector()

    def key_up(self, key):
        if key == pygame.locals.K_SPACE:
            self.engine = not self.engine
            if self.power == 0 and self.engine:
                self.engine = False
        try:
            direction = self.key_map[key]
        except KeyError:
            if key in {pygame.locals.K_e}:
                if self.highlighted:
                    if not self.grabbed:
                        self.grab(self.highlighted)
                        self.highlighted.set_highlight(False)
                        self.highlighted = None
                elif self.grabbed:
                    self.release()
                else:
                    # Could play a family fortunes sound here
                    pass
            return

        self.desired_field &= ~direction
        self.update_desired_vector()

    def disable(self):
        for line in itertools.chain(self.jet_lines, self.anchors):
            line.disable()
        self.quad.disable()

    def enable(self):
        for line in itertools.chain(self.jet_lines, self.anchors):
            line.enable()
        self.quad.enable()

    def delete(self):
        for line in itertools.chain(self.jet_lines, self.anchors):
            line.delete()
        self.quad.delete()
        for squirt in itertools.chain(self.left_squirters, self.right_squirters):
            squirt.delete()
        for light in self.lights:
            light.delete()
        globals.space.remove(self.body, self.shape)


class Line(object):
    # TODO: I haven't got lines in world coords working yet. Use a quad for now
    def __init__(self, parent, start, end, colour=(1, 0, 0, 1)):
        self.parent = parent
        self.line = drawing.Line(globals.line_buffer)
        # self.line = drawing.Quad(globals.quad_buffer, tc=parent.atlas.texture_coords(debug_sprite_name))

        self.line.set_colour(colour)

        self.set(start, end)

    def set_start(self, start):
        self.start = start
        self.update()

    def set_end(self, end):
        self.end = end
        self.update()

    def set(self, start, end):
        self.start = start
        self.end = end
        self.update()

    def update(self):
        if self.start and self.end:
            self.line.set_vertices(self.start, self.end, 8)

    def enable(self):
        self.line.enable()

    def disable(self):
        self.line.disable()

    def delete(self):
        self.line.delete()


def call_with(callback, arg):
    def caller(pos):
        return callback(pos, arg)

    return caller


class MainMenu(ui.HoverableBox):
    line_width = 1

    def __init__(self, parent, bl, tr):
        self.border = drawing.QuadBorder(globals.ui_buffer, line_width=self.line_width)
        self.level_buttons = []
        self.high_scores = []
        self.game = parent
        super(MainMenu, self).__init__(globals.screen_root, bl, tr, (0.05, 0.05, 0.05, 1))
        self.text = ui.TextBox(
            self,
            Point(0, 0.8),
            Point(1, 0.95),
            "Mobile Drone",
            3,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.info = ui.TextBox(
            self,
            Point(0, 0.0),
            Point(1, 0.05),
            "Delete stops the music. Escape for main menu",
            1.5,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.border.set_colour(drawing.constants.colours.red)
        self.border.set_vertices(self.absolute.bottom_left, self.absolute.top_right)
        self.border.enable()
        self.quit_button = ui.TextBoxButton(self, "Quit", Point(0.45, 0.1), size=2, callback=self.game.quit)
        self.resume_button = ui.TextBoxButton(self, "Resume", Point(0.7, 0.1), size=2, callback=self.resume)
        self.resume_button.disable()

        self.high_score_header = ui.TextBox(self, Point(0.65, 0.7), Point(0.9, 0.8), "High Score", scale=2)

        pos = Point(0.2, 0.6)
        for i, level in enumerate(parent.levels):
            button = ui.TextBoxButton(
                self,
                f"{i}: {level.name}",
                pos,
                size=2,
                callback=call_with(self.start_level, i),
            )
            self.level_buttons.append(button)
            self.high_scores.append(
                ui.TextBox(
                    self,
                    pos + Point(0.45, 0.00),
                    tr=pos + Point(0.65, 0.05),
                    text=" ",
                    scale=2,
                    colour=drawing.constants.colours.white,
                    alignment=drawing.texture.TextAlignments.CENTRE,
                )
            )

            pos.y -= 0.1

    def resume(self, pos):
        self.game.unpause()
        self.disable()

    def start_level(self, pos, level):
        self.disable()
        self.game.current_level = level
        self.game.init_level()
        # self.parent.stop_throw()
        self.game.unpause()

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            self.border.enable()
        for button in self.level_buttons:
            button.enable()
        super(MainMenu, self).enable()
        for i, score in enumerate(self.high_scores):
            high_score = self.game.high_scores[i]
            if high_score:
                score.set_text(f"{high_score}")
                score.enable()
            else:
                score.disable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.border.disable()
        super(MainMenu, self).disable()
        for score in self.high_scores:
            score.disable()


class GameOver(ui.HoverableBox):
    line_width = 1

    def __init__(self, parent, bl, tr):
        self.border = drawing.QuadBorder(globals.ui_buffer, line_width=self.line_width)
        self.game = parent
        super(GameOver, self).__init__(globals.screen_root, bl, tr, (0, 0, 0, 1))
        self.text = ui.TextBox(
            self,
            Point(0, 0.5),
            Point(1, 0.6),
            "There are no more packages. Rest little one",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.border.set_colour(drawing.constants.colours.red)
        self.border.set_vertices(self.absolute.bottom_left, self.absolute.top_right)
        self.border.enable()
        self.replay_button = ui.TextBoxButton(
            self, "Keep Flying", Point(0.1, 0.1), size=2, callback=self.keep_flying
        )
        self.quit_button = ui.TextBoxButton(self, "Quit", Point(0.7, 0.1), size=2, callback=self.game.quit)

    def keep_flying(self, pos):
        self.game.keep_flying()
        self.disable()

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            self.border.enable()
        super(GameOver, self).enable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.border.disable()
        super(GameOver, self).disable()


@dataclass
class PackageInfo:
    contents: str
    size: Point
    target: int
    max_speed: int
    time: float
    density: float = 1.0
    fragility: float = 1.0


class Level(object):
    disappear = False
    min_distance = 300
    ground_height = 300
    restricted_start = None
    boxes_pos_fixed = False
    infinite = False
    tutorial = False

    prebuilts = [
        PackageInfo(
            contents="Glass", size=Point(40, 40), target=0, density=0.5, max_speed=10, time=30, fragility=4.0
        ),
        PackageInfo(contents="Things", size=Point(40, 40), target=1, max_speed=100, time=20),
        PackageInfo(contents="Wood", size=Point(50, 10), target=2, max_speed=50, density=6, time=20),
        PackageInfo(contents="Lead Bars", size=Point(50, 10), target=2, max_speed=50, density=10, time=20),
        PackageInfo(contents="Feathers", size=Point(50, 50), target=3, max_speed=100, density=0.1, time=15),
    ]

    def get_random_package(self):
        # let's have a 40 % chance of a pre-built
        index = random.randint(1, 12)
        try:
            return self.prebuilts[index]
        except IndexError:
            pass

        return PackageInfo(
            contents=random.choice(
                [
                    "Cheese",
                    "Widgets",
                    "Cabbage",
                    "Live Animals",
                    "Human Hair",
                    "Unicycles",
                    "Cork",
                    "Headphones",
                    "Chewing Gum",
                    "Lasers",
                    "Black Holes",
                    "Candy Floss",
                    "Marmite",
                ]
            ),
            size=random.choice(list(Package.sprite_size_lookup.keys())),
            target=0,
            max_speed=random.randint(10, 100),
            time=random.randint(12, 30),
        )


class TutorialLevel(Level):
    text = "Tutorial"
    name = "Tutorial"
    subtext = " "
    tutorial = True
    start_pos = Point(100 + offset, 50)
    items = [
        PackageInfo(contents="Things", size=Point(40, 40), target=0, max_speed=100, time=20),
    ]
    receivers = [200]
    chargers = [20]
    fences = []
    min_distance = 200
    min_force = 50


class LevelOne(Level):
    text = "Another Day another Package"
    name = "Deliver Items"
    subtext = "Be careful not to break things!"
    start_pos = Point(100 + offset, 50)
    items = [
        PackageInfo(contents="Plastic Minis", size=Point(40, 40), target=0, max_speed=100, time=20),
        PackageInfo(
            contents="Glass", size=Point(40, 40), target=1, density=0.5, max_speed=10, time=35, fragility=4.0
        ),
        PackageInfo(contents="Wood", size=Point(50, 10), target=2, max_speed=50, density=6, time=35),
        PackageInfo(contents="Feathers", size=Point(50, 50), target=3, max_speed=100, density=0.1, time=24),
        PackageInfo(
            contents="TTRPG Books",
            size=Point(30, 30),
            target=2,
            max_speed=50,
            density=5.5,
            time=60,
            fragility=2.0,
        ),
    ]
    receivers = [600 + i * 500 for i in range(5)]
    chargers = [20]
    fences = [400]
    min_distance = 200
    min_force = 50


class LevelTwo(Level):
    text = "There's Always Another Package"
    name = "Free Flying"
    infinite = True
    subtext = "In Delivery, Deliverance"
    start_pos = Point(100 + offset, 50)
    items = []
    receivers = [600 + i * 500 for i in range(5)]
    chargers = [20]
    fences = [400]
    min_distance = 200
    min_force = 50


class TimeOfDay(object):
    night_light_dir = (1, 3, -5)
    night_light_colour = tuple((c * 0.2 for c in (0.25, 0.25, 0.4)))

    def __init__(self, t):
        self.last = None
        self.set(t)
        self.speed = 0

    def set(self, t):
        self.t = t
        for obj in globals.daytime_dependent:
            obj.set_time(self.t)

    def daylight(self):
        # Direction will be
        a_k = 0.2
        d_k = 0.4
        r = 1000
        b = -1.5
        t = (self.t + 0.75) % 1.0
        a = t * math.pi * 2
        z = math.sin(a) * r
        p = math.cos(a) * r
        x = math.cos(b) * p
        y = math.sin(b) * p
        if t < 0.125:
            # dawn
            colour = [d_k * math.sin(40 * t / math.pi) for i in (0, 1, 2)]
            ambient = [a_k * math.sin(40 * t / math.pi) for i in (0, 1, 2)]
        elif t < 0.375:
            # daylight
            colour = (d_k, d_k, d_k)
            ambient = (a_k, a_k, a_k)
        elif t < 0.5:
            # dusk
            colour = (d_k * math.sin(40 * (t + 0.25) / math.pi) for i in (0, 1, 2))
            ambient = [a_k * math.sin(40 * (t + 0.25) / math.pi) for i in (0, 1, 2)]
        else:
            x, y, z = (1, 1, 1)
            colour = (0, 0, 0)
            ambient = (0, 0, 0)

        return (-x, -y, -z), colour, ambient, ambient[0] / a_k

    def ambient(self):
        t = (self.t + 0.75) % 1.0
        return (0.5, 0.5, 0.5)

    def nightlight(self):
        # Direction will be

        return self.night_light_dir, self.night_light_colour

    def update(self, t):
        if not self.last:
            self.last = t
        if self.speed:
            elapsed = t - self.last
            self.last = t
            new_val = (self.t + self.speed * elapsed / 1000.0) % 1.0
            self.set(new_val)

    def set_speed(self, val):
        self.speed = val


def format_time(t):
    seconds = t // 1000
    ms = t % 1000
    colour = drawing.constants.colours.white if t > 0 else drawing.constants.colours.red
    return f"{seconds:4d}.{ms:03d}", colour


class Tutorial:
    stages = [
        "Use WASD or the Arrow Keys to fly around",
        "Press space to turn your engines off and on again",
        "Fly onto the charging platform and turn off your engines to regain power",
        "Pick up a package by flying close over it and clicking on the top of it with the left mouse",
        "Release it by clicking anywhere with the left mouse",
        "Adjust your thrust with the scroll wheel or the slider",
        "Deliver it to the target platform. Going too fast or collisions will damage it and reduce your score, as will being late",
        "Well done",
    ]

    def __init__(self, parent):
        self.parent = parent
        self.stage = 0
        self.text = ui.TextBox(
            globals.screen_root,
            Point(0, 0.4),
            Point(1, 0.5),
            self.stages[self.stage],
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.text.enable()
        self.bitfield = 0
        self.thrust_field = 0
        self.engines_toggled = False
        self.anchor_disabled = True

    def thrust_adjust(self, amount):
        if self.stage != 5:
            return
        if amount > 0:
            self.thrust_field |= 1
        if amount < 0:
            self.thrust_field |= 2

    def update(self):
        if self.stage == 0:
            self.bitfield |= self.parent.drone.desired_field
            if int(self.bitfield) == 0xF:
                self.bitfield = 0
                return self.next_stage()
        if self.stage == 1:
            if not self.parent.drone.engine and not self.engines_toggled:
                self.engines_toggled = True
                return
            if self.parent.drone.engine and self.engines_toggled:
                return self.next_stage()
        if self.stage == 2:
            if self.parent.drone.power == 100:
                return self.next_stage()
        if self.stage == 3:
            if self.parent.drone.grabbed:
                return self.next_stage()
        if self.stage == 4:
            if not self.parent.drone.grabbed:
                self.parent.enable_controls()
                return self.next_stage()
        if self.stage == 5:
            if self.thrust_field == 3:
                return self.next_stage()

        return False

    def next_stage(self):
        self.stage += 1
        if self.stage == 2:
            self.parent.drone.power = 80
        if self.stage == 3:
            self.anchor_disabled = False
        if self.stage == 4:
            # disable the controls in case the user tries to take the package
            self.parent.disable_controls()
        if self.stage == 5:
            self.parent.package_start = globals.game_time + (self.parent.current_info.time * 1000)
        if self.stage >= len(self.stages):
            return True
        self.text.set_text(self.stages[self.stage])
        return False

    def delete(self):
        self.text.delete()

    def enable(self):
        self.text.enable()

    def disable(self):
        self.text.disable()


class GameView(ui.RootElement):
    text_fade_duration = 1000
    next_package_format = "Number {number}"

    def __init__(self):
        # self.atlas = globals.atlas = drawing.texture.TextureAtlas('tiles_atlas_0.png','tiles_atlas.txt')
        # globals.ui_atlas = drawing.texture.TextureAtlas('ui_atlas_0.png','ui_atlas.txt',extra_names=False)
        super(GameView, self).__init__(Point(0, 0), Point(128 * 100, 1000))
        self.timeofday = TimeOfDay(0.5)
        self.viewpos = ViewPos(TutorialLevel.start_pos)
        self.mouse_pos = Point(0, 0)
        pygame.mixer.music.load(os.path.join(globals.dirs.music, "music.ogg"))
        pygame.mixer.music.set_volume(0.3)
        pygame.mixer.music.play(loops=-1)

        self.pause_offset = 0
        self.pause_start = None
        self.game_time_diff = 0
        self.current_info = None

        # self.donkey = ui.TextBox(
        #     self,
        #     self.get_relative(Point(100, 100)),
        #     self.get_relative(Point(250, 200)),
        #     "DONKEY",
        #     2,
        #     colour=drawing.constants.colours.white,
        #     textType=drawing.texture.TextTypes.GRID_RELATIVE,
        #     alignment=drawing.texture.TextAlignments.CENTRE,
        # )

        # For the ambient light
        self.atlas = drawing.texture.TextureAtlas("atlas_0.png", "atlas.txt")
        self.ground = Ground(self, TutorialLevel.ground_height)
        self.sky = Sky(self)
        self.light = drawing.Quad(globals.light_quads)
        self.light.set_vertices(self.ground.bottom_left, self.ground.ceiling_right, 0)

        self.top_bar = ui.Box(
            parent=globals.screen_root, pos=Point(0, 0.9), tr=Point(1, 1), colour=(0.2, 0.2, 0.2, 0.7)
        )
        self.bottom_bar = ui.Box(
            parent=globals.screen_root, pos=Point(0, 0), tr=Point(1, 0.07), colour=(0.2, 0.2, 0.2, 0.7)
        )
        self.thrust_points = [(offset, i) for i, offset in enumerate(range(4, 21))]
        self.thrust_slider = ui.Slider(
            self.bottom_bar,
            Point(0.01, 0.3),
            Point(0.3, 0.9),
            self.thrust_points,
            callback=self.thrust_callback,
        )
        self.thrust_slider.text = ui.TextBox(
            self.bottom_bar,
            Point(0.01, 0),
            Point(0.3, 0.28),
            "Thrust",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.thrust_slider.index = int(len(self.thrust_points) // 2)
        self.thrust_slider.set_pointer()
        self.thrust_slider.enable()
        self.next_level_menu = None
        self.game_over = None
        self.controls = True

        self.bottom_bar.time_text = ui.TextBox(
            self.bottom_bar,
            Point(0.41, 0),
            Point(0.41 + 0.2, 0.28),
            "Package Time",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.bottom_bar.timer = ui.TextBox(
            self.bottom_bar,
            Point(0.41, 0.3),
            Point(0.41 + 0.2, 0.88),
            " ",
            3,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.bottom_bar.score_num_text = ui.TextBox(
            self.bottom_bar,
            Point(0.71, 0.3),
            Point(0.71 + 0.2, 0.88),
            "0",
            3,
            colour=drawing.constants.colours.yellow,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.bottom_bar.score_text = ui.TextBox(
            self.bottom_bar,
            Point(0.71, 0),
            Point(0.71 + 0.2, 0.28),
            "Score",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.help_text = ui.TextBox(
            globals.screen_root,
            Point(0, 0),
            Point(1, 0.1),
            "Grab a package to start",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.top_bar.power_bar = ui.PowerBar(
            self.top_bar,
            pos=Point(0.01, 0.4),
            tr=Point(0.12, 0.9),
            level=1,
            bar_colours=(
                drawing.constants.colours.red,
                drawing.constants.colours.yellow,
                drawing.constants.colours.green,
            ),
            border_colour=drawing.constants.colours.white,
        )
        self.top_bar.power_bar.text = ui.TextBox(
            self.top_bar,
            Point(0.01, 0),
            Point(0.12, 0.36),
            "Power",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.top_bar.contents_value = ui.TextBox(
            self.top_bar,
            Point(0.13, 0.4),
            Point(0.13 + 0.2, 0.8),
            " ",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.top_bar.contents = ui.TextBox(
            self.top_bar,
            Point(0.13, 0),
            Point(0.13 + 0.2, 0.36),
            "Contents",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.top_bar.max_speed_bar = ui.PowerBar(
            self.top_bar,
            pos=Point(0.34, 0.4),
            tr=Point(0.34 + 0.2, 0.9),
            level=0,
            bar_colours=(
                drawing.constants.colours.blue,
                drawing.constants.colours.yellow,
                drawing.constants.colours.red,
            ),
            border_colour=drawing.constants.colours.blue,
        )

        self.top_bar.max_speed = ui.TextBox(
            self.top_bar,
            Point(0.34, 0),
            Point(0.34 + 0.2, 0.36),
            "Max Speed",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.top_bar.jostle_bar = ui.PowerBar(
            self.top_bar,
            pos=Point(0.55, 0.4),
            tr=Point(0.55 + 0.2, 0.9),
            level=0,
            bar_colours=(
                drawing.constants.colours.blue,
                drawing.constants.colours.yellow,
                drawing.constants.colours.red,
            ),
            border_colour=drawing.constants.colours.red,
        )

        self.top_bar.jostle_text = ui.TextBox(
            self.top_bar,
            Point(0.55, 0),
            Point(0.55 + 0.2, 0.36),
            "Jostle Meter",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        self.next_package_text = ui.TextBox(
            self.top_bar,
            Point(0.76, 0.4),
            Point(0.76 + 0.2, 0.8),
            " ",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.top_bar.jostle_text = ui.TextBox(
            self.top_bar,
            Point(0.76, 0),
            Point(0.76 + 0.2, 0.36),
            "Address",
            2,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )

        # self.ground = None
        self.drone = None
        self.packages = []
        self.receivers = []
        self.houses = []
        self.fences = []
        self.chargers = []
        self.mailbox_lookup = {}
        self.tutorial = None

        self.level_text = None
        self.score = 0

        self.bottom_handler = globals.space.add_collision_handler(CollisionTypes.DRONE, CollisionTypes.BOTTOM)
        self.box_handlers = [
            globals.space.add_collision_handler(CollisionTypes.BOX, item_type)
            for item_type in (
                CollisionTypes.BOTTOM,
                CollisionTypes.DRONE,
                CollisionTypes.BOX,
                CollisionTypes.WALL,
                CollisionTypes.RECEIVER,
                CollisionTypes.CHARGER,
            )
        ]

        for handler in self.box_handlers:
            handler.post_solve = self.box_post_solve
        self.box_ground_handler = globals.space.add_collision_handler(
            CollisionTypes.BOX, CollisionTypes.BOTTOM
        )
        self.charger_handler = globals.space.add_collision_handler(
            CollisionTypes.DRONE, CollisionTypes.CHARGER
        )

        self.receiver_handler = globals.space.add_collision_handler(
            CollisionTypes.BOX, CollisionTypes.RECEIVER
        )

        # self.cup_handler = globals.space.add_collision_handler(CollisionTypes.BALL, CollisionTypes.CUP)

        self.bottom_handler.begin = self.bottom_collision_start
        self.bottom_handler.separate = self.bottom_collision_end
        # self.box_handler.post_solve = self.receiver_handler.post_solve = self.box_post_solve
        self.receiver_handler.begin = self.receiver_start
        self.receiver_handler.separate = self.receiver_end
        self.charger_handler.begin = self.charger_start
        self.charger_handler.separate = self.charger_end

        self.levels = [
            TutorialLevel(),
            LevelOne(),
            LevelTwo(),
        ]
        self.high_scores = [0 for level in self.levels]

        self.main_menu = MainMenu(self, Point(0.2, 0.3), Point(0.8, 0.7))

        self.start_pause()
        self.current_level = 0
        self.top_bar.disable()
        self.bottom_bar.disable()

        # Skip the main menu for now
        # self.main_menu.disable()
        # self.main_menu.start_level(0, 0)

        # self.rotating = None
        # self.rotating_pos = None

        # self.cup = Cup(self, Point(globals.screen.x / 2, 0))
        # self.init_level()
        # self.cup.disable()
        # self.ball.disable()

    def enable_controls(self):
        self.controls = True

    def disable_controls(self):
        self.controls = False

    def release(self, package):
        # self.next_package_text.set_text(" ")
        self.help_text.set_text(" ")
        # self.update_jostle(None)
        # self.bottom_bar.timer.set_text(" ")

    def thrust_callback(self, index):
        if not self.drone:
            return
        old_thrust = self.drone.thrust
        self.drone.thrust = self.thrust_points[index][0]
        diff = self.drone.thrust - old_thrust
        if self.tutorial:
            self.tutorial.thrust_adjust(diff)

    def bottom_collision_start(self, arbiter, space, data):
        # If two vertices are *very* close to the floor, we can turn off the engine
        # print(f"{self.drone.landed()}")
        if self.drone.landed():
            self.drone.on_ground = globals.game_time
        # if self.drone.landed() and not self.drone.flying():
        #    self.drone.engine = False

        return True

    def bottom_collision_end(self, arbiter, space, data):
        self.drone.on_ground = None
        return True

    def charger_start(self, arbiter, space, data):
        self.drone.mark_on_charger(True)
        return True

    def charger_end(self, arbiter, space, data):
        self.drone.mark_on_charger(False)

    def receiver_start(self, arbiter, space, data):
        ids = [shape.parent for shape in arbiter.shapes]
        if ids[0].id != ids[1].id:
            return True

        receiver, package = ids
        if not package.is_package:
            receiver, package = package, receiver

        package.mark_on_receiver(True)
        package.parent.set_mailbox_flag(package.id, True)

        return True

    def receiver_end(self, arbiter, space, data):
        ids = [shape.parent for shape in arbiter.shapes]
        if ids[0].id != ids[1].id:
            return True

        receiver, package = ids
        if not package.is_package:
            receiver, package = package, receiver

        package.mark_on_receiver(False)
        package.parent.set_mailbox_flag(package.id, False)

        return True

    def box_post_solve(self, arbiter, space, data):
        if not arbiter.is_first_contact or arbiter.total_ke < 150:
            return

        for shape in arbiter.shapes:
            if not isinstance(shape.parent, Package):
                continue
            package = shape.parent
            package.jostle(arbiter.total_ke / 300)
            globals.sounds.bang.play()

        return True

    def quit(self, pos):
        raise SystemExit()

    def init_level(self):
        self.score = 0
        self.controls = True
        self.bottom_bar.score_num_text.set_text(f"{self.score}", colour=drawing.constants.colours.yellow)
        if self.level_text:
            self.level_text.delete()

        self.top_bar.enable()
        self.bottom_bar.enable()

        self.start_level = globals.t
        self.package_start = None
        level = self.levels[self.current_level]
        self.min_distance = level.min_distance
        self.level_text = ui.TextBox(
            globals.screen_root,
            Point(0, 0.5),
            Point(1, 0.6),
            level.text,
            3,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        if level.subtext:
            self.sub_text = ui.TextBox(
                globals.screen_root,
                Point(0, 0.4),
                Point(1, 0.5),
                level.subtext,
                2,
                colour=drawing.constants.colours.white,
                alignment=drawing.texture.TextAlignments.CENTRE,
            )
        else:
            self.sub_text = None
        self.text_fade = False

        for item in itertools.chain(self.packages, self.receivers, self.houses, self.fences, self.chargers):
            item.delete()

        self.packages = []
        self.receivers = []
        self.fences = []
        self.chargers = []
        self.houses = []

        if self.tutorial:
            self.tutorial.delete()
            self.tutorial = None
        if level.tutorial:
            self.tutorial = Tutorial(self)

        self.mailbox_lookup = {}

        # We're going to generate a random package for delivery

        for i, pos in enumerate(level.receivers):
            self.receivers.append(Receiver(self, pos, id=i))
            self.houses.append(House(self, pos + 50, 0))
            mailbox = Mailbox(self, i, pos - 50, 0)
            self.houses.append(mailbox)
            self.mailbox_lookup[mailbox.id] = mailbox

        # Hack, put some fences up the left side
        for y in range(0, 1000, Fence.size.y):
            self.fences.append(Fence(self, -80, y))

        for pos in level.fences:
            self.fences.append(Fence(self, pos))

        for pos in level.chargers:
            self.chargers.append(Charger(self, pos, id=0))

        self.level_items = level.items[::]

        try:
            package_info = self.level_items.pop(0)
        except IndexError:
            # An initial empty list means random!
            package_info = level.get_random_package()
            package_info.target = random.randint(0, len(self.receivers) - 1)
        self.create_package(package_info)

        # if self.ground:
        #    self.ground.delete()

        if self.drone:
            self.drone.delete()
        # self.ground = Ground(self, level.ground_height)
        self.drone = Drone(self, level.start_pos)
        # This will initialise the thrust
        self.thrust_slider.scroll(0)
        self.viewpos.set_follow_target(self.drone)
        # self.cup.enable()
        # self.ball.enable()
        # self.old_line.disable()

        # globals.cursor.disable()
        self.unpause()

        # self.last_throw = None
        # if self.restricted_box:
        #    self.restricted_box.delete()
        #    self.restricted_box = None
        # if level.restricted_start:
        #    self.restricted_box = DottedBox(self, level.restricted_start[0], level.restricted_start[1])
        #    self.cup.remove_line()
        # else:
        #    self.cup.reset_line()

    def set_mailbox_flag(self, id, state):
        self.mailbox_lookup[id].set_flag(state)

    def create_package(self, info):
        self.current_info = info
        # print("PACKAGE with target", info.target)
        self.package_start = globals.game_time + (info.time * 1000)
        bl = Point(70 + offset + random.randint(-20, 20), 0)

        package = Package(self, bl, bl + info.size, info)
        # box.body.angle = [0.4702232572610111, -0.2761159031752114, 0.06794826568042156, -0.06845718620994479, 1.3234945990935332][jim]
        package.update()
        # jim += 1
        self.packages.append(package)
        self.help_text.set_text("Grab the next package")
        self.next_package_text.set_text(self.next_package_format.format(number=package.id + 1))
        self.update_jostle(package)
        self.top_bar.contents_value.set_text(package.contents)

    def score_for_package(self, package, time):
        score = max(package.max_damage - package.damage, 0)
        played_sound = False
        if score == 0:
            globals.sounds.broken.play()
            played_sound = True

        score += max((5000 + time) / 20, 0)

        damage_ratio = package.damage / package.max_damage

        if damage_ratio < 0.01 and time > 0:
            globals.sounds.perfect.play()
            played_sound = True
            score *= 2

        if not played_sound and damage_ratio < 0.5:
            globals.sounds.thank_you.play()

        return int(score * 10)

    def package_delivered(self, delivered_package):
        print("Package delivered!")
        if self.tutorial:
            self.tutorial.delete()
            self.tutorial = None
        self.score += self.score_for_package(delivered_package, self.get_package_time())
        self.bottom_bar.score_num_text.set_text(f"{self.score}", colour=drawing.constants.colours.yellow)
        self.packages = [package for package in self.packages if package is not delivered_package]
        if self.drone and self.drone.grabbed is delivered_package:
            self.drone.release()
        self.package_start = None
        self.top_bar.contents_value.set_text(" ")
        self.update_jostle(None)

        delivered_package.delete()

        level = self.levels[self.current_level]

        if len(self.level_items) == 0:
            if level.infinite:
                info = level.get_random_package()
                info.target = random.randint(0, len(self.receivers) - 1)
            else:
                if self.score > self.high_scores[self.current_level]:
                    self.high_scores[self.current_level] = self.score

                self.main_menu.enable()
                self.main_menu.resume_button.disable()
                self.start_pause()

                globals.cursor.enable()
                self.level_text.disable()
                if self.sub_text:
                    self.sub_text.disable()
                if self.next_level_menu:
                    self.next_level_menu.disable()
                if self.game_over:
                    self.game_over.disable()

                return
        else:
            info = self.level_items.pop(0)
        self.create_package(info)

    def end_game(self):
        self.game_over = GameOver(self, Point(0.2, 0.2), Point(0.8, 0.8))
        self.start_pause()

    def box_hit(self, arbiter, space, data):
        if not self.thrown:
            return False

        # print('Boop box')

        for shape in arbiter.shapes:
            if hasattr(shape, "parent"):
                shape.parent.set_touched(self.levels[self.current_level].disappear)
        return True

    def keep_flying(self):
        self.unpause()
        # We'll add a bunch of boxes to the level
        level = self.levels[self.current_level]

        level.items = [
            (
                Point(15 + random.randint(1, 20), 15 + random.randint(1, 20)),
                random.randint(0, len(self.receivers) - 1),
            )
            for i in range(100)
        ]

        info = self.level_items.pop(0)
        self.create_package(info)

    def next_level(self):
        self.current_level += 1
        self.init_level()
        self.unpause()

    def bottom_hit(self, arbiter, space, data):
        if not self.thrown or self.ball.body.velocity[1] > 0:
            return False
        # print('KLARG bottom hit')
        self.stop_throw()
        globals.sounds.bad.play()
        return True

    def key_down(self, key):
        #        if key == pygame.locals.K_RETURN:
        #            if self.current_player.is_player():
        #                self.current_player.end_turn(Point(0,0))
        if key == pygame.locals.K_ESCAPE:
            if self.main_menu.enabled:
                return self.quit(0)

            if self.levels[self.current_level].infinite:
                if self.score > self.high_scores[self.current_level]:
                    self.high_scores[self.current_level] = self.score

            self.main_menu.enable()
            self.start_pause()

            globals.cursor.enable()
            self.level_text.disable()
            if self.sub_text:
                self.sub_text.disable()
            if self.next_level_menu:
                self.next_level_menu.disable()
            if self.game_over:
                self.game_over.disable()
        if key == pygame.locals.K_SPACE:
            # space is as good as the left button
            self.mouse_button_down(globals.mouse_screen, 1)

        elif key in (pygame.locals.K_RSHIFT, pygame.locals.K_LSHIFT):
            # shifts count as the right button
            self.mouse_button_down(globals.mouse_screen, 3)
        elif key == pygame.locals.K_DELETE:
            if pygame.mixer.music.get_busy():
                pygame.mixer.music.pause()
            else:
                pygame.mixer.music.unpause()

        if self.controls and self.drone:
            self.drone.key_down(key)
        # This makes it super easy
        # elif key == pygame.locals.K_r and self.last_throw:
        #    self.throw_ball(*self.last_throw)

    def key_up(self, key):
        if 0 and key == pygame.locals.K_SPACE:
            # space is as good as the left button
            self.mouse_button_up(globals.mouse_screen, 1)

        elif key in (pygame.locals.K_RSHIFT, pygame.locals.K_LSHIFT):
            # shifts count as the right button
            self.mouse_button_up(globals.mouse_screen, 3)

        elif key in {pygame.locals.K_LEFTBRACKET}:
            self.parent.thrust_slider.scroll(-1)
        elif key in {pygame.locals.K_RIGHTBRACKET}:
            self.parent.thrust_slider.scroll(1)

        if self.controls and self.drone:
            self.drone.key_up(key)

    def get_package_time(self):
        if self.package_start is None:
            return None

        extra = 0
        for package in self.packages:
            if package.on_receiver is not None:
                extra += globals.game_time - package.on_receiver
                break

        return self.package_start + extra - globals.game_time

    def start_pause(self):
        self.paused = True
        self.pause_start = globals.time
        globals.game_time = globals.time - self.game_time_diff
        if self.tutorial:
            self.tutorial.disable()

    def unpause(self):
        self.paused = False
        self.game_time_diff += self.pause_offset
        self.pause_offset = 0
        self.pause_start = None
        if self.tutorial:
            self.tutorial.enable()

    def update(self, t):
        # for box in self.boxes:
        #    box.update()
        if self.paused:
            # Hack, skip the main menu
            # self.main_menu.disable()
            # self.main_menu.start_level(0, 0)
            self.pause_offset = globals.time - self.pause_start
            return

        globals.game_time = globals.time - self.game_time_diff

        for x in range(25):  # 10 iterations to get a more stable simulation
            globals.current_view.apply_forces()
            globals.space.step(globals.dt)

        if self.package_start is not None:
            text, colour = format_time(self.get_package_time())
            self.bottom_bar.timer.set_text(text, colour=colour)

        if self.tutorial:
            self.tutorial.update()

        if self.text_fade == False and self.start_level and globals.t - self.start_level > 5000:
            self.text_fade = globals.t + self.text_fade_duration

        if self.text_fade:
            if globals.t > self.text_fade:
                self.level_text.disable()
                if self.sub_text:
                    self.sub_text.disable()
                self.text_fade = None
            else:
                colour = (1, 1, 1, (self.text_fade - globals.t) / self.text_fade_duration)
                self.level_text.set_colour(colour)
                if self.sub_text:
                    self.sub_text.set_colour(colour)

        # if not self.thrown:
        # self.ball.body.position = globals.mouse_screen
        # self.ball.set_pos(globals.mouse_pos)

        self.drone.update()
        for package in itertools.chain(self.packages, self.receivers):
            package.update()

        # if self.thrown:
        #     diff = self.ball.body.position - self.last_ball_pos
        #     if diff.get_length_sqrd() > 10:

        #         if (self.dots & 1) == 0 and self.dots < len(self.dotted_line):
        #             self.dotted_line[self.dots].set(self.last_ball_pos, self.ball.body.position)
        #             self.dotted_line[self.dots].enable()

        #         self.dots += 1
        #         self.last_ball_pos = self.ball.body.position
        self.viewpos.update()
        globals.mouse_world = self.viewpos.pos + to_world_coords(self.mouse_pos)

    def draw(self):
        # drawing.draw_no_texture(globals.ui_buffer)
        drawing.scale(*globals.scale, 1)
        drawing.translate(*-(self.viewpos.pos), 0)
        drawing.draw_all(globals.quad_buffer, self.atlas.texture)

    def draw_no_lights(self):
        drawing.reset_state()
        drawing.scale(*globals.scale, 1)
        drawing.translate(*-(self.viewpos.pos), 0)

        drawing.opengl.draw_all(globals.nonstatic_text_buffer, globals.text_manager.atlas.texture)
        drawing.line_width(4)
        drawing.opengl.draw_no_texture(globals.line_buffer_highlights)

    def mouse_motion(self, pos, rel, handled):
        if self.paused:
            return super(GameView, self).mouse_motion(pos, rel, handled)

        self.mouse_pos = pos
        if 1:
            pass
        elif self.dragging:
            self.dragging_line.set_end(pos)
            self.dragging_line.update()

        elif self.moving:
            self.moving.body.position = pos - self.moving_pos
            self.moving.update()
            globals.space.reindex_static()

        elif self.rotating:
            # old_r, old_a = cmath.polar(self.rotating_pos.x + self.rotating_pos.y*1j)
            p = pos - self.rotating.body.position
            new_r, new_a = cmath.polar(p.x + p.y * 1j)
            # print(old_a, new_a, self.rotating.body.angle)
            self.rotating.body.angle = self.rotating_angle + new_a
            self.rotating.update()
            globals.space.reindex_static()

    # def stop_throw(self):
    #     self.thrown = False
    #     globals.cursor.disable()
    #     self.boop = 0
    #     for box in self.boxes:
    #         box.reset_touched()

    def mouse_button_down(self, pos, button):
        if self.paused:
            return super(GameView, self).mouse_button_down(pos, button)
        if button == 1:
            # Clicked the main mouse button. We shouldn't be dragging anything or somethings gone wrong
            # if self.dragging:
            #    self.dragging = None
            # if self.thrown:
            #    self.stop_throw()

            # in_box = None
            # if False == self.levels[self.current_level].boxes_pos_fixed:
            #     for box in self.boxes:
            #         info = box.shape.point_query(tuple(pos))
            #         if info.distance < 0:
            #             self.moving = box
            #             self.moving_pos = pos - box.body.position
            #             return False, False

            # if self.restricted_box and pos not in self.restricted_box:
            #     return False, False

            # throw_distance = (pos - self.cup.centre).length()
            # if throw_distance < self.min_distance:
            #     return False, False

            # # We start dragging
            # self.dragging = pos
            # self.dragging_line.start = pos
            # self.dragging_line.end = pos
            # self.dragging_line.update()
            # self.dragging_line.enable()
            pass
        elif button == 4:
            self.thrust_slider.scroll(1)
        elif button == 5:
            self.thrust_slider.scroll(-1)
        elif button == 3:
            pass

        # elif button == 3 and not self.thrown and not self.dragging:
        #     # Perhaps we can move the blocks around
        #     for box in self.boxes:
        #         info = box.shape.point_query(tuple(pos))
        #         if info.distance < 0:
        #             # print('In box',distance,info)
        #             self.rotating = box
        #             # self.rotating_pos = (pos - box.body.position)
        #             diff = pos - box.body.position
        #             r, a = cmath.polar(diff.x + diff.y * 1j)
        #             self.rotating_angle = box.body.angle - a

        return False, False

    def mouse_button_up(self, pos, button):
        if self.paused:
            return super(GameView, self).mouse_button_up(pos, button)

        # The tutorial disables the mouse buttons for a bit
        if self.tutorial and self.tutorial.anchor_disabled:
            return False, False

        # if button == 1:
        #     if self.drone.grabbed:
        #         self.drone.release()
        #     else:
        #         info = self.drone.shape.point_query(tuple(to_phys_coords(globals.mouse_world)))

        #         diff = from_phys_coords(
        #             self.drone.body.world_to_local(tuple(to_phys_coords(globals.mouse_world)))
        #         )

        #         if (
        #             abs(diff.x) < self.drone.size.x * 0.5
        #             and diff.y < 0
        #             and self.drone.in_grab_range(info.distance * phys_scale)
        #         ):
        #             for package in self.packages:
        #                 info = package.shape.point_query(tuple(to_phys_coords(globals.mouse_world)))
        #                 if info.distance >= 0:
        #                     continue

        #                 self.drone.grab(package)

        #                 # self.next_package_text.set_text(
        #                 #    self.next_package_format.format(number=package.id + 1)
        #                 # )
        #                 # self.update_jostle(package)

        #                 self.help_text.set_text("Deliver the package")
        #                 break

        # if button == 1 and self.dragging:
        #     # release!
        #     # print(f'Drag release from {self.dragging=} to {pos=}')
        #     diff = self.dragging - pos
        #     if diff.length() > 5:
        #         # pos, diff = Point(1084.00,13.00), Point(-41.00,149.00)
        #         self.throw_ball(pos, diff)

        #         if self.text_fade == False:
        #             self.text_fade = globals.t + self.text_fade_duration
        #     else:
        #         self.dragging = None
        #         self.dragging_line.disable()

        # elif button == 1 and self.moving:
        #     if self.moving:
        #         self.moving = None
        #         self.moving_pos = None
        #         return False, False
        # elif button == 3 and self.rotating:
        #     self.rotating = None
        #     self.rotating_pos = None
        #     return False, False

        # elif button == 3 and self.thrown and not self.dragging:
        #     self.stop_throw()

        return False, False

    def update_jostle(self, package):
        if not package:
            self.top_bar.jostle_bar.set_bar_level(0)
            return
        self.top_bar.jostle_bar.set_bar_level(package.jostle_amount())

    def apply_forces(self):
        if self.drone:
            self.drone.apply_forces()
