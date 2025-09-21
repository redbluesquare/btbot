# btBot

## Setup

Create an .env file with the following variables

```
ENV_TYPE=test/prod

IDENTIFIER=<<username>>
PASSWORD=<<user-password>>
ENCRYPTED_PASSWORD=null
API_KEY=<<enter_the_api_key>>
BASE_URL=https://demo-api.ig.com/gateway/deal/
```

```bash
sudo journalctl -u ohlc-stream.service -f
```

```bash
sudo systemctl status ohlc-stream.service

```