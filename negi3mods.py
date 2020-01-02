#!/usr/bin/python3

""" i3 negi3mods daemon script.

This module loads all negi3mods an start it via main's manager
mailoop. Inotify-based watchers for all negi3mods TOML-based configuration
spawned here, to use it just start it from any place without parameters. Also
there is i3 config watcher to convert it from ppi3 format to plain i3
automatically. Moreover it contains pid-lock which prevents running several
times.

Usage:
    ./negi3mods.py [--debug|--tracemalloc|--start]

Options:
    --debug         disables signal handlers for debug.
    --tracemalloc   calculates and shows memory tracing with help of
                    tracemalloc.
    --start         make actions for the start, not reloading

Created by :: Neg
email :: <serg.zorg@gmail.com>
github :: https://github.com/neg-serg?tab=repositories
year :: 2020

"""

import os
import timeit
import atexit
import sys
import subprocess
import signal
import functools
import importlib
import shutil
from threading import Thread

for m in ["inotipy", "i3ipc", "docopt", "pulsectl",
          "toml", "Xlib", "yaml", "yamlloader", "ewmh"]:
    if not importlib.util.find_spec(m):
        print("Cannot import [{m}], please install")

import asyncio
import inotipy

import i3ipc
from docopt import docopt

from lib.locker import get_lock
from lib.msgbroker import MsgBroker
from lib.misc import Misc
from lib.standalone_cfg import modconfig


