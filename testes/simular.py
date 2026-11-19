"""Roda o robô com respostas falsas das lojas, para testar sem credenciais.
    python testes/simular.py
Não grava nada em docs/: usa uma pasta temporária."""
import json, os, sys, tempfile, time, urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "robo"))
import robo  # noqa: E402

tmp = Path(tempfile.mkdtemp())
robo.SAIDA = tmp / "ofertas.json"
robo.NOVO_REFRESH_ML = tmp / "token"
os.environ.update(SHOPEE_APP_ID="123", SHOPEE_SECRET="abc", ML_CLIENT_ID="1", ML_CLIENT_SECRET="2",
                  ML_MATT_WORD="coolgirls", ML_MATT_TOOL="999")
cfg_txt = robo.CONFIG.read_text(encoding="utf-8").replace("shop_id = 0", "shop_id = 777", 1)
robo.CONFIG = tmp / "config.toml"
robo.CONFIG.write_text(cfg_txt, encoding="utf-8")
robo.CUPONS = tmp / "cupons.toml"
robo.CUPONS.write_text("""
[[cupom]]
loja = "Shopee"
codigo = "glow15"
titulo = "15% OFF em skincare"
regra = "Acima de R$ 79"
link = "https://s.shopee.com.br/cupom"
validade = "2099-12-31"

[[cupom]]
loja = "Sephora"
codigo = "VELHO"
titulo = "Cupom vencido"
link = "https://sephora.com.br"
validade = "2020-01-01"

[[cupom]]
loja = "Mercado Livre"
titulo = "Frete grátis em beleza"
link = "https://meli.la/abc"
destaque = true

[[cupom]]
loja = "Shopee"
titulo = "Exemplo"
link = "https://shopee.com.br"
exemplo = true
""", encoding="utf-8")

chamadas = []
PRECO = {"x": 59.9}


def falso(method, url, *, headers=None, data=None, **k):
    chamadas.append(url)
    if "shopee" in url:
        assert headers["Authorization"].startswith("SHA256 Credential=123, Timestamp=")
        q = json.loads(data)["query"]
        if "shopId:777" in q:
            nodes = [{"itemId": 1, "productName": "Anua Heartleaf 77% Toner 250ml", "priceMin": "89.90", "priceDiscountRate": 15,
                      "imageUrl": "https://img/1.jpg", "offerLink": "https://s.shopee.com.br/aff1", "shopId": 777, "shopName": "K-Glow Store",
                      "shopType": [], "ratingStar": "4.9", "sales": 1200}]
        else:
            nodes = [
                {"itemId": 2, "productName": "Sérum Vitamina C 30ml", "priceMin": str(PRECO["x"]), "priceDiscountRate": 40, "imageUrl": "https://img/2.jpg",
                 "offerLink": "https://s.shopee.com.br/aff2", "shopId": 5, "shopName": "Marca Oficial", "shopType": [1], "ratingStar": "4.8", "sales": 300},
                {"itemId": 3, "productName": "Batom genérico", "priceMin": "9.90", "priceDiscountRate": 50, "imageUrl": "",
                 "offerLink": "https://s.shopee.com.br/aff3", "shopId": 6, "shopName": "Loja X", "shopType": [], "ratingStar": "4.9", "sales": 10},
                {"itemId": 4, "productName": "Perfume contratipo 100ml", "priceMin": "49.90", "priceDiscountRate": 60, "imageUrl": "",
                 "offerLink": "https://s.shopee.com.br/aff4", "shopId": 5, "shopName": "Marca Oficial", "shopType": [1], "ratingStar": "4.8", "sales": 10},
            ]
        return {"data": {"productOfferV2": {"nodes": nodes, "pageInfo": {"hasNextPage": False}}}}
    if url.endswith("/oauth/token"):
        return {"access_token": "TOKEN"}
    if "/sites/MLB/search" in url:
        assert headers["Authorization"] == "Bearer TOKEN"
        return {"results": [
            {"id": "MLB1", "title": "O Boticário Elysée Kit Presente (2 itens)", "price": 320.31, "original_price": 514.70,
             "permalink": "https://produto.mercadolivre.com.br/MLB-1-elysee", "thumbnail": "http://http2.mlstatic.com/D_1-I.jpg",
             "official_store_id": 10, "installments": {"quantity": 7, "amount": 50.84, "rate": 0}, "shipping": {"logistic_type": "fulfillment"}},
            {"id": "MLB2", "title": "Shampoo sem desconto", "price": 30.0, "original_price": None, "permalink": "https://p/2", "thumbnail": ""},
        ]}
    raise AssertionError(url)


