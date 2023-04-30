import drawing
import os

from OpenGL.arrays import numpymodule
from OpenGL.GL import *
from OpenGL.GLU import *
from OpenGL.GL import shaders
from OpenGL.GL.framebufferobjects import *
from globals.types import Point
import globals
import time
from . import constants
import itertools


numpymodule.NumpyHandler.ERROR_ON_COPY = True


class LightTypes:
    AMBIENT = 1
    POINT = 2
    SCREEN = 3  # This also does an ambient light to save passes, but you should only do one of these


class GeometryBuffer(object):
    TEXTURE_TYPE_DIFFUSE = 0
    TEXTURE_TYPE_NORMAL = 1
    TEXTURE_TYPE_DISPLACEMENT = 2
    TEXTURE_TYPE_OCCLUDE = 3
    TEXTURE_TYPE_SHADOW = 4  # Is this right? Not sure
    NUM_TEXTURES = 4

    def __init__(self, width, height):
        self.fbo = glGenFramebuffers(1)
        self.bind_for_writing()
        try:
            self.init_bound(width, height)
        finally:
            self.unbind()

    def init_bound(self, width, height):
        self.textures = glGenTextures(self.NUM_TEXTURES)
        if self.NUM_TEXTURES == 1:
            # Stupid inconsistent interface
            self.textures = [self.textures]
        self.depth_texture = glGenTextures(1)
        glActiveTexture(GL_TEXTURE0)

        for i in range(self.NUM_TEXTURES):
            glBindTexture(GL_TEXTURE_2D, self.textures[i])
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, width, height, 0, GL_RGBA, GL_FLOAT, None)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glFramebufferTexture2D(
                GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0 + i, GL_TEXTURE_2D, self.textures[i], 0
            )

        glBindTexture(GL_TEXTURE_2D, self.depth_texture)
        glTexImage2D(
            GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT32, width, height, 0, GL_DEPTH_COMPONENT, GL_FLOAT, None
        )
        glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, self.depth_texture, 0)

        glDrawBuffers(
            [GL_COLOR_ATTACHMENT0, GL_COLOR_ATTACHMENT1, GL_COLOR_ATTACHMENT2, GL_COLOR_ATTACHMENT3]
        )
        if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            print("crapso_")
            raise SystemExit

    def bind_for_writing(self):
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.fbo)

    def bind_for_reading(self):
        # glBindFramebuffer(GL_READ_FRAMEBUFFER, self.fbo)
        self.unbind()
        for i, texture in enumerate(self.textures):
            glActiveTexture(GL_TEXTURE0 + i)
            glBindTexture(GL_TEXTURE_2D, texture)

    def unbind(self):
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, 0)


