import logging
import sys
from imp import load_source
from os import listdir
from os.path import join, abspath

import bartender
import bartender.local_plugins
from bartender.local_plugins.config import find_config
from bartender.local_plugins.plugin_runner import LocalPluginRunner
from brewtils.models import Instance, System

logger = logging.getLogger(__name__)


def scan_plugin_path(plugin_path=None):
    """Find valid plugin directories

    Note: This scan does not walk the directory tree. All plugins must be
    direct children of the given path.

    Args:
        plugin_path: The root path to scan

    Returns:
        A list containing tuples of (directory, config_path) for plugins
    """
    plugin_path = plugin_path or bartender.config.plugin.local.directory
    plugins = set()

    if plugin_path is None:
        return plugins

    for name in listdir(plugin_path):
        path = abspath(join(plugin_path, name))

        config = find_config(path)
        if config:
            plugins.add((path, abspath(config),))

    logger.debug("Found plugin directories: %s" % [p[0] for p in plugins])

    return plugins


class LocalPluginLoader(object):
    """Class that helps with loading local plugins"""

    logger = logging.getLogger(__name__)

    def __init__(self, validator, registry):
        self.validator = validator
        self.registry = registry

    def load_plugins(self):
        """Load all plugins

        After each has been loaded, it checks the requirements to ensure
        the plugin can be loaded correctly.
        """
        for plugin in scan_plugin_path():
            self.load_plugin(plugin)

        self.validate_plugin_requirements()

    def validate_plugin_requirements(self):
        """Validates requirements for each plugin can be satisfied by one of the loaded plugins"""
        plugin_list = self.registry.get_all_plugins()
        plugin_names = self.registry.get_unique_plugin_names()
        plugins_to_remove = []

        for plugin in plugin_list:
            for required_plugin in plugin.requirements:
                if required_plugin not in plugin_names:
                    self.logger.warning(
                        "Not loading plugin %s - it requires plugin %s which "
                        "is not one of the known plugins.",
                        plugin.system.name, required_plugin)
                    plugins_to_remove.append(plugin)

        for plugin in plugins_to_remove:
            self.registry.remove(plugin.unique_name)

    def load_plugin(self, plugin_tuple):
        """Loads a plugin

        It will use the validator to validate the plugin before registering the
        plugin in the database as well as adding an entry to the plugin map

        :param plugin_tuple: tuple with path, config file
        :return: The loaded plugin
        """
        plugin_path = plugin_tuple[0]
        config_path = plugin_tuple[1]

        if not self.validator.validate_plugin(plugin_path):
            self.logger.warning("Not loading invalid plugin at %s", plugin_path)
            return False

        config = self._load_plugin_config(config_path)

        plugin_id = None
        plugin_commands = []
        plugin_name = config['NAME']
        plugin_version = config['VERSION']
        plugin_entry = config["PLUGIN_ENTRY"]
        plugin_instances = config['INSTANCES']
        plugin_args = config['PLUGIN_ARGS']

        # If this system already exists we need to do some stuff
        plugin_system = bartender.bv_client.find_unique_system(
            name=plugin_name, version=plugin_version)

        if plugin_system:
            # TODO Remove the current instances so they aren't left dangling
            # plugin_system.delete_instances()

            # Carry these over to the new system
            plugin_id = plugin_system.id
            plugin_commands = plugin_system.commands

        plugin_system = System(
            id=plugin_id,
            name=plugin_name,
            version=plugin_version,
            commands=plugin_commands,
            instances=[Instance(name=name, status='INITIALIZING') for name in plugin_instances],
            max_instances=len(plugin_instances),
            description=config.get('DESCRIPTION'),
            icon_name=config.get('ICON_NAME'),
            display_name=config.get('DISPLAY_NAME'),
            metadata=config.get('METADATA'),
        )

        plugin_system = bartender.bv_client.create_system(plugin_system)

        plugin_list = []
        for instance_name in plugin_instances:
            plugin = LocalPluginRunner(
                plugin_entry,
                plugin_system,
                instance_name,
                plugin_path,
                plugin_args=plugin_args.get(instance_name),
                environment=config['ENVIRONMENT'],
                requirements=config['REQUIRES'],
                plugin_log_directory=bartender.config.plugin.local.log_directory,
                username=bartender.config.plugin.local.auth.username,
                password=bartender.config.plugin.local.auth.password,
                log_level=config['LOG_LEVEL'],
            )

            self.registry.register_plugin(plugin)
            plugin_list.append(plugin)

        return plugin_list

    def _load_plugin_config(self, path_to_config):
        """Loads a validated plugin config"""
        self.logger.debug("Loading configuration at %s", path_to_config)

        config_module = load_source('BGPLUGINCONFIG', path_to_config)

        instances = getattr(config_module, 'INSTANCES', None)
        plugin_args = getattr(config_module, 'PLUGIN_ARGS', None)
        log_name = getattr(config_module, 'LOG_LEVEL', 'INFO')
        log_level = getattr(logging, str(log_name).upper(), logging.INFO)

        if instances is None and plugin_args is None:
            instances = ['default']
            plugin_args = {'default': None}

        elif plugin_args is None:
            plugin_args = {}
            for instance_name in instances:
                plugin_args[instance_name] = None

        elif instances is None:
            if isinstance(plugin_args, list):
                instances = ['default']
                plugin_args = {'default': plugin_args}
            elif isinstance(plugin_args, dict):
                instances = list(plugin_args.keys())
            else:
                raise ValueError('Unknown plugin args type: %s' % plugin_args)

        elif isinstance(plugin_args, list):
            temp_args = {}
            for instance_name in instances:
                temp_args[instance_name] = plugin_args

            plugin_args = temp_args

        config = {
            'NAME': config_module.NAME,
            'VERSION': config_module.VERSION,
            'INSTANCES': instances,
            'PLUGIN_ENTRY': config_module.PLUGIN_ENTRY,
            'PLUGIN_ARGS': plugin_args,
            'LOG_LEVEL': log_level,
            'DESCRIPTION': getattr(config_module, 'DESCRIPTION', ''),
            'ICON_NAME': getattr(config_module, 'ICON_NAME', None),
            'DISPLAY_NAME': getattr(config_module, 'DISPLAY_NAME', None),
            'REQUIRES': getattr(config_module, 'REQUIRES', []),
            'ENVIRONMENT': getattr(config_module, 'ENVIRONMENT', {}),
            'METADATA': getattr(config_module, 'METADATA', {}),
        }

        if 'BGPLUGINCONFIG' in sys.modules:
            del sys.modules['BGPLUGINCONFIG']

        return config
