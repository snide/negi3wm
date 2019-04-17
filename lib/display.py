from Xlib import display
from Xlib.ext import randr

class Display():
    d = display.Display()
    s = d.screen()
    window = s.root.create_window(0, 0, 1, 1, 1, s.root_depth)
    xrandr_cache = randr.get_screen_info(window)._data
    resolution_list = []

    @classmethod
    def get_screen_resolution(cls) -> dict:
        size_id = cls.xrandr_cache['size_id']
        resolution = cls.xrandr_cache['sizes'][size_id]
        return {
            'width': int(resolution['width_in_pixels']),
            'height': int(resolution['height_in_pixels'])
        }

    @classmethod
    def get_screen_resolution_data(cls) -> dict:
        return cls.xrandr_cache['sizes']

    @classmethod
    def xrandr_resolution_list(cls) -> dict:
        if not cls.resolution_list:
            delimiter = 'x'
            resolution_data = cls.get_screen_resolution_data()
            for size_id, res in enumerate(resolution_data):
                if res is not None and res:
                    cls.resolution_list += [(
                        str(size_id) + ': ' +
                        str(res['width_in_pixels']) +
                        delimiter +
                        str(res['height_in_pixels'])
                    )]

        return cls.resolution_list

    @classmethod
    def set_screen_size(cls, size_id=0) -> None:
        subprocess.run(['xrandr', '-s', str(size_id)])

