import configparser
import os
import time


class LGDConf(configparser.ConfigParser):
    def __init__(self, *args, **kwargs):
        self.modified = False
        self.read_only = False
        self.modtime = None
        super().__init__(*args, **kwargs)

    def read(self, filename):
        # if config file exists, save modification time
        if os.path.exists(filename):
            self.modtime = int(os.stat(filename).st_mtime)

        return super().read(filename)

    def write(self, *args, **kwargs):
        self.modified = False
        super().write(*args, **kwargs)
        self.modtime = int(time.time())

    def set(self, *args, **kwargs):
        if self.read_only:
            return

        self.modified = True
        super().set(*args, **kwargs)

    def remove_option(self, section, option):
        if self.read_only:
            return False

        self.modified = True
        return super().remove_option(section, option)

    def __setitem__(self, key, value):
        if self.read_only:
            return

        self.modified = True
        super().__setitem__(key, value)