robo.http = falso
robo.time.sleep = lambda s: None

robo.main()
d = json.loads(robo.SAIDA.read_text())
ids = [o["id"] for o in d["ofertas"]]
cps = d["cupons"]
assert [c["loja"] for c in cps] == ["Mercado Livre", "Shopee"], cps   # destaque primeiro; vencido e exemplo fora
assert cps[1]["codigo"] == "GLOW15" and "Código: *GLOW15*" in cps[1]["msg"] and "Válido até 31/12" in cps[1]["msg"]
assert "Resgate aqui" in cps[0]["msg"]
print("ofertas:", ids)
assert set(ids) == {"shp-2", "shp-1", "ml-MLB1"}, ids          # batom barato, contratipo e sem desconto ficam fora
ml = next(o for o in d["ofertas"] if o["id"] == "ml-MLB1")
assert "matt_word=coolgirls" in ml["link"] and "matt_tool=999" in ml["link"], ml["link"]
assert ml["img"].startswith("https://") and ml["img"].endswith("-O.jpg")
assert ml["cat"] == "Kits e presentes" and "7x R$ 50,84 sem juros" in ml["msg"]
fav = next(o for o in d["ofertas"] if o["id"] == "shp-1")
assert fav["fav"] and fav["cat"] == "Skincare" and abs(fav["de"] - 105.76) < 0.01
print(next(o for o in d["ofertas"] if o["id"] == "shp-2")["msg"])

# segunda rodada: preço baixa → marca "baixou"; desde é preservado nos outros
desde_ml = ml["desde"]
robo.AGORA += 1200
PRECO["x"] = 49.9
robo.main()
d2 = {o["id"]: o for o in json.loads(robo.SAIDA.read_text())["ofertas"]}
assert d2["shp-2"]["baixou"] and "BAIXOU" in d2["shp-2"]["msg"]
assert d2["ml-MLB1"]["desde"] == desde_ml and not d2["ml-MLB1"]["baixou"]

# terceira rodada 30h depois sem a Shopee responder: ofertas da Shopee ficam (fonte fora do ar), ML expira
robo.AGORA += 30 * 3600
os.environ.pop("SHOPEE_APP_ID")
def ml_vazio(method, url, **k):
    return {"access_token": "TOKEN"} if url.endswith("/oauth/token") else {"results": []}
robo.http = ml_vazio
robo.main()
d3 = {o["id"] for o in json.loads(robo.SAIDA.read_text())["ofertas"]}
assert d3 == {"shp-1", "shp-2"}, d3
print("\nTODOS OS TESTES PASSARAM ✓")

