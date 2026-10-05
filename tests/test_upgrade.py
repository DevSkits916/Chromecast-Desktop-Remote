import json
import zipfile
from copy import deepcopy

import pytest
from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtTest import QTest
from PySide6.QtCore import Qt

from chromecast_remote.adb import AdbController, AdbResult, parse_mdns_services, parse_getprop, parse_packages, valid_package, validate_apk, escape_android_text
from chromecast_remote.config import DEFAULTS, migrate_settings, new_profile, load_settings
from chromecast_remote.connection import ConnectionState, ConnectionSession, match_discovered
from chromecast_remote.ui import RemoteWindow, HoldRepeat, SettingsDialog
from chromecast_remote import updates


def window(profiles=None):
    QApplication.instance() or QApplication([])
    settings = deepcopy(DEFAULTS)
    settings.update(auto_connect=False, close_to_tray=False)
    if profiles:
        settings['profiles'] = profiles
        settings['selected_profile'] = profiles[0]['id']
    return RemoteWindow(settings)


def test_legacy_migration_preserves_preferences():
    legacy = dict(device_ip='192.168.1.3', adb_port=43210, auto_connect=False, adb_path='C:/adb.exe', compact_default=True, always_on_top=True, launch_windows=True, close_to_tray=False, window={'x':12,'y':34,'width':450,'height':700})
    migrated = migrate_settings(legacy)
    assert migrated['schema_version'] == 2
    assert migrated['profiles'][0]['ip'] == legacy['device_ip']
    assert migrated['profiles'][0]['port'] == legacy['adb_port']
    assert not migrated['profiles'][0]['auto_connect']
    for key, value in legacy.items():
        assert migrated[key] == value
    assert migrate_settings(migrated) == migrated


@pytest.mark.parametrize('saved', [None, [], {'window':None,'profiles':[None,5],'adb_port':999999}, {'device_ip':12,'auto_connect':[]}, {'window':{'width':'bad'}}])
def test_malformed_config_recovers(saved):
    value = migrate_settings(saved)
    assert isinstance(value['window']['width'], int)
    assert 1 <= value['adb_port'] <= 65535


def test_profile_ids_selection_and_metadata():
    first, second = new_profile('Living', '192.168.1.2'), new_profile('Bedroom','192.168.1.3',4321,False)
    assert first['id'] != second['id']
    second.update(favorites=['com.example.tv'], model='Streamer')
    settings = migrate_settings(dict(profiles=[first,second], selected_profile=second['id']))
    assert settings['device_ip'] == second['ip']
    assert settings['profiles'][1]['favorites'] == ['com.example.tv']
    assert not settings['auto_connect']


def test_discovery_dedup_and_invalid_ports():
    devices = parse_mdns_services('tv _adb-tls-connect._tcp 192.168.1.2:1234\ntv _adb-tls-connect._tcp 192.168.1.2:1234\nbad _adb-tls-connect._tcp x:0\nbad _adb-tls-connect._tcp x:no\ninvalid')
    assert len(devices) == 1


def test_discovery_identity_changed_port_and_disappearance():
    profile = new_profile('TV', '192.168.1.2',1234)
    devices = parse_mdns_services('tv _adb-tls-connect._tcp 192.168.1.2:55555\nother _adb-tls-connect._tcp 192.168.1.3:5555')
    assert match_discovered(devices, profile).port == 55555
    assert match_discovered(devices[1:], profile) is None
    profile['service_name'] = 'tv'
    devices = parse_mdns_services('tv _adb-tls-connect._tcp 192.168.1.8:44444')
    assert match_discovered(devices, profile).ip == '192.168.1.8'
    assert match_discovered([], profile) is None


def test_reconnect_policy_and_user_disconnect():
    session = ConnectionSession()
    session.start()
    assert session.state == ConnectionState.SEARCHING
    assert [session.failed() for _ in range(6)] == [5,10,20,40,60,60]
    session.connected()
    assert session.state == ConnectionState.CONNECTED
    assert session.retry_seconds == 5
    session.failed('not authorized')
    assert session.state == ConnectionState.UNAUTHORIZED
    session.disconnect()
    assert session.paused
    session.start()
    assert not session.paused


