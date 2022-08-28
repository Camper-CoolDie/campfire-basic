from typing import Union, Tuple
from threading import Thread
from contextlib import asynccontextmanager
import json
import asyncio
from .firebase import firebase, notifications
from .request import Request, _send_request
from .tools import file

credentials_path = file.path("firebase/credentials.json")

async def send(request: Union[Tuple[Request], Request, str], body: dict = {}, data_output: tuple = ()) -> dict:
    """
    Send request(s) asynchronously.
    """
    
    if isinstance(request, tuple):
        tasks = []
        for req in request:
            task = asyncio.create_task(_send_request(req))
            tasks.append(task)
        return await asyncio.gather(*tasks)
    else:
        return await _send_request(request, body, data_output)

def login(email: str, password: str) -> firebase.FirebaseLogin:
    """
    Login in Campfire using Firebase.
    """
    
    fb_login = firebase.FirebaseLogin(email, password)
    fb_login.start()
    return fb_login

def token() -> notifications.GCM:
    """
    Get FCM token for receiving notifications.
    """
    
    notifications._optional_dependencies_check()
    credentials = file.read(credentials_path)
    credentials_exists = False
    gcm = None
    if credentials != None:
        try:
            credentials = json.loads(credentials)
            gcm = notifications.GCM()
            gcm._token = credentials["token"]
            gcm._android_id = credentials["androidId"]
            gcm._security_token = credentials["securityToken"]
            gcm._keys = credentials["keys"]
            gcm = notifications._register(gcm)
            gcm.exists = True
            credentials_exists = True
        except Exception:
            pass
    if not credentials_exists:
        gcm = notifications._gcm_register()
        gcm = notifications._register(gcm)
        file.write(credentials_path, bytes(json.dumps({
            "token": gcm._token,
            "androidId": gcm._android_id,
            "securityToken": gcm._security_token,
            "keys": gcm._keys
        }, separators = (",", ":")), "ascii"))
        gcm.exists = False
    
    return gcm

async def listen(gcm: notifications.GCM, func):
    """
    Listen for notifications.
    """
    
    notifications._optional_dependencies_check()
    await notifications._login(gcm)
    asyncio.create_task(notifications._listen(gcm, func, None))

@asynccontextmanager
async def wait(gcm: notifications.GCM, json_filter: dict = {}, timeout: float = None) -> dict:
    """
    Wait for notification.
    """
    
    try:
        notifications._optional_dependencies_check()
        await notifications._login(gcm)
        if timeout:
            try:
                yield await asyncio.wait_for(notifications._listen(gcm, None, json_filter), timeout)
            except asyncio.TimeoutError:
                await notifications._aclose(gcm._writer)
                raise
        else:
            yield await notifications._listen(gcm, None, json_filter)
    finally:
        pass