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

box_level = 7
ground_level = 6
drone_level = 8
sf = 1
debug_sprite_name = "resource/sprites/box.png"


def to_world_coords(p):
    return p / globals.scale


def to_screen_coords(p):
    return p * globals.scale


class CollisionTypes:
    DRONE = 1
    BOTTOM = 2
    BOX = 3
    WALL = 4
    RECEIVER = 5


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
        self._pos = point
        self.no_target()
        self.follow = None
        self.follow_locked = False
        self.t = 0
        self.shake_end = None
        self.shake_duration = 1
        self.shake = Point(0, 0)
        self.last_update = globals.time

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
        self.shake_end = globals.time + duration
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
        self.start_time = globals.time
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
        self.follow_start = globals.time
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
        self.t = globals.time
        elapsed = globals.time - self.last_update
        self.last_update = globals.time
        t = globals.time

        if self.shake_end:
            if globals.time >= self.shake_end:
                self.shake_end = None
                self.shake = Point(0, 0)
            else:
                left = (self.shake_end - t) / self.shake_duration
                radius = left * self.shake_radius
                self.shake = Point(random.random() * radius, random.random() * radius)

        if self.follow:
            # We haven't locked onto it yet, so move closer, and lock on if it's below the threshold
            fpos = self.follow.body.position + globals.screen * Point(0, 0.03)
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
    is_package = True
    receive_time = 5000

    def __init__(self, parent, bl, tr, target):
        self.parent = parent
        self.id = target
        # bl, tr = (to_world_coords(x) for x in (bl, tr))
        self.quad = drawing.Quad(globals.quad_buffer)
        self.quad.set_vertices(bl, tr, box_level)
        self.normal_tc = parent.atlas.texture_coords(self.sprite_name)
        self.quad.set_texture_coordinates(self.normal_tc)
        self.collision_impulse = Point(0, 0)

        centre = self.quad.get_centre()
        vertices = [tuple(Point(*v[:2]) - centre) for v in self.quad.vertex[:4]]
        # vertices = [vertices[2],vertices[3],vertices[0],vertices[1]]
        self.moment = pymunk.moment_for_poly(self.mass, vertices)
        self.body = Body(moment=self.moment)
        self.body.position = self.quad.get_centre().to_float()
        self.body.force = 0, 0
        self.body.torque = 0
        self.body.velocity = 0, 0
        self.body.angular_velocity = 0
        # print(self.body.position,self.body.velocity)
        # print(vertices)
        self.shape = pymunk.Poly(self.body, vertices)
        self.shape.density = self.density
        self.shape.friction = 0.2
        self.shape.elasticity = 0.5
        self.shape.collision_type = CollisionTypes.BOX
        self.shape.parent = self
        globals.space.add(self.body, self.shape)
        self.in_world = True
        # Our anchors are the top left and top right.
        # TODO: These should actually be the two that are most upright (if it flips things go wrong)
        # self.anchor_points = [point * 0.9 for point in self.shape.get_vertices()[2:]][::-1]
        self.on_receiver = None

    def anchor_points(self):
        orig_vertices = self.shape.get_vertices()
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(orig_vertices):
            vertices[i] = (i, v.rotated(self.body.angle) + self.body.position)

        # We want the one that's most left and most up, and the one that's most right and most up
        vertices.sort(key=lambda x: -x[1][1])
        print(vertices)
        output = [orig_vertices[vertices[0][0]], orig_vertices[vertices[1][0]]]
        output = [p * 0.8 for p in output]

        if vertices[0][1][0] < vertices[1][1][0]:
            self._anchor_points = output
        else:
            self._anchor_points = output[::-1]
        return self._anchor_points

    def mark_on_receiver(self, on_receiver):
        if not on_receiver:
            self.on_receiver = None
            return

        if self.on_receiver is None:
            self.on_receiver = globals.time

    def update(self):
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(self.shape.get_vertices()):
            vertices[(4 - i) & 3] = v.rotated(self.body.angle) + self.body.position

        self.quad.set_all_vertices(vertices, box_level)

        if self.on_receiver is not None and globals.time - self.on_receiver > self.receive_time:
            self.on_receiver = None
            self.parent.package_delivered(self)

    def delete(self):
        self.quad.delete()
        globals.space.remove(self.body, self.shape)
        self.in_world = False


