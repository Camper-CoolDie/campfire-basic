from typing import Union
import socket
import ssl
import json
from threading import Thread
from .exceptions import ApiRequestException
from .config import Config
from .tools import file

def _send_request(request_name: str, body: dict = {}, data_output: tuple = (), token: str = None) -> dict:
    extra = bytes()
    if data_output:
        body["dataOutput"] = []
        for media in data_output:
            body["dataOutput"].append(len(media))
            extra += media
    
    body["J_REQUEST_NAME"] = request_name
    if token:
        body["J_API_LOGIN_TOKEN"] = token
    
    data = json.loads(_create_request(bytes(json.dumps(body), "ascii") + extra))

    if data["J_STATUS"] == "J_STATUS_ERROR":
        raise ApiRequestException(data["J_RESPONSE"]["code"])
    
    return data["J_RESPONSE"]

def _create_request(body: bytes) -> bytes:
    if Config.Client.https:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_verify_locations(file.path("cert.pem"))
        sock = context.wrap_socket(s, server_hostname = Config.Server.hostname)
        link = (Config.Server.ip, Config.Server.port_https)
    else:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        link = (Config.Server.ip, Config.Server.port_http)

    sock.connect(link)
    _send(len(body).to_bytes(4, "big") + body, sock)

    data_length = int.from_bytes(_recv(4, sock), "big")
    data = _recv(data_length, sock)

    sock.close()
    
    return data

def _send(data: bytes, sock: Union[ssl.SSLSocket, socket.socket]):
    sent = 0
    data_length = len(data)
    while sent < data_length:
        sock.settimeout(Config.Client.timeout)
        sdata_length = sock.send(data[sent:sent + Config.Client.data_chunk_size] if data_length - sent > Config.Client.data_chunk_size else data)
        if not sdata_length:
            if sent > 0:
                break
            raise ConnectionError("No data sent")
        sent += sdata_length

def _recv(size: int, sock: Union[ssl.SSLSocket, socket.socket]) -> bytes:
    data = bytes()
    received = 0
    while received < size:
        sock.settimeout(Config.Client.timeout)
        rdata = sock.recv(Config.Client.data_chunk_size if size - received > Config.Client.data_chunk_size else size - received)
        if not rdata:
            if received > 0:
                break
            raise ConnectionError("No data received")
        received += len(rdata)
        data += rdata
    return data