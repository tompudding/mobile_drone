import globals
import drawing
from globals.types import Point
import bisect
import pygame


class UIState(object):
    def __init__(self):
        self.debug_mode = False

    def toggle_debug(self):
        self.debug_mode = False if self.debug_mode else True


class UIElementList:
    """
    Very basic implementation of a list of UIElements that can be looked up by position.
    It's using an O(n) algorithm, and I'm sure I can do better once everything's working
    """

    def __init__(self):
        self.items = {}

    def __setitem__(self, item, value):
        self.items[item] = value

    def __delitem__(self, item):
        del self.items[item]

    def __contains__(self, item):
        return item in self.items

    def __str__(self):
        return repr(self)

    def __repr__(self):
        out = ["UIElementList:"]
        for item in self.items:
            out.append(
                "%s:%s - %s(%s)"
                % (
                    item.absolute.bottom_left,
                    item.absolute.top_right,
                    str(item),
                    item.text if hasattr(item, "text") else "N/A",
                )
            )
        return "\n".join(out)

    def get(self, pos):
        """Return the object at a given absolute position, or None if None exist"""
        match = [-1, None]
        for ui, height in self.items.items():
            if pos in ui and ui.selectable():
                if height > match[0]:
                    match = [height, ui]
        return match[1]


class AbsoluteBounds(object):
    """
    Store the bottom left, top right and size data for a rectangle in screen coordinates. We could
    ask the parent and compute this each time, but it will be more efficient if we store it and
    use it directly, and rely on the parent to update its children when things change
    """

    def __init__(self):
        self.bottom_left = None
        self.top_right = None
        self.size = None

    @property
    def bottom_right(self):
        return Point(self.top_right.x, self.bottom_left.y)

    @property
    def top_left(self):
        return Point(self.bottom_left.x, self.top_right.y)


class UIElement(object):
    """Base class for all UI elements that can be drawn to the screen, including things like text boxes and
    buttons and all menus and so forth. UIElements all have a parent (which is None for the root element), and
    coords are given relative to the parent.

    When a UIElements's position or size changes, it updates all of its children so they can work out their
    new position and size

    """

    def __init__(self, parent, pos, tr):
        self.parent = parent
        self.absolute = AbsoluteBounds()
        self.on = True
        self.children = []
        self.parent.add_child(self)
        self.get_absolute_in_parent = parent.get_absolute
        self.root = parent.root
        self.level = parent.level + 1
        self.set_bounds(pos, tr)
        self.enabled = False
        self.dragging = None

    def set_bounds(self, pos, tr):
        self.absolute.bottom_left = self.get_absolute_in_parent(pos)
        self.absolute.top_right = self.get_absolute_in_parent(tr)
        self.absolute.size = self.absolute.top_right - self.absolute.bottom_left
        self.bottom_left = pos
        self.top_right = tr
        self.size = tr - pos

    def update_position(self):
        self.set_bounds(self.bottom_left, self.top_right)
        for child_element in self.children:
            child_element.update_position()

    def set_pos(self, pos):
        """Called by the user to update our position directly"""
        self.set_bounds(pos, pos + self.size)
        self.update_position()

    def get_absolute(self, p):
        """
        Given a position in coords relative to this object, return coordinates relative to the root object
        (usually screen coords)
        """
        return self.absolute.bottom_left + (self.absolute.size * p)

    def get_relative(self, p):
        """
        Given a position in coords relative to the root object (Probably screen coords), return coords relative
        to this object
        """
        return (p - self.absolute.bottom_left) / self.absolute.size.to_float()

    def add_child(self, element):
        self.children.append(element)

    def remove_child(self, element):
        for i, child in enumerate(self.children):
            if child is element:
                break
        else:
            return
        del self.children[i]

    def __contains__(self, pos):
        """
        Is a given point inside this Element? The point is in absolute coords
        """
        if pos.x < self.absolute.bottom_left.x or pos.x >= self.absolute.top_right.x:
            return False
        if pos.y >= self.absolute.bottom_left.y and pos.y < self.absolute.top_right.y:
            return True
        return False

    def hover(self):
        """
        Called when the mouse cursor first moves over this element
        """
        pass

    def end_hover(self):
        """
        Called when the mouse cursor moves off this object
        """
        pass

    def depress(self, pos):
        """
        Called when you the mouse cursor is over the element and the button is pushed down. If the cursor
        is moved away while the button is still down, and then the cursor is moved back over this element
        still with the button held down, this is called again.

        Returns the target of a dragging event if any. For example, if we return self, then we indicate
        that we have begun a drag and want to receive all mousemotion events until that drag is ended.
        """
        if globals.ui_state.debug_mode:
            self.dragging = self.parent.get_relative(pos)
            return self
        else:
            return None

    def undepress(self, pos):
        """
        Called after depress has been called, either when the button is released while the cursor is still
        over the element (In which case a on_click is called too), or when the cursor moves off the element
        (when on_click is not called)
        """
        self.dragging = None

    def on_click(self, pos, button):
        """
        Called when the mouse button is pressed and released over an element (although the cursor may move
        off and return between those two events). Pos is absolute coords
        """
        pass

    def scroll(self, amount):
        """
        Called with the value of 1 for a scroll up, and -1 for a scroll down event. Other things could call
        this with larger values for a bigger scoll action
        """
        pass

    def mouse_motion(self, pos, rel, handled):
        """
        Called when the mouse is moved over the element. Pos is absolute coords
        """
        if globals.ui_state.debug_mode and self.dragging:
            diff = self.parent.get_relative(pos) - self.dragging
            self.dragging = self.dragging + diff
            self.set_pos(self.bottom_left + diff)
            print("%s at %s" % (type(self), self.bottom_left))
            return True

    def selectable(self):
        return self.on

    def disable(self):
        for child in self.children:
            child.disable()
        self.enabled = False

    def enable(self):
        for child in self.children:
            child.enable()
        self.enabled = True

    def delete(self):
        self.disable()
        for child in self.children:
            child.delete()

    def make_selectable(self):
        self.on = True
        for child in self.children:
            child.make_selectable()

    def make_unselectable(self):
        self.on = False
        for child in self.children:
            child.make_unselectable()

    def __hash__(self):
        return hash((self.absolute.bottom_left, self.absolute.top_right, self.level))


