import logging
from datetime import datetime, timedelta

from gridfs import GridFS
from mongoengine import Q
from mongoengine.connection import get_db

from bg_utils.mongo.models import RequestFile
from brewtils.stoppable_thread import StoppableThread


class PruneTask(object):
    def __init__(self, collection, field, delete_after, additional_query=None):
        self.logger = logging.getLogger(__name__)
        self.collection = collection
        self.field = field
        self.delete_after = delete_after
        self.additional_query = additional_query

    def setup_query(self, delete_older_than):
        query = Q(**{self.field + "__lt": delete_older_than})
        if self.additional_query:
            query = query & self.additional_query
        return query

    def execute(self):
        current_time = datetime.utcnow()
        delete_older_than = current_time - self.delete_after
        query = self.setup_query(delete_older_than)
        self.logger.debug(
            "Removing %ss older than %s"
            % (self.collection.__name__, str(delete_older_than))
        )
        self.collection.objects(query).delete()


class GridFSPrune(object):
    def __init__(self, gridfs=None):
        self.fs = gridfs

    def execute(self):
        if self.fs is None:
            self.fs = GridFS(get_db())

        orphan_ids = {f._id for f in self.fs.find()}
        for rf in RequestFile.objects:
            if rf.body.grid_id in orphan_ids:
                orphan_ids.remove(rf.body.grid_id)

        for file_id in orphan_ids:
            self.fs.delete(file_id)


class MongoPruner(StoppableThread):
    def __init__(self, tasks=None, run_every=timedelta(minutes=15)):
        self.logger = logging.getLogger(__name__)
        self.display_name = "Mongo Pruner"
        self._run_every = run_every.total_seconds()
        self._tasks = tasks or []

        super(MongoPruner, self).__init__(logger=self.logger, name="Remover")

    def run(self):
        self.logger.info(self.display_name + " is started")

        while not self.wait(self._run_every):
            for task in self._tasks:
                task.execute()

        self.logger.info(self.display_name + " is stopped")
