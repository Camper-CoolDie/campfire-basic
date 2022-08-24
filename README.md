This module includes several basic functions for sending
and receiving data from Campfire server. It can also
receive push notifications.

# Examples

## Requesting

```py
import campfire

print(campfire.send("RProjectVersionGet"))
# {'ABParams': {}, 'version': '1.290'}
```

This code getting current version of Campfire.

## Log in

A lot of requests will raise exception if user is not
logged in.

```py
import campfire

req = {
    "fandomId": 10,
    "languageId": 1
}

print(campfire.send("RFandomsGet", req))
# ApiRequestException: Error occurred while processing request ("ERROR_UNAUTHORIZED")

log = campfire.login("email", "password")

print(log.send("RFandomsGet", req))
# {'fandom': {'subscribesCount': 1105, 'imageId'...
```

## Receiving notifications

You can receive all notifications Campfire server sending
to you.

```py
import campfire

log = campfire.login("email", "password")

# Generating FCM token
ntoken = campfire.ntoken()

# Sending token to Campfire server
campfire.send("RAccountsAddNotificationsToken", {"token": ntoken.fcm})

# Listening for notifications
def notifi(n):
    print(notifi)
campfire.nlisten(ntoken, notifi)
```