class Receiver(object):
    sprite_name = "resource/sprites/receiver.png"
    name_name = "resource/sprites/receiver_%d.png"
    mass = 0.01
    density = 12 / 100000
    is_package = False

    def __init__(self, parent, pos, id):
        self.parent = parent

        bl = Point(pos, 0)
        tr = bl + Point(40, 10)
        # bl, tr = (to_world_coords(x) for x in (bl, tr))
        self.id = id
        self.quad = drawing.Quad(globals.quad_buffer)
        self.quad.set_vertices(bl, tr, box_level)
        self.normal_tc = parent.atlas.texture_coords(self.sprite_name)
        self.quad.set_texture_coordinates(self.normal_tc)

        name_bl = bl - Point(0, 10)
        name_tr = name_bl + Point(40, 10)
        self.name_quad = drawing.Quad(globals.quad_buffer)

        self.name_quad.set_vertices(name_bl, name_tr, box_level)
        self.name_tc = parent.atlas.texture_coords(self.name_name % self.id)
        self.name_quad.set_texture_coordinates(self.name_tc)

        self.collision_impulse = Point(0, 0)

        centre = self.quad.get_centre()
        vertices = [tuple(Point(*v[:2]) - centre) for v in self.quad.vertex[:4]]
        # vertices = [vertices[2],vertices[3],vertices[0],vertices[1]]
        self.moment = pymunk.moment_for_poly(self.mass, vertices)
        self.body = Body(mass=self.mass, moment=self.moment, body_type=pymunk.Body.STATIC)
        self.body.position = self.quad.get_centre().to_float()
        self.body.force = 0, 0
        self.body.torque = 0
        self.body.velocity = 0, 0
        self.body.angular_velocity = 0
        # print(self.body.position,self.body.velocity)
        # print(vertices)
        self.shape = pymunk.Poly(self.body, vertices)
        self.shape.density = self.density
        self.shape.friction = 0.2
        self.shape.elasticity = 0.5
        self.shape.collision_type = CollisionTypes.RECEIVER
        self.shape.parent = self
        globals.space.add(self.body, self.shape)
        self.in_world = True

    def update(self):
        vertices = [0, 0, 0, 0]
        for i, v in enumerate(self.shape.get_vertices()):
            vertices[(4 - i) & 3] = v.rotated(self.body.angle) + self.body.position

        self.quad.set_all_vertices(vertices, box_level)

    def delete(self):
        self.quad.delete()
        globals.space.remove(self.body, self.shape)
        self.in_world = False
        self.name_quad.delete()


class Ground(object):
    sprite_name = "resource/sprites/ground.png"

    def __init__(self, parent, height):
        self.parent = parent
        self.height = height

        # TODO: Put proper lower bounds on so we don't fall off. Also make this a ui object so we can use its absolute bounds easier?
        self.bottom_left = Point(0, -self.height)
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

            pos.x += subimage.size.x

        # The ground is a simple static horizontal line (for now)

        self.segment = Segment(
            globals.space.static_body,
            self.top_left,
            self.top_right,
            0.0,
        )
        # bottom.sensor = True
        self.segment.collision_type = CollisionTypes.BOTTOM
        self.segment.friction = 1
        self.elasticity = 0.3

        globals.space.add(self.segment)
        self.segments = [self.segment]

        for (start, end) in (
            (self.bottom_left, self.ceiling_left),
            (self.ceiling_left, self.ceiling_right),
            (self.ceiling_right, self.bottom_right),
        ):
            # We'll also add a wall to the left
            segment = Segment(
                globals.space.static_body,
                start,
                end,
                0.0,
            )

            segment.collision_type = CollisionTypes.WALL
            segment.friction = 1
            segment.elasticity = 0.5
            globals.space.add(segment)
            self.segments.append(segment)

    def delete(self):
        for segment in self.segments:
            globals.space.remove(segment)


