"""Serial framing and anti-alias conversion tests without hardware."""
import binascii
import struct
import numpy as np
import pytest
from scipy.signal import lfilter
from auriscore.serial_bridge import MAGIC,SerialFrames,AudioConverter,network_frame


def frame(seq=0,flags=0):
    audio=np.arange(1024,dtype='<i2').tobytes()
    prefix=struct.pack('<BBHIIHI',4,flags,1024,seq,32000,0,0)
    crc=binascii.crc_hqx(audio,binascii.crc_hqx(prefix,0xffff))
    return MAGIC+prefix+struct.pack('<H',crc)+audio


def test_incremental_serial_and_continuity():
    data=b'boot text'+frame()+frame(1)
    parser=SerialFrames()
    rows=[]
    for start in range(0,len(data),11):
        rows.extend(parser.feed(data[start:start+11]))
    assert len(rows)==2 and rows[0][0].shape==(512,2)
    np.testing.assert_array_equal(rows[0][0][:,0],np.arange(0,1024,2))
    with pytest.raises(ValueError,match='Missing'):
        parser.feed(frame(3))


def test_crc_and_loss_are_rejected():
    bad=bytearray(frame())
    bad[-1]^=1
    with pytest.raises(ValueError,match='CRC'):
        SerialFrames().feed(bad)
    with pytest.raises(ValueError,match='short serial'):
        SerialFrames().feed(frame(flags=1))


def test_resampling_state_and_binary_layout():
    converter=AudioConverter()
    x=np.rint(3000*np.sin(np.arange(512*20)*.13)).astype(np.int16)
    actual=np.concatenate([b for i in range(0,len(x),512) for b in converter.push(x[i:i+512])])
    reference=np.clip(np.rint(lfilter(converter.coefficients,[1.],x)[::2]),-32768,32767).astype(np.int16)
    np.testing.assert_array_equal(actual,reference[:len(actual)])
    packet=network_frame(actual[:400],23,4)
    assert len(packet)==832 and packet[:8]==b'AURI\x02\x00\x20\x00'
    assert struct.unpack_from('<Q',packet,16)[0]==1600
    np.testing.assert_array_equal(np.frombuffer(packet,dtype='<i2',offset=32),actual[:400])
