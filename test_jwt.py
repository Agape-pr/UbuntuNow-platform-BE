import jwt
from datetime import datetime, timedelta

secret = "wrlSG46CDWC-m8ge75TbYw0abA7syy7p4Aj-ybk6CJsFktEthb31re0ILyLY2qmrG-E"
payload = {
    "token_type": "access",
    "exp": datetime.utcnow() + timedelta(minutes=60),
    "jti": "1234567890",
    "user_id": 1,
    "role": "buyer"
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(token)