class ShadowMapBuffer(GeometryBuffer):
    TEXTURE_TYPE_SHADOW = 0
    NUM_TEXTURES = 1
    # WIDTH               = 1024
    # HEIGHT              = 256

    def __init__(self):
        self.WIDTH = globals.screen.x
        self.HEIGHT = globals.screen.y
        super(ShadowMapBuffer, self).__init__(self.WIDTH, self.HEIGHT)

    def init_bound(self, width, height):
        self.textures = glGenTextures(self.NUM_TEXTURES)
        if self.NUM_TEXTURES == 1:
            # Stupid inconsistent interface
            self.textures = [self.textures]
        # self.depth_texture = glGenTextures(1)
        glActiveTexture(GL_TEXTURE0)

        for i in range(self.NUM_TEXTURES):
            glBindTexture(GL_TEXTURE_2D, self.textures[i])
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA32F, width, height, 0, GL_RGBA, GL_FLOAT, None)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameterf(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glFramebufferTexture2D(
                GL_DRAW_FRAMEBUFFER, GL_COLOR_ATTACHMENT0 + i, GL_TEXTURE_2D, self.textures[i], 0
            )

        # glBindTexture(GL_TEXTURE_2D, self.depth_texture)
        # glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT32, width, height, 0, GL_DEPTH_COMPONENT, GL_FLOAT, None)
        # glFramebufferTexture2D(GL_DRAW_FRAMEBUFFER, GL_DEPTH_ATTACHMENT, GL_TEXTURE_2D, self.depth_texture, 0)
        glDrawBuffers([GL_COLOR_ATTACHMENT0])

        if glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE:
            print("crapso")
            raise SystemExit

    def bind_for_writing(self):
        glBindFramebuffer(GL_DRAW_FRAMEBUFFER, self.fbo)

    def bind_for_reading(self, offset):
        self.unbind()
        for i, texture in enumerate(self.textures):
            glActiveTexture(GL_TEXTURE0 + i + offset)
            glBindTexture(GL_TEXTURE_2D, texture)


class ShaderLocations(object):
    def __init__(self):
        self.tex = None
        self.vertex_data = None
        self.tc_data = None
        self.colour_data = None
        self.using_textures = None
        self.screen_dimensions = None
        self.translation = None
        self.scale = None


class ShaderData(object):
    def __init__(self):
        self.program = None
        self.locations = ShaderLocations()
        self.dimensions = (0, 0, 0)

    def use(self):
        shaders.glUseProgram(self.program)
        state.set_shader(self)
        state.update()

    def load(self, name, uniforms, attributes):
        vertex_name, fragment_name = (
            os.path.join("drawing", "shaders", "%s_%s.glsl" % (name, typeof))
            for typeof in ("vertex", "fragment")
        )
        codes = []
        for name in vertex_name, fragment_name:
            with open(name, "rb") as f:
                data = f.read()
            codes.append(data)
        VERTEX_SHADER = shaders.compileShader(codes[0], GL_VERTEX_SHADER)
        FRAGMENT_SHADER = shaders.compileShader(codes[1], GL_FRAGMENT_SHADER)
        self.program = glCreateProgram()
        shads = (VERTEX_SHADER, FRAGMENT_SHADER)
        for shader in shads:
            glAttachShader(self.program, shader)
        self.fragment_shader_attrib_binding()
        self.program = shaders.ShaderProgram(self.program)
        glLinkProgram(self.program)
        self.program.check_validate()
        self.program.check_linked()
        for shader in shads:
            glDeleteShader(shader)
        # self.program    = shaders.compileProgram(VERTEX_SHADER,FRAGMENT_SHADER)
        for (namelist, func) in ((uniforms, glGetUniformLocation), (attributes, glGetAttribLocation)):
            for name in namelist:
                setattr(self.locations, name, func(self.program, name))

    def fragment_shader_attrib_binding(self):
        pass


class GeometryShaderData(ShaderData):
    def fragment_shader_attrib_binding(self):
        glBindFragDataLocation(self.program, 0, "diffuse")
        glBindFragDataLocation(self.program, 1, "normal")
        glBindFragDataLocation(self.program, 2, "displacement")
        glBindFragDataLocation(self.program, 3, "occlude")


class State(object):
    """Stores the state of the tactical viewer; position and scale"""

    def __init__(self, shader):
        self.set_shader(shader)
        self.reset()

    def set_shader(self, shader):
        self.shader = shader

    def reset(self):
        self.pos = Point(0, 0).to_float()
        self.scale = Point(1, 1).to_float()
        self.update()

    def update(self, pos=None, scale=None):
        if pos is None:
            pos = self.pos
        if scale is None:
            scale = self.scale
        if self.shader.locations.translation is not None:
            glUniform2f(self.shader.locations.translation, pos.x, pos.y)
        if self.shader.locations.scale is not None:
            glUniform2f(self.shader.locations.scale, scale.x, scale.y)


class UIBuffers(object):
    """Simple storage for ui_buffers that need to be drawn at the end of the frame after the scene has been fully rendered"""

    def __init__(self):
        self.reset()

    def add(self, quad_buffer, texture):
        if quad_buffer.mouse_relative:
            local_state = (state.pos, state.scale)
        else:
            local_state = None
        if texture is not None:
            self.buffers.append(((quad_buffer, texture, default_shader), local_state, draw_all_now))
        else:
            self.buffers.append(((quad_buffer, default_shader), local_state, draw_no_texture_now))

    def reset(self):
        self.buffers = []

    def draw(self):
        for args, local_state, func in self.buffers:
            if local_state:
                state.update(*local_state)

            func(*args)
            if local_state:
                state.update()


z_max = 10000
light_shader = ShaderData()
geom_shader = GeometryShaderData()
default_shader = ShaderData()
shadow_shader = ShaderData()
state = State(geom_shader)
ui_buffers = UIBuffers()
gbuffer = None
shadow_buffer = None


def init(w, h):
    global gbuffer, shadow_buffer
    """
    One time initialisation of the screen
    """
    light_shader.load(
        "light",
        uniforms=(
            "tex",
            "screen_dimensions",
            "translation",
            "scale",
            "displacement_map",
            "colour_map",
            "normal_map",
            "occlude_map",
            "shadow_map",
            "light_type",
            "light_pos",
            "ambient_colour",
            "ambient_attenuation",
            "directional_light_dir",
            "cone_dir",
            "shadow_index",
            "cone_width",
            "light_colour",
            "light_radius",
            "light_intensity",
        ),
        attributes=("vertex_data",),
    )

    geom_shader.load(
        "geometry",
        uniforms=(
            "screen_dimensions",
            "using_textures",
            "translation",
            "scale",
            "tex",
            "normal_tex",
            "occlude_tex",
            "displace_tex",
        ),
        attributes=("vertex_data", "tc_data", "normal_data", "occlude_data", "displace_data", "colour_data"),
    )

    default_shader.load(
        "default",
        uniforms=("tex", "translation", "scale", "screen_dimensions", "using_textures"),
        attributes=("vertex_data", "tc_data", "colour_data"),
    )

    shadow_shader.load(
        "shadow",
        uniforms=(
            "colour_map",
            "displacement_map",
            "normal_map",
            "occlude_map",
            "sb_dimensions",
            "screen_dimensions",
            "light_dimensions",
            "light_pos",
        ),
        attributes=("vertex_data",),
    )

    gbuffer = GeometryBuffer(w, h)
    shadow_buffer = ShadowMapBuffer()

    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

    set_render_dimensions(w, h, z_max)

    glEnable(GL_TEXTURE_2D)
    glEnable(GL_BLEND)
    glEnable(GL_DEPTH_TEST)
    # glAlphaFunc(GL_GREATER, 0.25);
    glEnable(GL_ALPHA_TEST)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


def reset_state():
    state.reset()


def translate(x, y, z):
    state.pos += Point(x, y)
    state.update()


def scale(x, y, z):
    state.scale = Point(x, y)
    state.update()


def new_frame():
    ui_buffers.reset()
    geom_shader.use()
    gbuffer.bind_for_writing()
    glDepthMask(GL_TRUE)
    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glEnable(GL_DEPTH_TEST)
    glEnable(GL_BLEND)
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)


