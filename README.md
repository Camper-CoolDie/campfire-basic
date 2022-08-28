This module includes several basic functions for asynchronously
sending and receiving data from Campfire server. It can also
receive push notifications.

[![campfire-basic PyPI](https://img.shields.io/pypi/v/campfire-basic.svg)](https://pypi.org/project/campfire-basic) 

# Installation

Using `pip` command:

```
pip install campfire-basic
```

Clone this repository using `git` command:

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

Code above gets current version of Campfire.

## Log in

A lot of requests will raise exception if user is not
logged in.

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

You can receive all notifications Campfire server sending
to you.

```py
import campfire

log = campfire.login("email", "password")

# Generate FCM token
token = campfire.token()

async def main():
    # Send token to Campfire server if it is not added
    if not token.exists():
        await log.send("RAccountsAddNotificationsToken", {"token": ntoken.fcm})
    
    # Listen to notifications
    def notifi(n):
        print(notifi)
    await campfire.listen(token, notifi)
    
    print("It works asynchronously!")

asyncio.run(main())
```

Or, wait for notification:

```py
import campfire
import asyncio

log = campfire.login("email", "password")
token = campfire.token()

async def main():
    if not token.exists():
        await log.send("RAccountsAddNotificationsToken", {"token": token})
    
    # Wait for notification
    async with campfire.wait(token) as n:
        print(n)
    
    # With filter (wait for subscriber)
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