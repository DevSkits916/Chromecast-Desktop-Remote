from __future__ import annotations

import json
import re
import urllib.request
import xml.etree.ElementTree as ET

from PySide6.QtCore import QObject, QRunnable, Signal

from . import __version__

RELEASE_URL = 'https://github.com/DevSkits916/Chromecast-Desktop-Remote/releases/latest'
RELEASE_API = 'https://api.github.com/repos/DevSkits916/Chromecast-Desktop-Remote/releases/latest'
GOOGLE_REPOSITORY = 'https://dl.google.com/android/repository/repository2-1.xml'


def read_url(url, maximum=4 * 1024 * 1024):
    request = urllib.request.Request(url, headers={'User-Agent': f'ChromecastDesktopRemote/{__version__}'})
    with urllib.request.urlopen(request, timeout=12) as response:
        if not response.geturl().startswith('https://'):
            raise ValueError('An HTTPS response is required.')
        data = response.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError('Update response exceeded the size limit.')
        return data


def version_tuple(version):
    match = re.fullmatch(r'v?(\d+)\.(\d+)\.(\d+)', version)
    if not match:
        raise ValueError('Unsupported release version.')
    return tuple(map(int, match.groups()))


def check_update():
    try:
        release = json.loads(read_url(RELEASE_API))
        latest = release['tag_name']
        newer = version_tuple(latest) > version_tuple(__version__)
        return True, f'Update available: {latest}' if newer else f'Version {__version__} is current.'
    except Exception as exc:
        return False, f'Could not check updates: {exc}'


def check_platform_update():
    try:
        root = ET.fromstring(read_url(GOOGLE_REPOSITORY))
        for package in root.iter():
            if package.tag.split('}')[-1] == 'remotePackage' and package.get('path') == 'platform-tools':
                revision = next(c for c in package if c.tag.split('}')[-1] == 'revision')
                numbers = {c.tag.split('}')[-1]: c.text or '0' for c in revision}
                return True, 'Latest official Platform Tools: ' + '.'.join(numbers.get(k, '0') for k in ('major', 'minor', 'micro'))
        raise ValueError('Official Platform Tools revision was not found.')
    except Exception as exc:
        return False, f'Could not check Platform Tools: {exc}'


class UpdateSignals(QObject):
    finished = Signal(bool, str)


class UpdateTask(QRunnable):
    def __init__(self, platform=False):
        super().__init__()
        self.platform = platform
        self.signals = UpdateSignals()

    def run(self):
        self.signals.finished.emit(*(check_platform_update() if self.platform else check_update()))