def end_frame():
    glDepthMask(GL_FALSE)
    glDisable(GL_DEPTH_TEST)
    gbuffer.unbind()
    if globals.game_view:
        end_frame_game_mode()

    # default_shader.Use()
    # glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    # ui_buffers.draw()


def draw_ui():
    default_shader.use()
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    # glDepthMask(GL_TRUE)
    # glEnable(GL_DEPTH_TEST)
    # glEnable(GL_BLEND)
    # glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
    ui_buffers.draw()


def set_zoom(zoom):
    glUniform1f(light_shader.locations.zoom, 1)


def end_frame_game_mode():
    # Now we're going to try a light pass...

    gbuffer.bind_for_reading()
    shadow_buffer.bind_for_writing()
    glClearColor(0.0, 0.0, 1.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    # Create the shadow maps...
    shadow_shader.use()

    # do the mouse light
    glUniform2f(shadow_shader.locations.light_pos, *(globals.mouse_screen))
    quad_buffer = globals.shadow_quadbuffer
    glEnableVertexAttribArray(shadow_shader.locations.vertex_data)
    glVertexAttribPointer(
        shadow_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data
    )

    glDrawElements(GL_QUADS, 4, GL_UNSIGNED_INT, quad_buffer.indices)

    # Now do the other lights with shadows
    for light in itertools.chain(globals.lights, globals.cone_lights):
        glUniform2f(shadow_shader.locations.light_pos, *light.screen_pos[:2])
        # glVertexAttribPointer( shadow_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data )
        glDrawElements(GL_QUADS, 4, GL_UNSIGNED_INT, quad_buffer.indices[light.shadow_index * 4 :])

    # return

    shadow_buffer.bind_for_reading(gbuffer.NUM_TEXTURES)
    glBlendEquation(GL_FUNC_ADD)
    glBlendFunc(GL_ONE, GL_ONE)
    glClearColor(0.0, 0.0, 0.0, 1.0)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    light_shader.use()
    glUniform1f(light_shader.locations.light_radius, 400)
    glUniform1f(light_shader.locations.light_intensity, 1)

    scale(globals.scale.x, globals.scale.y, 1)
    # Need to draw some lights...
    timeofday = globals.game_view.timeofday
    quad_buffer = globals.light_quads
    sunlight_dir, sunlight_colour, ambient_colour, ambient_attenuation = timeofday.daylight()
    # ambient_colour = timeofday.Ambient()
    glUniform1i(light_shader.locations.light_type, 1)
    glUniform3f(light_shader.locations.directional_light_dir, *sunlight_dir)
    glUniform3f(light_shader.locations.light_colour, *sunlight_colour)
    glUniform3f(light_shader.locations.ambient_colour, *ambient_colour)
    glUniform1f(light_shader.locations.ambient_attenuation, ambient_attenuation)
    glEnableVertexAttribArray(light_shader.locations.vertex_data)
    glVertexAttribPointer(
        light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data
    )

    # This is the ambient light box around the whole screen for sunlight
    glDrawElements(GL_QUADS, quad_buffer.current_size, GL_UNSIGNED_INT, quad_buffer.indices)

    quad_buffer = globals.temp_mouse_light

    # Hack, do the mouse light separate for now so we can set it's position. Should be done elsewhere really and be in
    # the lights list

    # translate(-globals.game_view.viewpos.pos.x, -globals.game_view.viewpos.pos.y, 0)
    glUniform1i(light_shader.locations.light_type, 2)
    glUniform1i(light_shader.locations.shadow_index, 0)
    glUniform3f(light_shader.locations.light_pos, globals.mouse_screen.x, globals.mouse_screen.y, 120)
    glUniform3f(light_shader.locations.light_colour, 1, 1, 1)
    glUniform1f(light_shader.locations.cone_dir, 0)
    glUniform1f(light_shader.locations.cone_width, 4)
    glUniform1f(light_shader.locations.ambient_attenuation, 0)
    glVertexAttribPointer(
        light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data
    )
    globals.mouse_light_quad.set_vertices(
        globals.mouse_world - Point(400, 400), globals.mouse_world + Point(400, 400), 0.1
    )

    # glDrawElements(GL_QUADS, quad_buffer.current_size, GL_UNSIGNED_INT, quad_buffer.indices)

    # Now get the nighttime illumination
    # dev hack so I can see what's going on
    # nightlight_dir,nightlight_colour = timeofday.Nightlight()
    # quad_buffer = globals.nightlight_quads
    # glUniform1i(light_shader.locations.light_type, 1)
    # glUniform3f(light_shader.locations.directional_light_dir, *nightlight_dir)
    # glUniform3f(light_shader.locations.light_colour, *nightlight_colour)
    # glEnableVertexAttribArray( light_shader.locations.vertex_data );
    # glVertexAttribPointer( light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data )
    # glDrawElements(GL_QUADS,quad_buffer.current_size,GL_UNSIGNED_INT,quad_buffer.indices)

    # Scale(globals.scale.x,globals.scale.y,1)
    # translate(-globals.game_view.viewpos.pos.x,-globals.game_view.viewpos.pos.y,0)

    glUniform1i(light_shader.locations.light_type, 2)
    for light in globals.lights:

        if not light.on:
            continue

        glUniform1i(light_shader.locations.shadow_index, light.shadow_index)
        glUniform1i(light_shader.locations.light_type, 2)
        glUniform3f(light_shader.locations.light_pos, *light.screen_pos)
        glUniform3f(light_shader.locations.light_colour, *light.colour)
        glUniform1f(light_shader.locations.light_radius, light.radius)
        glUniform1f(light_shader.locations.ambient_attenuation, 0)
        glUniform1f(light_shader.locations.cone_dir, 0)
        glUniform1f(light_shader.locations.cone_width, 7)
        glVertexAttribPointer(
            light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, light.quad_buffer.vertex_data
        )
        glDrawElements(GL_QUADS, light.quad_buffer.current_size, GL_UNSIGNED_INT, light.quad_buffer.indices)

    glUniform1f(light_shader.locations.light_radius, 400)
    glUniform1f(light_shader.locations.light_intensity, 1)

    for light in globals.cone_lights:
        if not light.on:
            continue

        glUniform1i(light_shader.locations.light_type, 2)
        glUniform1i(light_shader.locations.shadow_index, light.shadow_index)
        glUniform3f(light_shader.locations.light_pos, *light.screen_pos)
        glUniform3f(light_shader.locations.light_colour, *light.colour)
        glUniform1f(light_shader.locations.cone_dir, light.angle)
        glUniform1f(light_shader.locations.cone_width, light.angle_width)

        glVertexAttribPointer(
            light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, light.quad_buffer.vertex_data
        )
        glDrawElements(GL_QUADS, light.quad_buffer.current_size, GL_UNSIGNED_INT, light.quad_buffer.indices)

    glUniform1i(light_shader.locations.light_type, 3)
    for light in globals.non_shadow_lights:
        if not light.on:
            continue
        glUniform3f(light_shader.locations.light_pos, *light.pos)
        glUniform3f(light_shader.locations.light_colour, *light.colour)
        glUniform1f(light_shader.locations.light_radius, light.radius)
        glUniform1f(light_shader.locations.light_intensity, light.intensity)
        glVertexAttribPointer(
            light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, light.quad_buffer.vertex_data
        )
        glDrawElements(GL_QUADS, light.quad_buffer.current_size, GL_UNSIGNED_INT, light.quad_buffer.indices)

    glUniform1i(light_shader.locations.light_type, 1)
    for light in globals.uniform_lights:
        glUniform3f(light_shader.locations.light_pos, *light.pos)
        glUniform3f(light_shader.locations.light_colour, *light.colour)
        glVertexAttribPointer(
            light_shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, light.quad_buffer.vertex_data
        )
        glDrawElements(GL_QUADS, light.quad_buffer.current_size, GL_UNSIGNED_INT, light.quad_buffer.indices)

    glDisableVertexAttribArray(light_shader.locations.vertex_data)
    reset_state()


def set_render_dimensions(x, y, z):
    geom_shader.dimensions = (x, y, z)


def get_render_dimensions():
    return geom_shader.dimensions


def init_drawing():
    """
    Should only need to be called once at the start (but after Init)
    to enable the full client state. We turn off and on again where necessary, but
    generally try to keep them all on
    """
    shadow_shader.use()
    glUniform1i(shadow_shader.locations.displacement_map, gbuffer.TEXTURE_TYPE_DISPLACEMENT)
    glUniform1i(shadow_shader.locations.colour_map, gbuffer.TEXTURE_TYPE_DIFFUSE)
    glUniform1i(shadow_shader.locations.normal_map, gbuffer.TEXTURE_TYPE_NORMAL)
    glUniform1i(shadow_shader.locations.occlude_map, gbuffer.TEXTURE_TYPE_OCCLUDE)
    glUniform3f(shadow_shader.locations.screen_dimensions, globals.screen.x, globals.screen.y, z_max)
    glUniform3f(shadow_shader.locations.sb_dimensions, globals.screen.x, globals.screen.y, 1)
    glUniform2f(shadow_shader.locations.light_dimensions, 256, 256)
    light_shader.use()
    glUniform1i(light_shader.locations.displacement_map, gbuffer.TEXTURE_TYPE_DISPLACEMENT)
    glUniform1i(light_shader.locations.colour_map, gbuffer.TEXTURE_TYPE_DIFFUSE)
    glUniform1i(light_shader.locations.normal_map, gbuffer.TEXTURE_TYPE_NORMAL)
    glUniform1i(light_shader.locations.occlude_map, gbuffer.TEXTURE_TYPE_OCCLUDE)
    glUniform1i(light_shader.locations.shadow_map, gbuffer.TEXTURE_TYPE_SHADOW)
    glUniform1f(light_shader.locations.light_radius, 400)
    glUniform1f(light_shader.locations.light_intensity, 1)
    glUniform3f(light_shader.locations.screen_dimensions, globals.screen.x, globals.screen.y, z_max)
    # glUniform1f(light_shader.locations.ambient_level, 0.3)
    default_shader.use()
    glUniform3f(default_shader.locations.screen_dimensions, globals.screen.x, globals.screen.y, z_max)
    glUniform1i(default_shader.locations.tex, 0)
    geom_shader.use()
    glUniform1i(geom_shader.locations.tex, 0)
    glUniform1i(geom_shader.locations.normal_tex, 1)
    glUniform1i(geom_shader.locations.occlude_tex, 2)
    glUniform1i(geom_shader.locations.displace_tex, 3)
    glUniform3f(geom_shader.locations.screen_dimensions, globals.screen.x, globals.screen.y, z_max)


def draw_all(quad_buffer, texture):
    """
    Draw a quadbuffer with with a vertex array, texture coordinate array, and a colour
    array
    """
    if quad_buffer.is_ui:
        ui_buffers.add(quad_buffer, texture)
        return
    draw_all_now_normals(quad_buffer, texture, geom_shader)


def draw_all_now_normals(quad_buffer, texture, shader):
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, texture.texture)
    glActiveTexture(GL_TEXTURE1)
    glBindTexture(GL_TEXTURE_2D, texture.normal_texture)
    glActiveTexture(GL_TEXTURE2)
    glBindTexture(GL_TEXTURE_2D, texture.occlude_texture)
    glActiveTexture(GL_TEXTURE3)
    glBindTexture(GL_TEXTURE_2D, texture.displacement_texture)

    glUniform1i(shader.locations.using_textures, 1)

    glEnableVertexAttribArray(shader.locations.vertex_data)
    glEnableVertexAttribArray(shader.locations.tc_data)
    glEnableVertexAttribArray(shader.locations.normal_data)
    glEnableVertexAttribArray(shader.locations.occlude_data)
    glEnableVertexAttribArray(shader.locations.displace_data)
    glEnableVertexAttribArray(shader.locations.colour_data)

    glVertexAttribPointer(shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data)
    glVertexAttribPointer(shader.locations.tc_data, 2, GL_FLOAT, GL_FALSE, 0, quad_buffer.tc_data)
    glVertexAttribPointer(shader.locations.normal_data, 2, GL_FLOAT, GL_FALSE, 0, quad_buffer.tc_data)
    glVertexAttribPointer(shader.locations.occlude_data, 2, GL_FLOAT, GL_FALSE, 0, quad_buffer.tc_data)
    glVertexAttribPointer(shader.locations.displace_data, 2, GL_FLOAT, GL_FALSE, 0, quad_buffer.tc_data)
    glVertexAttribPointer(shader.locations.colour_data, 4, GL_FLOAT, GL_FALSE, 0, quad_buffer.colour_data)

    glDrawElements(GL_QUADS, quad_buffer.current_size, GL_UNSIGNED_INT, quad_buffer.indices)
    glDisableVertexAttribArray(shader.locations.vertex_data)
    glDisableVertexAttribArray(shader.locations.tc_data)
    glDisableVertexAttribArray(shader.locations.normal_data)
    glDisableVertexAttribArray(shader.locations.occlude_data)
    glDisableVertexAttribArray(shader.locations.displace_data)
    glDisableVertexAttribArray(shader.locations.colour_data)


