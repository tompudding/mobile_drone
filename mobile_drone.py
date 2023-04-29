import pygame
import ui
import globals
import drawing
from globals.types import Point, Segment
import sounds
import game
import pymunk
import sys
import time
import os
from typing import Generator, List


def light_lister():
    for light in itertools.chain(globals.shadow_lights, globals.non_shadow_lights):
        yield light


def init():
    """Initialise everything. Run once on startup"""
    if hasattr(sys, "_MEIPASS"):
        os.chdir(sys._MEIPASS)

    try:
        if "i3" == os.environ["DESKTOP_SESSION"]:
            os.environ["SDL_VIDEO_WINDOW_POS"] = "500,400"
    except KeyError:
        pass

    w, h = (1280, 720)

    globals.dirs = globals.types.Directories("resource")

    globals.screen = Point(w, h)
    globals.scale = Point(3, 3)
    globals.screen_root = ui.UIRoot(Point(0, 0), globals.screen)
    globals.ui_state = ui.UIState()
    globals.time_step = 1
    globals.epsilon = 0.001
    globals.t = globals.time = 0

    # Light stuff
    globals.shadow_lights = []
    globals.crt_lights = []
    globals.non_shadow_lights = []
    globals.cone_lights = []
    globals.uniform_lights = []
    globals.lights = []
    globals.daytime_dependent = set()
    globals.light_lister = light_lister

    globals.quad_buffer = drawing.QuadBuffer(131072)
    globals.light_quads = drawing.QuadBuffer(16384)
    globals.nightlight_quads = drawing.QuadBuffer(16)
    globals.nonstatic_text_buffer = drawing.QuadBuffer(131072)
    globals.screen_quadbuffer = drawing.QuadBuffer(16)
    globals.space = pymunk.Space()  # Create a Space which contain the simulation
    globals.space.gravity = (0.0, -300.0)
    globals.space.damping = 0.999  # to prevent it from blowing up.

    # Hackeroo
    globals.temp_mouse_light = drawing.QuadBuffer(16)
    globals.mouse_light_quad = drawing.Quad(globals.temp_mouse_light)
    globals.mouse_world = Point(0, 0)

    # Put lines around the screen
    # bottom = Segment(
    #     globals.space.static_body,
    #     globals.screen_root.absolute.bottom_left,
    #     globals.screen_root.absolute.bottom_right,
    #     0.0,
    # )
    # # bottom.sensor = True
    # bottom.collision_type = game.CollisionTypes.BOTTOM
    # static_lines = [bottom]

    # # left hand side
    # static_lines.append(
    #     Segment(
    #         globals.space.static_body,
    #         globals.screen_root.absolute.bottom_left,
    #         globals.screen_root.absolute.top_left,
    #         0.0,
    #     )
    # )
    # # top
    # static_lines.append(
    #     Segment(
    #         globals.space.static_body,
    #         globals.screen_root.absolute.top_left,
    #         globals.screen_root.absolute.top_right,
    #         0.0,
    #     )
    # )
    # # right
    # static_lines.append(
    #     Segment(
    #         globals.space.static_body,
    #         globals.screen_root.absolute.top_right,
    #         globals.screen_root.absolute.bottom_right,
    #         0.0,
    #     )
    # )
    # for i, l in enumerate(static_lines):
    #     l.friction = 1
    #     l.elasticity = 0.95
    #     if i == 0:
    #         l.collision_type = game.CollisionTypes.BOTTOM
    #     else:
    #         l.collision_type = game.CollisionTypes.WALL

    # globals.space.add(*static_lines)

    globals.screen.full_quad = drawing.Quad(globals.screen_quadbuffer)
    globals.screen.full_quad.set_vertices(Point(0, 0), globals.screen, 0.01)
    globals.ui_buffer = drawing.QuadBuffer(131072, ui=True)
    globals.screen_relative = drawing.QuadBuffer(131072, ui=True)
    globals.shadow_quadbuffer = drawing.ShadowQuadBuffer(256 * 4)
    globals.line_buffer = drawing.LineBuffer(131072)
    globals.sounds = sounds.Sounds()

    globals.mouse_relative_text = drawing.QuadBuffer(1024, ui=True, mouse_relative=True)

    # more hackeroo
    globals.temp_mouse_shadow = globals.shadow_quadbuffer.new_light()

    globals.mouse_screen = Point(0, 0)
    globals.tiles = None

    pygame.init()
    screen = pygame.display.set_mode((w, h), pygame.OPENGL | pygame.DOUBLEBUF)
    pygame.display.set_caption("LD53")
    pygame.mouse.set_visible(False)
    drawing.init(*globals.screen)
    globals.cursor = drawing.cursors.Cursor()

    globals.text_manager = drawing.texture.TextManager()


