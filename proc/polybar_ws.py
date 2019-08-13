#!/usr/bin/pypy3 -u

""" Current workspace printing daemon.

This daemon prints current i3 workspace. You need this because of bugs inside
of polybar's i3 current workspace implementation: you will get race condition
leading to i3 wm dead-lock.

Also it print current keybinding mode.

Usage:
    ./polybar_ws.py

Suppoused to be used inside polybar.

Config example:

[module/ws]
type = custom/script
exec = ~/.config/i3/proc/polybar_ws.py
exec-if = sleep 1
format = <label>
tail = true

Also you need to use unbuffered output for polybar, otherwise you will see no
output at all. I've considered that pypy3 is better choise here, because of
this application run pretty long time to get advantages of JIT compilation.

Created by :: Neg
email :: <serg.zorg@gmail.com>
github :: https://github.com/neg-serg?tab=repositories
year :: 2019

"""

import sys
import asyncio
from threading import Thread, Event
import re
import i3ipc

from lib.standalone_cfg import modconfig
from lib.misc import Misc


class polybar_ws(modconfig):
    def __init__(self):
        # initialize asyncio loop
        self.loop = asyncio.get_event_loop()

        # Initialize modcfg.
        modconfig.__init__(self, self.loop)

        self.event = Event()
        self.event.set()

        self.i3 = i3ipc.Connection()
        self.i3.on('workspace::focus', self.on_ws_focus)
        self.i3.on('binding', self.on_event)

        self.ws_name = ""
        self.binding_mode = ""

        # regexes used to extract current binding mode.
        self.mode_regex = re.compile('.*mode ')
        self.split_by = re.compile('[;,]')

        self.ws_color_field = self.conf("ws_color_field")
        self.binding_color_field = self.conf("binding_color_field")
        self.ws_color = Misc.extract_xrdb_value(self.ws_color_field)
        self.binding_color = Misc.extract_xrdb_value(self.binding_color_field)
        self.ws_name = ""

        for ws in self.i3.get_workspaces():
            if ws.focused:
                ws_name = ws.name
                self.ws_name = ws_name.split(' :: ')[1:][0]
                break

    def on_ws_focus(self, i3, event):
        """ Get workspace name and throw event.
        """
        ws_name = event.current.name
        self.ws_name = ws_name.split(' :: ')[1:][0]
        self.event.set()

    @staticmethod
    def colorize(s, color):
        return f"%{{T4}}%{{F{color}}}{s}%{{F-}}%{{T-}}"

    def on_event(self, i3, event):
        bind_cmd = event.binding.command
        for t in re.split(self.split_by, bind_cmd):
            if 'mode' in t:
                ret = re.sub(self.mode_regex, '', t)
                if ret[0] == ret[-1] and ret[0] in {'"', "'"}:
                    ret = ret[1:-1]
                    if ret == "default":
                        self.binding_mode = ''
                    else:
                        self.binding_mode = \
                            polybar_ws.colorize(
                                ret, color=self.binding_color
                            ) + ' '
                    self.event.set()

    def special_reload(self):
        """ Reload mainloop here.
        """
        asyncio.get_event_loop().close()
        self.loop = asyncio.get_event_loop()
        self.main()

    def main(self):
        """ Mainloop starting here.
        """
        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(
            self.update_status(),
        )

    async def update_status(self):
        """ Print workspace information here. Event-based.
        """
        while True:
            if self.event.wait():
                workspace = self.ws_name
                if not workspace[0].isalpha():
                    workspace = polybar_ws.colorize(
                        workspace[0], color=self.ws_color
                    ) + workspace[1:]
                sys.stdout.write(f"{self.binding_mode + workspace}\n")
                self.event.clear()
                await asyncio.sleep(0)


def main():
    """ Start polybar_ws from here """
    loop = polybar_ws()
    Thread(target=loop.main, daemon=False).start()
    loop.i3.main()


if __name__ == '__main__':
    main()