class RootElement(UIElement):
    """
    A Root Element has no parent. It represents the top level UI element, and thus its coords are
    screen coords. It handles dispatching mouse movements and events. All of its children and
    grand-children (and so on) can register with it (and only it) for handling mouse actions,
    and those actions get dispatched
    """

    def __init__(self, bl, tr):
        self.absolute = AbsoluteBounds()
        self.on = True
        self.get_absolute_in_parent = lambda x: x
        self.root = self
        self.level = 0
        self.hovered = None
        self.children = []
        self.active_children = UIElementList()
        self.depressed = None
        self.cheats = ()
        self.set_bounds(bl, tr)

    def register_ui_element(self, element):
        self.active_children[element] = element.level

    def remove_ui_element(self, element):
        try:
            del self.active_children[element]
        except KeyError:
            pass

    def remove_all_ui_elements(self):
        toremove = [child for child in self.active_children.items]
        for child in toremove:
            child.delete()
        self.active_children = UIElementList()

    def key_down(self, key):
        #        if key == pygame.locals.K_RETURN:
        #            if self.current_player.is_player():
        #                self.current_player.end_turn(Point(0,0))
        if key == pygame.locals.K_ESCAPE:
            self.quit(0)
        for cheat in self.cheats:
            cheat.key_down(key)

    def key_up(self, key):
        pass

    def mouse_motion(self, pos, rel, handled):
        """
        Try to handle mouse motion. If it's over one of our elements, return True to indicate that
        the lower levels should not handle it. Else return false to indicate that they should
        """
        if handled:
            return handled
        hovered = self.active_children.get(pos)
        # I'm not sure about the logic here. It might be a bit inefficient. Seems to work though
        if hovered:
            hovered.mouse_motion(pos, rel, handled)
        if hovered is not self.hovered:
            if self.hovered is not None:
                self.hovered.end_hover()
        if not hovered or not self.depressed or (self.depressed and hovered is self.depressed):
            if hovered is not self.hovered:
                if hovered:
                    hovered.hover()
        self.hovered = hovered

        return True if hovered else False

    def mouse_button_down(self, pos, button):
        """
        Handle a mouse click at the given position (screen coords) of the given mouse button.
        Return whether it was handled, and whether it started a drag event
        """
        dragging = None
        if self.hovered:
            if button == 1:
                # If you click and hold on a button, it becomes depressed. If you then move the mouse away,
                # it becomes undepressed, and you can move the mouse back and depress it again (as long as you
                # keep the mouse button down. You can't move over another button and depress it though, so
                # we record which button is depressed
                if self.depressed:
                    # Something's got a bit messed up and we must have missed undepressing that last depressed
                    # button. Do that now
                    self.depressed.undepress(pos)
                self.depressed = self.hovered
                dragging = self.depressed.depress(pos)
            elif button == 4:
                self.hovered.scroll(1)
            elif button == 5:
                self.hovered.scroll(-1)
            elif button == 3:
                self.hovered.on_click(pos, button)
        return True if self.hovered else False, dragging

    def mouse_button_up(self, pos, button):
        handled = False
        if button == 1:
            if self.hovered and self.hovered is self.depressed:
                self.hovered.on_click(pos, button)
                handled = True
            if self.depressed:
                # Whatever happens, the button gets depressed
                self.depressed.undepress(pos)
                self.depressed = None

            return handled, False
        return False, False

    def cancel_mouse_motion(self):
        pass


class UIRoot(RootElement):
    """A RootElement that also handle two additional types of children to allow for more advanced render;
    drawable children and updateable children.

    Child types can register with us as drawable, and every frame we will call their draw function.  This
    allows for more complex drawing such as using viewports to take advantage of hardware acceleration to give
    smooth scrolling.

    Children can also register with us as updateable, which means their update method will get called every
    frame. This is to allow for animations and so forth, currently just the fader text box which fades out
    over time.

    """

    def __init__(self, *args, **kwargs):
        super(UIRoot, self).__init__(*args, **kwargs)
        self.drawable_children = {}
        self.updateable_children = {}

    def draw(self):
        drawing.reset_state()
        drawing.draw_no_texture(globals.ui_buffer)

        for item in self.drawable_children:
            item.draw()

    def draw_last(self):
        pass

    def update(self, t):
        """
        When we have updateable children, they can indicate to us that they are complete,
        which allows us to stop updating them and save time
        """
        # self.updateable_children = {item : value for item,value in self.updateable_children.iteritems() if (not item.enabled or not item.update(t))}
        new_children = {}
        for item, value in list(self.updateable_children.items()):
            complete = False
            if item.enabled:
                complete = item.update(t)
            if not complete:
                new_children[item] = value
        self.updateable_children = new_children
        # to_remove = []
        # for item in self.updateable_children:
        #     if item.enabled:
        #         complete = item.update(t)
        #         if complete:
        #             to_remove.append(item)
        # print to_remove
        # if len(to_remove) > 0:
        #     for item in to_remove:
        #         self.remove_updatable(item)

    def register_drawable(self, item):
        self.drawable_children[item] = True

    def remove_drawable(self, item):
        try:
            del self.drawable_children[item]
        except KeyError:
            pass

    def register_updateable(self, item):
        self.updateable_children[item] = True

    def remove_updatable(self, item):
        try:
            del self.updateable_children[item]
        except KeyError:
            print("failed to remove", item, "from", self.updateable_children)
        else:
            print("removed", item)


