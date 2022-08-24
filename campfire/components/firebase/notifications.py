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
        raise ImportError("4 dependencies are requried for \"notifications\" module: %s" % ", ".join(("cryptography", "oscrypto", "http_ece", "protobuf")))

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
_sock = None

class GCM:
    __slots__ = ("exists", "fcm", "_token", "_android_id", "_security_token", "_keys")

def encode32(x: int) -> bytes:
    res = bytearray([])
    while x != 0:
        b = (x & 0x7f)
        x >>= 7
        if x != 0:
            b |= 0x80
        res.append(b)
    return bytes(res)

def read32() -> int:
    res = 0
    shift = 0
    while True:
        b, = struct.unpack("B", _recv(1))
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
    
    resp = urlopen(Request(url = CHECKIN_URL, headers = {"Content-Type": "application/x-protobuf"}, data = payload.SerializeToString()), timeout = 5)
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
    ))
    rdata = resp.read().decode("utf8")
    resp.close()
    
    if "Error" in rdata:
        raise ApiException("Error occured while authorization")
    token = rdata.split("=")[1]
    gcm = GCM()
    gcm._token = token
    gcm._android_id = chk["androidId"]
    gcm._security_token = chk["securityToken"]
    return gcm

def _register(gcm: GCM) -> Union[GCM, None]:
    global _sock
    if _sock == None:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        context = ssl.create_default_context()
        _sock = context.wrap_socket(s, server_hostname=MT_HOST)
        _sock.connect((MT_HOST, 5228))
    
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
        resp = urlopen(Request(url = FCM_SUBSCRIBE, data = data), timeout = 5)
    except HTTPError:
        return None
    rdata = json.loads(resp.read())
    resp.close()
    
    gcm.fcm = rdata["token"]
    return gcm

def _login(gcm: GCM):
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
    _send_packet(p)
    resp = _recv_packet(True)

def _listen(gcm: GCM, func):
    while True:
        try:
            p = _recv_packet()
            if type(p) == DataMessageStanza:
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
                func(json.loads(decrypted))
            elif type(p) == HeartbeatPing:
                req = HeartbeatAck()
                req.stream_id = p.stream_id + 1
                req.last_stream_id_received = p.stream_id
                req.status = p.status
                _send_packet(req)
        except ConnectionResetError:
            return

def _send_packet(packet):
    header = bytearray((MCS_VERSION, MCS_PACKETS.index(type(packet))))
    payload = packet.SerializeToString()
    buf = bytes(header) + encode32(len(payload)) + payload
    
    buf_length = len(buf)
    sent = 0
    while sent < buf_length:
        _sock.settimeout(Config.Client.timeout)
        sdata_length = _sock.send(buf[sent:sent + Config.Client.data_chunk_size] if buf_length - sent > Config.Client.data_chunk_size else buf)
        if not sdata_length:
            if sent > 0:
                break
            raise ConnectionError("Connection closed while sending packet")
        sent += sdata_length

def _recv_packet(ver: bool = False) -> Union[bytes, None]:
    if ver:
        version, tag = struct.unpack("BB", _recv(2))
        if version < MCS_VERSION:
            raise ValueError("Unsupported protocol version: " + version)
    else:
        tag, = struct.unpack("B", _recv(1))
    size = read32()
    if size >= 0:
        buf = _recv(size)
        p = MCS_PACKETS[tag]
        payload = p()
        payload.ParseFromString(buf)
        return payload
    return None

def _recv(size: bytes) -> bytes:
    data = bytes()
    received = 0
    while received < size:
        _sock.settimeout(None)
        rdata = _sock.recv(Config.Client.data_chunk_size if size - received > Config.Client.data_chunk_size else size - received)
        received += len(rdata)
        data += rdata
    return data