import os
from os.path import join

CONFIG_NAME = "beer.conf"
NAME_KEY = "NAME"
VERSION_KEY = "VERSION"
ENTRY_POINT_KEY = "PLUGIN_ENTRY"
INSTANCES_KEY = "INSTANCES"
ARGS_KEY = "PLUGIN_ARGS"
REQUIRED_KEYS = [NAME_KEY, VERSION_KEY, ENTRY_POINT_KEY]


def find_config(root):
    for dir_path, dir_names, file_names in os.walk(root):
        if CONFIG_NAME in file_names:
            return join(dir_path, CONFIG_NAME)

    return None
