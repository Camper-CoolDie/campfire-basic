from threading import Thread, Event
from hashlib import sha512
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import time
import json
from ..config import Config
from ..exceptions import ApiLoginException
from ..request import _send_request

FB_HOST = "identitytoolkit.googleapis.com"

class FirebaseLogin(Thread):
    email: str = ""
    
    _id_token: str = ""
    _token_changed_event = Event()
    _error: bool = False
    _password: str = ""
    _refresh_token: str = ""
    
    def __init__(self, email: str, password: str):
        super().__init__(daemon = True)
        self.email = email
        self._password = sha512(bytes(password, "utf8")).hexdigest()
    
    def run(self):
        while True:
            body = bytes('{"email":"%s","password":"%s","returnSecureToken":true}' % (self.email, self._password), "utf8")
            headers = {
                "Content-Type": "application/json",
                "Host": FB_HOST
            }
            
            try:
                resp = urlopen(Request(
                    url = "https://" + FB_HOST + "/v1/accounts:signInWithPassword?key=" + Config.Firebase.api_key,
                    headers = headers,
                    data = body
                ))
            except HTTPError as e:
                self._error = True
                self._token_changed_event.set()
                raise ApiLoginException
            
            rdata = json.loads(resp.read())
            resp.close()
            
            setn = self._id_token != None
            self._id_token = rdata["idToken"]
            self._refresh_token = rdata["refreshToken"]
            self.email = rdata["email"]
            if setn:
                self._token_changed_event.set()
            
            time.sleep(int(rdata["expiresIn"]))
    
    @property
    def token(self):
        if not self._id_token:
            self._token_changed_event.wait()
        if self._error:
            return ""
        
        return "Email2 - " + self._id_token
    
    def send(self, request_name: str, body: dict = {}, data_output: tuple = ()) -> dict:
        """
        Send a request.
        """
        
        return _send_request(request_name, body, data_output, self.token)