import json
from .tools import file

_config = json.loads(file.read(file.path("../config.json")))

class Config:
    __slots__ = ()

    class Client:
        __slots__ = ()

        https: str = _config["client"]["https"]
        data_chunk_size: int = _config["client"]["dataChunkSize"]
        timeout: float = _config["client"]["timeout"]

    class Server:
        __slots__ = ()

        ip: str = _config["server"]["ip"]
        port_https: int = _config["server"]["portHttps"]
        port_http: int = _config["server"]["portHttp"]
        hostname: str = _config["server"]["hostname"]
    
    class Firebase:
        __slots__ = ()
        
        api_key: str = _config["firebase"]["apiKey"]
        project_id: str = _config["firebase"]["projectId"]
        sender_id: int = _config["firebase"]["senderId"]
        app_id: str = _config["firebase"]["appId"]