# ───── Amazon (Creators API) com respostas falsas ─────
os.environ.update(AMAZON_CREDENTIAL_ID="cid", AMAZON_CREDENTIAL_SECRET="sec", AMAZON_VERSION="3.1", AMAZON_TAG="coolgirls-20")
pedidos = []
def amz_falso(method, url, *, headers=None, data=None, **k):
    if url == "https://api.amazon.com/auth/o2/token":
        corpo = json.loads(data)
        assert corpo["scope"] == "creatorsapi::default" and corpo["client_id"] == "cid"
        return {"access_token": "AMZTOKEN"}
    assert url == robo.AMZ_API and headers["x-marketplace"] == "www.amazon.com.br" and headers["Authorization"] == "Bearer AMZTOKEN"
    corpo = json.loads(data); pedidos.append(corpo)
    if "minSavingPercent" in corpo and len(pedidos) == 1:
        raise RuntimeError("HTTP 400 em searchItems: filtro desconhecido")
    return {"searchResult": {"items": [{
        "asin": "B0TESTE", "detailPageURL": "https://www.amazon.com.br/dp/B0TESTE?tag=outra-20&linkCode=ogi",
        "itemInfo": {"title": {"displayValue": "Sérum Facial Niacinamida 30ml"}},
        "images": {"primary": {"large": {"url": "https://m.media-amazon.com/images/I/x.jpg"}}},
        "offersV2": {"listings": [{"price": {"money": {"amount": 59.9}, "savings": {"percentage": 40},
                                             "savingBasis": {"money": {"amount": 99.9}}}}]}}]}}
robo.http = amz_falso
cfg = robo.tomllib.loads(robo.CONFIG.read_text(encoding="utf-8"))
cfg["amazon"]["ligado"] = True
res = robo.amazon_buscar(cfg)
assert res and res[0]["id"] == "amz-B0TESTE" and res[0]["off"] == 40 and res[0]["de"] == 99.9
assert "tag=coolgirls-20" in res[0]["link"] and "outra-20" not in res[0]["link"], res[0]["link"]
assert "minSavingPercent" not in pedidos[-1]   # caiu pro modo sem filtro depois do 400
print("AMAZON OK ✓")

# ───── Cupons automáticos da Shopee ─────
os.environ.update(SHOPEE_APP_ID="123", SHOPEE_SECRET="abc")
agora = robo.AGORA
def cup_falso(method, url, *, headers=None, data=None, **k):
    q = json.loads(data)["query"]
    if "generateShortLink" in q:
        assert "cupom-de-desconto" in q
        return {"data": {"generateShortLink": {"shortLink": "https://s.shopee.com.br/CUPONS1"}}}
    if "shopeeOfferV2" in q:
        return {"data": {"shopeeOfferV2": {"nodes": [
            {"offerName": "Cupons de Natal Shopee", "offerLink": "https://s.shopee.com.br/NATAL", "periodEndTime": agora + 5 * 86400},
            {"offerName": "Eletrônicos em oferta", "offerLink": "https://s.shopee.com.br/ELET", "periodEndTime": agora + 5 * 86400},
            {"offerName": "Campanha velha de cupom", "offerLink": "https://s.shopee.com.br/OLD", "periodEndTime": agora - 10},
            {"offerName": "Skincare Week", "offerLink": "https://s.shopee.com.br/SKIN", "periodEndTime": 0}]}}}
    raise AssertionError(q)
robo.http = cup_falso
fixos = {}
cps = robo.shopee_cupons({"aviso_afiliada": "#publi"}, fixos)
nomes = [c["titulo"] for c in cps]
assert nomes[0] == "Cupons do dia na Shopee" and cps[0]["link"] == "https://s.shopee.com.br/CUPONS1", nomes
assert "Cupons de Natal Shopee" in nomes and "Skincare Week" in nomes, nomes
assert "Campanha velha de cupom" not in nomes   # vencida sai
assert "Eletrônicos em oferta" not in nomes      # fora de beleza sai
assert fixos["cupons_shopee"]["url"].endswith("CUPONS1")
assert "Resgate aqui: https://s.shopee.com.br/CUPONS1" in cps[0]["msg"]
# segunda vez não gera o link de novo (usa o guardado)
def sem_link(method, url, *, data=None, **k):
    q = json.loads(data)["query"]; assert "generateShortLink" not in q
    return {"data": {"shopeeOfferV2": {"nodes": []}}}
robo.http = sem_link
assert robo.shopee_cupons({"aviso_afiliada": "#publi"}, fixos)[0]["id"] == "cp-shopee-central"
print("CUPONS SHOPEE OK ✓")
