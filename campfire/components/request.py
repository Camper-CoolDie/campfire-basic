from typing import Union
import socket
import ssl
import asyncio
import json
from threading import Thread
from .exceptions import ApiRequestException
from .config import Config
from .tools import file

class Request:
    __slots__ = ("name", "body", "data_output")
    
    def __init__(self, name: str, body: dict = {}, data_output: tuple = ()):
        self.name = name
        self.body = body
        self.data_output = data_output
    
    def _parse(self, token: str = None) -> dict:
        body = self.body
        
        extra = bytes()
        if self.data_output:
            body["dataOutput"] = []
            for media in self.data_output:
                body["dataOutput"].append(len(media))
                extra += media
        
        body["J_REQUEST_NAME"] = self.name
        if token:
            body["J_API_LOGIN_TOKEN"] = token
        
        return body, extra

class RequestMedia(Request):
    def _parse(self, token: str = None) -> dict:
        return super()._parse(None)

async def _send_request(request: Union[Request, str], body: dict = {}, data_output: tuple = (), token: str = None, *, server: int = 0) -> Union[dict, bytes]:
    if not isinstance(request, Request):
        if (server == 0):
            request = Request(request, body, data_output)
        elif (server == 1):
            request = RequestMedia(request, body, data_output)
        else:
            raise NameError("Unknown server: " + str(server))
    elif isinstance(request, RequestMedia):
        server = 1
    else:
        server = 0
    
    body, extra = request._parse(token)
    data = await _create_request(bytes(json.dumps(body, separators = (",", ":")), "utf8") + extra, server)
    
    if data[0] == "{":
        data = json.loads(data)
        if data["J_STATUS"] == "J_STATUS_ERROR":
            raise ApiRequestException(data["J_RESPONSE"]["code"])
        return data["J_RESPONSE"]
    else:
        return data

async def _create_request(body: bytes, server) -> bytes:
    if Config.Client.https:
        context = ssl.SSLContext(ssl.PROTOCOL_TLSv1_2)
        context.load_verify_locations(file.path("cert.pem"))
        if (server == 0):
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                Config.Server.ip,
                Config.Server.port_https,
                server_hostname = Config.Server.hostname,
                family = socket.AF_INET,
                ssl = context
            ), timeout = Config.Client.timeout)
        else:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                Config.ServerMedia.ip,
                Config.ServerMedia.port_https,
                server_hostname = Config.ServerMedia.hostname,
                family = socket.AF_INET,
                ssl = context
            ), timeout = Config.Client.timeout)
    else:
        if (server == 0):
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                Config.Server.ip,
                Config.Server.port_http,
                server_hostname = Config.Server.hostname,
                family = socket.AF_INET
            ), timeout = Config.Client.timeout)
        else:
            reader, writer = await asyncio.wait_for(asyncio.open_connection(
                Config.ServerMedia.ip,
                Config.ServerMedia.port_http,
                server_hostname = Config.ServerMedia.hostname,
                family = socket.AF_INET
            ), timeout = Config.Client.timeout)
    
    await _send(writer, len(body).to_bytes(4, "big") + body)
    
    data_length = int.from_bytes(await _recv(reader, 4), "big")
    data = await _recv(reader, data_length)
    
    await _aclose(writer)
    
    return data

async def _send(writer: asyncio.StreamWriter, data: bytes):
    return await asyncio.wait_for(_asend(writer, data), timeout = Config.Client.timeout)

async def _recv(reader: asyncio.StreamReader, size: bytes) -> bytes:
    return await asyncio.wait_for(_arecv(reader, size), timeout = Config.Client.timeout)

async def _asend(writer: asyncio.StreamWriter, data: bytes):
    writer.write(data)
    await writer.drain()
    return

async def _arecv(reader: asyncio.StreamReader, size: bytes) -> bytes:
    data = bytes()
    received = 0
    while received < size:
        rdata = await reader.read(Config.Client.data_chunk_size if size - received > Config.Client.data_chunk_size else size - received)
        if not rdata:
            if received > 0:
                break
            raise ConnectionError("No data received")
        received += len(rdata)
        data += rdata
    return data

async def _aclose(stream: asyncio.StreamWriter):
    stream.close()
    await stream.wait_closed()