class Drone(object):
    sprite_name = "resource/sprites/drone.png"
    up_keys = {pygame.locals.K_w, pygame.locals.K_UP}
    down_keys = {pygame.locals.K_s, pygame.locals.K_DOWN}
    left_keys = {pygame.locals.K_a, pygame.locals.K_LEFT}
    right_keys = {pygame.locals.K_d, pygame.locals.K_RIGHT}
    key_map = (
        {key: Directions.UP for key in up_keys}
        | {key: Directions.DOWN for key in down_keys}
        | {key: Directions.LEFT for key in left_keys}
        | {key: Directions.RIGHT for key in right_keys}
    )
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

    def __init__(self, parent, pos):
        self.parent = parent
        self.quad = drawing.Quad(globals.quad_buffer)
        self.quad.set_texture_coordinates(parent.atlas.texture_coords(self.sprite_name))

        self.size = parent.atlas.subimage(self.sprite_name).size
        # pos = to_world_coords(pos)
        self.bottom_left = pos
        self.top_right = pos + self.size
        self.turning_enabled = True
        self.grabbed = None

        self.quad.set_vertices(self.bottom_left, self.top_right, drone_level)

        centre = self.quad.get_centre()
        vertices = [tuple(Point(*v[:2]) - centre) for v in self.quad.vertex[:4]]

        self.mass = 0.08
        self.moment = pymunk.moment_for_poly(self.mass, vertices)
        self.body = Body(mass=self.mass, moment=self.moment)
        self.body.position = self.quad.get_centre().to_float()
        self.body.force = 0, 0
        self.body.torque = 0
        self.body.velocity = 0, 0
        self.body.angular_velocity = 0
        # print(self.body.position,self.body.velocity)
        self.shape = pymunk.Poly(self.body, vertices)
        self.shape.friction = 0.5
        self.shape.elasticity = 0.3
        self.shape.collision_type = CollisionTypes.DRONE
        globals.space.add(self.body, self.shape)

        # self.polar_vertices = [cmath.polar(v[0] + v[1] * 1j) for v in self.vertices]

        # For debugging we'll draw a box around the desired pos
        self.desired_quad = drawing.Quad(
            globals.quad_buffer, tc=parent.atlas.texture_coords(debug_sprite_name)
        )
        self.desired_quad.disable()

        # Also for debugging we'll draw some lines for the jet forces
        self.jet_lines = [Line(self, Point(0, 0), Point(300, 3000)) for i in (0, 1)]

        self.desired_shift = Point(0, 0)
        self.desired_pos = self.body.position
        self.desired_field = 0
        self.desired_vector = Point(0, 0)
        self.last_update = None
        self.jets = self.shape.get_vertices()[:2]
        self.reset_forces()
        self.target_rotation = 0
        self.engine = True
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
            print(f"{our_anchor=} {item_anchor=}")
            joint = pymunk.PinJoint(self.body, item.body, anchor_a=our_anchor, anchor_b=item_anchor)
            self.joints.append(joint)
            globals.space.add(joint)
            self.anchors.append(
                Line(
                    self,
                    self.body.local_to_world(our_anchor),
                    item.body.local_to_world(item_anchor),
                    colour=(1, 1, 1, 1),
                )
            )
        # We also add an unseen stabilization joint
        stable = pymunk.PinJoint(self.body, item.body)
        self.joints.append(stable)
        globals.space.add(stable)

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

    def enable_turning(self):
        self.turning_enabled = True
        self.update_desired_vector()

    def update(self):
        if self.last_update is None:
            self.last_update = globals.time
            return

        vertices = [0, 0, 0, 0]
        for i, v in enumerate(self.shape.get_vertices()):
            vertices[(4 - i) & 3] = v.rotated(self.body.angle) + self.body.position

        if self.forces is not None:
            # Debug draw the lines
            for force, jet, line in zip(self.forces, vertices[::3], self.jet_lines):
                line.set(start=jet, end=jet - force)

        self.quad.set_all_vertices(vertices, box_level)

        elapsed = (globals.time - self.last_update) * globals.time_step
        self.last_update = globals.time

        if self.desired_field == 0:
            # decay the desired pos
            self.desired_vector = Point(0, 0)
            if self.desired_shift.length() > self.min_desired:
                self.desired_vector = self.desired_shift * -0.2
            else:
                self.desired_shift = Point(0, 0)

        self.desired_shift += self.desired_vector * self.desired_speed * (elapsed / 1000)
        desired_length = self.desired_shift.length()
        if self.desired_shift.length() > self.max_desired:
            scale_factor = self.max_desired / desired_length
            self.desired_shift *= scale_factor
        self.desired_pos = self.body.position + self.desired_shift
        self.desired_quad.set_vertices(
            self.desired_pos - Point(4, 4), self.desired_pos + Point(4, 4), drone_level + 1
        )
        self.reset_forces()

        if not self.turning_enabled and self.body.position[1] > 100:
            self.enable_turning()

        if self.grabbed:
            for our_anchor, item_anchor, anchor in zip(
                self.anchor_points, self.grabbed._anchor_points, self.anchors
            ):
                anchor.set(
                    self.body.local_to_world(our_anchor), self.grabbed.body.local_to_world(item_anchor)
                )

    def calculate_forces(self):
        if not self.engine:
            self.forces = ((0, 0), (0, 0))
            return

        mass = self.body.mass
        anti_grav = -globals.space.gravity * mass * 0.5
        if self.grabbed:
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

        desired = self.desired_shift - self.body.velocity * 0.1

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
        force = (0, (anti_grav + desired)[1])
        self.force = (desired[0], (anti_grav + desired)[1])
        # print(f"{force=}")

    def reset_forces(self):
        self.forces = None
        self.force = None

        # for line in self.jet_lines:
        #    line.disable()

    def apply_forces(self):
        if self.force is None:
            self.calculate_forces()
        if not self.engine:
            return

        self.body.apply_force_at_world_point(self.force, (0, 0))
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
        try:
            direction = self.key_map[key]
        except KeyError:
            return

        self.desired_field &= ~direction
        self.update_desired_vector()

    def disable(self):
        self.quad.disable()

    def enable(self):
        self.quad.enable()


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