class HoverableElement(UIElement):
    """
    This class represents a UI element that accepts a hover; i.e when the cursor is over it the hover event
    does not get passed through to the next layer.
    """

    def __init__(self, parent, pos, tr):
        super(HoverableElement, self).__init__(parent, pos, tr)
        self.root.register_ui_element(self)

    def delete(self):
        self.root.remove_ui_element(self)
        super(HoverableElement, self).delete()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
        super(HoverableElement, self).disable()

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
        super(HoverableElement, self).enable()


class Box(UIElement):
    """A coloured box. Pretty boring!"""

    def __init__(self, parent, pos, tr, colour):
        super(Box, self).__init__(parent, pos, tr)
        self.quad = drawing.Quad(globals.ui_buffer)
        self.colour = colour
        self.unselectable_colour = tuple(component * 0.6 for component in self.colour)
        self.quad.set_colour(self.colour)
        self.quad.set_vertices(
            self.absolute.bottom_left, self.absolute.top_right, drawing.constants.DrawLevels.ui
        )
        self.enable()

    def update_position(self):
        super(Box, self).update_position()
        self.quad.set_vertices(self.absolute.bottom_left, self.absolute.top_right, drawing.constants.ui_level)

    def delete(self):
        super(Box, self).delete()
        self.quad.delete()

    def disable(self):
        if self.enabled:
            self.quad.disable()
        super(Box, self).disable()

    def enable(self):
        if not self.enabled:
            self.quad.enable()
        super(Box, self).enable()

    def make_selectable(self):
        super(Box, self).make_selectable()
        self.quad.set_colour(self.colour)

    def make_unselectable(self):
        super(Box, self).make_unselectable()
        self.quad.set_colour(self.unselectable_colour)


class HoverableBox(Box, HoverableElement):
    pass


