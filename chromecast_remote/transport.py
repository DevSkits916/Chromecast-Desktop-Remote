"""Route navigation independently of the ADB-only management features."""


class RemoteTransport:
    def __init__(self, adb, bluetooth):
        self.adb = adb
        self.bluetooth = bluetooth
        self.mode = 'adb'
        self.bluetooth_connected = False

    def select(self, mode):
        if mode not in ('adb', 'bluetooth'):
            raise ValueError('Unknown control transport')
        self.bluetooth.release_all()
        self.mode = mode

    def tap(self, name, adb_connected):
        if self.mode == 'bluetooth':
            return self.bluetooth.tap(name) if self.bluetooth_connected else False
        return self.adb.key(name) if adb_connected else False

    def press(self, name):
        if self.mode == 'bluetooth' and self.bluetooth_connected:
            return self.bluetooth.press(name)
        return False

    def release(self, name):
        if self.mode == 'bluetooth':
            return self.bluetooth.release(name)
        return False
