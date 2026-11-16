"""Physical USB serial v4 source for the existing WebSocket device gateway."""
import argparse
import json
import queue
import secrets
import sys
import threading
import time
from pathlib import Path

import numpy as np
import serial
import websocket

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'AI-Pipeline/src'))
from auriscore.serial_bridge import SerialFrames,AudioConverter,network_frame


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',required=True)
    parser.add_argument('--gateway',default='ws://127.0.0.1:8082/device')
    parser.add_argument('--token-file',type=Path,default=Path(__file__).resolve().parents[1]/'.runtime/hardware/pairing-token.txt')
    args=parser.parse_args()
    token=args.token_file.read_text().strip()
    if len(token)<16:
        raise ValueError('Pairing token required')
    sock=websocket.create_connection(args.gateway,timeout=3,enable_multithread=True)
    serial_port=serial.Serial()
    serial_port.port=args.port
    serial_port.baudrate=921600
    serial_port.timeout=.02
    serial_port.dtr=False
    serial_port.rts=False
    commands=queue.Queue(maxsize=32)
    try:
        serial_port.open()
        sock.send(json.dumps(dict(type='authenticate',token=token)))
        if json.loads(sock.recv()).get('type')!='authenticated':
            raise ValueError('Gateway authentication failed')
        stream=secrets.randbelow(0xfffffffe)+1
        sock.send(json.dumps(dict(type='device_hello',protocol=2,device='ESP32S3-USB-COM3',
            fw='serial-v4-usb-bridge-1',source='hardware',streamId=stream,samplingRate=8000,channels=1,encoding='pcm16le')))
        def receive():
            try:
                while True:
                    raw=sock.recv()
                    if not raw:
                        raise RuntimeError('Gateway disconnected')
                    commands.put_nowait(json.loads(raw))
            except Exception as exc:
                try:
                    commands.put_nowait(exc)
                except queue.Full:
                    sock.close()
        threading.Thread(target=receive,daemon=True).start()
        active=False
        frames=SerialFrames()
        converter=AudioConverter()
        seq=0
        raw_samples=clipped=ecg_count=0
        report_at=time.monotonic()
        print(f'Physical serial bridge ready: {args.port}, two-channel 16kHz -> organ mono 8kHz',flush=True)
        while True:
            while not commands.empty():
                message=commands.get_nowait()
                if isinstance(message,Exception):
                    raise message
                if message.get('type')!='command':
                    continue
                command=message.get('command')
                if command not in ('start_stream','stop_stream'):
                    raise ValueError('Unsupported hardware command')
                active=False
                serial_port.reset_input_buffer()
                frames=SerialFrames()
                converter=AudioConverter()
                seq=raw_samples=clipped=ecg_count=0
                sock.send(json.dumps(dict(type='command_ack',id=message['id'],command=command,ok=True)))
                active=command=='start_stream'
                print(command,flush=True)
            data=serial_port.read(8192)
            if not active:
                continue
            for samples,ecg,flags in frames.feed(data):
                organ=samples[:,0]
                raw_samples+=len(organ)
                clipped+=int(np.count_nonzero((organ==-32768)|(organ==32767)))
                ecg_count+=ecg
                if flags & 2:
                    print('ECG ring overflow reported; ECG timing reference incomplete',flush=True)
                for block in converter.push(organ):
                    sock.send_binary(network_frame(block,stream,seq))
                    seq+=1
            now=time.monotonic()
            if now-report_at>=5:
                print(f'audio={seq*.05:.1f}s raw-organ-clipping={100*clipped/max(raw_samples,1):.2f}% ECG-samples={ecg_count}',flush=True)
                report_at=now
    except KeyboardInterrupt:
        return False
    except websocket.WebSocketConnectionClosedException:
        print('Gateway session closed; reconnecting with a new stream identity.', flush=True)
        return True
    except Exception as exc:
        if isinstance(exc, RuntimeError) and str(exc) == 'Gateway disconnected':
            print('Controller disconnected; reconnecting with a new stream identity.', flush=True)
            return True
        try:
            sock.send(json.dumps(dict(type='source_error',reason=str(exc))))
        except Exception:
            pass
        raise
    finally:
        serial_port.close()
        sock.close()


if __name__=='__main__':
    while main():
        time.sleep(1)