class TextBox(UIElement):
    """A Screen-relative text box wraps text to a given size"""

    def __init__(
        self,
        parent,
        bl,
        tr,
        text,
        scale,
        colour=None,
        textType=drawing.texture.TextTypes.SCREEN_RELATIVE,
        alignment=drawing.texture.TextAlignments.LEFT,
    ):
        if tr is None:
            # If we're given no tr; just set it to one row of text, as wide as it can get without overflowing
            # the parent
            self.shrink_to_fit = True
            text_size = globals.text_manager.get_size(text, scale).to_float() / parent.absolute.size
            margin = Point(text_size.y * 0.06, text_size.y * 0.15)
            tr = bl + text_size + margin * 2  # Add a little breathing room by using 2.1 instead of 2
            # We'd like to store the margin relative to us, rather than our parent
            self.margin = margin / (tr - bl)
        else:
            self.shrink_to_fit = False
        super(TextBox, self).__init__(parent, bl, tr)
        if not self.shrink_to_fit:
            # In this case our margin is a fixed part of the box
            self.margin = Point(0.05, 0.05)
        self.text = text
        self.scale = scale
        self.colour = colour
        self.text_type = textType
        self.alignment = alignment
        self.text_manager = globals.text_manager
        self.reallocate_resources()
        # self.quads       = [self.text_manager.letter(char,self.text_type) for char in self.text]
        self.viewpos = 0
        # that sets the texture coords for us
        self.position(self.bottom_left, self.scale, self.colour)
        self.enable()

    def position(self, pos, scale, colour=None, ignore_height=False):
        """Draw the text at the given location and size. Maybe colour too"""
        # set up the position for the characters. Note that we do everything here in size relative
        # to our text box (so (0,0) is bottom_left, (1,1) is top_right.
        self.pos = pos
        self.absolute.bottom_left = self.get_absolute_in_parent(pos)
        self.scale = scale
        self.lowest_y = 0
        row_height = (
            float(self.text_manager.font_height * self.scale * drawing.texture.global_scale)
            / self.absolute.size.y
        )
        # Do this without any kerning or padding for now, and see what it looks like
        cursor = Point(self.margin.x, -self.viewpos + 1 - row_height - self.margin.y)
        letter_sizes = [
            Point(
                float(quad.width * self.scale * drawing.texture.global_scale) / self.absolute.size.x,
                float(quad.height * self.scale * drawing.texture.global_scale) / self.absolute.size.y,
            )
            for quad in self.quads
        ]
        # for (i,(quad,letter_size)) in enumerate(zip(self.quads,letter_sizes)):
        i = 0
        while i < len(self.quads):
            quad, letter_size = self.quads[i], letter_sizes[i]
            if cursor.x + letter_size.x > (1 - self.margin.x) * 1.001:
                # This would take us over a line. If we're in the middle of a word, we need to go back to the start of the
                # word and start the new line there
                restart = False
                if quad.letter in " \t":
                    # It's whitespace, so ok to start a new line, but do it after the whitespace
                    try:
                        while self.quads[i].letter in " \t":
                            i += 1
                    except IndexError:
                        break
                    restart = True
                else:
                    # look for the start of the word
                    while i >= 0 and self.quads[i].letter not in " \t":
                        i -= 1
                    if i <= 0:
                        # This single word is too big for the line. Shit, er, lets just bail
                        break
                    # skip the space
                    i += 1
                    restart = True

                cursor.x = self.margin.x
                cursor.y -= row_height * 1.2
                if restart:
                    continue

            if cursor.x == self.margin.x and self.alignment == drawing.texture.TextAlignments.CENTRE:
                # If we're at the start of a row, and we're trying to centre the text, then check to see how full this row is
                # and if it's not full, offset so that it becomes centred
                width = 0
                for size in letter_sizes[i:]:
                    width += size.x
                    if width > 1 - self.margin.x:
                        width -= size.x
                        break
                if width > 0:
                    cursor.x += float(1 - (self.margin.x * 2) - width) / 2

            target_bl = cursor
            target_tr = target_bl + letter_size
            if target_bl.y < self.lowest_y:
                self.lowest_y = target_bl.y
            if target_bl.y < 0 and not ignore_height:
                # We've gone too far, no more room to write!
                break
            absolute_bl = self.get_absolute(target_bl)
            absolute_tr = self.get_absolute(target_tr)
            self.set_letter_vertices(
                i, absolute_bl, absolute_tr, drawing.texture.TextTypes.LEVELS[self.text_type]
            )
            if colour:
                quad.set_colour(colour)
            cursor.x += letter_size.x
            i += 1
        # For the quads that we're not using right now, set them to display nothing
        for quad in self.quads[i:]:
            quad.set_vertices(Point(0, 0), Point(0, 0), -10)
        height = max([q.height for q in self.quads])
        super(TextBox, self).update_position()

    def set_letter_vertices(self, index, bl, tr, textType):
        self.quads[index].set_vertices(bl, tr, textType)

    def update_position(self):
        """Called by the parent to tell us we need to recalculate our absolute position"""
        super(TextBox, self).update_position()
        self.position(self.pos, self.scale, self.colour)

    def set_pos(self, pos):
        """Called by the user to update our position directly"""
        self.set_bounds(pos, pos + self.size)
        self.position(pos, self.scale, self.colour)

    def set_colour(self, colour):
        self.colour = colour
        for quad in self.quads:
            quad.set_colour(colour)

    def delete(self):
        """We're done; pack up and go home!"""
        super(TextBox, self).delete()
        for quad in self.quads:
            quad.delete()

    def set_text(self, text, colour=None):
        enabled = self.enabled
        self.delete()
        if enabled:
            self.enable()
        self.text = text
        if self.shrink_to_fit:
            text_size = globals.text_manager.get_size(text, self.scale).to_float() / self.parent.absolute.size
            margin = Point(text_size.y * 0.06, text_size.y * 0.15)
            tr = self.pos + text_size + margin * 2
            # We'd like to store the margin relative to us, rather than our parent
            self.margin = margin / (tr - self.pos)
            self.set_bounds(self.pos, tr)
        self.reallocate_resources()
        self.viewpos = 0
        self.position(self.pos, self.scale, colour)
        # Updating the quads with self.position re-enables them, so if we're disabled: don't draw
        if not self.enabled:
            for q in self.quads:
                q.disable()

    def reallocate_resources(self):
        self.quads = [self.text_manager.letter(char, self.text_type) for char in self.text]

    def disable(self):
        if self.enabled:
            for q in self.quads:
                q.disable()
        super(TextBox, self).disable()

    def enable(self):
        if not self.enabled:
            for q in self.quads:
                q.enable()
        super(TextBox, self).enable()


class FaderTextBox(TextBox):
    """A Textbox that can be smoothly faded to a different size / colour"""

    def __init__(self, *args, **kwargs):
        super(FaderTextBox, self).__init__(*args, **kwargs)
        self.draw_scale = 1

    def __hash__(self):
        return id(self)

    def set_letter_vertices(self, index, bl, tr, textType):
        self.quads[index].set_vertices(
            bl - self.absolute.bottom_left, tr - self.absolute.bottom_left, textType
        )

    def SetFade(self, start_time, end_time, end_size, end_colour):
        self.start_time = start_time
        self.end_time = end_time
        self.duration = end_time - start_time
        self.start_size = 1
        self.end_size = end_size
        self.size_difference = self.end_size - self.start_size
        self.end_colour = end_colour
        self.draw_scale = 1
        # self.bl = (self.absolute.bottom_left - self.absolute.size*1.5).to_int()
        # self.tr = (self.absolute.top_right + self.absolute.size*1.5).to_int()
        self.colour_delay = 0.4
        # print bl,tr
        self.enable()

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            self.root.register_drawable(self)
            self.root.register_updateable(self)
        super(FaderTextBox, self).enable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.root.remove_drawable(self)
        super(FaderTextBox, self).disable()

    def update(self, t):
        # print 'bbb',t,self.start_time,self.end_time
        if t > self.end_time:
            # self.disable()
            return True
        if t < self.start_time:
            return False
        partial = float(t - self.start_time) / self.duration
        partial = partial * partial * (3 - 2 * partial)  # smoothstep
        self.draw_scale = self.start_size + (self.size_difference * partial)
        if partial > self.colour_delay:
            new_colour = self.colour[:3] + (1 - ((partial - self.colour_delay) / (1 - self.colour_delay)),)
            for quad in self.quads:
                quad.set_colour(new_colour)

    def reallocate_resources(self):
        self.quad_buffer = drawing.QuadBuffer(1024)
        self.text_type = drawing.texture.TextTypes.CUSTOM
        self.quads = [self.text_manager.letter(char, self.text_type, self.quad_buffer) for char in self.text]

    def draw(self):
        drawing.reset_state()
        drawing.scale(globals.tiles.zoom, globals.tiles.zoom, 1)
        drawing.translate(-globals.tiles.viewpos.get().x, -globals.tiles.viewpos.get().y, 0)
        drawing.translate(self.absolute.bottom_left.x, self.absolute.bottom_left.y, 0)
        drawing.scale(self.draw_scale * globals.tiles.zoom, self.draw_scale * globals.tiles.zoom, 1)
        drawing.draw_all(self.quad_buffer, globals.text_manager.atlas.texture)


