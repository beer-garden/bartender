import os
from contextlib import contextmanager


@contextmanager
def mangle_env(updates):
    env_copy = os.environ.copy()
    for k, v in updates.items():
        os.environ[k] = v

    yield
    os.environ = env_copy
