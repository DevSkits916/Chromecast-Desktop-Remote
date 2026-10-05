from enum import Enum


class ConnectionState(str, Enum):
    ADB_MISSING = 'ADB_MISSING'
    SEARCHING = 'SEARCHING'
    DEVICE_FOUND = 'DEVICE_FOUND'
    PAIRING_REQUIRED = 'PAIRING_REQUIRED'
    PAIRING = 'PAIRING'
    CONNECTING = 'CONNECTING'
    CONNECTED = 'CONNECTED'
    OFFLINE = 'OFFLINE'
    UNAUTHORIZED = 'UNAUTHORIZED'
    RECONNECTING = 'RECONNECTING'
    ERROR = 'ERROR'


class ConnectionSession:
    """Scheduling policy independent of Qt and ADB, for deterministic tests."""
    def __init__(self):
        self.state = ConnectionState.OFFLINE
        self.paused = False
        self.retry_seconds = 5

    def disconnect(self):
        self.paused = True
        self.state = ConnectionState.OFFLINE

    def start(self):
        self.paused = False
        self.state = ConnectionState.SEARCHING

    def connected(self):
        self.state = ConnectionState.CONNECTED
        self.retry_seconds = 5

    def failed(self, output=''):
        self.state = ConnectionState.UNAUTHORIZED if 'authoriz' in output.lower() else ConnectionState.OFFLINE
        delay = self.retry_seconds
        self.retry_seconds = min(60, delay * 2)
        return delay


def match_discovered(devices, profile):
    """Prefer saved service identity, then IP. Never fall back to another TV."""
    if not profile:
        return None
    matches = [d for d in devices if profile.get('service_name') and d.name == profile['service_name']]
    if not matches:
        matches = [d for d in devices if d.ip == profile.get('ip')]
    return matches[0] if len(matches) == 1 else None