class negi3mods(modconfig):
    def __init__(self, cmd_args):
        """ Init function

            Using of self.intern for better performance, create i3ipc
            connection, connects to the asyncio eventloop.
        """

        # i3 path used to get i3 config path for "send" binary, _config needed
        # by ppi3 path and another configs.
        self.i3_path = Misc.i3path()
        loop = asyncio.new_event_loop()

        self.tracemalloc_enabled = False

        if cmd_args["--tracemalloc"]:
            self.tracemalloc_enabled = True
            import tracemalloc

        if self.tracemalloc_enabled:
            tracemalloc.start()

        self.first_run = False
        if cmd_args["--start"]:
            self.first_run = True

        if not (cmd_args['--debug'] or self.tracemalloc_enabled):
            def loop_exit(signame):
                print(f"Got signal {signame}: exit")
                loop.stop()
                os._exit(0)

            for signame in {'SIGINT', 'SIGTERM'}:
                loop.add_signal_handler(
                    getattr(signal, signame),
                    functools.partial(loop_exit, signame))
            loop.set_exception_handler(None)

        modconfig.__init__(self, loop)

        self.loop = loop

        self.mods = {}
        for mod in self.conf("module_list"):
            self.mods[sys.intern(mod)] = None

        self.prepare_notification_text()

        # i3 path used to get "send" binary path
        self.i3_cfg_path = self.i3_path + '/cfg/'

        # test config to check ppi3 conversion result
        self.test_cfg_path = os.path.realpath(
            os.path.expandvars('$HOME/tmp/config_test')
        )

        self.port = int(self.conf('port'))

        self.echo = Misc.echo_off
        self.notify = Misc.notify_off

        # main i3ipc connection created here and can be bypassed to the most of
        # modules here.
        self.i3 = i3ipc.Connection()

    def prepare_notification_text(self):
        """ stuff for startup notifications """
        self.notification_text = "Starting negi3mods\n\n"
        notification_color_field = self.conf("notification_color_field")
        notification_color = Misc.extract_xrdb_value(notification_color_field)
        prefix = self.conf("prefix")
        self.msg_prefix = f"<span weight='normal' \
            color='{notification_color}'> {prefix} </span>"

    def load_modules(self):
        """ Load modules.

            This function init MsgBroker, use importlib to load all the
            stuff, then add_ipc and update notification with startup
            benchmarks.
        """
        mod_startup_times = []
        self.echo('Loading modules')
        for mod in self.mods:
            start_time = timeit.default_timer()
            i3mod = importlib.import_module('lib.' + mod)
            self.mods[mod] = getattr(i3mod, mod)(self.i3, loop=self.loop)
            mod_startup_times.append(timeit.default_timer() - start_time)
            time_elapsed = f'{mod_startup_times[-1]:4f}s'
            mod_loaded_info = f'{mod:<10s} ~ {time_elapsed:>10s}'
            self.notification_text += self.msg_prefix + mod_loaded_info + '\n'
            self.echo(mod_loaded_info, flush=True)
        loading_time_msg = f'Loading time = {sum(mod_startup_times):6f}s'
        self.notification_text += loading_time_msg
        self.echo(loading_time_msg)

    def mods_cfg_watcher(self):
        """ cfg watcher to update modules config in realtime.
        """
        watcher = inotipy.Watcher.create()
        watcher.watch(self.i3_cfg_path, inotipy.IN.MODIFY)
        return watcher

    def autostart(self):
        """ Autostart auto negi3mods initialization """
        if self.first_run:
            try:
                subprocess.run(
                    [self.i3_path + 'send', 'circle', 'next', 'term'],
                    check=True
                )
            except subprocess.CalledProcessError as proc_err:
                Misc.print_run_exception_info(proc_err)

    def i3_config_watcher(self):
        """ i3 config watcher to run ppi3 on write.
        """
        watcher = inotipy.Watcher.create()
        watcher.watch(self.i3_path, inotipy.IN.CLOSE_WRITE)
        return watcher

    async def mods_cfg_worker(self, watcher, reload_one=True):
        """ Reloading configs on change. Reload only appropriate config by
            default.

            Args:
                watcher: watcher for cfg.
        """
        while True:
            event = await watcher.get()
            print(event)
            changed_mod = event.pathname[:-4]
            if changed_mod in self.mods:
                if reload_one:
                    try:
                        subprocess.run(
                            [self.i3_path + 'send', changed_mod, 'reload'],
                            check=True
                        )
                        self.notify(f'[Reloaded {changed_mod}]')
                    except subprocess.CalledProcessError as proc_err:
                        Misc.print_run_exception_info(proc_err)
                else:
                    for mod in self.mods:
                        try:
                            subprocess.run(
                                [self.i3_path + 'send', mod, 'reload'],
                                check=True
                            )
                        except subprocess.CalledProcessError as proc_err:
                            Misc.print_run_exception_info(proc_err)
                    self.notify(
                        '[Reloaded {' + ','.join(self.mods.keys()) + '}]'
                    )
        watcher.close()

    async def i3_config_worker(self, watcher):
        """ Run ppi3 when config is changed

            Args:
                watcher: watcher for i3 config.
        """
        while True:
            event = await watcher.get()
            if event.pathname == '_config':
                with open(self.test_cfg_path, "w") as fconf:
                    try:
                        subprocess.run(
                            ['ppi3', self.i3_path + '_config'],
                            stdout=fconf,
                            check=True
                        )
                        config_is_valid = self.validate_i3_config()
                    except subprocess.CalledProcessError as proc_err:
                        Misc.print_run_exception_info(proc_err)
                if config_is_valid:
                    self.echo("i3 config is valid!")
                    shutil.move(self.test_cfg_path, self.i3_path + 'config')

    def validate_i3_config(self):
        """ Checks that i3 config is ok.
        """
        try:
            check_config = subprocess.run(
                ['i3', '-c', self.test_cfg_path, '-C'],
                stdout=subprocess.PIPE,
                check=True
            ).stdout.decode('utf-8')
        except subprocess.CalledProcessError as proc_err:
            Misc.print_run_exception_info(proc_err)
        if check_config:
            error_data = check_config.encode('utf-8')
            self.echo(error_data)
            self.notify(error_data, "Error >")

            # remove invalid config
            os.remove(self.test_cfg_path)

            return False
        return True

    def run_config_watchers(self):
        """ Start all watchers here via ensure_future to run it in background.
        """
        asyncio.ensure_future(self.mods_cfg_worker(self.mods_cfg_watcher()))
        asyncio.ensure_future(self.i3_config_worker(self.i3_config_watcher()))

    def run(self):
        """ Run negi3mods here.
        """
        def start(func, args=None):
            """ Helper for pretty-printing of loading process.

                Args:
                    func (callable): callable routine to run.
                    name: routine name.
                    args: routine args, optional.
            """
            if args is None:
                func()
            elif args is not None:
                func(*args)

        start(self.load_modules)
        start(self.run_config_watchers)

        # Start modules mainloop.
        mainloop = Thread(
            target=MsgBroker.mainloop,
            args=(self.loop, self.mods, self.port,),
            daemon=True
        )
        start((mainloop).start)

        self.echo('... everything loaded ...')
        self.notify(self.notification_text)
        try:
            self.autostart()
            self.i3.main()
        except KeyboardInterrupt:
            self.i3.main_quit()
        self.echo('... exit ...')


def main():
    """ Run negi3mods from here """
    get_lock(os.path.basename(__file__))

    # We need it because of thread_wait on Ctrl-C.
    atexit.register(lambda: os._exit(0))

    cmd_args = docopt(__doc__, version='0.8')

    negi3mods_instance = negi3mods(cmd_args)
    negi3mods_instance.run()

    if negi3mods_instance.tracemalloc_enabled:
        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics('lineno')

        print("[ Top 10 ]")
        for stat in top_stats[:10]:
            print(stat)


if __name__ == '__main__':
    main()