def test_getprop_missing_and_malformed():
    info = parse_getprop('[ro.product.model]: [Google TV]\n[ro.build.version.sdk]: [33]\nbroken property\n[ro.product.manufacturer]: [Vendor]')
    assert info['model'] == 'Google TV'
    assert info['api_level'] == '33'
    assert info['android_version'] == ''
    assert all(v == '' for v in parse_getprop('junk').values())


@pytest.mark.parametrize('package', ['com.example.tv', 'org.vendor_1.App'])
def test_valid_packages(package):
    assert valid_package(package)


@pytest.mark.parametrize('package', ['com.foo;reboot', 'com.foo bar', '../tv', '-evil', 'com..foo', 'com.foo\n', ''])
def test_invalid_packages(package):
    assert not valid_package(package)


def test_package_parser_ignores_junk_duplicates():
    assert parse_packages('package:com.foo.tv\npackage:com.foo.tv\npackage:com.bar.tv;reboot\ngarbage') == ['com.foo.tv']


def test_text_control_characters_and_shell_metacharacters():
    assert escape_android_text('a\nb\tc\r') == 'a%sb%sc%s'
    with pytest.raises(ValueError):
        escape_android_text('a\x00b')
    for char in '&|;<>*()\'"`$\\':
        assert '\\' + char in escape_android_text(char)
    assert escape_android_text('') == ''


@pytest.mark.parametrize('extension', ['.apks','.xapk','.apkm','.txt'])
def test_split_containers_explicitly_rejected(tmp_path, extension):
    path = tmp_path / ('bundle' + extension)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('../../outside.apk', b'bad')
    with pytest.raises(ValueError):
        validate_apk(path)
    assert not (tmp_path.parent / 'outside.apk').exists()


def test_apk_archive_validation(tmp_path):
    path = tmp_path / 'app.apk'
    path.write_bytes(b'bad')
    with pytest.raises(ValueError):
        validate_apk(path)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('no-manifest', b'bad')
    with pytest.raises(ValueError):
        validate_apk(path)
    with zipfile.ZipFile(path, 'w') as archive:
        archive.writestr('AndroidManifest.xml', b'manifest')
    validate_apk(path)


def test_update_failure_is_graceful(monkeypatch):
    def offline(*args):
        raise OSError('offline')
    monkeypatch.setattr(updates, 'read_url', offline)
    assert updates.check_update()[0] is False
    assert updates.check_platform_update()[0] is False


@pytest.mark.parametrize('tag, message', [('v1.3.1','Update available'),('v1.3.0','current'),('bad','Could not check')])
def test_update_versions(monkeypatch, tag, message):
    monkeypatch.setattr(updates, 'read_url', lambda url: json.dumps({'tag_name':tag}).encode())
    assert message in updates.check_update()[1]


def test_platform_revision(monkeypatch):
    monkeypatch.setattr(updates, 'read_url', lambda url: b'<repository><remotePackage path="platform-tools"><revision><major>36</major><minor>0</minor><micro>2</micro></revision></remotePackage></repository>')
    assert updates.check_platform_update() == (True,'Latest official Platform Tools: 36.0.2')


def test_switch_profile_ignores_stale_results(monkeypatch):
    first, second = new_profile('One','192.168.1.2',5555,False), new_profile('Two','192.168.1.3',4444,False)
    remote = window([first,second])
    remote.controller.serial = '192.168.1.2:5555'
    monkeypatch.setattr(remote.controller, 'execute', lambda *args: True)
    previous = remote.controller.generation
    remote.profile_selector.setCurrentIndex(1)
    assert remote.ip_edit.text() == second['ip']
    remote._handle_result(AdbResult('connect',True,'connected',0,previous))
    assert not remote.connected
    assert remote.settings['selected_profile'] == second['id']
    remote.quitting=True
    remote.close()


