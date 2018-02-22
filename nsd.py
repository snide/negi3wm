import i3ipc
import uuid
import re
import os
import shlex
import toml
import subprocess
import geom
from i3gen import *
from typing import Callable, List

from singleton import *
from cfg_master import *

class ns(CfgMaster):
    __metaclass__ = Singleton
    def __init__(self) -> None:
        self.winlist=None
        self.fullscreen_list=[]
        self.factors=["class", "instance", "class_r", "instance_r", "name_r", "role_r"]
        self.cfg={}
        self.load_config("ns")
        self.nsgeom=geom.geom(self.cfg)
        self.marked={l:[] for l in self.cfg}
        self.i3 = i3ipc.Connection()
        self.transients=[]
        self.mark_all_tags(hide=True)

        self.i3.on('window::new', self.mark_tag)
        self.i3.on('window::close', self.unmark_tag)

    def make_mark_str(self, tag: str) -> str:
        uuid_str = str(str(uuid.uuid4().fields[-1]))
        return 'mark {}'.format("%(tag)s-%(uuid_str)s" % {"tag":tag, "uuid_str":uuid_str})

    def focus(self, tag: str, hide=True) -> None:
        if not len(self.transients):
            [
                win.command('move container to workspace current')
                for win in self.marked[tag]
            ]
            if hide:
                self.unfocus_all_but_current(tag)
        else:
            try:
                self.transients[0].command('focus')
                del self.transients[0]
            except:
                self.mark_all_tags(hide=False)

    def unfocus(self, tag: str) -> None:
        [
            win.command('move scratchpad')
            for win in self.marked[tag]
        ]
        self.restore_fullscreens()

    def unfocus_all_but_current(self, tag: str) -> None:
        focused = self.i3.get_tree().find_focused()
        for win in self.marked[tag]:
            if win.id != focused.id:
                win.command('move scratchpad')
            else:
                win.command('move container to workspace current')

    def find_visible_windows(self):
        visible_windows = []
        wswins=filter(
            lambda win: win.window,
            self.i3.get_tree().find_focused().workspace().descendents()
        )
        for w in wswins:
            xprop = subprocess.check_output(['xprop', '-id', str(w.window)]).decode()
            if '_NET_WM_STATE_HIDDEN' not in xprop:
                visible_windows.append(w)
        return visible_windows

    def check_dialog_win(self, w):
        if w.window_instance == "Places" or w.window_role == "GtkFileChooserDialog":
            return False
        xprop = subprocess.check_output(['xprop', '-id', str(w.window)]).decode()
        return not (
            '_NET_WM_WINDOW_TYPE_DIALOG' in xprop
            or
            '_NET_WM_STATE_MODAL' in xprop
        )

    def dialog_toggle(self):
        wlist = self.i3.get_tree().leaves()
        for win in wlist:
            if not self.check_dialog_win(win):
                win.command('move container to workspace current, show scratchpad')

    def toggle(self, tag : str) -> None:
        if not len(self.marked[tag]) and "prog" in self.cfg[tag]:
            try:
                prog_str=re.sub("~", os.path.realpath(os.path.expandvars("$HOME")), self.cfg[tag]["prog"])
                self.i3.command('exec {}'.format(prog_str))
            except:
                pass

        if self.visible_count(tag) > 0:
            self.unfocus(tag)
            return

        # We need to hide scratchpad it is visible, regardless it focused or not
        focused = self.i3.get_tree().find_focused()

        for w in self.marked[tag]:
            if focused.id == w.id:
                self.unfocus(tag)
                return

        if focused.fullscreen_mode:
            focused.command('fullscreen toggle')
            self.fullscreen_list.append(focused)

        self.focus(tag)

    def focus_sub_tag(self, tag: str, subtag_classes_set):
        focused=self.i3.get_tree().find_focused()

        if focused.fullscreen_mode:
            focused.command('fullscreen toggle')
            self.fullscreen_list.append(focused)

        if focused.window_class in subtag_classes_set:
            return

        self.focus(tag, hide=True)

        visible_windows = self.find_visible_windows()
        for w in visible_windows:
            for i in self.marked[tag]:
                if w.window_class in subtag_classes_set and w.id == i.id:
                    self.i3.command('[con_id=%s] focus' % w.id)

        for _ in self.marked[tag]:
            focused=self.i3.get_tree().find_focused()
            if not focused.window_class in subtag_classes_set:
                self.next_win()

    def run_subtag(self, tag: str, app : str) -> None:
        if app in self.cfg[tag].get("prog_dict",{}):
            class_list=[win.window_class for win in self.marked[tag]]
            subtag_classes_set=set(self.cfg[tag].get("prog_dict",{}).get(app,{}).get("includes",{}))
            subtag_classes_matched=[w for w in class_list if w in subtag_classes_set]
            if not len(subtag_classes_matched):
                try:
                    prog_str=re.sub(
                        "~", os.path.realpath(os.path.expandvars("$HOME")),
                        self.cfg[tag].get("prog_dict",{}).get(app,{}).get("prog",{})
                    )
                    self.i3.command('exec {}'.format(prog_str))
                except:
                    pass
            else:
                self.focus_sub_tag(tag, subtag_classes_set)
        else:
            self.toggle(tag)

    def restore_fullscreens(self) -> None:
        [win.command('fullscreen toggle') for win in self.fullscreen_list]
        self.fullscreen_list=[]

    def visible_count(self, tag: str):
        visible_windows = self.find_visible_windows()
        vmarked = 0
        for w in visible_windows:
            for i in self.marked[tag]:
                vmarked+=(w.id == i.id)
        return vmarked

    def get_current_tag(self, focused) -> str:
        for tag in self.cfg:
            for i in self.marked[tag]:
                if focused.id == i.id:
                    return tag

    def apply_to_current_tag(self, func : Callable) -> bool:
        curr_tag=self.get_current_tag(self.i3.get_tree().find_focused())
        curr_tag_exits=(curr_tag != None)
        if curr_tag_exits:
            func(curr_tag)
        return curr_tag_exits

    def next_win(self, hide=True) -> None:
        def next_win_(tag: str) -> None:
            self.focus(tag, Hide)
            for idx,win in enumerate(self.marked[tag]):
                if focused_win.id != win.id:
                    self.marked[tag][idx].command('move container to workspace current')
                    self.marked[tag].insert(len(self.marked[tag]), self.marked[tag].pop(idx))
                    win.command('move scratchpad')
            self.focus(tag, Hide)
        Hide=hide
        focused_win=self.i3.get_tree().find_focused()
        self.apply_to_current_tag(next_win_)

    def hide_current(self) -> None:
        if not self.apply_to_current_tag(self.unfocus):
            self.i3.command('[con_id=__focused__] scratchpad show')

    def geom_restore(self, tag: str) -> None:
        for idx,win in enumerate(self.marked[tag]):
            # delete previous mark
            del self.marked[tag][idx]

            # then make a new mark and move scratchpad
            win_cmd="%(make_mark)s, move scratchpad, %(get_geom)s" % {
                "make_mark": self.make_mark_str(tag),
                "get_geom": self.nsgeom.get_geom(tag)
            }
            win.command(win_cmd)
            self.marked[tag].append(win)

    def geom_restore_current(self) -> None:
        self.apply_to_current_tag(self.geom_restore)

    def switch(self, args : List) -> None:
        switch_ = {
            "show": self.focus,
            "hide": self.unfocus_all_but_current,
            "next": self.next_win,
            "toggle": self.toggle,
            "hide_current": self.hide_current,
            "geom_restore": self.geom_restore_current,
            "run": self.run_subtag,
            "reload": self.reload_config,
            "dialog": self.dialog_toggle,
        }
        try:
            switch_[args[0]](*args[1:])
        except:
            pass

    def match(self, win, factor, tag):
        if factor == "class":
            return win.window_class in self.cfg.get(tag,{}).get(factor, {})
        elif factor == "instance":
            return win.window_instance in self.cfg.get(tag,{}).get(factor, {})
        elif factor == "class_r":
            regexes=self.cfg.get(tag,{}).get(factor, {})
            for reg in regexes:
                cls_by_regex=self.winlist.find_classed(reg)
                if cls_by_regex:
                    for class_regex in cls_by_regex:
                        if win.window_class == class_regex.window_class:
                            return True
        elif factor == "instance_r":
            regexes=self.cfg.get(tag,{}).get(factor, {})
            for reg in regexes:
                inst_by_regex=self.winlist.find_instanced(reg)
                if inst_by_regex:
                    for inst_regex in inst_by_regex:
                        if win.window_instance == inst_regex.window_instance:
                            return True
        elif factor == "role_r":
            regexes=self.cfg.get(tag,{}).get(factor, {})
            for reg in regexes:
                role_by_regex=self.winlist.find_by_role(reg)
                if role_by_regex:
                    for role_regex in role_by_regex:
                        if win.window_role == role_regex.window_role:
                            return True
        elif factor == "name_r":
            regexes=self.cfg.get(tag,{}).get(factor, {})
            for reg in regexes:
                name_by_regex=self.winlist.find_named(reg)
                if name_by_regex:
                    for name_regex in name_by_regex:
                        if win.name == name_regex.name:
                            return True

    def mark_tag(self, i3, event) -> None:
        win=event.container
        for tag in self.cfg:
            for factor in self.factors:
                if self.match(win, factor, tag):
                    if self.check_dialog_win(win):
                        # scratch_move
                        win_cmd="%(make_mark)s, move scratchpad, %(get_geom)s" % {
                            "make_mark": self.make_mark_str(tag),
                            "get_geom": self.nsgeom.get_geom(tag)
                        }
                        win.command(win_cmd)
                        self.marked[tag].append(win)
                        break
                    else:
                        self.transients.append(win)
        self.dialog_toggle()
        self.winlist=self.i3.get_tree()

    def unmark_tag(self, i3, event) -> None:
        for tag in self.cfg:
            for _,win in enumerate(self.marked[tag]):
                if win.id == event.container.id:
                    del self.marked[tag][_]
                    self.focus(tag)
                    for tr in self.transients:
                        if tr.id == win.id:
                            self.transients.remove(tr)
                    break

    def mark_all_tags(self, hide : bool=True) -> None:
        self.winlist = self.i3.get_tree()
        leaves=self.winlist.leaves()
        for tag in self.cfg:
            for win in leaves:
                for factor in self.factors:
                    if self.match(win, factor, tag):
                        if self.check_dialog_win(win):
                            # scratch move
                            hide_cmd=''
                            if hide:
                                hide_cmd='[con_id=__focused__] scratchpad show'
                            win_cmd="%(make_mark)s, move scratchpad, %(get_geom)s, %(hide_cmd)s" % \
                                {
                                    "make_mark": self.make_mark_str(tag),
                                    "get_geom": self.nsgeom.get_geom(tag),
                                    "hide_cmd": hide_cmd
                                }
                            win.command(win_cmd)
                            self.marked[tag].append(win)
                            break
                        else:
                            self.transients.append(win)
        self.winlist = self.i3.get_tree()
