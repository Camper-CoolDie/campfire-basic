class ApiException(Exception):
    pass

class ApiRequestException(ApiException):
    def __init__(self, errorCode: str):
        super().__init__("Error occurred while processing request (\"%s\")" % errorCode)

class ApiLoginException(ApiException):
    def __init__(self):
        super().__init__("Could not login")