def test_ui_disappearing_tv_never_selects_another(monkeypatch):
    remote = window([new_profile('One','192.168.1.2',5555,False)])
    attempts=[]
    monkeypatch.setattr(remote,'connect_device',lambda: attempts.append(remote.ip_edit.text()))
    remote._handle_discovery(AdbResult('discover_connect',True,'other _adb-tls-connect._tcp 192.168.1.3:4444'),True)
    assert attempts == ['192.168.1.2']
    remote.quitting=True
    remote.close()


def test_heartbeat_reconnect_and_pause(monkeypatch):
    remote = window([new_profile('One','192.168.1.2')])
    remote.connected=True
    remote._handle_result(AdbResult('heartbeat',False,'offline'))
    assert not remote.connected
    assert remote.reconnect_timer.isActive()
    monkeypatch.setattr(remote.controller, 'disconnect_device', lambda: True)
    remote.disconnect_device()
    assert remote.session.paused
    assert not remote.reconnect_timer.isActive()
    scans=[]
    monkeypatch.setattr(remote.controller,'discover_devices',scans.append)
    remote._reconnect()
    assert scans == []
    remote.quitting=True
    remote.close()


def test_hold_repeat_stops_on_release():
    app=QApplication.instance() or QApplication([])
    parent=QPushButton('Up')
    sent=[]
    repeat=HoldRepeat(parent,lambda: sent.append(1))
    parent.setDown(True)
    repeat.start()
    assert len(sent)==1
    QTest.qWait(390)
    assert len(sent)>=2
    repeat.stop()
    count=len(sent)
    QTest.qWait(150)
    assert len(sent)==count
    repeat.start()
    repeat.stop()
    assert len(sent)==count+1


def test_advanced_compact_and_settings():
    remote=window()
    remote.more_button.setChecked(True)
    assert not remote.advanced.isHidden()
    remote.set_compact(True)
    assert remote.advanced.isHidden()
    assert remote.profile_bar.isHidden()
    assert remote.settings['compact_default']
    remote.set_compact(False)
    assert not remote.advanced.isHidden()
    dialog=SettingsDialog(remote)
    assert dialog.findChild(__import__('PySide6.QtWidgets',fromlist=['QTabWidget']).QTabWidget).count()==6
    remote.quitting=True
    remote.close()


def test_first_run_help_policy(monkeypatch):
    remote=window([new_profile('TV','192.168.1.2',5555,False)])
    monkeypatch.setattr(AdbController,'available',property(lambda self:True))
    calls=[]
    monkeypatch.setattr(remote,'open_help',lambda: calls.append(1))
    remote.settings['setup_completed']=True
    remote._startup_help()
    assert calls==[]
    remote.settings['show_setup_help']=True
    remote._startup_help()
    assert calls==[1]
    remote.quitting=True
    remote.close()


def test_no_untargeted_remote_commands():
    controller=AdbController()
    with pytest.raises(ValueError):
        controller.target_args(['shell','getprop'])
    assert controller.disconnect_device() is False
    assert controller.key('up') is False


def test_controller_suppresses_overlapping_discovery_and_bounds_keys(tmp_path, monkeypatch):
    adb=tmp_path/'adb.exe'
    adb.write_bytes(b'mock')
    controller=AdbController(str(adb))
    pending=[]
    monkeypatch.setattr(controller.pool, 'start', pending.append)
    monkeypatch.setattr(controller.command_pool, 'start', pending.append)
    assert controller.discover_devices('discover')
    assert not controller.discover_devices('discover_connect')
    controller.serial='192.168.1.2:5555'
    assert controller.key('up')
    assert controller.key('up')
    assert controller.key('up')
    assert not controller.key('up')
    assert len(pending)==4
    assert pending[1].args[:2] == ['-s','192.168.1.2:5555']
    emitted=[]
    controller.result.connect(emitted.append)
    old_generation=controller.generation
    controller.invalidate()
    controller._on_finished(AdbResult('discover',True,'',0,old_generation))
    assert emitted == []


