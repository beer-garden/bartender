import logging
import sys
from imp import load_source
from os.path import isdir, isfile, join

from bartender.errors import PluginValidationError
from bartender.local_plugins.config import (
    ARGS_KEY, ENTRY_POINT_KEY, INSTANCES_KEY, REQUIRED_KEYS)

logger = logging.getLogger(__name__)


def validate_config(plugin_path, config_path):
    """Validate a plugin config

    Args:
        config_path (str): Path to plugin config file

    Returns:
        bool: True if the configuration is valid, False otherwise
    """
    logger.debug("Validating config at %s ", config_path)

    try:
        if config_path is None or isdir(config_path) or not isfile(config_path):
            return False

        config_module = load_source('BGPLUGINCONFIG', config_path)

        if config_module is None:
            raise PluginValidationError("Configuration module is None")

        validate_required_config_keys(config_module)
        logger.debug("Required keys are present.")

        validate_entry_point(config_module, plugin_path)
        logger.debug("Validated Plugin Entry Point successfully.")

        validate_instances_and_args(config_module)
        logger.debug("Validated plugin instances & arguments successfully.")

        validate_plugin_environment(config_module)
        logger.debug("Validated Plugin Environment successfully.")

    except PluginValidationError as pve:
        logger.error("Error validating config at %s", config_path)
        logger.error(str(pve))
        return False
    finally:
        if 'BGPLUGINCONFIG' in sys.modules:
            del sys.modules['BGPLUGINCONFIG']

    logger.debug("Successfully validated Plugin at %s", config_path)

    return True


def validate_required_config_keys(config_module):

    for key in REQUIRED_KEYS:
        if not hasattr(config_module, key):
            raise PluginValidationError("Required key '%s' not present" % key)


def validate_entry_point(config_module, plugin_path):
    """Validate a plugin's entry point

    An entry point is considered valid if the config has an entry with key
    PLUGIN_ENTRY and the value is a path to either a file or the name of a
    runnable Python module.

    Args:
        config_module:
        plugin_path:

    Returns:
        bool: True if the entry point is valid, False otherwise

    Raises:
        PluginValidationError: The entry point is invalid

    """
    if not hasattr(config_module, ENTRY_POINT_KEY):
        raise PluginValidationError(
            "No %s defined in the plugin configuration." % ENTRY_POINT_KEY)

    entry_point = getattr(config_module, ENTRY_POINT_KEY)

    if isfile(join(plugin_path, entry_point)):
        return True
    elif entry_point.startswith('-m '):
        pkg_path = join(plugin_path, entry_point[3:])
        if (isdir(pkg_path) and
                isfile(join(pkg_path, '__init__.py')) and
                isfile(join(pkg_path, '__main__.py'))):
            return True

    raise PluginValidationError(
        "The %s must be a Python script or a runnable Python package: %s" %
        (ENTRY_POINT_KEY, entry_point))


def validate_instances_and_args(config_module):

    plugin_args = getattr(config_module, ARGS_KEY, None)
    instances = getattr(config_module, INSTANCES_KEY, None)

    if instances is not None and not isinstance(instances, list):
        raise PluginValidationError("'%s' entry was not None or a list. This is invalid. "
                                    "Got: %s" % (INSTANCES_KEY, instances))

    if plugin_args is None:
        return True
    elif isinstance(plugin_args, list):
        return validate_individual_plugin_arguments(plugin_args)
    elif isinstance(plugin_args, dict):
        for instance_name, instance_args in plugin_args.items():
            if instances is not None and instance_name not in instances:
                raise PluginValidationError(
                    "'%s' contains key '%s' but that instance is not specified in the '%s'"
                    "entry." % (ARGS_KEY, instance_name, INSTANCES_KEY))
            validate_individual_plugin_arguments(instance_args)

        if instances:
            for instance_name in instances:
                if instance_name not in plugin_args.keys():
                    raise PluginValidationError(
                        "'%s' contains key '%s' but that instance is not specified in the "
                        "'%s' entry." % (INSTANCES_KEY, instance_name, ARGS_KEY))

        return True
    else:
        raise PluginValidationError("'%s' entry was not a list or dictionary. This is invalid. "
                                    "Got: %s" % (ARGS_KEY, plugin_args))


def validate_individual_plugin_arguments(plugin_args):
    """Validates an individual PLUGIN_ARGS entry"""

    if plugin_args is not None and not isinstance(plugin_args, list):
        raise PluginValidationError(
            "Invalid Plugin Argument Specified: %s. It was not a list or None. "
            "This is not allowed." % plugin_args)

    if isinstance(plugin_args, list):
        for plugin_arg in plugin_args:
            if not isinstance(plugin_arg, str):
                raise PluginValidationError(
                    "Invalid plugin argument: %s - this argument must be a "
                    "string." % plugin_arg)

    return True


def validate_plugin_environment(config_module):
    """Validates ENVIRONMENT if specified.

    ENVIRONMENT must be a dictionary of Strings to Strings. Otherwise it is invalid.

    :param config_module:
    :return: True if valid
    :raises: PluginValidationError if something goes wrong while validating

    """
    if hasattr(config_module, "ENVIRONMENT"):
        env = config_module.ENVIRONMENT
        if not isinstance(env, dict):
            raise PluginValidationError(
                "Invalid ENVIRONMENT type specified: %s. This argument must be "
                "a dictionary." % env)

        for key, value in env.items():
            if not isinstance(key, str):
                raise PluginValidationError(
                    "Invalid Key: %s specified for plugin environment. This "
                    "must be a String." % key)

            if key.startswith("BG_"):
                raise PluginValidationError(
                    "Invalid key: %s specified for plugin environment. The "
                    "'BG_' prefix is a special case for beer-garden only "
                    "environment variables. You will have to pick another "
                    "name. Sorry for the inconvenience." % key)

            if not isinstance(value, str):
                raise PluginValidationError(
                    "Invalid Value: %s specified for plugin environment. "
                    "This must be a String." % value)

    return True
