import subprocess
import collections
from itertools import cycle
import i3ipc
from modlib import find_visible_windows
from singleton import Singleton
from cfg_master import CfgMaster


class wm3(Singleton, CfgMaster):
    def __init__(self):
        super().__init__()
        self.initialize()

    def initialize(self):
        self.i3 = i3ipc.Connection()
        maxlength = self.cfg["cache_list_size"]
        self.geom_list = collections.deque(
            [None] * maxlength,
            maxlen=maxlength
        )
        self.current_resolution = self.get_screen_resolution()
        self.useless_gaps = self.cfg["useless_gaps"]
        self.quad_use_gaps = self.cfg["quad_use_gaps"]
        self.x2_use_gaps = self.cfg["x2_use_gaps"]

    def switch(self, args):
        {
            "reload": self.reload_config,
            "focus_next_visible": self.focus_next_visible,
            "focus_prev_visible": self.focus_prev_visible,
            "maximize": self.maximize,
            "maxhor": lambda: self.maximize(by='X'),
            "maxvert": lambda: self.maximize(by='Y'),
            "x2": self.x2,
            "x4": self.quad,
            "quad": self.quad,
            "revert_maximize": self.revert_maximize,
        }[args[0]](*args[1:])

    def reload_config(self):
        self.__init__()

    def get_prev_geom(self):
        self.geom_list.append(
            {
                "id": self.current_win.id,
                "geom": self.save_geom()
            }
        )
        return self.geom_list[-1]["geom"]

    def x2(self, mode):
        curr_scr = self.current_resolution
        self.current_win = self.i3.get_tree().find_focused()

        if self.x2_use_gaps:
            gaps = self.useless_gaps
        else:
            gaps = {"w": 0, "a": 0, "s": 0, "d": 0}

        half_width = int(curr_scr['width'] / 2)
        half_height = int(curr_scr['height'] / 2)
        double_dgaps = int(gaps['d'] * 2)
        double_sgaps = int(gaps['s'] * 2)

        if 'h1' == mode or 'hup' == mode:
            print('h1')
            geom = {
                'x': gaps['a'],
                'y': gaps['w'],
                'width': curr_scr['width'] - double_dgaps,
                'height': half_height - double_sgaps,
            }
        elif 'h2' == mode or 'hdown' == mode:
            print('h2')
            geom = {
                'x': gaps['a'],
                'y': half_height + gaps['w'],
                'width': curr_scr['width'] - double_dgaps,
                'height': half_height - double_sgaps,
            }
        elif 'v1' == mode or 'vleft' == mode:
            print('v1')
            geom = {
                'x': gaps['a'],
                'y': gaps['w'],
                'width': half_width - double_dgaps,
                'height': curr_scr['height'] - double_sgaps,
            }
        elif 'v2' == mode or 'vright' == mode:
            print('v2')
            geom = {
                'x': gaps['a'] + half_width,
                'y': gaps['w'],
                'width': half_width - double_dgaps,
                'height': curr_scr['height'] - double_sgaps,
            }
        else:
            return

        if self.current_win is not None:
            if not self.geom_list[-1]:
                self.get_prev_geom()
            elif self.geom_list[-1]:
                prev = self.geom_list[-1].get('id', {})
                if prev != self.current_win.id:
                    geom = self.get_prev_geom()

            self.set_geom(self.current_win, geom)

    def quad(self, mode):
        try:
            mode = int(mode)
        except TypeError:
            print("cannot convert mode={mode} to int")
            return

        curr_scr = self.current_resolution
        self.current_win = self.i3.get_tree().find_focused()

        if self.quad_use_gaps:
            gaps = self.useless_gaps
        else:
            gaps = {"w": 0, "a": 0, "s": 0, "d": 0}

        half_width = int(curr_scr['width'] / 2)
        half_height = int(curr_scr['height'] / 2)
        double_dgaps = int(gaps['d'] * 2)
        double_sgaps = int(gaps['s'] * 2)

        if 1 == mode:
            geom = {
                'x': gaps['a'],
                'y': gaps['w'],
                'width': half_width - double_dgaps,
                'height': half_height - double_sgaps,
            }
        elif 2 == mode:
            geom = {
                'x': half_width + gaps['a'],
                'y': gaps['w'],
                'width': half_width - double_dgaps,
                'height': half_height - double_sgaps,
            }
        elif 3 == mode:
            geom = {
                'x': gaps['a'],
                'y': gaps['w'] + half_height,
                'width': half_width - double_dgaps,
                'height': half_height - double_sgaps,
            }
        elif 4 == mode:
            geom = {
                'x': gaps['a'] + half_width,
                'y': gaps['w'] + half_height,
                'width': half_width - double_dgaps,
                'height': half_height - double_sgaps,
            }
        else:
            return

        if self.current_win is not None:
            if not self.geom_list[-1]:
                self.get_prev_geom()
            elif self.geom_list[-1]:
                prev = self.geom_list[-1].get('id', {})
                if prev != self.current_win.id:
                    geom = self.get_prev_geom()

            self.set_geom(self.current_win, geom)

    def maximize(self, by='XY'):
        geom = {}

        self.current_win = self.i3.get_tree().find_focused()
        if self.current_win is not None:
            if not self.geom_list[-1]:
                geom = self.get_prev_geom()
            elif self.geom_list[-1]:
                prev = self.geom_list[-1].get('id', {})
                if prev != self.current_win.id:
                    geom = self.get_prev_geom()
                else:
                    # do nothing
                    return
            if 'XY' == by or 'YX' == by:
                max_geom = self.maximized_geom(
                    geom.copy(), byX=True, byY=True
                )
            elif 'X' == by:
                max_geom = self.maximized_geom(
                    geom.copy(), byX=True, byY=False
                )
            elif 'Y' == by:
                max_geom = self.maximized_geom(
                    geom.copy(), byX=False, byY=True
                )
            self.set_geom(self.current_win, max_geom)

    def revert_maximize(self):
        try:
            focused = self.i3.get_tree().find_focused()
            if self.geom_list[-1].get("geom", {}):
                self.set_geom(focused, self.geom_list[-1]["geom"])
            del self.geom_list[-1]
        except (KeyError, TypeError, AttributeError):
            pass

    def maximized_geom(self, geom, gaps={}, byX=False, byY=False):
        if gaps == {}:
            gaps = self.useless_gaps
        if byX:
            geom['x'] = 0 + gaps['a']
            geom['width'] = self.current_resolution['width'] - gaps['d'] * 2
        if byY:
            geom['y'] = 0 + gaps['w']
            geom['height'] = self.current_resolution['height'] - gaps['s'] * 2
        return geom

    def set_geom(self, win, geom):
        win.command(f"move absolute position {geom['x']} {geom['y']}")
        win.command(f"resize set {geom['width']} {geom['height']} px")

    def create_geom_from_rect(self, rect):
        geom = {}
        geom['x'] = rect.x
        geom['y'] = rect.y
        geom['height'] = rect.height
        geom['width'] = rect.width

        return geom

    def save_geom(self, target_win=None):
        if target_win is None:
            target_win = self.current_win
        return self.create_geom_from_rect(target_win.rect)

    def get_windows_on_ws(self):
        return filter(
            lambda x: x.window,
            self.i3.get_tree().find_focused().workspace().descendents()
        )

    def focus_next(self, reversed_order=False):
        visible_windows = find_visible_windows(self.get_windows_on_ws())
        if reversed_order:
            cycle_windows = cycle(reversed(visible_windows))
        else:
            cycle_windows = cycle(visible_windows)
        for window in cycle_windows:
            if window.focused:
                focus_to = next(cycle_windows)
                self.i3.command('[id="%d"] focus' % focus_to.window)
                break

    def focus_prev_visible(self):
        self.focus_next(reversed_order=True)

    def focus_next_visible(self):
        self.focus_next()

    def get_screen_resolution(self):
        output = subprocess.Popen(
            'xrandr | awk \'/*/{print $1}\'',
            shell=True,
            stdout=subprocess.PIPE
        ).communicate()[0]
        resolution = output.split()[0].split(b'x')
        return {'width': int(resolution[0]), 'height': int(resolution[1])}
