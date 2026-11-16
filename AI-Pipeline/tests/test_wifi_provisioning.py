"""Generated boot-line tests; no network password, device or audio is read."""
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('wifi_provision',Path(__file__).resolve().parents[2]/'scripts/configure_wifi_capture.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_brownout_is_power_error_not_pairing_timeout():
    with pytest.raises(RuntimeError,match='BROWNOUT'):
        module.check_boot_diagnostic('E BOD: Brownout detector was triggered',1)


def test_normal_boot_then_auth_is_not_restart_failure():
    count=0
    for line in ('CONFIG_SAVED_REBOOTING','CONFIG_PRESENT','WIFI_IP=192.0.2.5','GATEWAY_AUTHENTICATED'):
        count=module.check_boot_diagnostic(line,count)
    assert count==1


def test_repeated_boots_and_capture_failures_are_explicit():
    count=module.check_boot_diagnostic('CONFIG_PRESENT',0)
    count=module.check_boot_diagnostic('CONFIG_PRESENT',count)
    with pytest.raises(RuntimeError,match='repeatedly restarts'):
        module.check_boot_diagnostic('CONFIG_PRESENT',count)
    for line in ('I2S_INIT_FAILED','CAPTURE_TASK_FAILED'):
        with pytest.raises(RuntimeError,match='initialization failed'):
            module.check_boot_diagnostic(line,0)


def test_wifi_and_hotspot_payloads_preserve_profile_roles_and_priority():
    for kind,primary in [('wifi',True),('hotspot',False)]:
        value=module.build_payload('Arbitrary network', 'fixture-password', 'gateway.local', 'fixture-token-12345',kind,primary)
        assert value.endswith(b'\n')
        config=json.loads(value)
        assert config['kind']==kind and config['primary'] is primary
        assert 'reset_profiles' not in config


@pytest.mark.parametrize('host',['ws://host','bad host','bad\thost','host:8082','host/path','host@name'])
def test_host_validation_rejects_url_control_and_authority_characters(host):
    with pytest.raises(ValueError):
        module.build_payload('Fixture','fixture-pass',host,'fixture-token-1234')


def test_utf8_byte_limits_and_unsupported_cellular_modem_role_rejected():
    with pytest.raises(ValueError):
        module.build_payload('😀'*9,'fixture-pass','192.0.2.1','fixture-token-1234')
    with pytest.raises(ValueError):
        module.build_payload('Fixture','fixture-pass','192.0.2.1','fixture-token-1234','cellular-modem')
