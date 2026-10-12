from copy import deepcopy
import asyncio
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication
from chromecast_remote.config import DEFAULTS, migrate_settings, new_profile
from chromecast_remote.hid import reports
from chromecast_remote.transport import RemoteTransport
from chromecast_remote.ui import RemoteWindow
from chromecast_remote.bluetooth import BluetoothController


def test_hid_hold_and_release_reports():
    assert reports({'left'}) == (bytes([0, 0, 0x50, 0, 0, 0, 0, 0]), bytes(2))
    assert reports({'volume_up'}) == (bytes(8), bytes([0xE9, 0]))
    assert reports(set()) == (bytes(8), bytes(2))
    assert reports({'left', 'up'})[0][2:4] == bytes([0x50, 0x52])


def test_transport_never_sends_bluetooth_actions_to_adb():
    events = []
    adb = SimpleNamespace(key=lambda key: events.append(('adb', key)))
    bt = SimpleNamespace(tap=lambda key: events.append(('tap', key)),
                         press=lambda key: events.append(('press', key)),
                         release=lambda key: events.append(('up', key)),
                         release_all=lambda: events.append(('release', 'all')))
    transport = RemoteTransport(adb, bt)
    transport.select('bluetooth')
    transport.tap('left', True)
    assert events == [('release', 'all')]
    transport.bluetooth_connected = True
    transport.press('left')
    transport.release('left')
    transport.tap('home', True)
    assert events[-3:] == [('press', 'left'), ('up', 'left'), ('tap', 'home')]
    assert not any(kind == 'adb' for kind, key in events)


def test_bluetooth_peer_survives_settings_migration():
    profile = new_profile('TV')
    profile['bluetooth_peer'] = 'test-host-id'
    migrated = migrate_settings({'profiles': [profile], 'control_transport': 'bluetooth'})
    assert migrated['profiles'][0]['bluetooth_peer'] == 'test-host-id'
    assert migrated['control_transport'] == 'bluetooth'
    assert migrate_settings({'control_transport': 'invalid'})['control_transport'] == 'adb'


def test_notifications_target_only_the_selected_host():
    selected = SimpleNamespace(session=SimpleNamespace(device_id=SimpleNamespace(id='selected')),
                               max_notification_size=20)
    other = SimpleNamespace(session=SimpleNamespace(device_id=SimpleNamespace(id='other')),
                            max_notification_size=20)
    delivered = []
    async def notify(value, client):
        delivered.append((bytes(value), client.session.device_id.id))
        return SimpleNamespace(status='success')
    controller = BluetoothController()
    controller.gatt = SimpleNamespace(GattCommunicationStatus=SimpleNamespace(SUCCESS='success'))
    controller._buffer = lambda value: value
    controller._reports = [SimpleNamespace(subscribed_clients=[other, selected],
                                           notify_value_for_subscribed_client_async=notify)]
    controller._pressed = {'left'}
    controller._peer = 'selected'
    asyncio.run(controller._notify())
    assert delivered == [(bytes([0, 0, 0x50, 0, 0, 0, 0, 0]), 'selected')]
    delivered.clear()
    controller._peer = ''
    asyncio.run(controller._notify())
    assert delivered == []


def test_input_queue_accepts_press_and_release_and_clears_overflow():
    controller = BluetoothController()
    async def check():
        controller._loop = asyncio.get_running_loop()
        controller._queue = asyncio.Queue(maxsize=2)
        controller._ready.set()
        controller._peer = 'selected'
        assert controller.press('left')
        assert controller.release('left')
        await asyncio.sleep(0)
        assert controller._queue.get_nowait() == ('press', 'left')
        assert controller._queue.get_nowait() == ('up', 'left')
        controller.press('left')
        controller.press('right')
        controller.release('left')
        await asyncio.sleep(0)
        assert controller._queue.get_nowait() == ('release', None)
        assert controller._queue.empty()
        controller._ready.clear()
        assert not controller.press('left')
    asyncio.run(check())


def test_bluetooth_dialog_and_buttons_without_adb(monkeypatch):
    app = QApplication.instance() or QApplication([])
    settings = deepcopy(DEFAULTS)
    settings.update(close_to_tray=False, auto_connect=False)
    window = RemoteWindow(settings)
    window.open_bluetooth()
    started = []
    monkeypatch.setattr(window.bluetooth, 'start', lambda peer: started.append(peer))
    window._bluetooth_dialog.start()
    assert started == ['']
    assert window.transport.mode == 'bluetooth'
    assert window._profile()['name'] == 'Bluetooth TV'
    window._bluetooth_clients(['host-1'])
    peers = []
    monkeypatch.setattr(window.bluetooth, 'select_peer', lambda peer: peers.append(peer) or True)
    window._bluetooth_dialog.use_host()
    assert peers == ['host-1']
    assert window._profile()['bluetooth_peer'] == 'host-1'
    window._bluetooth_status('CONNECTED', 'Subscribed')
    actions = []
    monkeypatch.setattr(window.bluetooth, 'tap', lambda key: actions.append(key) or True)
    window.send_key('left')
    assert actions == ['left']
    window.quitting = True
    window.close()
    app.processEvents()
