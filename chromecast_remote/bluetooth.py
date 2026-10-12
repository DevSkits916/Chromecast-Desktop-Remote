"""Real Windows BLE HID peripheral, with all WinRT work on one MTA thread."""
from __future__ import annotations

import asyncio
import logging
import sys
import threading
from uuid import UUID

from PySide6.QtCore import QObject, Signal
from .hid import REPORT_MAP, reports

log = logging.getLogger(__name__)


def uuid16(value):
    return UUID(f'0000{value:04x}-0000-1000-8000-00805f9b34fb')


class BluetoothController(QObject):
    status = Signal(str, str)  # state, explanation
    clients_changed = Signal(object)  # IDs, never imply paired from advertising alone

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread = None
        self._loop = None
        self._queue = None
        self._ready = threading.Event()
        self._stopping = threading.Event()
        self._providers = []
        self._handlers = []
        self._pressed = set()
        self._reports = []
        self._values = [bytes(8), bytes(2)]
        self._clients = {}
        self._peer = ''
        self._suspended = False

    @property
    def running(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, peer=''):
        if self.running:
            return
        from logging.handlers import RotatingFileHandler
        from .config import config_dir
        if not log.handlers:
            try:
                folder = config_dir() / 'logs'
                folder.mkdir(parents=True, exist_ok=True)
                handler = RotatingFileHandler(folder / 'bluetooth.log', maxBytes=1024*1024,
                                              backupCount=2, encoding='utf-8')
                handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
                log.addHandler(handler)
                log.setLevel(logging.INFO)
            except OSError:
                log.warning('Unable to open Bluetooth diagnostic log')
        self._peer = peer
        self._stopping.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, name='BluetoothHID', daemon=True)
        self._thread.start()

    def _enqueue(self, action, value=None):
        if not self._ready.is_set() or self._stopping.is_set():
            return False
        def put():
            if self._queue.full():
                while not self._queue.empty():
                    self._queue.get_nowait()
                self._queue.put_nowait(('release', None))
                self.status.emit('ERROR', 'Bluetooth input queue overflow; released all buttons.')
            else:
                self._queue.put_nowait((action, value))
        try:
            self._loop.call_soon_threadsafe(put)
            return True
        except RuntimeError:
            return False

    def select_peer(self, peer):
        return self._enqueue('peer', peer)

    def press(self, name):
        return self._enqueue('press', name)

    def release(self, name):
        return self._enqueue('up', name)

    def tap(self, name):
        return self._enqueue('tap', name)

    def release_all(self):
        return self._enqueue('release')

    def stop(self):
        self._stopping.set()
        if self._loop is not None:
            try:
                def finish():
                    if self._ready.is_set():
                        self._stop_event.set()
                    elif getattr(self, '_main_task', None):
                        self._main_task.cancel()
                self._loop.call_soon_threadsafe(finish)
            except RuntimeError:
                pass
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        return not self.running

    def _run(self):
        initialized = False
        try:
            if sys.platform != 'win32':
                raise RuntimeError('Bluetooth HID requires Windows 10/11.')
            from winrt.runtime import init_apartment, uninit_apartment, ApartmentType
            init_apartment(ApartmentType.MULTI_THREADED)
            initialized = True
            asyncio.run(self._serve())
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            log.exception('Bluetooth HID failed')
            self.status.emit('ERROR', f'Bluetooth unavailable: {exc}')
        finally:
            self._ready.clear()
            self._loop = None
            if initialized:
                uninit_apartment()

    def _on(self, obj, event, callback):
        token = getattr(obj, 'add_' + event)(callback)
        self._handlers.append((obj, event, token))

    def _buffer(self, value):
        with self.streams.DataWriter() as writer:
            writer.write_bytes(value)
            return writer.detach_buffer()

    async def _characteristic(self, service, short_id, properties, value=None, secure=True):
        params = self.gatt.GattLocalCharacteristicParameters()
        params.characteristic_properties = properties
        protection = (self.gatt.GattProtectionLevel.ENCRYPTION_REQUIRED if secure
                      else self.gatt.GattProtectionLevel.PLAIN)
        params.read_protection_level = protection
        params.write_protection_level = protection
        if value is not None:
            params.static_value = self._buffer(value)
        result = await service.create_characteristic_async(uuid16(short_id), params)
        if result.error != self.bt.BluetoothError.SUCCESS:
            raise RuntimeError(f'Cannot create characteristic {short_id:04x}: {result.error.name}')
        return result.characteristic

    def _request_handler(self, kind, index=None):
        def callback(sender, args):
            try:
                deferral = args.get_deferral()
                future = asyncio.run_coroutine_threadsafe(self._request(kind, index, args, deferral), self._loop)
                # Keep callbacks exception-safe; errors are reported by _request.
                future.add_done_callback(lambda done: None)
            except Exception:
                log.exception('Bluetooth request dispatch failed')
        return callback

    async def _request(self, kind, index, args, deferral):
        try:
            request = await args.get_request_async()
            if request is None:
                return
            if kind == 'read':
                value = self._values[index]
                if request.offset > len(value):
                    request.respond_with_protocol_error(0x07)
                else:
                    request.respond_with_value(self._buffer(value[request.offset:]))
            else:
                if self._peer and args.session.device_id.id != self._peer:
                    if request.option == self.gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                        request.respond_with_protocol_error(0x08)
                    return
                with self.streams.DataReader.from_buffer(request.value) as reader:
                    value = reader.read_byte() if reader.unconsumed_buffer_length == 1 else -1
                if value not in (0, 1) or request.offset:
                    if request.option == self.gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                        request.respond_with_protocol_error(0x0D)
                    return
                self._suspended = value == 0
                self._pressed.clear()
                await self._notify()
                if request.option == self.gatt.GattWriteOption.WRITE_WITH_RESPONSE:
                    request.respond()
        except Exception as exc:
            log.exception('Bluetooth GATT request failed')
            self.status.emit('ERROR', f'Bluetooth request failed: {exc}')
        finally:
            deferral.complete()

    def _subscription_event(self, sender, args):
        try:
            self._loop.call_soon_threadsafe(self._update_clients)
        except RuntimeError:
            pass

    def _update_clients(self):
        if self._stopping.is_set() or not self._ready.is_set():
            return
        self._clients = {}
        for report in self._reports:
            for client in report.subscribed_clients:
                self._clients[client.session.device_id.id] = client
        self.clients_changed.emit(sorted(self._clients))
        keyboard_hosts = {client.session.device_id.id for client in self._reports[0].subscribed_clients}
        if self._peer and self._peer in keyboard_hosts:
            self.status.emit('CONNECTED', 'Bluetooth host subscribed. Test navigation on the TV.')
        else:
            self._pressed.clear()
            self._values = [bytes(8), bytes(2)]
            self.status.emit('ADVERTISING', 'Waiting for the selected TV to subscribe.' if self._peer
                             else 'Advertising. Pair from the TV, then choose its host below.')

    def _advertisement_event(self, sender, args):
        try:
            log.info('HID advertising: %s (%s)', args.status.name, args.error.name)
            if args.status in (self.gatt.GattServiceProviderAdvertisementStatus.STARTED,
                               self.gatt.GattServiceProviderAdvertisementStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA):
                self._loop.call_soon_threadsafe(self._advertised_event.set)
            elif (args.status == self.gatt.GattServiceProviderAdvertisementStatus.ABORTED
                  and args.error != self.bt.BluetoothError.SUCCESS):
                self.status.emit('ERROR', f'Bluetooth advertising aborted: {args.error.name}')
                self._loop.call_soon_threadsafe(self._stop_event.set)
        except Exception:
            log.exception('Bluetooth advertising callback failed')

    async def _notify(self):
        self._values = list(reports(self._pressed))
        for index, report in enumerate(self._reports):
            for client in report.subscribed_clients:
                if client.session.device_id.id != self._peer:
                    continue
                if client.max_notification_size < len(self._values[index]):
                    raise RuntimeError('Host notification limit is too small for HID reports.')
                result = await asyncio.wait_for(report.notify_value_for_subscribed_client_async(
                    self._buffer(self._values[index]), client), 3)
                if result.status != self.gatt.GattCommunicationStatus.SUCCESS:
                    raise RuntimeError(f'Input delivery failed: {result.status.name}')

    async def _serve(self):
        from winrt.windows.devices import bluetooth as bt
        from winrt.windows.devices.bluetooth import genericattributeprofile as gatt
        from winrt.windows.storage import streams
        from winrt.windows.devices.radios import RadioState
        self.bt, self.gatt, self.streams = bt, gatt, streams
        self._loop = asyncio.get_running_loop()
        self._main_task = asyncio.current_task()
        self._queue = asyncio.Queue(maxsize=64)
        self._stop_event = asyncio.Event()
        self._advertised_event = asyncio.Event()
        self._reports, self._providers, self._handlers = [], [], []
        self._pressed.clear()
        self._suspended = False
        self.status.emit('STARTING', 'Checking Windows Bluetooth peripheral support…')
        try:
            adapter = await asyncio.wait_for(bt.BluetoothAdapter.get_default_async(), 10)
            if adapter is None:
                raise RuntimeError('No Bluetooth adapter found.')
            if not adapter.is_peripheral_role_supported:
                raise RuntimeError('This adapter/driver cannot advertise a BLE HID peripheral.')
            radio = await adapter.get_radio_async()
            if radio.state != RadioState.ON:
                raise RuntimeError('Turn Bluetooth on in Windows Settings, then retry.')
            result = await gatt.GattServiceProvider.create_async(uuid16(0x1812))
            if result.error != bt.BluetoothError.SUCCESS:
                raise RuntimeError(f'Windows rejected HID service creation: {result.error.name}')
            provider = result.service_provider
            self._providers.append(provider)
            props = gatt.GattCharacteristicProperties
            await self._characteristic(provider.service, 0x2A4B, props.READ, REPORT_MAP)
            # Report-only HID, no boot protocol, no claim of remote wake support.
            await self._characteristic(provider.service, 0x2A4A, props.READ, b'\x11\x01\x00\x02')
            control = await self._characteristic(provider.service, 0x2A4C, props.WRITE_WITHOUT_RESPONSE)
            self._on(control, 'write_requested', self._request_handler('control'))
            for index in range(2):
                report = await self._characteristic(provider.service, 0x2A4D, props.READ | props.NOTIFY)
                params = gatt.GattLocalDescriptorParameters()
                params.static_value = self._buffer(bytes([index + 1, 1]))
                params.read_protection_level = gatt.GattProtectionLevel.ENCRYPTION_REQUIRED
                descriptor = await report.create_descriptor_async(uuid16(0x2908), params)
                if descriptor.error != bt.BluetoothError.SUCCESS:
                    raise RuntimeError(f'Cannot create report reference: {descriptor.error.name}')
                self._reports.append(report)
                self._on(report, 'read_requested', self._request_handler('read', index))
                self._on(report, 'subscribed_clients_changed', self._subscription_event)
            battery = await gatt.GattServiceProvider.create_async(uuid16(0x180F))
            if battery.error != bt.BluetoothError.SUCCESS:
                raise RuntimeError(f'Cannot create battery service: {battery.error.name}')
            self._providers.append(battery.service_provider)
            await self._characteristic(battery.service_provider.service, 0x2A19, props.READ, b'\x64', False)
            advertising = gatt.GattServiceProviderAdvertisingParameters()
            advertising.is_discoverable = True
            advertising.is_connectable = True
            self._on(provider, 'advertisement_status_changed', self._advertisement_event)
            provider.start_advertising_with_parameters(advertising)
            # Publish the battery service without spending a second advertising slot.
            battery.service_provider.start_advertising()
            await asyncio.wait_for(self._advertised_event.wait(), 10)
            if provider.advertisement_status not in (
                    gatt.GattServiceProviderAdvertisementStatus.STARTED,
                    gatt.GattServiceProviderAdvertisementStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA):
                raise RuntimeError(f'Advertising did not start: {provider.advertisement_status.name}')
            self._ready.set()
            self.status.emit('ADVERTISING', 'Windows is advertising HID using its Bluetooth name. '
                             'Pair from the TV; accept any Windows pairing prompt.')
            self._update_clients()
            if self._stopping.is_set():
                self._stop_event.set()
            consumer = asyncio.create_task(self._consume())
            await self._stop_event.wait()
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)
        finally:
            self._ready.clear()
            self._pressed.clear()
            try:
                await asyncio.wait_for(self._notify(), 2)
            except Exception:
                log.exception('Final Bluetooth key release failed')
            for obj, event, token in reversed(self._handlers):
                try:
                    getattr(obj, 'remove_' + event)(token)
                except Exception:
                    log.exception('Bluetooth event cleanup failed')
            for provider in self._providers:
                try:
                    if provider.advertisement_status in (
                            gatt.GattServiceProviderAdvertisementStatus.STARTED,
                            gatt.GattServiceProviderAdvertisementStatus.STARTED_WITHOUT_ALL_ADVERTISEMENT_DATA,
                            gatt.GattServiceProviderAdvertisementStatus.ABORTED):
                        provider.stop_advertising()
                except Exception:
                    log.exception('Bluetooth advertising cleanup failed')
            self._handlers.clear()
            self._providers.clear()
            self._reports.clear()
            self._clients.clear()
            self.clients_changed.emit([])
            self.status.emit('STOPPED', 'Bluetooth advertising stopped.')

    async def _consume(self):
        while True:
            action, value = await self._queue.get()
            try:
                if action == 'peer':
                    self._pressed.clear()
                    await self._notify()  # Release on old host before selecting a new one.
                    self._peer = value
                    self._suspended = False
                    self._update_clients()
                elif action == 'release':
                    self._pressed.clear()
                    await self._notify()
                elif not self._suspended and self._peer in self._clients:
                    if action == 'up':
                        self._pressed.discard(value)
                    else:
                        self._pressed.add(value)
                    await self._notify()
                    if action == 'tap':
                        self._pressed.discard(value)
                        await self._notify()
            except Exception as exc:
                self._pressed.clear()
                log.exception('Bluetooth input delivery failed')
                self.status.emit('ERROR', str(exc))
                self._stop_event.set()
                return


def main():
    """Short real-adapter advertising check; never sends input to any host."""
    from PySide6.QtCore import QCoreApplication, QTimer
    app = QCoreApplication([])
    controller = BluetoothController()
    result = {'advertising': False, 'error': False}
    def status(state, message):
        log.info('%s: %s', state, message)
        print(f'{state}: {message}', flush=True)
        if state == 'ADVERTISING':
            result['advertising'] = True
        if state == 'ERROR':
            result['error'] = True
    controller.status.connect(status)
    controller.start()
    def finish():
        stopped = controller.stop()
        result['error'] |= not stopped
        print(f'Clean shutdown: {stopped}', flush=True)
        log.info('Adapter check clean shutdown: %s', stopped)
        app.quit()
    QTimer.singleShot(8000, finish)
    app.exec()
    return 0 if result['advertising'] and not result['error'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