class ScrollTextBox(TextBox):
    """A TextBox that can be scrolled to see text that doesn't fit in the box"""

    def __init__(self, *args, **kwargs):
        super(ScrollTextBox, self).__init__(*args, **kwargs)
        self.dragging = None
        self.enable()

    def position(self, pos, scale, colour=None):
        super(ScrollTextBox, self).position(pos, scale, colour, ignore_height=True)

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            self.root.register_drawable(self)
        super(ScrollTextBox, self).enable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.root.remove_drawable(self)
        super(ScrollTextBox, self).disable()

    def depress(self, pos):
        self.dragging = self.viewpos + self.get_relative(pos).y
        return self

    def reallocate_resources(self):
        self.quad_buffer = drawing.QuadBuffer(1024)
        self.text_type = drawing.texture.TextTypes.CUSTOM
        self.quads = [self.text_manager.letter(char, self.text_type, self.quad_buffer) for char in self.text]

    def draw(self):
        pass
        # glPushAttrib(GL_VIEWPORT_BIT)
        # glMatrixMode(GL_PROJECTION)
        # drawing.reset_state()
        # bl = self.absolute.bottom_left.to_int()
        # tr = self.absolute.top_right.to_int()
        # glOrtho(bl.x, tr.x, bl.y, tr.y,-10000,10000)
        # glMatrixMode(GL_MODELVIEW)
        # glViewport(bl.x, bl.y, tr.x-bl.x, tr.y-bl.y)

        # drawing.translate(0,-self.viewpos*self.absolute.size.y,0)
        # glVertexPointerf(self.quad_buffer.vertex_data)
        # glTexCoordPointerf(self.quad_buffer.tc_data)
        # glColorPointer(4,GL_FLOAT,0,self.quad_buffer.colour_data)
        # glDrawElements(GL_QUADS,self.quad_buffer.current_size,GL_UNSIGNED_INT,self.quad_buffer.indices)

        # glMatrixMode(GL_PROJECTION)
        # drawing.reset_state()
        # glOrtho(0, globals.screen.x, 0, globals.screen.y,-10000,10000)
        # glMatrixMode(GL_MODELVIEW)
        # glPopAttrib()

    def undepress(self, pos):
        self.dragging = None

    def scroll(self, amount):
        self.viewpos = self.valid_viewpos(self.viewpos - float(amount) / 30)

    def valid_viewpos(self, viewpos):
        low_thresh = 0.05
        high_thresh = 1.05
        if viewpos < self.lowest_y - low_thresh:
            viewpos = self.lowest_y - low_thresh
        if viewpos > low_thresh:
            viewpos = low_thresh
        return viewpos

    def mouse_motion(self, pos, rel, handled):
        if globals.ui_state.debug_mode:
            return super(ScrollTextBox, self).mouse_motion(pos, rel, handled)
        pos = self.get_relative(pos)
        low_thresh = 0.05
        high_thresh = 1.05
        if self.dragging is not None:
            # print pos,'vp:',self.viewpos,(self.dragging - pos).y
            self.viewpos = self.valid_viewpos(self.dragging - pos.y)

            self.dragging = self.viewpos + pos.y
            if self.dragging > high_thresh:
                self.dragging = high_thresh
            if self.dragging < low_thresh:
                self.dragging = low_thresh
            # print 'stb vp:',self.viewpos
            # self.update_position()