def main_run():

    done = False
    last = 0
    clock = pygame.time.Clock()
    last_handled = False

    while not done:

        clock.tick(60)
        t = pygame.time.get_ticks()
        fps = clock.get_fps()
        if t - last > 1000:
            print("FPS:", fps)
            last = t

        globals.t = globals.time = t
        if fps == 0:
            fps = 50
        iterations = 25
        globals.dt = dt = 1.0 / float(fps) / float(iterations)
        for x in range(iterations):  # 10 iterations to get a more stable simulation
            globals.current_view.apply_forces()
            globals.space.step(dt)

        drawing.new_frame()
        globals.current_view.update(t)
        globals.current_view.draw()

        # drawing.draw_no_texture(globals.ui_buffer)

        drawing.line_width(2)
        drawing.draw_no_texture(globals.line_buffer)

        drawing.end_frame()
        globals.screen_root.draw()
        globals.text_manager.draw()
        globals.cursor.draw()

        drawing.draw_ui()

        pygame.display.flip()

        eventlist = pygame.event.get()
        for event in eventlist:
            if event.type == pygame.locals.QUIT:
                done = True
                break

            elif event.type == pygame.KEYDOWN:
                try:
                    key = ord(event.unicode)
                except (AttributeError, TypeError):
                    key = event.key

                globals.current_view.key_down(key)
            elif event.type == pygame.KEYUP:
                try:
                    key = ord(event.unicode)
                except AttributeError:
                    key = event.key
                except TypeError:
                    continue
                globals.current_view.key_up(key)
            else:
                try:
                    pos = Point(event.pos[0], globals.screen[1] - event.pos[1])
                except AttributeError:
                    continue
                if event.type == pygame.MOUSEMOTION:
                    rel = Point(event.rel[0], -event.rel[1])
                    globals.mouse_screen = pos
                    if globals.dragging:
                        globals.dragging.mouse_motion(pos, rel, False)
                    else:
                        handled = globals.screen_root.mouse_motion(pos, rel, False)
                        # Only cancel the mouse motion if wasn't cancelled already
                        if handled and not last_handled:
                            globals.current_view.cancel_mouse_motion()
                        last_handled = handled
                        globals.current_view.mouse_motion(pos, rel, True if handled else False)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    for layer in globals.screen_root, globals.current_view:
                        handled, dragging = layer.mouse_button_down(pos, event.button)
                        if handled and dragging:
                            globals.dragging = dragging
                            break
                        if handled:
                            break

                elif event.type == pygame.MOUSEBUTTONUP:
                    for layer in globals.screen_root, globals.current_view:
                        handled, dragging = layer.mouse_button_up(pos, event.button)
                        if handled and not dragging:
                            globals.dragging = None
                        if handled:
                            break


def main():
    """Main loop for the game"""
    init()

    # globals.current_view = main_menu.MainMenu()
    # globals.main_menu = globals.current_view

    globals.dragging = None

    drawing.init_drawing()

    globals.game_view = game.GameView()
    globals.current_view = globals.game_view

    main_run()


if __name__ == "__main__":
    import logging

    try:
        logging.basicConfig(level=logging.DEBUG, filename="errorlog.log")
        # logging.basicConfig(level=logging.DEBUG)
    except IOError:
        # pants, can't write to the current directory, try using a tempfile
        pass

    try:
        main()
    except Exception as e:
        print("Caught exception, writing to error log...")
        logging.exception("Oops:")
        # Print it to the console too...
        raise
