import numpy
from globals.types import Point


class Sprite(object):
    """
    Abstract base class to define the sprite interface. Basically it just represents a sprite, and you
    can ask for the texture coordinates (of the main texture atlas) at a given time
    """

    def texture_coordinates(self, time):
        return NotImplemented


class SpriteFrame(object):
    """
    A single fixed frame of a sprite
    """

    def __init__(self, tex_coords, offset, light_pos, size, opacity=0):
        self.tex_coords = tex_coords
        sf = 1.05
        self.outline_vertices = numpy.array(
            ((0, 0, 0), (0, size.y * sf, 0), (size.x * sf, size.y * sf, 0), (size.x * sf, 0, 0)),
            numpy.float32,
        )
        self.width = size.x
        self.height = size.y
        self.size = size
        self.light_pos = light_pos
        self.outline_size = self.size * sf
        self.offset = offset
        self.opacity = opacity
        self.outline_offset = Point(float(self.width) / 40, float(self.height) / 40)


class StaticSprite(object):
    """
    Contains a single sprite in a single direction. Multiple directions, and potentially actions (In the case
    of something like a door that can open) will be wrapped up in a spritecontainer
    """

    def __init__(self, name, tex_coords, offset, light_pos, size, movement_cost=0, opacity=0):
        self.frame = SpriteFrame(tex_coords, offset, light_pos, size, opacity)
        self.name = name
        self.movement_cost = movement_cost

    def get_frame(self, time):
        return self.frame

    def texture_coordinates(self, time):
        # This is a static sprite so just return the constant coords
        return self.frame.tex_coords


class StaticSpriteContainer(dict):
    """
    Contains all the sprites (directions and actions) for a static object
    """

    pass


class AnimatedSprite(object):
    def __init__(self, name, eventType, fps):
        self.name = name
        self.event_type = eventType
        self.fps = fps
        self.frame_duration = float(1) / fps
        self.frames = []

    def add_frame(self, frame):
        self.frames.append(frame)

    def get_frame(self, time):
        frame_num = int(time / self.frame_duration) % len(self.frames)
        return self.frames[frame_num]

    def texture_coordinates(self, time):
        return self.get_frame(time).tex_coords


class AnimatedSpriteContainer(dict):
    """
    Contains all the sprites (directions and actions) for an animated object
    """

    pass