class TextBoxButton(TextBox):
    def __init__(self, parent, text, pos, tr=None, size=0.5, callback=None, line_width=2, colour=None):
        self.callback = callback
        self.line_width = line_width
        self.hovered = False
        self.selected = False
        self.depressed = False
        self.enabled = False
        self.colour = colour
        self.border_margin = Point(5, 5)
        super(TextBoxButton, self).__init__(parent, pos, tr, text, size, colour=colour)
        self.border.disable()
        self.registered = False
        self.enable()

    def position(self, pos, scale, colour=None):
        super(TextBoxButton, self).position(pos, scale, colour)
        self.set_vertices()

    def update_position(self):
        super(TextBoxButton, self).update_position()
        self.set_vertices()

    def set_vertices(self):
        self.border.set_colour(drawing.constants.colours.red)
        self.border.set_vertices(
            self.absolute.bottom_left - self.border_margin, self.absolute.top_right + self.border_margin
        )
        if not self.enabled:
            self.border.disable()

    def set_pos(self, pos):
        # FIXME: This is shit. I can't be removing and adding every frame
        reregister = self.enabled
        if reregister:
            self.root.remove_ui_element(self)
        super(TextBoxButton, self).set_pos(pos)
        self.set_vertices()
        if reregister:
            self.root.register_ui_element(self)

    def reallocate_resources(self):
        super(TextBoxButton, self).reallocate_resources()
        self.border = drawing.QuadBorder(globals.ui_buffer, line_width=self.line_width)

    def delete(self):
        super(TextBoxButton, self).delete()
        self.border.delete()
        self.disable()

    def hover(self):
        self.hovered = True
        self.border.enable()

    def end_hover(self):
        self.hovered = False
        if not self.hovered and not self.selected:
            self.border.disable()

    def select(self):
        self.selected = True
        self.border.set_colour(drawing.constants.colours.blue)
        if self.enabled:
            self.border.enable()

    def unselect(self):
        self.selected = False
        self.border.set_colour(drawing.constants.colours.red)
        if not self.enabled or (not self.hovered and not self.selected):
            self.border.disable()

    def depress(self, pos):
        if globals.ui_state.debug_mode:
            return super(TextBoxButton, self).depress(pos)
        else:
            self.depressed = True
            self.border.set_colour(drawing.constants.colours.yellow)
            return None

    def undepress(self, pos):
        if globals.ui_state.debug_mode:
            return super(TextBoxButton, self).undepress()
        else:
            self.depressed = False
            self.border.set_colour(drawing.constants.colours.red)

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            if self.hovered:
                self.hover()
            elif self.selected:
                self.select()
            elif self.depressed:
                self.Depressed()
        super(TextBoxButton, self).enable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            self.border.disable()
        super(TextBoxButton, self).disable()

    def on_click(self, pos, button):
        if globals.ui_state.debug_mode:
            return
        if self.callback is not None and button == 1:
            self.callback(pos)


class Slider(UIElement):
    def __init__(self, parent, bl, tr, points, callback):
        super(Slider, self).__init__(parent, bl, tr)
        self.points = sorted(points, key=lambda x: x[0])
        self.callback = callback
        self.lines = []
        self.uilevel = drawing.constants.DrawLevels.ui + 1
        self.enabled = False
        self.clickable_area = UIElement(self, Point(0.05, 0), Point(0.95, 1))
        line = drawing.Quad(globals.ui_buffer)
        line_bl = self.clickable_area.absolute.bottom_left + self.clickable_area.absolute.size * Point(0, 0.3)
        line_tr = line_bl + self.clickable_area.absolute.size * Point(1, 0) + Point(0, 2)
        line.set_vertices(line_bl, line_tr, self.uilevel)
        line.disable()

        low = self.points[0][0]
        high = self.points[-1][0]
        self.offsets = [
            float(value - low) / (high - low) if low != high else 0 for value, index in self.points
        ]
        self.lines.append(line)
        self.index = 0
        self.pointer_quad = drawing.Quad(globals.ui_buffer)
        self.pointer_colour = (1, 0, 0, 1)
        self.lines.append(self.pointer_quad)
        self.pointer_ui = UIElement(self.clickable_area, Point(0, 0), Point(0, 0))
        self.set_pointer()
        self.pointer_quad.disable()
        self.dragging = False
        # now do the blips
        for offset in self.offsets:
            line = drawing.Quad(globals.ui_buffer)
            line_bl = (
                self.clickable_area.absolute.bottom_left
                + Point(offset, 0.3) * self.clickable_area.absolute.size
            )
            line_tr = line_bl + self.clickable_area.absolute.size * Point(0, 0.2) + Point(2, 0)
            line.set_vertices(line_bl, line_tr, self.uilevel)
            line.disable()
            self.lines.append(line)

    def set_pointer(self):
        offset = self.offsets[self.index]

        pointer_bl = Point(offset, 0.3) - (Point(2, 10) / self.clickable_area.absolute.size)
        pointer_tr = pointer_bl + (Point(7, 14) / self.clickable_area.absolute.size)
        self.pointer_ui.set_bounds(pointer_bl, pointer_tr)
        self.pointer_quad.set_vertices(
            self.pointer_ui.absolute.bottom_left, self.pointer_ui.absolute.top_right, self.uilevel + 0.1
        )
        self.pointer_quad.set_colour(self.pointer_colour)

    def enable(self):
        if not self.enabled:
            self.root.register_ui_element(self)
            for line in self.lines:
                line.enable()
        super(Slider, self).enable()

    def disable(self):
        if self.enabled:
            self.root.remove_ui_element(self)
            for line in self.lines:
                line.disable()
        super(Slider, self).disable()

    def depress(self, pos):
        # if pos in self.pointer_ui:
        self.dragging = True
        self.mouse_motion(pos, Point(0, 0), False)
        #    return self
        # else:
        #    return None

    def mouse_motion(self, pos, rel, handled):
        if not self.dragging:
            return  # we don't care
        outer_relative_pos = self.get_relative(pos)
        if outer_relative_pos.x < 0:
            outer_relative_pos.x = 0
        if outer_relative_pos.x > 1:
            outer_relative_pos = 1
        relative_pos = self.get_absolute(outer_relative_pos)
        relative_pos = self.clickable_area.get_relative(relative_pos)
        pointer_bl = Point(relative_pos.x, 0.3) - (Point(2, 10) / self.clickable_area.absolute.size)
        pointer_tr = pointer_bl + (Point(7, 14) / self.clickable_area.absolute.size)
        # This is a bit of a hack to avoid having to do a calculation
        temp_ui = UIElement(self.clickable_area, pointer_bl, pointer_tr)
        self.pointer_quad.set_vertices(
            temp_ui.absolute.bottom_left, temp_ui.absolute.top_right, self.uilevel + 0.1
        )
        self.clickable_area.remove_child(temp_ui)
        # If there are any eligible choices between the currently selected choice and the mouse cursor, choose
        # the one closest to the cursor
        # Where is the mouse?
        i = bisect.bisect_right(self.offsets, relative_pos.x)
        if i == len(self.offsets):
            # It's off the right, so choose the last option
            chosen = i - 1
        elif i == 0:
            # It's off the left, so choose the first
            chosen = 0
        else:
            # It's between 2 options, so choose whichevers closest
            if abs(relative_pos.x - self.offsets[i - 1]) < abs(relative_pos.x - self.offsets[i]):
                chosen = i - 1
            else:
                chosen = i

        if chosen != self.index:
            self.index = chosen
            # self.set_pointer()
            self.callback(self.index)

    def undepress(self, pos):
        self.dragging = False
        self.set_pointer()

    def on_click(self, pos, button):
        # For now try just changing which is selected
        return
        if pos in self.pointer_ui or self.dragging:
            # It's a click on the pointer, which we ignore
            return
        # If it's a click to the right or left of the pointer, adjust accordingly
        if pos.x > self.pointer_ui.absolute.top_right.x:
            self.index = (self.index + 1) % len(self.points)
        elif pos.x < self.pointer_ui.absolute.bottom_left.x:
            self.index = (self.index + len(self.points) - 1) % len(self.points)
        else:
            return
        self.set_pointer()
        self.callback(self.index)


