from __future__ import absolute_import

import os

from brewtils.plugin import PluginBase
from brewtils.rest.system_client import SystemClient
from .client import EchoSleeperClient


def main():
    ssl_enabled = os.getenv('BG_SSL_ENABLED', '').lower() != "false"

    plugin = PluginBase(
        EchoSleeperClient(
            SystemClient(os.getenv("BG_WEB_HOST"), os.getenv("BG_WEB_PORT"),
                         'echo', ssl_enabled=ssl_enabled),
            SystemClient(os.getenv("BG_WEB_HOST"), os.getenv("BG_WEB_PORT"),
                         'sleeper', ssl_enabled=ssl_enabled)),
        max_concurrent=5)
    plugin.run()


if __name__ == '__main__':
    main()
