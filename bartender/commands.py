from bg_utils.mongo.models import Command


def get_command(namespace, command_id):
    return Command.objects.get(namespace=namespace, id=command_id)


def get_commands(namespace):
    return Command.objects.filter(namespace=namespace)