class SmoothSlider(Slider):
    def mouse_motion(self, pos, rel, handled):
        if not self.dragging:
            return  # we don't care
        outer_relative_pos = self.get_relative(pos)
        if outer_relative_pos.x < 0:
            outer_relative_pos.x = 0
        if outer_relative_pos.x > 1:
            outer_relative_pos = 1
        relative_pos = self.get_absolute(outer_relative_pos)
        relative_pos = self.clickable_area.get_relative(relative_pos)
        if relative_pos.x > 1:
            relative_pos.x = 1
        if relative_pos.x < 0:
            relative_pos.x = 0
        self.set_value(relative_pos.x)
        self.callback(self.index)

    def set_value(self, value):
        pointer_bl = Point(value, 0.3) - (Point(2, 10) / self.clickable_area.absolute.size)
        pointer_tr = pointer_bl + (Point(7, 14) / self.clickable_area.absolute.size)
        # This is a bit of a hack to avoid having to do a calculation
        temp_ui = UIElement(self.clickable_area, pointer_bl, pointer_tr)
        self.pointer_quad.set_vertices(
            temp_ui.absolute.bottom_left, temp_ui.absolute.top_right, self.uilevel + 0.1
        )
        self.clickable_area.remove_child(temp_ui)
        # If there are any eligible choices between the currently selected choice and the mouse cursor, choose
        # the one closest to the cursor
        # Where is the mouse?
        self.index = value

    def set_pointer(self):
        offset = self.index

        pointer_bl = Point(offset, 0.3) - (Point(2, 10) / self.clickable_area.absolute.size)
        pointer_tr = pointer_bl + (Point(7, 14) / self.clickable_area.absolute.size)
        self.pointer_ui.set_bounds(pointer_bl, pointer_tr)
        self.pointer_quad.set_vertices(
            self.pointer_ui.absolute.bottom_left, self.pointer_ui.absolute.top_right, self.uilevel + 0.1
        )
        self.pointer_quad.set_colour(self.pointer_colour)


class ListBox(UIElement):
    def __init__(self, parent, bl, tr, text_size, items):
        super(ListBox, self).__init__(parent, bl, tr)
        self.text_size = text_size
        self.update_items(items)

    def update_items(self, items):
        # This is a massive hack, using hardcoded values, and generally being shit. I'm bored of UI things now
        enabled = self.enabled
        self.delete()
        if enabled:
            self.enable()
        self.children = []
        self.items = items
        height = 0.8
        maxx = 0

        for name, value in self.items:
            t = TextBox(parent=self, bl=Point(0.05, height), tr=None, text=name, scale=self.text_size)
            height -= t.size.y
            if t.top_right.x > maxx:
                maxx = t.top_right.x
            if not self.enabled:
                t.disable()

        last_height = height = 0.8
        for i, (name, value) in enumerate(self.items):
            if i == len(self.items) - 1:
                bl = Point(maxx + 0.02, 0)
                tr = Point(1, last_height)
            else:
                bl = Point(maxx + 0.05, height)
                tr = None
            t = TextBox(parent=self, bl=bl, tr=tr, text="%s" % value, scale=self.text_size)
            if not self.enabled:
                t.disable()
            last_height = height
            height -= t.size.y


class TabPage(UIElement):
    """A UIElement that is suitable for using as the target for a Tabbed environment. Instantiating this class
    with a Tabbed environment as the parent automatically adds it as a tab

    """

    def __init__(self, parent, bl, tr, name):
        self.name = name
        super(TabPage, self).__init__(parent, bl, tr)


class TabbedArea(UIElement):
    """Represents the drawable area in a Tabbed environment. It's necessary to allow TabPages to specify their
    coordinates from (0,0) to (1,1) and still only take up the part of the TabbedEnvironment reserved for
    TabPages. It doesn't do much, just pass things up to its parent TabbedEnvironment
    """

    def add_child(self, element):
        super(TabbedArea, self).add_child(element)
        if isinstance(element, TabPage):
            self.parent.add_tab_page(element)


