from typing import Union
import json
import base64
import os
import struct

from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode
import socket
import ssl
import asyncio


_notifications_dependencies = (
    "cryptography>=3.1",
    "oscrypto",
    "http_ece",
    "protobuf<=3.20"
)
try:
    from .proto.mcs_pb2 import *
    from .proto.android_checkin_pb2 import *
    from .proto.checkin_pb2 import *
    from google.protobuf.json_format import MessageToDict
    from oscrypto.asymmetric import generate_pair
    import cryptography.hazmat.primitives.serialization as serialization
    from cryptography.hazmat.backends import default_backend
    import http_ece
    _optional_dependencies = True
except ImportError:
    _optional_dependencies = False

from .firebase import FirebaseLogin
from ..config import Config
from ..tools import file
from ..exceptions import ApiException

def _optional_dependencies_check():
    if not _optional_dependencies:
        raise ImportError("4 dependencies are requried for \"notifications\" module.\n\nSimply run this pip command to install:\npip install --upgrade " + " ".join(_notifications_dependencies))

def urlsafe(data: bytes) -> str:
    return str(base64.urlsafe_b64encode(data).replace(b"=", b"").replace(b"\n", b""), "ascii")

REGISTER_URL = "https://android.clients.google.com/c2dm/register3"
CHECKIN_URL = "https://android.clients.google.com/checkin"
FCM_SUBSCRIBE = "https://fcm.googleapis.com/fcm/connect/subscribe"
FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send"

SERVER_KEY = urlsafe(
    b"\x04\x33\x94\xf7\xdf\xa1\xeb\xb1\xdc\x03\xa2\x5e\x15\x71\xdb\x48\xd3"
    + b"\x2e\xed\xed\xb2\x34\xdb\xb7\x47\x3a\x0c\x8f\xc4\xcc\xe1\x6f\x3c"
    + b"\x8c\x84\xdf\xab\xb6\x66\x3e\xf2\x0c\xd4\x8b\xfe\xe3\xf9\x76\x2f"
    + b"\x14\x1c\x63\x08\x6a\x6f\x2d\xb1\x1a\x95\xb0\xce\x37\xc0\x9c\x6e"
)

MCS_VERSION = 41
if _optional_dependencies:
    MCS_PACKETS = (
        HeartbeatPing,
        HeartbeatAck,
        LoginRequest,
        LoginResponse,
        Close,
        "MessageStanza",
        "PresenceStanza",
        IqStanza,
        DataMessageStanza,
        "BatchPresenceStanza",
        StreamErrorStanza,
        "HttpRequest",
        "HttpResponse",
        "BindAccountRequest",
        "BindAccountResponse",
        "TalkMetadata"
    )

MT_HOST = "mtalk.google.com"

def dict_walk(inner: dict, pre: list = None):
    pre = pre[:] if pre else []
    if isinstance(inner, dict):
        for key, value in inner.items():
            if isinstance(value, dict):
                for ret in dict_walk(value, pre + [key]):
                    yield ret
            else:
                yield pre + [key, value]
    else:
        yield pre + [inner]

class GCM:
    __slots__ = ("exists", "fcm", "_token", "_android_id", "_security_token", "_keys", "_reader", "_writer")

def encode32(x: int) -> bytes:
    res = bytearray([])
    while x != 0:
        b = (x & 0x7f)
        x >>= 7
        if x != 0:
            b |= 0x80
        res.append(b)
    return bytes(res)

def read32(sock: socket.socket) -> int:
    res = 0
    shift = 0
    while True:
        b, = struct.unpack("B", _recv(sock, 1))
        res |= (b & 0x7f) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return res

async def aread32(reader: asyncio.StreamReader) -> int:
    res = 0
    shift = 0
    while True:
        b, = struct.unpack("B", await _arecv(reader, 1))
        res |= (b & 0x7f) << shift
        if (b & 0x80) == 0:
            break
        shift += 7
    return res

def app_data_by_key(p, key) -> Union[str, None]:
    for x in p.app_data:
        if x.key == key:
            return x.value
    return None

def _gcm_checkin() -> dict:
    chrome = ChromeBuildProto()
    chrome.platform = 3
    chrome.chrome_version = "63.0.3234.0"
    chrome.channel = 1
    
    checkin = AndroidCheckinProto()
    checkin.type = 3
    checkin.chrome_build.CopyFrom(chrome)
    
    payload = AndroidCheckinRequest()
    payload.user_serial_number = 0
    payload.checkin.CopyFrom(checkin)
    payload.version = 3
    
    resp = urlopen(Request(url = CHECKIN_URL, headers = {"Content-Type": "application/x-protobuf"}, data = payload.SerializeToString()), timeout = Config.Client.timeout)
    p = AndroidCheckinResponse()
    p.ParseFromString(resp.read())
    resp.close()
    
    return MessageToDict(p)

def _gcm_register() -> GCM:
    chk = _gcm_checkin()
    
    data = urlencode({
        "app": "org.chromium.linux",
        "X-subtype": Config.Firebase.app_id,
        "device": chk["androidId"],
        "sender": SERVER_KEY
    })
    auth = "AidLogin %s:%s" % (chk["androidId"], chk["securityToken"])
    
    resp = urlopen(Request(
        url = REGISTER_URL,
        headers = {"Authorization": auth},
        data = bytes(data, "utf8")
    ), timeout = Config.Client.timeout)
    rdata = resp.read().decode("utf8")
    resp.close()
    
    if "Error=" in rdata:
        raise ApiException("Error occured while authorization (\"%s\")" % rdata[6:])
    token = rdata.split("=")[1]
    gcm = GCM()
    gcm._token = token
    gcm._android_id = chk["androidId"]
    gcm._security_token = chk["securityToken"]
    return gcm

