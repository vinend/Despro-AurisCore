"""Local interactive Wi-Fi provisioning; credentials never enter chat or source."""
import argparse
import getpass
import json
from pathlib import Path
import time

import serial


def build_payload(ssid: str, password: str, host: str, token: str,
                  kind: str = 'wifi', primary: bool = False) -> bytes:
    """One profile upsert; other stored networks are preserved."""
    if not 1 <= len(ssid.encode()) <= 32 or len(password.encode()) > 63 or not 16 <= len(token) <= 128:
        raise ValueError('Invalid provisioning input')
    if not host or len(host) > 253 or any(c in host for c in '/:?@# \t\r\n'):
        raise ValueError('Enter gateway IPv4 address or hostname only')
    if kind not in ('wifi', 'hotspot'):
        raise ValueError('Expected wifi or hotspot profile')
    value=json.dumps(dict(ssid=ssid,password=password,host=host,token=token,kind=kind,primary=primary),ensure_ascii=False).encode()+b'\n'
    if len(value)>768:
        raise ValueError('Configuration too long')
    return value


def check_boot_diagnostic(line: str, boots: int) -> int:
    """Detect concrete boot failures without exposing arbitrary serial payloads."""
    if 'Brownout detector was triggered' in line:
        raise RuntimeError('ESP32 BROWNOUT: supply voltage dropped. Check USB cable, port and board power; Wi-Fi password is already stored.')
    if line in ('I2S_INIT_FAILED', 'CAPTURE_TASK_FAILED', 'CAPTURE_QUEUE_FAILED'):
        raise RuntimeError('ESP32 capture initialization failed: ' + line)
    if line == 'CONFIG_PRESENT':
        boots += 1
        if boots >= 3:
            raise RuntimeError('ESP32 repeatedly restarts before Wi-Fi authentication. Inspect boot/power diagnostics; do not repeatedly re-enter credentials.')
    return boots


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', default='COM3')
    parser.add_argument('--ssid', help='Preselected network name; not a password')
    parser.add_argument('--host', help='Preselected local gateway host')
    parser.add_argument('--kind', choices=['wifi','hotspot'], default='wifi')
    parser.add_argument('--primary', action='store_true', help='Try first; preserve the fallback profiles')
    parser.add_argument('--save-only', action='store_true', help='Confirm persistence only, not radio/audio success')
    parser.add_argument('--token-file', type=Path, default=Path(__file__).resolve().parents[1]/'.runtime/hardware/pairing-token.txt')
    args = parser.parse_args()
    print('Use a 2.4 GHz Wi-Fi network or phone hotspot. Laptop/server must be reachable from it.')
    ssid = args.ssid or input('Wi-Fi / hotspot name (SSID): ').strip()
    password = getpass.getpass('Wi-Fi password (hidden): ')
    host = args.host or input('Local gateway laptop IP (no ws://, port fixed 8082): ').strip()
    token = args.token_file.read_text().strip()
    payload=build_payload(ssid,password,host,token,args.kind,args.primary)
    print(f'Upsert {args.kind} profile; other saved networks are preserved.',flush=True)
    port = serial.Serial()
    port.port=args.port; port.baudrate=115200; port.timeout=.5
    port.dtr=False; port.rts=False
    try:
        port.open(); port.reset_input_buffer(); port.write(b'STATUS\n'); port.flush()
        identified=False
        deadline=time.monotonic()+3
        while time.monotonic()<deadline:
            if port.readline().strip()==b'AURISCORE_WIFI_CAPTURE_V1':
                identified=True; break
        if not identified:
            raise RuntimeError('Wi-Fi firmware not identified; credentials were NOT sent')
        port.write(payload); port.flush()
        deadline=time.monotonic()+45
        boots=0
        while time.monotonic()<deadline:
            line=port.readline().decode('utf-8',errors='replace').strip()
            if args.save_only and line=='CONFIG_SAVED_REBOOTING':
                print('Profile saved; radio/audio acceptance is still pending.',flush=True)
                return
            boots=check_boot_diagnostic(line,boots)
            # Output only known diagnostic messages, never echoed credentials.
            if line.startswith(('CONFIG_', 'WIFI_', 'GATEWAY_', 'PROVISION_', 'I2S_', 'CAPTURE_', 'PROFILE_', 'RADIO_')):
                print(line,flush=True)
            if line=='GATEWAY_AUTHENTICATED':
                print('Wi-Fi device registered. Open the website and pair; audio readiness still requires real PCM.')
                return
        raise TimeoutError('No gateway authentication within 45s. Check 2.4GHz, password, IP, firewall and duplicate publisher.')
    finally:
        port.close()


if __name__=='__main__':
    main()