class TabbedEnvironment(UIElement):
    """An element that has a number of sub-element tabs. To make a tab you just create a TabPage that has
    tab_area as its parent
    """

    def __init__(self, parent, bl, tr):
        super(TabbedEnvironment, self).__init__(parent, bl, tr)
        self.tab_area = TabbedArea(self, Point(0, 0), Point(1, 0.9))
        self.buttons = []
        self.pages = []
        self.current_page = None

    def add_tab_page(self, page):
        # print 'Adding page',page.name,len(self.buttons)
        if len(self.buttons) == 0:
            xpos = 0
        else:
            xpos = self.buttons[-1].top_right.x
        new_button = TextBoxButton(
            parent=self,
            text=page.name,
            pos=Point(xpos, 0.9),
            tr=None,
            size=0.2,
            callback=utils.extra_args(self.on_click, len(self.buttons)),
        )

        self.buttons.append(new_button)
        self.pages.append(page)
        if len(self.pages) == 1:
            page.enable()
            self.current_page = page
        else:
            page.disable()

    def on_click(self, pos, button):
        if self.pages[button] is not self.current_page:
            self.current_page.disable()
            self.current_page = self.pages[button]
            self.current_page.enable()

    def enable(self):
        # Fixme, don't waste time by enabling then disabling the other pages, do some optimisation st
        # they're not enabled at all
        enabled = self.enabled
        super(TabbedEnvironment, self).enable()
        for page in self.pages:
            if page is not self.current_page:
                page.disable()


# This file is getting a bit silly; it really needs splitting up


class ClickInfo(object):
    def __init__(self, pos, t):
        self.pos = pos
        self.time = t


# The idea for this is to have 2 images, one shown normally and one when pressed
class ImageButtonBase(HoverableBox):
    def __init__(self, parent, pos, tr, normal_tc, pressed_tc, callback, level=None):
        super(Box, self).__init__(parent, pos, tr)

        self.quad = drawing.Quad(parent.backdrop_buffer)
        self.callback = callback
        self.normal_tc = normal_tc
        self.pressed_tc = pressed_tc
        self.quad.set_vertices(self.absolute.bottom_left, self.absolute.top_right, self.level)
        self.reset()
        self.enable()
        self.pressable = True

    def prevent_press(self):
        self.pressable = False

    def allow_press(self):
        self.pressable = True

    def reset(self):
        self.down = False
        self.keep_down = False
        self.layout()

    def depress(self, pos):
        if not self.down and self.pressable:
            self.down = True
            self.start_press = ClickInfo(pos, globals.t)
            self.layout()

    def undepress(self, pos):
        if not self.keep_down and self.pressable:
            self.down = False
        self.layout()

    def layout(self):
        if self.down:
            tc = self.pressed_tc
        else:
            tc = self.normal_tc
        self.quad.set_texture_coordinates(tc)


class ImageButton(ImageButtonBase):
    def on_click(self, pos, button):
        super(ImageButton, self).on_click(pos, button)
        if self.pressable:
            self.callback()


class ToggleButton(ImageButtonBase):
    def depress(self, pos):
        pass

    def undepress(self, pos):
        pass

    def on_click(self, pos, button):
        self.down = not self.down
        self.layout()
        self.callback(self.down)

    def set(self, value):
        self.down = value
        self.layout()


class DraggableItem(ImageButton):
    margin_above = 5
    margin_below = 25
    margin_total = margin_above + margin_below

    def __init__(self, parent, pos, image_size, normal_tc, pressed_tc, callback, text, scale, level=None):
        # We work out our full size based on the image size + some size for text
        self.rel_margin_above = self.margin_above / parent.absolute.size.y
        self.rel_margin_below = self.margin_below / parent.absolute.size.y
        self.start_press = None
        text_size = globals.text_manager.get_size(text, scale)
        text_size /= parent.absolute.size
        image_pos = pos + Point(0, text_size.y + self.rel_margin_below + self.rel_margin_above)

        super(DraggableItem, self).__init__(
            parent, image_pos, image_pos + image_size, normal_tc, pressed_tc, callback
        )

        self.text = TextBox(parent, pos + Point(0, self.rel_margin_below), None, text, scale)
        self.root.register_updateable(self)

    def depress(self, pos):
        self.start_press = ClickInfo(pos, globals.t)
        super(DraggableItem, self).depress(pos)

    def mouse_motion(self, pos, rel, handled):
        # Another way to grab the item in addition to a long press is to drag it any significant distance
        if self.start_press and (pos - self.start_press.pos).diaglength() > 10:
            self.callback()
            self.start_press = None

    def update(self, t):
        # If they've held a long press then we can grab it
        if self.start_press and (t - self.start_press.time) > globals.times.long_press:
            self.callback()
            self.start_press = None

    def undepress(self, pos):
        self.start_press = None
        super(DraggableItem, self).undepress(pos)
        # quick hack
        if self.root.hovered and self.root.hovered is not self:
            self.root.hovered.on_click(pos, 1)

    @staticmethod
    def get_size(image_size, text, scale):
        return Point(
            image_size.x,
            image_size.y + globals.text_manager.get_size(text, scale).y + DraggableItem.margin_total,
        )

    def delete(self):
        super(DraggableItem, self).delete()
        self.text.delete()


class DepressButton(ImageButtonBase):
    """An image button whose callback is called when its depressed rather than released like most buttons"""

    def depress(self, pos):
        if not self.down:
            self.callback()
        super(DepressButton, self).depress(pos)
