"""Incremental serial v4 decoder and continuous 16-to-8 kHz PCM conversion."""
import binascii
import struct
import numpy as np
from scipy.signal import firwin, lfilter

MAGIC = bytes.fromhex('a55ac34c')


class SerialFrames:
    def __init__(self):
        self.buffer=bytearray()
        self.previous=None
        self.locked=False

    def feed(self,data):
        self.buffer.extend(data)
        rows=[]
        while len(self.buffer)>=24:
            if self.buffer[:4]!=MAGIC:
                if self.locked:
                    raise ValueError('Serial framing lost')
                index=self.buffer.find(MAGIC)
                if index<0:
                    del self.buffer[:-3]
                    break
                del self.buffer[:index]
                if len(self.buffer)<24:
                    break
            version,flags,count,seq,t_us,ecg,event,crc=struct.unpack_from('<BBHIIHIH',self.buffer,4)
            if version!=4 or flags & ~7 or count!=1024 or ecg>64:
                raise ValueError('Unexpected serial v4 format')
            length=24+2*count+6*ecg
            if len(self.buffer)<length:
                break
            frame=bytes(self.buffer[:length])
            actual=binascii.crc_hqx(frame[4:22],0xffff)
            actual=binascii.crc_hqx(frame[24:],actual)
            if actual!=crc:
                raise ValueError('Serial CRC mismatch')
            if flags & 1:
                raise ValueError('Firmware reported short serial write')
            if self.previous is not None and seq!=(self.previous+1)&0xffffffff:
                raise ValueError('Missing/out-of-order serial block')
            self.previous=seq
            self.locked=True
            del self.buffer[:length]
            samples=np.frombuffer(frame,dtype='<i2',offset=24,count=count).reshape(-1,2).copy()
            rows.append((samples,ecg,flags))
        if len(self.buffer)>65536:
            raise ValueError('Serial buffer overflow')
        return rows


class AudioConverter:
    """Causal FIR with state across every chunk, followed by decimation by two."""
    def __init__(self):
        self.coefficients=firwin(127,3600,fs=16000,window=('kaiser',8.6))
        self.state=np.zeros(126)
        self.pending=np.empty(0,dtype=np.int16)

    def push(self,samples):
        if samples.ndim!=1 or len(samples)%2:
            raise ValueError('Even mono sample block required')
        filtered,self.state=lfilter(self.coefficients,[1.],samples.astype(float),zi=self.state)
        converted=np.clip(np.rint(filtered[::2]),-32768,32767).astype('<i2')
        self.pending=np.concatenate([self.pending,converted])
        blocks=[]
        while len(self.pending)>=400:
            blocks.append(self.pending[:400].copy())
            self.pending=self.pending[400:]
        return blocks


def network_frame(samples,stream,seq):
    if samples.shape!=(400,) or samples.dtype!=np.int16:
        raise ValueError('Expected 400 signed PCM16 samples')
    return struct.pack('<4sBBHIIQI HBB',b'AURI',2,0,32,stream,seq&0xffffffff,
                       seq*400,8000,400,1,1)+samples.astype('<i2').tobytes()
