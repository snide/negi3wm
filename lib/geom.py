""" Module to convert from 16:10 1080p geometry to target screen geometry.

    This module contains geometry converter and also i3-rules generator. Also
    in this module geometry is parsed from config X11 internal format to the i3
    commands.
"""

import re
from typing import List
from display import Display
from misc import Misc


class geom():
    def __init__(self, cfg: dict) -> None:
        """ Init function

        Args:
            cfg: config bypassed from target module, nsd for example.
        """
        # generated command list for i3 config
        self.cmd_list = []

        # geometry in the i3-commands format.
        self.parsed_geom = {}

        # set current screen resolution
        self.current_resolution = Display.get_screen_resolution()

        # external config
        self.cfg = cfg

        # fill self.parsed_geom with self.parse_geom function.
        for tag in self.cfg:
            self.parsed_geom[tag] = self.parse_geom(tag)

    # nsd need this function
    def get_geom(self, tag: str) -> str:
        """ External function used by nsd """
        return self.parsed_geom[tag]

    def parse_geom(self, tag: str) -> str:
        """ Convert geometry from self.cfg format to i3 commands.
            Args:
                tag (str): target self.cfg tag
        """
        rd = {'width': 1920, 'height': 1200}  # resolution_default
        cr = self.current_resolution          # current resolution

        g = re.split(r'[x+]', self.cfg[tag]["geom"])
        cg = []  # converted_geom

        cg.append(int(int(g[0])*cr['width'] / rd['width']))
        cg.append(int(int(g[1])*cr['height'] / rd['height']))
        cg.append(int(int(g[2])*cr['width'] / rd['width']))
        cg.append(int(int(g[3])*cr['height'] / rd['height']))

        return "move absolute position {2} {3}, resize set {0} {1}".format(*cg)
