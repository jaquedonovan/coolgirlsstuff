"""Conecta o robô à sua conta do Mercado Livre (só precisa se o robô pedir).

Sem código: mostra o link de autorização.
Com código (o TG-... que aparece no site depois de autorizar): troca por um
refresh_token e deixa no arquivo .ml_refresh_token_novo, que o GitHub guarda
como Secret ML_REFRESH_TOKEN.
"""
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
cid = os.environ["ML_CLIENT_ID"]
sec = os.environ["ML_CLIENT_SECRET"]
redirect = os.environ["ML_REDIRECT_URI"]
codigo = (os.getenv("CODIGO") or "").strip()

if not codigo:
    url = "https://auth.mercadolivre.com.br/authorization?" + urllib.parse.urlencode(
        {"response_type": "code", "client_id": cid, "redirect_uri": redirect})
    print("\n1) Abra este link, entre na sua conta e autorize:\n\n   " + url)
    print("\n2) Você vai cair no seu site com um código TG-... em destaque.")
    print("3) Rode este workflow de novo colando esse código no campo 'codigo'.\n")
    sys.exit(0)

dados = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": cid, "client_secret": sec,
                                "code": codigo, "redirect_uri": redirect}).encode()
req = urllib.request.Request("https://api.mercadolibre.com/oauth/token", data=dados, method="POST",
                             headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=25) as r:
        resp = json.loads(r.read())
except urllib.error.HTTPError as e:
    print("O Mercado Livre recusou o código:", e.read().decode(errors="replace")[:300])
    print("Códigos valem só 10 minutos e uma vez. Gere outro e tente de novo.")
    sys.exit(1)

(RAIZ / ".ml_refresh_token_novo").write_text(resp["refresh_token"])
print("Pronto! Conta do Mercado Livre conectada.")
