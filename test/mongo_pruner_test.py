import pytest
from datetime import timedelta

from mock import Mock, patch

from bartender.mongo_pruner import MongoPruner, PruneTask, GridFSPrune
from mongoengine import Q


class TestPruner(object):
    @pytest.fixture
    def collection(self):
        return Mock(__name__="mock")

    @pytest.fixture
    def prune_task(self, collection):
        query = Q(foo=None)
        return PruneTask(collection, "field", timedelta(microseconds=1), query)

    def test_task_execute(self, prune_task):
        prune_task.execute()
        assert prune_task.collection.objects.return_value.delete.call_count == 1

    def test_task_setup_query_no_children(self, collection):
        task = PruneTask(collection, "field", timedelta(microseconds=1))
        query = task.setup_query(0)
        assert query.query["field__lt"] == 0

    def test_task_setup_query(self, prune_task):
        q = prune_task.setup_query(0)
        assert len(q.children) == 2
        assert q.children[0].query["field__lt"] == 0
        assert q.children[1].query["foo"] is None

    @patch("bg_utils.mongo.models.RequestFile.objects")
    def test_gridfs_prune_empty(self, get_mock):
        get_mock.return_value = []
        gridfs = Mock(find=Mock(return_value=[]))
        task = GridFSPrune(gridfs)
        task.execute()
        assert gridfs.delete.call_count == 0

    @patch("bartender.mongo_pruner.RequestFile")
    def test_gridfs_no_delete(self, get_mock):
        get_mock.objects = [Mock(body=Mock(grid_id="id"))]
        find_mock = Mock(return_value=[Mock(_id="id")])
        gridfs = Mock(find=find_mock)
        task = GridFSPrune(gridfs)
        task.execute()
        assert gridfs.delete.call_count == 0

    @patch("bartender.mongo_pruner.RequestFile")
    def test_gridfs_delete_orphans(self, get_mock):
        get_mock.objects = [Mock(body=Mock(grid_id="id1"))]
        find_mock = Mock(return_value=[Mock(_id="id1"), Mock(_id="id2")])
        gridfs = Mock(find=find_mock)
        task = GridFSPrune(gridfs)
        task.execute()
        gridfs.delete.assert_called_with("id2")

    def test_pruner_thread(self, prune_task):
        pruner = MongoPruner([prune_task])
        prune_task.execute = Mock()
        pruner._stop_event = Mock(wait=Mock(side_effect=[False, True]))
        pruner.run()
        assert prune_task.execute.call_count == 1