def _register(gcm: GCM) -> Union[GCM, None]:
    if not hasattr(gcm, "_keys"):
        public_key, private_key = generate_pair("ec", curve = "secp256r1")
        keys = {
            "public": urlsafe(public_key.asn1.dump()[26:]),
            "private": urlsafe(private_key.asn1.dump()),
            "secret": urlsafe(os.urandom(16))
        }
        gcm._keys = keys
    
    data = bytes(urlencode({
        "authorized_entity": Config.Firebase.sender_id,
        "endpoint": FCM_ENDPOINT + "/" + gcm._token,
        "encryption_key": gcm._keys["public"],
        "encryption_auth": gcm._keys["secret"]
    }), "ascii")
    
    try:
        resp = urlopen(Request(url = FCM_SUBSCRIBE, data = data), timeout = Config.Client.timeout)
    except HTTPError:
        return None
    rdata = json.loads(resp.read())
    resp.close()
    
    gcm.fcm = rdata["token"]
    return gcm

async def _login(gcm: GCM):
    p = LoginRequest()
    p.adaptive_heartbeat = False
    p.auth_service = 2
    p.auth_token = gcm._security_token
    p.id = "chrome-63.0.3234.0"
    p.domain = "mcs.android.com"
    p.device_id = "android-%x" % int(gcm._android_id)
    p.network_type = 2
    p.resource = gcm._android_id
    p.user = gcm._android_id
    p.use_rmq2 = True
    p.setting.add(name = "new_vc", value = "1")
    p.received_persistent_id.extend(())
    
    # never do this:
    # s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    # context = ssl.create_default_context()
    # sock = context.wrap_socket(s, server_hostname=MT_HOST)
    # sock.connect((MT_HOST, 5228))
    # reader, writer = await asyncio.open_connection(sock = sock)
    
    context = ssl.create_default_context()
    reader, writer = await asyncio.open_connection(
        MT_HOST, 5228,
        server_hostname = MT_HOST,
        family = socket.AF_INET,
        ssl = context
    )
    gcm._reader = reader
    gcm._writer = writer
    
    await _asend_packet(writer, p)
    resp = await _arecv_packet(reader, True)

async def _listen(gcm: GCM, func = None, json_filter = None):
    random_code = None
    while True:
        try:
            p = await _arecv_packet(gcm._reader)
            if type(p) == DataMessageStanza:
                if len(p.raw_data) == 0: continue
                crypto_key = bytes(app_data_by_key(p, "crypto-key")[3:], "ascii")
                salt = bytes(app_data_by_key(p, "encryption")[5:], "ascii")
                crypto_key = base64.urlsafe_b64decode(crypto_key)
                salt = base64.urlsafe_b64decode(salt)
                
                der_data = bytes(gcm._keys["private"], "ascii")
                der_data = base64.urlsafe_b64decode(der_data + b"========")
                secret = bytes(gcm._keys["secret"], "ascii")
                secret = base64.urlsafe_b64decode(secret + b"========")
                
                private_key = serialization.load_der_private_key(der_data, password = None, backend = default_backend())
                decrypted = http_ece.decrypt(
                    p.raw_data,
                    salt = salt,
                    private_key = private_key,
                    dh = crypto_key,
                    version = "aesgcm",
                    auth_secret = secret
                ).decode("utf8")
                data = json.loads(json.loads(decrypted)["data"]["my_data"])
                if data["randomCode"] == random_code: continue
                random_code = data["randomCode"]
                
                if func:
                    await func(data)
                else:
                    if json_filter:
                        c = False
                        total = 0
                        confirms = 0
                        for x in dict_walk(json_filter):
                            total += 1
                            for y in dict_walk(data):
                                if x[:-1] == y[:-1]:
                                    if x[-1] != y[-1]:
                                        c = True
                                        break
                                    else:
                                        confirms += 1
                            if c: break
                        if confirms < total: c = True
                        if c: continue
                    _aclose(gcm._writer)
                    return data
            elif type(p) == HeartbeatPing:
                req = HeartbeatAck()
                req.stream_id = p.stream_id + 1
                req.last_stream_id_received = p.stream_id
                req.status = p.status
                await _asend_packet(gcm._writer, req)
            elif p == None or type(p) == Close:
                _aclose(gcm._writer)
                gcm = _login(gcm)
        except ConnectionResetError:
            gcm = _login(gcm)

async def _asend_packet(writer: asyncio.StreamWriter, packet):
    header = bytearray((MCS_VERSION, MCS_PACKETS.index(type(packet))))
    payload = packet.SerializeToString()
    buf = bytes(header) + encode32(len(payload)) + payload
    
    writer.write(buf)
    await writer.drain()
    return

async def _arecv_packet(reader: asyncio.StreamReader, ver: bool = False) -> Union[bytes, None]:
    if ver:
        version, tag = struct.unpack("BB", await _arecv(reader, 2))
        if version < MCS_VERSION:
            raise ValueError("Unsupported protocol version: " + version)
    else:
        tag, = struct.unpack("B", await _arecv(reader, 1))
    size = await aread32(reader)
    if size >= 0:
        buf = await _arecv(reader, size)
        p = MCS_PACKETS[tag]
        payload = p()
        payload.ParseFromString(buf)
        return payload
    return None

async def _arecv(reader: asyncio.StreamReader, size: bytes) -> bytes:
    data = bytes()
    received = 0
    while received < size:
        rdata = await reader.read(Config.Client.data_chunk_size if size - received > Config.Client.data_chunk_size else size - received)
        received += len(rdata)
        data += rdata
    return data

def _aclose(stream: asyncio.StreamWriter):
    stream.close()