class NextLevel(ui.HoverableBox):
    line_width = 1

    def __init__(self, parent, bl, tr):
        self.border = drawing.QuadBorder(globals.ui_buffer, line_width=self.line_width)
        super(NextLevel, self).__init__(parent, bl, tr, (0.05, 0.05, 0.05, 1))
        self.text = ui.TextBox(
            self,
            Point(0, 0.5),
            Point(1, 0.6),
            "Well done!",
            3,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.border.set_colour(drawing.constants.colours.red)
        self.border.set_vertices(self.absolute.bottom_left, self.absolute.top_right)
        self.border.enable()
        self.replay_button = ui.TextBoxButton(self, "Replay", Point(0.1, 0.1), size=2, callback=self.replay)
        self.continue_button = ui.TextBoxButton(
            self, "Next Level", Point(0.7, 0.1), size=2, callback=self.next_level
        )

    def replay(self, pos):
        self.parent.replay()
        self.disable()

    def next_level(self, pos):
        self.parent.next_level()
        self.disable()

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            self.border.enable()
        super(NextLevel, self).enable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.border.disable()
        super(NextLevel, self).disable()


class DottedBox(ui.UIElement):
    def __init__(self, parent, bl, tr):
        super(DottedBox, self).__init__(parent, bl, tr)
        # super(DottedBox, self).__init__(parent, bl, tr)
        self.lines = []
        seg_size = 5
        for start, end in (
            (self.absolute.bottom_left, self.absolute.bottom_right),
            (self.absolute.bottom_right, self.absolute.top_right),
            (self.absolute.top_right, self.absolute.top_left),
            (self.absolute.top_left, self.absolute.bottom_left),
        ):
            num_segs = ((end - start).length()) / seg_size
            seg = (end - start) / num_segs
            for i in range(0, int(num_segs), 2):
                line = drawing.Line(globals.line_buffer)
                seg_start = start + seg * i
                seg_end = start + seg * (i + 1)
                line.set_colour((0.4, 0.4, 0.4, 1))
                line.set_vertices(seg_start, seg_end, 6)
                self.lines.append(line)

    def disable(self):
        for line in self.lines:
            line.disable()

    def enable(self):
        for line in self.lines:
            line.enable()

    def delete(self):
        for line in self.lines:
            line.delete()


def call_with(callback, arg):
    def caller(pos):
        return callback(pos, arg)

    return caller


class MainMenu(ui.HoverableBox):
    line_width = 1

    def __init__(self, parent, bl, tr):
        self.border = drawing.QuadBorder(globals.ui_buffer, line_width=self.line_width)
        self.level_buttons = []
        self.ticks = []
        super(MainMenu, self).__init__(parent, bl, tr, (0.05, 0.05, 0.05, 1))
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
            "This is some helpful text. Escape for main menu",
            1.5,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        self.border.set_colour(drawing.constants.colours.red)
        self.border.set_vertices(self.absolute.bottom_left, self.absolute.top_right)
        self.border.enable()
        self.quit_button = ui.TextBoxButton(self, "Quit", Point(0.45, 0.1), size=2, callback=self.parent.quit)
        # self.continue_button = ui.TextBoxButton(self, 'Next Level', Point(0.7, 0.1), size=2, callback=self.next_level)

        pos = Point(0.2, 0.8)
        for i, level in enumerate(parent.levels):
            button = ui.TextBoxButton(
                self,
                f"{i}: {level.name}",
                pos,
                size=2,
                callback=call_with(self.start_level, i),
            )
            # self.ticks.append(
            #     ui.TextBox(
            #         self,
            #         pos - Point(0.05, 0.01),
            #         tr=pos + Point(0.1, 0.04),
            #         text="\x9a",
            #         scale=3,
            #         colour=(0, 1, 0, 1),
            #     )
            # )
            # if not self.parent.done[i]:
            #     self.ticks[i].disable()

        #     pos.y -= 0.1
        #     self.level_buttons.append(button)

    def start_level(self, pos, level):
        self.disable()
        self.parent.current_level = level
        self.parent.init_level()
        # self.parent.stop_throw()
        self.parent.paused = False

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            self.border.enable()
        for button in self.level_buttons:
            button.enable()
        super(MainMenu, self).enable()
        for i, tick in enumerate(self.ticks):
            if self.parent.done[i]:
                tick.enable()
            else:
                tick.disable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.border.disable()
        super(MainMenu, self).disable()
        for tick in self.ticks:
            tick.disable()


class GameOver(ui.HoverableBox):
    line_width = 1

    def __init__(self, parent, bl, tr):
        self.border = drawing.QuadBorder(globals.ui_buffer, line_width=self.line_width)
        super(GameOver, self).__init__(parent, bl, tr, (0, 0, 0, 1))
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
        self.quit_button = ui.TextBoxButton(self, "Quit", Point(0.7, 0.1), size=2, callback=parent.quit)

    def keep_flying(self, pos):
        self.parent.keep_flying()
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


class Level(object):
    disappear = False
    min_distance = 300
    ground_height = 100
    restricted_start = None
    boxes_pos_fixed = False


class LevelZero(Level):
    text = "Deliver Stuff"
    name = "Introduction"
    subtext = "idk lol"
    start_pos = Point(100 + 5000, 50)
    items = [(Point(20, 20), 0), (Point(40, 40), 1), (Point(50, 10), 2), (Point(50, 50), 3)]
    receivers = [800 + i * 600 for i in range(10)]
    min_distance = 200
    min_force = 50


class LevelOne(Level):
    text = "Level 1: Bounce the ball off the box first"
    name = "Box Bounce"
    subtext = "Left drag to move the box, right drag to rotate"
    items = [(Box, Point(100, 100), Point(200, 200))]
    min_distance = 300
    min_force = 50


class LevelTwo(Level):
    text = "Level 2: Bounce the ball off both boxes. Keep the streak alive!"
    name = "Two boxes"
    subtext = "Left drag to move, right drag to rotate"
    items = [(Box, Point(100, 100), Point(200, 200)), (Box, Point(300, 100), Point(400, 200))]
    min_distance = 300
    min_force = 0


class LevelThree(Level):
    text = "Level 3: Keep the streak alive!"
    name = "Three boxes"
    subtext = "Left drag to move, right drag to rotate"
    items = [
        (Box, Point(100, 100), Point(200, 200)),
        (Box, Point(300, 100), Point(400, 200)),
        (Box, Point(500, 100), Point(600, 200)),
    ]
    min_distance = 300
    min_force = 0


class LevelFour(Level):
    text = "Level 4: Keep the streak alive!"
    name = "Three Disappearing Boxes"
    disappear = True
    subtext = "Boxes disappear when hit"
    items = [
        (Box, Point(100, 100), Point(200, 200)),
        (Box, Point(300, 100), Point(400, 200)),
        (Box, Point(500, 100), Point(600, 200)),
    ]
    min_distance = 300
    min_force = 0


class LevelFive(Level):
    text = "Level 5: Keep the streak alive!"
    name = "Harderer"
    subtext = "Shoot from the grey box"
    items = [
        (Box, Point(100, 100), Point(200, 200)),
        (Box, Point(300, 100), Point(400, 200)),
        (Box, Point(500, 100), Point(600, 200)),
    ]
    min_distance = 300
    restricted_start = (Point(0.75, 0.1), Point(0.97, 0.25))
    min_force = 0


class LevelSix(Level):
    text = "Level 5: Keep the streak alive!"
    name = "Hardestest"
    disappear = False
    subtext = "Now you can't move the boxes (only rotate). Good luck!"
    items = [
        (Box, Point(423, 619) - Point(50, 50), Point(423, 619) + Point(50, 50)),
        (Box, Point(912, 637) - Point(50, 50), Point(912, 637) + Point(50, 50)),
        (Box, Point(736, -7) - Point(50, 50), Point(736, -7) + Point(50, 50)),
        (Box, Point(518, -1) - Point(50, 50), Point(518, -1) + Point(50, 50)),
        (Box, Point(733, 560) - Point(50, 50), Point(733, 560) + Point(50, 50)),
    ]
    min_distance = 300
    min_force = 0
    restricted_start = (Point(0.75, 0.1), Point(0.97, 0.25))
    boxes_pos_fixed = True


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


class GameView(ui.RootElement):
    text_fade_duration = 1000

    def __init__(self):
        # self.atlas = globals.atlas = drawing.texture.TextureAtlas('tiles_atlas_0.png','tiles_atlas.txt')
        # globals.ui_atlas = drawing.texture.TextureAtlas('ui_atlas_0.png','ui_atlas.txt',extra_names=False)
        super(GameView, self).__init__(Point(0, 0), globals.screen)
        self.timeofday = TimeOfDay(0.5)
        self.viewpos = ViewPos(Point(0, 0))
        self.mouse_pos = Point(0, 0)

        # For the ambient light
        self.atlas = drawing.texture.TextureAtlas("atlas_0.png", "atlas.txt")
        self.ground = Ground(self, LevelZero.ground_height)
        self.light = drawing.Quad(globals.light_quads)
        self.light.set_vertices(self.ground.bottom_left, self.ground.ceiling_right, 0)

        # self.ground = None
        self.drone = None
        self.packages = []
        self.receivers = []

        # self.test_line = Line(self, Point(0, 0), Point(0, 0))
        # self.test_line.set(Point(48, 167), Point(48, 217))
        # self.test_line.enable()

        # self.boxes = []
        # self.boxes.append(Box(self, Point(100,100), Point(200,200)))
        # self.boxes.append(Box(self, Point(160,210), Point(260,310)))

        # self.ball = Circle(self, globals.mouse_screen)
        # self.ball = Ball(self, Point(150, 400), 10)
        # self.dragging_line = Line(self, None, None)
        # self.old_line = Line(self, None, None, (0.2, 0.2, 0.2, 1))

        # Make 100 line segments for a dotted trajectory line
        # self.dotted_line = [Line(self, None, None, (0, 0, 0.4, 1)) for i in range(1000)]
        # self.dots = 0

        # self.dragging = None
        # self.thrown = False
        self.level_text = None
        # self.sub_text = None

        self.bottom_handler = globals.space.add_collision_handler(CollisionTypes.DRONE, CollisionTypes.BOTTOM)
        self.box_handler = globals.space.add_collision_handler(CollisionTypes.BOX, CollisionTypes.BOTTOM)

        self.receiver_handler = globals.space.add_collision_handler(
            CollisionTypes.BOX, CollisionTypes.RECEIVER
        )

        # self.cup_handler = globals.space.add_collision_handler(CollisionTypes.BALL, CollisionTypes.CUP)

        self.bottom_handler.begin = self.bottom_collision_start
        self.bottom_handler.separate = self.bottom_collision_end
        self.box_handler.post_solve = self.receiver_handler.post_solve = self.box_post_solve
        self.receiver_handler.begin = self.receiver_start
        self.receiver_handler.separate = self.receiver_end
        # self.box_handler.begin = self.box_hit
        # self.cup_handler.begin = self.cup_hit
        # # self.cup_handler.separate = self.cup_sep
        # self.moving = None
        # self.moving_pos = None
        # self.current_level = 0
        # self.game_over = False
        # self.restricted_box = None
        # self.start_level = None

        self.levels = [
            LevelZero(),
            #     LevelOne(),
            #     LevelTwo(),
            #     LevelThree(),
            #     LevelFour(),
            #     LevelFive(),
            #     LevelSix(),
            #     # LevelSeven(),
        ]
        # self.done = [False for level in self.levels]

        # self.last_throw = None
        # self.next_level_menu = NextLevel(self, Point(0.25, 0.3), Point(0.75, 0.7))
        # self.next_level_menu.disable()
        self.main_menu = MainMenu(self, Point(0.2, 0.1), Point(0.8, 0.9))

        # Skip the main menu for now
        # self.main_menu.disable()
        # self.main_menu.start_level(0, 0)

        self.paused = True
        # self.rotating = None
        # self.rotating_pos = None

        self.current_level = 0
        # self.cup = Cup(self, Point(globals.screen.x / 2, 0))
        # self.init_level()
        # self.cup.disable()
        # self.ball.disable()

    def bottom_collision_start(self, arbiter, space, data):
        # self.drone.disable_turning()
        return True

    def bottom_collision_end(self, arbiter, space, data):
        # print("BCE")
        return True

    def receiver_start(self, arbiter, space, data):
        ids = [shape.parent for shape in arbiter.shapes]
        if ids[0].id != ids[1].id:
            return True

        receiver, package = ids
        if not package.is_package:
            receiver, package = package, receiver

        package.mark_on_receiver(True)

        return True

    def receiver_end(self, arbiter, space, data):
        ids = [shape.parent for shape in arbiter.shapes]
        if ids[0].id != ids[1].id:
            return True

        receiver, package = ids
        if not package.is_package:
            receiver, package = package, receiver

        package.mark_on_receiver(False)

        return True

    def box_post_solve(self, arbiter, space, data):
        for shape in arbiter.shapes:
            if shape is self.ground.segment:
                continue

            for package in self.packages:
                if shape is not package.shape:
                    continue

                package.collision_impulse = arbiter.total_impulse
                # print("BCS", shape, arbiter.total_impulse)
        return True

    def quit(self, pos):
        raise SystemExit()

    def init_level(self):
        if self.level_text:
            self.level_text.delete()

        self.start_level = globals.t
        level = self.levels[self.current_level]
        self.min_distance = level.min_distance
        self.level_text = ui.TextBox(
            self,
            Point(0, 0.5),
            Point(1, 0.6),
            level.text,
            3,
            colour=drawing.constants.colours.white,
            alignment=drawing.texture.TextAlignments.CENTRE,
        )
        if level.subtext:
            self.sub_text = ui.TextBox(
                self,
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
        for package in self.packages:
            package.delete()

        # We're going to generate a random package for delivery

        for i, pos in enumerate(level.receivers):
            self.receivers.append(Receiver(self, pos, id=i))

        size, target = level.items.pop(0)
        print("PACKAGE with target", target)

        bl = Point(5050 + random.randint(-20, 20), 0)

        package = Box(self, bl, bl + size, target=target)
        # box.body.angle = [0.4702232572610111, -0.2761159031752114, 0.06794826568042156, -0.06845718620994479, 1.3234945990935332][jim]
        package.update()
        # jim += 1
        self.packages.append(package)

        # if self.ground:
        #    self.ground.delete()

        if self.drone:
            self.drone.delete()
        # self.ground = Ground(self, level.ground_height)
        self.drone = Drone(self, level.start_pos)
        self.viewpos.set_follow_target(self.drone)
        # self.cup.enable()
        # self.ball.enable()
        # self.old_line.disable()

        # globals.cursor.disable()
        self.paused = False
        # self.last_throw = None
        # if self.restricted_box:
        #    self.restricted_box.delete()
        #    self.restricted_box = None
        # if level.restricted_start:
        #    self.restricted_box = DottedBox(self, level.restricted_start[0], level.restricted_start[1])
        #    self.cup.remove_line()
        # else:
        #    self.cup.reset_line()

    def package_delivered(self, delivered_package):
        print("Package delivered!")
        self.packages = [package for package in self.packages if package is not delivered_package]
        delivered_package.delete()

        level = self.levels[self.current_level]

        if len(level.items) == 0:
            self.end_game()
            return

        size, target = level.items.pop(0)
        print("PACKAGE with target", target)

        bl = Point(50 + random.randint(-20, 20), 0)

        package = Box(self, bl, bl + size, target=target)
        # box.body.angle = [0.4702232572610111, -0.2761159031752114, 0.06794826568042156, -0.06845718620994479, 1.3234945990935332][jim]
        package.update()
        # jim += 1
        self.packages.append(package)

    def end_game(self):
        self.game_over = GameOver(self, Point(0.2, 0.2), Point(0.8, 0.8))
        self.paused = True

    def cup_hit(self, arbiter, space, data):
        if self.paused:
            return True

        if not all(box.touched for box in self.boxes):
            self.bottom_hit(arbiter, space, data)
            return True

        # for i,box in enumerate(self.boxes):
        #    print(i,box.body.position,box.body.angle)
        #    print(self.last_throw)

        self.paused = True
        self.done[self.current_level] = True
        globals.sounds.win.play()

        if self.current_level + 1 >= len(self.levels):
            self.end_game()
        else:
            self.next_level_menu.enable()
        self.level_text.disable()
        if self.sub_text:
            self.sub_text.disable()
        return True

    def box_hit(self, arbiter, space, data):
        if not self.thrown:
            return False

        # print('Boop box')

        for shape in arbiter.shapes:
            if hasattr(shape, "parent"):
                shape.parent.set_touched(self.levels[self.current_level].disappear)
        return True

    def keep_flying(self):
        self.paused = False
        # We'll add a bunch of boxes to the level
        level = self.levels[self.current_level]

        level.items = [
            (
                Point(15 + random.randint(1, 20), 15 + random.randint(1, 20)),
                random.randint(0, len(self.receivers) - 1),
            )
            for i in range(100)
        ]

        size, target = level.items.pop(0)

        bl = Point(50 + random.randint(-20, 20), 0)

        package = Box(self, bl, bl + size, target=target)
        print("PACKAGE with target", target, "size", size)
        # box.body.angle = [0.4702232572610111, -0.2761159031752114, 0.06794826568042156, -0.06845718620994479, 1.3234945990935332][jim]
        package.update()
        # jim += 1
        self.packages.append(package)

    def next_level(self):
        self.stop_throw()
        self.current_level += 1
        self.init_level()
        self.paused = False

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
            self.main_menu.enable()
            self.paused = True
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

        if self.drone:
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

        if self.drone:
            self.drone.key_up(key)

    def update(self, t):
        # for box in self.boxes:
        #    box.update()
        if self.paused:
            # Hack, skip the main menu
            # self.main_menu.disable()
            # self.main_menu.start_level(0, 0)
            return

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

        if button == 1:
            if self.drone.grabbed:
                self.drone.release()
            else:
                info = self.drone.shape.point_query(tuple(globals.mouse_world))

                diff = self.drone.body.world_to_local(tuple(globals.mouse_world))

                if (
                    abs(diff.x) < self.drone.size.x * 0.5
                    and diff.y < 0
                    and self.drone.in_grab_range(info.distance)
                ):
                    for package in self.packages:
                        info = package.shape.point_query(tuple(globals.mouse_world))
                        if info.distance >= 0:
                            continue

                        self.drone.grab(package)
                        break

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

    def throw_ball(self, pos, direction):
        self.last_throw = (pos, direction)
        self.ball.body.position = pos
        self.ball.body.angle = 0
        self.ball.body.force = 0, 0
        self.ball.body.torque = 0
        self.ball.body.velocity = 0, 0
        self.ball.body.angular_velocity = 0
        self.ball.body.moment = self.ball.moment
        self.ball.body.apply_impulse_at_local_point(direction)
        self.thrown = True
        globals.cursor.enable()
        for line in self.dotted_line[: self.dots]:
            line.disable()
        self.dots = 0

        self.dragging = None
        self.dragging_line.disable()
        self.last_ball_pos = self.ball.body.position
        self.old_line.set(self.dragging_line.start, self.dragging_line.end)
        self.old_line.enable()

    def apply_forces(self):
        if self.drone:
            self.drone.apply_forces()