def test_multiple_unknown_devices_choose_explicitly(monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    remote=window()
    monkeypatch.setattr(QInputDialog,'getItem',lambda parent,title,label,items,*args: (items[1],True))
    remote._handle_discovery(AdbResult('discover',True,'one _adb-tls-connect._tcp 192.168.1.2:5555\ntwo _adb-tls-connect._tcp 192.168.1.3:4444'),False)
    assert remote.ip_edit.text()=='192.168.1.3'
    assert remote._profile()['service_name']=='two'
    remote.quitting=True
    remote.close()


def test_empty_named_profile_is_populated_without_duplicate():
    profile=new_profile('Living Room','',5555,False)
    remote=window([profile])
    remote._handle_discovery(AdbResult('discover',True,'tv _adb-tls-connect._tcp 192.168.1.2:43210'),False)
    assert len(remote.settings['profiles'])==1
    assert remote._profile()['name']=='Living Room'
    assert remote._profile()['port']==43210
    remote.quitting=True
    remote.close()


def test_text_focus_preserves_keyboard(monkeypatch):
    remote=window()
    sent=[]
    monkeypatch.setattr(remote,'send_key',sent.append)
    remote.show()
    remote.activateWindow()
    remote.more_button.setChecked(True)
    remote.advanced.setCurrentIndex(1)
    remote.text_edit.setFocus()
    QApplication.processEvents()
    QTest.keyClick(remote.text_edit,Qt.Key.Key_M)
    assert remote.text_edit.text()=='m'
    assert sent==[]
    remote.quitting=True
    remote.close()


def test_system_uninstall_blocked_without_confirmation(monkeypatch):
    remote=window([new_profile('TV','192.168.1.2',5555,False)])
    remote.connected=True
    remote.apps_cache[remote.settings['selected_profile']]={'packages':['com.vendor.system'],'system':['com.vendor.system']}
    remote._filter_apps()
    remote.app_list.setCurrentRow(0)
    calls=[]
    monkeypatch.setattr(remote.controller,'execute',lambda *args: calls.append(args))
    remote._uninstall_app()
    assert calls==[]
    assert 'cannot be removed' in remote.message.text()
    remote.quitting=True
    remote.close()


def test_config_invalid_geometry_cannot_crash():
    settings=migrate_settings({'window':{'width':None,'height':-1,'x':'bad'},'profiles':[{'id':'x','ip':'1.2.3.4','port':999999}]})
    assert settings['window']['width']==DEFAULTS['window']['width']
    assert settings['window']['height']==DEFAULTS['window']['height']
    assert settings['profiles'][0]['port']==5555


def test_platform_tools_revision_and_force_reinstall(tmp_path, monkeypatch):
    import chromecast_remote.platform_tools as platform
    archive=tmp_path/'tools.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for name in platform.REQUIRED_FILES:
            z.writestr('platform-tools/'+name,b'new runtime')
        z.writestr('platform-tools/source.properties','Pkg.Revision=36.0.2\n')
    root=tmp_path/'config'
    destination=root/'platform-tools'
    destination.mkdir(parents=True)
    for name in platform.REQUIRED_FILES:
        (destination/name).write_bytes(b'old')
    monkeypatch.setattr(platform,'PLATFORM_TOOLS_URL',archive.as_uri())
    monkeypatch.setattr(platform,'config_dir',lambda:root)
    monkeypatch.setattr(platform,'managed_adb_path',lambda:destination/'adb.exe')
    assert platform.install_managed_platform_tools()[0]
    assert (destination/'adb.exe').read_bytes()==b'old'
    assert platform.install_managed_platform_tools(force=True)[0]
    assert (destination/'adb.exe').read_bytes()==b'new runtime'
    assert platform.installed_platform_version(destination)=='36.0.2'
    assert len(json.loads((destination/'install-info.json').read_text())['download_sha256'])==64
    assert not list(root.glob('platform-tools-backup-*'))


def test_platform_tools_failed_download_retains_old_runtime(tmp_path, monkeypatch):
    import chromecast_remote.platform_tools as platform
    root=tmp_path/'config'
    destination=root/'platform-tools'
    destination.mkdir(parents=True)
    for name in platform.REQUIRED_FILES:
        (destination/name).write_bytes(b'old')
    monkeypatch.setattr(platform,'PLATFORM_TOOLS_URL',(tmp_path/'missing.zip').as_uri())
    monkeypatch.setattr(platform,'config_dir',lambda:root)
    monkeypatch.setattr(platform,'managed_adb_path',lambda:destination/'adb.exe')
    assert not platform.install_managed_platform_tools(force=True)[0]
    assert (destination/'adb.exe').read_bytes()==b'old'


def test_platform_tools_rejects_duplicate_required_member(tmp_path):
    import chromecast_remote.platform_tools as platform
    archive=tmp_path/'duplicate.zip'
    with zipfile.ZipFile(archive,'w') as z:
        for name in platform.REQUIRED_FILES:
            z.writestr('platform-tools/'+name,b'runtime')
        with pytest.warns(UserWarning):
            z.writestr('platform-tools/adb.exe',b'bad duplicate')
    with pytest.raises(ValueError,match='Duplicate'):
        platform.extract_platform_tools_archive(archive,tmp_path/'extract')


def test_uninstall_confirmation_and_targeting(monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    remote=window([new_profile('TV','192.168.1.2',5555,False)])
    remote.connected=True
    remote.controller.serial='192.168.1.2:5555'
    remote.apps_cache[remote.settings['selected_profile']]={'packages':['com.example.tv'],'system':[]}
    remote._filter_apps()
    remote.app_list.setCurrentRow(0)
    calls=[]
    monkeypatch.setattr(remote.controller,'execute',lambda *args: calls.append(args))
    monkeypatch.setattr(QMessageBox,'warning',lambda *args: QMessageBox.StandardButton.No)
    remote._uninstall_app()
    assert calls==[]
    monkeypatch.setattr(QMessageBox,'warning',lambda *args: QMessageBox.StandardButton.Yes)
    remote._uninstall_app()
    assert calls[0][0]==['-s','192.168.1.2:5555','uninstall','com.example.tv']
    remote.quitting=True
    remote.close()


def test_pairing_another_tv_preserves_old_profile(monkeypatch):
    profile=new_profile('Living','192.168.1.2',5555,False)
    remote=window([profile])
    attempts=[]
    monkeypatch.setattr(remote,'connect_with_discovery',lambda:attempts.append(remote.ip_edit.text()))
    remote._adopt_paired_device('192.168.1.3')
    assert len(remote.settings['profiles'])==2
    assert remote.settings['profiles'][0]['ip']=='192.168.1.2'
    assert remote._profile()['ip']=='192.168.1.3'
    assert attempts==['192.168.1.3']
    remote.quitting=True
    remote.close()


def test_invalid_apk_is_rejected_in_worker_without_subprocess(tmp_path,monkeypatch):
    from chromecast_remote.adb import AdbTask
    path=tmp_path/'bad.apk'
    path.write_bytes(b'not apk')
    task=AdbTask('adb',['-s','192.168.1.2:5555','install','-r',str(path)],'install:bad.apk',180)
    calls=[]
    monkeypatch.setattr('chromecast_remote.adb.run_adb',lambda *args:calls.append(args))
    results=[]
    task.signals.finished.connect(results.append)
    task.run()
    assert calls==[]
    assert not results[0].ok
    assert 'Invalid APK' in results[0].output


def test_launch_supports_tv_and_mobile_categories_without_random_events(monkeypatch):
    controller=AdbController()
    controller.serial='192.168.1.2:5555'
    calls=[]
    monkeypatch.setattr(controller,'execute',lambda *args:calls.append(args) or True)
    assert controller.launch_package('com.example.tv')
    args=calls[0][0]
    assert args[:2]==['-s','192.168.1.2:5555']
    assert 'android.intent.category.LEANBACK_LAUNCHER' in args
    assert 'android.intent.category.LAUNCHER' in args
    assert '--dbg-no-events' in args


def test_monkey_aborted_is_not_reported_as_launched():
    import sys
    from chromecast_remote.adb import run_adb
    result=run_adb(sys.executable,['-c',"print('No activities found to run, monkey aborted')"],'launch:com.example.tv')
    assert not result.ok
