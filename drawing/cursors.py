import pygame
import os
import numpy
import glob
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GL.framebufferobjects import *
import globals
import drawing

# drawing modules
from . import constants
from . import quads
from . import opengl
from . import sprite

from globals.types import Point


def expand_resource(name):
    return f"resource/cursor/{name}.png"


class Cursor(object):
    def __init__(self):
        self.atlas = drawing.texture.TextureAtlas("cursor_atlas_0.png", "cursor_atlas.txt", extra_names=False)
        self.buffer = drawing.QuadBuffer(1024, ui=True, mouse_relative=True)
        self.cursor_quad = drawing.Quad(self.buffer)
        self.set_cursor("default")

    def disable(self):
        self.cursor_quad.disable()

    def enable(self):
        self.cursor_quad.enable()

    def set_cursor(self, name):
        try:
            subimage = self.get_subimage(name)
        except KeyError:
            raise Error(f"Unknown cursor named {name}")

        # We want to draw it so that the top left of the image is exactly at the mouse cursor

        bl = Point(0, -subimage.size.y)
        tr = Point(subimage.size.x, 0)
        self.cursor_quad.set_vertices(bl, tr, drawing.constants.DrawLevels.ui + 10)
        self.cursor_quad.set_texture_coordinates(self.atlas.texture_coords(expand_resource(name)))

    def draw(self):
        drawing.reset_state()
        drawing.translate(globals.mouse_screen.x, globals.mouse_screen.y, 0)
        drawing.draw_all(self.buffer, self.atlas.texture)
        drawing.reset_state()

    def get_subimage(self, name):
        return self.atlas.subimage(expand_resource(name))
