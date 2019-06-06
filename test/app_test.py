import unittest
from datetime import timedelta

import requests.exceptions
from mock import MagicMock, Mock, patch
from yapconf import YapconfSpec

import bartender
from bartender.app import BartenderApp, HelperThread
from bartender.mongo_pruner import GridFSPrune
from bartender.specification import SPECIFICATION
from bg_utils.mongo.models import Event, Request, RequestFile


@patch("bartender.app.time", Mock())
class BartenderAppTest(unittest.TestCase):
    def setUp(self):
        self.config = YapconfSpec(SPECIFICATION).load_config()
        bartender.config = self.config

        self.app = BartenderApp()
        self.thrift_server = Mock()
        self.queue_manager = Mock()
        self.local_monitor = Mock()
        self.status_monitor = Mock()
        self.plugin_manager = Mock()
        self.plugin_loader = Mock()
        self.clients = MagicMock()
        self.mongo_pruner = Mock()

    @patch("bartender.app.BartenderApp._shutdown")
    @patch("bartender.app.BartenderApp._startup")
    def test_run(self, startup_mock, shutdown_mock):
        self.app.helper_threads = []
        self.app.stopped = Mock(side_effect=[False, True])

        self.app.run()
        startup_mock.assert_called_once_with()
        shutdown_mock.assert_called_once_with()

    @patch("bartender.app.BartenderApp._shutdown", Mock())
    @patch("bartender.app.BartenderApp._startup", Mock())
    def test_helper_thread_restart(self):
        helper_mock = Mock()
        helper_mock.thread.isAlive.return_value = False
        self.app.helper_threads = [helper_mock]
        self.app.stopped = Mock(side_effect=[False, True])

        self.app.run()
        helper_mock.start.assert_called_once_with()

    @patch("bartender.bv_client", Mock())
    @patch("bartender.app.BartenderApp._shutdown", Mock())
    def test_startup(self):
        self.app.stopped = Mock(return_value=True)
        self.app.thrift_server = self.thrift_server
        self.app.local_monitor = self.local_monitor
        self.app.status_monitor = self.status_monitor
        self.app.plugin_loader = self.plugin_loader
        self.app.clients = self.clients
        self.app.plugin_manager = self.plugin_manager
        self.app.queue_manager = self.queue_manager
        self.app.helper_threads = [
            self.mongo_pruner,
            self.thrift_server,
            self.local_monitor,
            self.status_monitor,
        ]

        self.app.run()
        self.app.plugin_loader.load_plugins.assert_called_once_with()
        self.app.plugin_manager.start_all_plugins.assert_called_once_with()

        for helper in self.app.helper_threads:
            helper.start.assert_called_once_with()

    @patch("bartender.bv_client")
    def test_startup_notification_error(self, client_mock):
        self.app.plugin_manager = self.plugin_manager
        self.app.clients = self.clients
        self.app.helper_threads = []

        client_mock.publish_event.side_effect = requests.exceptions.ConnectionError

        self.app._startup()

    @patch("bartender.bv_client", Mock())
    @patch("bartender.app.BartenderApp._startup", Mock())
    def test_shutdown(self):
        self.app.stopped = Mock(return_value=True)
        self.app.plugin_manager = self.plugin_manager
        self.app.helper_threads = [
            self.mongo_pruner,
            self.thrift_server,
            self.local_monitor,
            self.status_monitor,
        ]

        self.app.run()
        self.plugin_manager.stop_all_plugins.assert_called_once_with()

        for helper in self.app.helper_threads:
            helper.stop.assert_called_once_with()

    @patch("bartender.bv_client")
    def test_shutdown_notification_error(self, client_mock):
        self.app.plugin_manager = self.plugin_manager
        self.app.clients = self.clients
        self.app.helper_threads = []

        client_mock.publish_event.side_effect = requests.exceptions.ConnectionError

        self.app._shutdown()

    def test_setup_pruning_tasks(self):
        bartender.config.db.ttl.info = 5
        bartender.config.db.ttl.action = 10
        bartender.config.db.ttl.event = 15

        prune_tasks, run_every = BartenderApp._setup_pruning_tasks()
        self.assertEqual(5, len(prune_tasks))
        self.assertEqual(2.5, run_every)

        rf_task = prune_tasks[0]
        info_task = prune_tasks[1]
        action_task = prune_tasks[2]
        event_task = prune_tasks[3]
        gridfs_task = prune_tasks[4]

        self.assertEqual(RequestFile, rf_task.collection)
        self.assertEqual(Request, info_task.collection)
        self.assertEqual(Request, action_task.collection)
        self.assertEqual(Event, event_task.collection)
        self.assertIsInstance(gridfs_task, GridFSPrune)

        self.assertEqual("created_at", rf_task.field)
        self.assertEqual("created_at", info_task.field)
        self.assertEqual("created_at", action_task.field)
        self.assertEqual("timestamp", event_task.field)

        self.assertEqual(timedelta(minutes=15), rf_task.delete_after)
        self.assertEqual(timedelta(minutes=5), info_task.delete_after)
        self.assertEqual(timedelta(minutes=10), action_task.delete_after)
        self.assertEqual(timedelta(minutes=15), event_task.delete_after)

    def test_setup_pruning_tasks_empty(self):
        bartender.config.db.ttl.info = -1
        bartender.config.db.ttl.action = -1
        bartender.config.db.ttl.event = -1

        prune_tasks, run_every = BartenderApp._setup_pruning_tasks()
        self.assertEqual(len(prune_tasks), 2)
        self.assertEqual(7.5, run_every)

    def test_setup_pruning_tasks_one(self):
        bartender.config.db.ttl.info = -1
        bartender.config.db.ttl.action = 1
        bartender.config.db.ttl.event = -1

        prune_tasks, run_every = BartenderApp._setup_pruning_tasks()
        self.assertEqual(3, len(prune_tasks))
        self.assertEqual(0.5, run_every)

    def test_setup_pruning_tasks_mixed(self):
        bartender.config.db.ttl.info = 5
        bartender.config.db.ttl.action = -1
        bartender.config.db.ttl.event = 15

        prune_tasks, run_every = BartenderApp._setup_pruning_tasks()
        self.assertEqual(4, len(prune_tasks))
        self.assertEqual(2.5, run_every)

        info_task = prune_tasks[1]
        event_task = prune_tasks[2]

        self.assertEqual(Request, info_task.collection)
        self.assertEqual(Event, event_task.collection)

        self.assertEqual("created_at", info_task.field)
        self.assertEqual("timestamp", event_task.field)

        self.assertEqual(timedelta(minutes=5), info_task.delete_after)
        self.assertEqual(timedelta(minutes=15), event_task.delete_after)


class HelperThreadTest(unittest.TestCase):
    def setUp(self):
        self.callable_mock = Mock()
        self.helper = HelperThread(self.callable_mock)

    def test_start(self):
        self.helper.start()
        self.assertTrue(self.callable_mock.called)
        self.assertIsNotNone(self.helper.thread)
        self.assertTrue(self.helper.thread.start.called)

    def test_stop_thread_alive_successful(self):
        self.helper.thread = Mock(isAlive=Mock(side_effect=[True, False]))

        self.helper.stop()
        self.assertTrue(self.helper.thread.stop.called)
        self.assertTrue(self.helper.thread.join.called)

    def test_stop_thread_alive_unsuccessful(self):
        self.helper.thread = Mock(isAlive=Mock(return_value=True))

        self.helper.stop()
        self.assertTrue(self.helper.thread.stop.called)
        self.assertTrue(self.helper.thread.join.called)

    def test_stop_thread_dead(self):
        self.helper.thread = Mock(isAlive=Mock(return_value=False))

        self.helper.stop()
        self.assertFalse(self.helper.thread.stop.called)
        self.assertFalse(self.helper.thread.join.called)
