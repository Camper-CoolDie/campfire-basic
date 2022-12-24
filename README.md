This module includes several basic functions for asynchronously
*communicating* with Campfire server. It can also
receive push notifications. To learn what requests you can send, visit https://github.com/ZeonXX/CampfireApi/tree/master/src/main/java/com/dzen/campfire/api/requests

[![campfire-basic PyPI](https://img.shields.io/pypi/v/campfire-basic.svg)](https://pypi.org/project/campfire-basic) 

# Installation

Using `pip` command:

```
pip install campfire-basic
```

Or, clone this repository using `git` command:

```
git clone https://github.com/Camper-CoolDie/campfire-basic
```

# Examples

## Requesting

```py
import campfire
import asyncio

async def main():
    print(await campfire.send("RProjectVersionGet"))
    # {'ABParams': {}, 'version': '1.290'}

asyncio.run(main())
```

The code above gets the current version of Campfire server and shows it.

## Log in

Certain types of requests will raise an exception if you're not
logged in. To proceed with those requests, you need to authorize first.
In this module, this can be done via calling the `login()` function,
and to send the request as an authorized user, call the `send()` method of
a returned object.

```py
import campfire
import asyncio

req = {
    "fandomId": 10,
    "languageId": 1
}

async def main():
    print(await campfire.send("RFandomsGet", req))
    # ApiRequestException: Error occurred while processing request ("ERROR_UNAUTHORIZED")
    
    log = campfire.login("email", "password")
    
    print(await log.send("RFandomsGet", req))
    # {'fandom': {'subscribesCount': 1105, 'imageId'...

asyncio.run(main())
```

## Receiving notifications

You can receive every notification Campfire server sends
to you, or only a certain type.

```py
import campfire
import asyncio

log = campfire.login("email", "password")

# Generate GCM token, which contains a FCM token we need
token = campfire.token()

async def main():
    # Send the token to Campfire server
    await log.send("RAccountsAddNotificationsToken", {"token": token.fcm})
    
    # Listen to notifications
    def notifi(n):
        print(notifi)

    # The "final point" where our program will continue listening to notifications
    # until we press Ctrl + C or some unexpected exception happens;
    # if you want to wait for a single notification, see the next example
    await campfire.listen(token, notifi)

asyncio.run(main())
```

Or, wait for a notification:

```py
import campfire
import asyncio

log = campfire.login("email", "password")
token = campfire.token()

async def main():
    await log.send("RAccountsAddNotificationsToken", {"token": token.fcm})
    
    # Wait for a notification
    async with campfire.wait(token) as n:
        print(n)
    
    # With filter (wait for a subscriber)
    async with campfire.wait(token, {"J_N_TYPE": 4}) as n:
        print(n["account"]["J_NAME"])
    
    # Timeout!
    try:
        async with campfire.wait(token, {}, 15.0) as n:
            print(n)
    except asyncio.TimeoutError:
        print("Time is out")

asyncio.run(main())
```

## Getting a resource

You can also request Campfire to get a picture or another sort of a
resource. This can be done almost the same way we request the main
server. To request Media server, if you prefer requesting using
Request class, just replace it with "RequestMedia". Or add a "server = 1"
argument to the `send()` function. Returning value will be of type `bytes`
if `RResourcesGet` request sent.

```py
import campfire
import asyncio

async def main():
    res = await campfire.send("RResourceGet", {"resourceId": 1}, server = 1)
    print(len(res))
    # The length of res will be printed

asyncio.run(main())
```