import pygame
import os
import numpy
import glob
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GL.framebufferobjects import *
from typing import Dict, Tuple, Optional, List
import globals

# drawing modules
from . import constants
from . import quads
from . import opengl
from . import sprite

from globals.types import Point

cache: Dict[str, Tuple[str, int, int]] = {}
global_scale = 1


class TextureImage(object):
    """Load a file into a gltexture and store that texture for later use"""

    def __init__(self, filename):
        filename = os.path.join(globals.dirs.resource, filename)
        if filename not in cache:
            with open(filename, "rb") as f:
                self.textureSurface = pygame.image.load(f)
            self.textureData = pygame.image.tostring(self.textureSurface, "RGBA", 1)

            self.width = self.textureSurface.get_width()
            self.height = self.textureSurface.get_height()

            self.texture = glGenTextures(1)
            cache[filename] = (self.texture, self.width, self.height)
            glBindTexture(GL_TEXTURE_2D, self.texture)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexImage2D(
                GL_TEXTURE_2D,
                0,
                GL_RGBA,
                self.width,
                self.height,
                0,
                GL_RGBA,
                GL_UNSIGNED_BYTE,
                self.textureData,
            )
        else:
            self.texture, self.width, self.height = cache[filename]
            glBindTexture(GL_TEXTURE_2D, self.texture)


class Texture(object):
    """Load a (potential) group of textures"""

    normal_texture: int
    occlude_texture: int
    displacement_texture: int

    def __init__(
        self,
        filename: str,
        normal_filename: Optional[str] = None,
        occlusion_filename: Optional[str] = None,
        displacement_filename: Optional[str] = None,
    ):
        self.filenames = [filename]
        for fname in normal_filename, occlusion_filename, displacement_filename:
            if fname:
                self.filenames.append(fname)
        self.textures = [TextureImage(filename) for filename in self.filenames]
        # They need to all be the same size...
        if len(set((im.width, im.height) for im in self.textures)) != 1:
            raise TypeError("Invalid texture sizes")

        self.width = self.textures[0].width
        self.height = self.textures[0].height
        self.texture = self.textures[0].texture
        for i, name in enumerate(("normal_texture", "occlude_texture", "displacement_texture")):
            try:
                t = self.textures[i + 1].texture
            except IndexError:
                t = None
            setattr(self, name, t)


class RenderTarget(object):
    """
    Create a texture for rendering onto. Call Target on the object, do some rendering, then call
    detarget. Hey presto, self.texture is now a texture containing that drawing!
    """

    def __init__(self, x, y, screensize):
        self.fbo = glGenFramebuffers(1)
        self.depthbuffer = glGenRenderbuffers(1)
        self.x = int(x)
        self.y = int(y)
        self.size = Point(x, y)
        self.screensize = screensize
        self.texture = glGenTextures(1)
        glActiveTexture(GL_TEXTURE0)
        glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, self.fbo)
        glBindTexture(GL_TEXTURE_2D, self.texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA8, self.x, self.y, 0, GL_RGBA, GL_UNSIGNED_BYTE, None)
        glBindRenderbufferEXT(GL_RENDERBUFFER_EXT, self.depthbuffer)
        glRenderbufferStorageEXT(GL_RENDERBUFFER_EXT, GL_DEPTH_COMPONENT, self.x, self.y)
        glFramebufferRenderbufferEXT(
            GL_FRAMEBUFFER_EXT, GL_DEPTH_ATTACHMENT, GL_RENDERBUFFER_EXT, self.depthbuffer
        )
        glFramebufferTexture2DEXT(
            GL_FRAMEBUFFER_EXT, GL_COLOR_ATTACHMENT0_EXT, GL_TEXTURE_2D, self.texture, 0
        )
        if glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT) != GL_FRAMEBUFFER_COMPLETE_EXT:
            print("crapso")
            raise SystemExit
        glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, 0)

    def target(self):
        glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, self.fbo)
        if glCheckFramebufferStatusEXT(GL_FRAMEBUFFER_EXT) != GL_FRAMEBUFFER_COMPLETE_EXT:
            print("crapso1")
            raise SystemExit

    def detarget(self):
        glBindFramebufferEXT(GL_FRAMEBUFFER_EXT, 0)


# texture atlas code taken from
# http://omnisaurusgames.com/2011/06/texture-atlas-generation-using-python/
# I'm assuming it's open source!


class SubImage(object):
    def __init__(self, pos, size):
        self.pos = pos
        self.size = size

    def texture_coordinates(self, left, right, top, bottom):
        left, right = [float(v) / self.size.x for v in (left, right)]
        top, bottom = [float(v) / self.size.y for v in (top, bottom)]
        return numpy.array(
            ((left, 1 - bottom), (left, 1 - top), (right, 1 - top), (right, 1 - bottom)), numpy.float32
        )


