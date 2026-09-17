import base64
import ssl
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.ssl_ import create_urllib3_context

CLIENT_ID = "080842f43f7a4ec3843f2d81bc2f3b85"
CLIENT_SECRET = "54905bf39cf24e0f89bc8fddd2e67f1a"

class TLS12Adapter(HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.options |= ssl.OP_NO_TLSv1_3
        ctx.minimum_version = ssl.TLSVersion.TLSv1_2
        ctx.maximum_version = ssl.TLSVersion.TLSv1_2
        kwargs['ssl_context'] = ctx
        return super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount("https://", TLS12Adapter())


def get_spotify_token():
    auth = f"{CLIENT_ID}:{CLIENT_SECRET}"
    b64 = base64.b64encode(auth.encode()).decode()

    r = session.post(
    "https://accounts.spotify.com/api/token",
    headers={"Authorization": f"Basic {b64}"},
    data={"grant_type": "client_credentials"}
)

    return r.json()

def get_spotify_track(track_id, token):
    r = session.get(
    f"https://api.spotify.com/v1/tracks/{track_id}",
    headers={"Authorization": f"Bearer {token}"}
    )
    print(r.status_code, r.text)

    return r.json()

token = get_spotify_token()
data = get_spotify_track("4uLU6hMCjMI75M1A2tKUQC", token['access_token'])
print(data)