def draw_all_now(quad_buffer, texture, shader):
    # This is a copy paste from the above function, but this is the inner loop of the program, and we need it to be fast.
    # I'm not willing to put conditionals around the normal lines, so I made a copy of the function without them
    glActiveTexture(GL_TEXTURE0)
    glBindTexture(GL_TEXTURE_2D, texture.texture)
    glUniform1i(shader.locations.using_textures, 1)

    glEnableVertexAttribArray(shader.locations.vertex_data)
    glEnableVertexAttribArray(shader.locations.tc_data)
    glEnableVertexAttribArray(shader.locations.colour_data)

    glVertexAttribPointer(shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data)
    glVertexAttribPointer(shader.locations.tc_data, 2, GL_FLOAT, GL_FALSE, 0, quad_buffer.tc_data)
    glVertexAttribPointer(shader.locations.colour_data, 4, GL_FLOAT, GL_FALSE, 0, quad_buffer.colour_data)

    glDrawElements(GL_QUADS, quad_buffer.current_size, GL_UNSIGNED_INT, quad_buffer.indices)
    glDisableVertexAttribArray(shader.locations.vertex_data)
    glDisableVertexAttribArray(shader.locations.tc_data)
    glDisableVertexAttribArray(shader.locations.colour_data)


def draw_no_texture(quad_buffer):
    """
    Draw a quadbuffer with only vertex arrays and colour arrays. We need to make sure that
    we turn the clientstate for texture coordinates back on after we're finished
    """
    if quad_buffer.is_ui:
        ui_buffers.add(quad_buffer, None)
        return
    draw_no_texture_now(quad_buffer, geom_shader)


def draw_no_texture_now(quad_buffer, shader):

    glUniform1i(shader.locations.using_textures, 0)

    glEnableVertexAttribArray(shader.locations.vertex_data)
    glEnableVertexAttribArray(shader.locations.colour_data)

    glVertexAttribPointer(shader.locations.vertex_data, 3, GL_FLOAT, GL_FALSE, 0, quad_buffer.vertex_data)
    glVertexAttribPointer(shader.locations.colour_data, 4, GL_FLOAT, GL_FALSE, 0, quad_buffer.colour_data)

    glDrawElements(quad_buffer.draw_type, quad_buffer.current_size, GL_UNSIGNED_INT, quad_buffer.indices)

    glDisableVertexAttribArray(shader.locations.vertex_data)
    glDisableVertexAttribArray(shader.locations.colour_data)


def line_width(width):
    glEnable(GL_LINE_SMOOTH)
    glLineWidth(width)