class TextureAtlas(object):
    def __init__(self, image_filename, data_filename, extra_names=True):
        if extra_names:
            extra_names = ("_normal", "_occlude", "_displace")
            extra_names = [image_filename[:-4] + extra + image_filename[-4:] for extra in extra_names]
        else:
            extra_names = []

        self.texture = Texture(image_filename, *extra_names)
        self.subimages = {}
        data_filename = os.path.join(globals.dirs.resource, data_filename)
        with open(data_filename, "r") as f:
            for line in f:
                subimage_name, image_name, x, y, w, h = line.strip().split(":")
                # print image_name,image_filename
                # assert(image_name) == image_filename
                w = int(w)
                h = int(h)
                if subimage_name.startswith("font_"):
                    subimage_name = chr(int(subimage_name[5:7], 16))
                    h -= 4
                subimage_name = "_".join(subimage_name.split("/"))
                self.subimages[subimage_name] = SubImage(
                    Point(float(x) / self.texture.width, float(y) / self.texture.height), (Point(w, h))
                )

    def subimage(self, name):
        name = "_".join(name.split("/"))
        return self.subimages[name]

    def transform_coord(self, subimage, value):
        value[0] = subimage.pos.x + value[0] * (float(subimage.size.x) / self.texture.width)
        value[1] = subimage.pos.y + value[1] * (float(subimage.size.y) / self.texture.height)

    def transform_coords(self, subimage, tc):
        subimage = "_".join(subimage.split("/"))
        subimage = self.subimages[subimage]
        for i in range(len(tc)):
            self.transform_coord(subimage, tc[i])

    def texture_coords(self, subimage):
        full_tc = [[0, 0], [0, 1], [1, 1], [1, 0]]
        self.transform_coords(subimage, full_tc)
        return full_tc


class PetsciiAtlas(TextureAtlas):
    """
    A texture atlas that takes a petscii image as a constructor and infers the subimage locations
    """

    def __init__(self, image_filename):
        self.texture = Texture(image_filename)
        self.subimages = {}
        image_name = os.path.basename(image_filename)
        for ch in range(0x20, 0xA0):
            subimage_name = chr(ch)
            if subimage_name.isalpha():
                subimage_name = chr(ch ^ 0x20)
            # get the row,col pos in the image, with the 0,0 being in the top left
            x = ch & 0xF
            y = ((ch - 0x20) >> 4) & 0xF
            # Now we need it relative to 0,0 in the top left, and all multiplied by 8 for pixel coords
            x *= 8
            y = (7 - y) * 8
            w = 8
            h = 8
            self.subimages[subimage_name] = SubImage(
                Point(float(x) / self.texture.width, float(y) / self.texture.height), (Point(w, h))
            )


class TextTypes:
    SCREEN_RELATIVE = 1
    GRID_RELATIVE = 2
    MOUSE_RELATIVE = 3
    CUSTOM = 4
    LEVELS = {
        SCREEN_RELATIVE: constants.DrawLevels.text,
        CUSTOM: constants.DrawLevels.text,
        GRID_RELATIVE: constants.DrawLevels.grid + 0.1,
        MOUSE_RELATIVE: constants.DrawLevels.text,
    }


class TextAlignments:
    LEFT = 1
    RIGHT = 2
    CENTRE = 3
    JUSTIFIED = 4


class TextManager(object):
    def __init__(self):
        # fontname,fontdataname = (os.path.join('fonts',name) for name in ('pixelmix.png','pixelmix.txt'))
        # self.atlas = TextureAtlas(fontname,fontdataname)
        self.atlas = PetsciiAtlas(os.path.join("fonts", "petscii.png"))
        self.font_height = max(subimage.size.y for subimage in self.atlas.subimages.values())
        # these are reclaimed when out of use so this means 131072 concurrent chars
        self.quads = quads.QuadBuffer(131072, ui=True)
        TextTypes.BUFFER = {
            TextTypes.SCREEN_RELATIVE: self.quads,
            TextTypes.GRID_RELATIVE: globals.nonstatic_text_buffer,
            TextTypes.MOUSE_RELATIVE: globals.mouse_relative_text,
        }

    def letter(self, char, textType, userBuffer=None):
        """Given a character, return a quad with the corresponding letter on it in this textManager's font"""
        quad = quads.Quad(userBuffer if textType == TextTypes.CUSTOM else TextTypes.BUFFER[textType])
        quad.tc[0:4] = self.atlas.texture_coords(char)
        # this is a bit dodge, should get its own class if I want to store extra things in it
        quad.width, quad.height = self.atlas.subimage(char).size
        quad.letter = char
        return quad

    def get_size(self, text, scale):
        """
        How big would the text be if drawn on a single row in the given size?
        """
        sizes = [self.atlas.subimage(char).size * scale * global_scale for char in text]
        out = Point(sum(item.x for item in sizes), max(item.y for item in sizes))
        return out

    def draw(self):
        glLoadIdentity()
        opengl.draw_all(self.quads, self.atlas.texture)

    def purge(self):
        self.quads.truncate(0)
