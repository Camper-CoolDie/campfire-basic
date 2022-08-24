from threading import Thread
import json
from .firebase import firebase, notifications
from .request import _send_request
from .tools import file

credentials_path = file.path("firebase/credentials.json")

def send(request_name: str, body: dict = {}, data_output: tuple = ()) -> dict:
    """
    Send a request.
    """
    
    return _send_request(request_name, body, data_output)

def login(email: str, password: str) -> firebase.FirebaseLogin:
    """
    Login in Campfire using Firebase.
    """
    
    fb_login = firebase.FirebaseLogin(email, password)
    fb_login.start()
    return fb_login

def ntoken() -> notifications.GCM:
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

def nlisten(gcm: notifications.GCM, func):
    """
    Listen for notifications.
    """
    
    notifications._optional_dependencies_check()
    notifications._login(gcm)
    thr = Thread(target = notifications._listen, args = (gcm, func))
    thr.start()