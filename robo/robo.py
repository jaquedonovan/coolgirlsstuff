"""
COOL GIRLS STUFF · robô de ofertas
Busca promoções de beleza na Shopee e no Mercado Livre (Amazon quando liberar),
coloca o seu link de afiliada e atualiza docs/ofertas.json, que o site lê.

Roda sozinho no GitHub a cada 20 minutos. Para testar no computador:
    python robo/robo.py
Usa só a biblioteca padrão do Python (3.11+).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
import tomllib
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
CONFIG = RAIZ / "config.toml"
CUPONS = RAIZ / "cupons.toml"
SAIDA = RAIZ / "docs" / "ofertas.json"
NOVO_REFRESH_ML = RAIZ / ".ml_refresh_token_novo"

AGORA = int(time.time())


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


# ───────────────────────── HTTP ─────────────────────────
def http(method, url, *, headers=None, data=None, tentativas=3, timeout=25):
    body = None
    if data is not None:
        body = data if isinstance(data, bytes) else data.encode()
    ultimo = None
    for i in range(tentativas):
        req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
        req.add_header("User-Agent", "CoolGirlsStuffBot/1.0")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            txt = e.read().decode(errors="replace")[:300]
            ultimo = RuntimeError(f"HTTP {e.code} em {url.split('?')[0]}: {txt}")
            if e.code in (400, 401, 403, 404):
                break
        except Exception as e:  # rede instável: tenta de novo
            ultimo = e
        time.sleep(2 * (i + 1))
    raise ultimo


# ───────────────────────── utilidades ─────────────────────────
def sem_acento(s):
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


CATEGORIAS = [
    ("Kits e presentes", ["kit ", "kit-", "estojo", "presente", "combo"]),
    ("Perfumes", ["perfume", "eau de", "body splash", "colonia", "deo parfum", "edp", "edt"]),
    ("Cabelo", ["shampoo", "condicionador", "capilar", "cabelo", "leave-in", "leave in", "mascara de hidratacao", "finalizador", "secador", "chapinha", "babyliss"]),
    ("Unhas", ["esmalte", "unha", "gel uv", "cabine led", "removedor"]),
    ("Maquiagem", ["batom", "base ", "corretivo", "rimel", "mascara de cilios", "cilios", "sombra", "paleta", "blush", "iluminador", "delineador", "gloss", "lip", "po compacto", "primer", "pincel", "esponja", "maquiagem"]),
    ("Skincare", ["serum", "facial", "rosto", "protetor solar", "fps", "acido", "vitamina c", "niacinamida", "retinol", "hidratante", "tonico", "essence", "ampoule", "sabonete facial", "skincare", "cosrx", "anua", "skin1004", "beauty of joseon", "centella", "snail", "olheiras", "anti-idade", "antissinais"]),
    ("Corpo e banho", ["corporal", "corpo", "banho", "sabonete", "desodorante", "oleo", "esfoliante", "locao", "manteiga"]),
]


def categoria(titulo):
    t = sem_acento(titulo) + " "
    for nome, chaves in CATEGORIAS:
        if any(k in t for k in chaves):
            return nome
    return "Achadinhos"


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def brl(n):
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {s}"


# ───────────────────────── SHOPEE ─────────────────────────
SHOPEE_URL = "https://open-api.affiliate.shopee.com.br/graphql"
SHOPEE_CAMPOS = "itemId productName priceMin priceMax priceDiscountRate imageUrl offerLink productLink shopId shopName shopType ratingStar sales commissionRate"


def shopee_chamar(app_id, segredo, query):
    payload = json.dumps({"query": query}, separators=(",", ":"))
    ts = str(int(time.time()))
    assinatura = hashlib.sha256(f"{app_id}{ts}{payload}{segredo}".encode()).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"SHA256 Credential={app_id}, Timestamp={ts}, Signature={assinatura}",
    }
    r = http("POST", SHOPEE_URL, headers=headers, data=payload)
    if r.get("errors"):
        raise RuntimeError(f"Shopee respondeu erro: {r['errors'][0].get('message', r['errors'])}")
    return r["data"]


def shopee_descobrir_lojas(favs, conhecidos):
    """Acha o número (shop_id) das lojas favoritas a partir do usuário/nome."""
    app_id, segredo = os.getenv("SHOPEE_APP_ID"), os.getenv("SHOPEE_SECRET")
    for l in favs:
        if int(l.get("shop_id") or 0) > 0:
            continue
        chave = (l.get("usuario") or l.get("nome") or "").lower()
        if chave in conhecidos:
            l["shop_id"] = conhecidos[chave]
            continue
        if not app_id or not segredo:
            continue
        busca = l.get("busca") or l.get("nome") or ""
        alvo = sem_acento(busca).replace(" ", "")
        usuario = (l.get("usuario") or "").lower()
        achado = None
        try:  # 1ª tentativa: busca de lojas
            q = f"{{shopOfferV2(keyword:{json.dumps(busca, ensure_ascii=False)},limit:30){{nodes{{shopId shopName originalLink}}}}}}"
            for n in shopee_chamar(app_id, segredo, q)["shopOfferV2"]["nodes"] or []:
                link = (n.get("originalLink") or "").lower()
                if (usuario and usuario in link) or alvo in sem_acento(n.get("shopName") or "").replace(" ", ""):
                    achado = n["shopId"]
                    break
        except Exception as e:
            log(f"Shopee: busca de loja '{busca}' sem sucesso ({e}).")
        if not achado:  # 2ª tentativa: produtos com o nome da loja
            try:
                q = f"{{productOfferV2(keyword:{json.dumps(busca, ensure_ascii=False)},limit:50){{nodes{{shopId shopName}}}}}}"
                for n in shopee_chamar(app_id, segredo, q)["productOfferV2"]["nodes"] or []:
                    if alvo in sem_acento(n.get("shopName") or "").replace(" ", ""):
                        achado = n["shopId"]
                        break
            except Exception as e:
                log(f"Shopee: busca de produtos da loja '{busca}' sem sucesso ({e}).")
        if achado:
            l["shop_id"] = int(achado)
            conhecidos[chave] = int(achado)
            log(f"Shopee: loja favorita '{l.get('nome')}' encontrada (shop_id {achado}).")
        else:
            log(f"Shopee: não achei a loja favorita '{l.get('nome')}'. Coloque o shop_id dela no config.toml.")


def shopee_buscar(cfg, favs_ids):
    app_id, segredo = os.getenv("SHOPEE_APP_ID"), os.getenv("SHOPEE_SECRET")
    if not app_id or not segredo:
        log("Shopee: sem SHOPEE_APP_ID / SHOPEE_SECRET, pulando.")
        return None
    nodes = []
    pedidos = [("busca", b) for b in cfg["geral"]["buscas"]] + [("loja", s) for s in favs_ids]
    for tipo, alvo in pedidos:
        paginas = 3 if tipo == "loja" else 1
        for pag in range(1, paginas + 1):
            filtro = f'shopId:{int(alvo)}' if tipo == "loja" else f'keyword:{json.dumps(alvo, ensure_ascii=False)}'
            q = f"{{productOfferV2({filtro},sortType:2,page:{pag},limit:50){{nodes{{{SHOPEE_CAMPOS}}} pageInfo{{hasNextPage}}}}}}"
            try:
                d = shopee_chamar(app_id, segredo, q)["productOfferV2"]
            except Exception as e:
                log(f"Shopee ({tipo} {alvo}): {e}")
                break
            nodes += d.get("nodes") or []
            if not (d.get("pageInfo") or {}).get("hasNextPage"):
                break
            time.sleep(0.4)
    out = []
    for n in nodes:
        por = num(n.get("priceMin"))
        off = int(num(n.get("priceDiscountRate")) or 0)
        if not por or not n.get("offerLink"):
            continue
        de = round(por / (1 - off / 100), 2) if 0 < off < 95 else None
        tipos = n.get("shopType") or []
        out.append({
            "id": f"shp-{n['itemId']}",
            "loja": "shopee",
            "titulo": (n.get("productName") or "").strip(),
            "de": de, "por": por, "off": off,
            "img": n.get("imageUrl") or "",
            "link": n["offerLink"],
            "vendedor": n.get("shopName") or "",
            "shop_id": n.get("shopId"),
            "oficial": 1 in tipos,  # 1 = Shopee Mall (loja oficial)
            "nota": num(n.get("ratingStar")),
            "vendidos": int(num(n.get("sales")) or 0),
            "parc": "",
        })
    log(f"Shopee: {len(out)} produtos recebidos.")
    return out


# ───────────────────────── MERCADO LIVRE ─────────────────────────
ML_API = "https://api.mercadolibre.com"


def ml_token():
    cid, sec = os.getenv("ML_CLIENT_ID"), os.getenv("ML_CLIENT_SECRET")
    if not cid or not sec:
        return None
    form = {"grant_type": "client_credentials", "client_id": cid, "client_secret": sec}
    hdr = {"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    try:
        return http("POST", f"{ML_API}/oauth/token", headers=hdr, data=urllib.parse.urlencode(form), tentativas=1)["access_token"]
    except Exception as e:
        log(f"Mercado Livre: client_credentials não aceito ({e}); tentando refresh_token.")
    ref = os.getenv("ML_REFRESH_TOKEN")
    if not ref:
        return None
    form = {"grant_type": "refresh_token", "client_id": cid, "client_secret": sec, "refresh_token": ref}
    r = http("POST", f"{ML_API}/oauth/token", headers=hdr, data=urllib.parse.urlencode(form), tentativas=1)
    if r.get("refresh_token") and r["refresh_token"] != ref:
        NOVO_REFRESH_ML.write_text(r["refresh_token"])  # o GitHub guarda o novo token sozinho
    return r["access_token"]


def ml_link(permalink, word, tool):
    p = urllib.parse.urlsplit(permalink)
    qs = urllib.parse.parse_qsl(p.query)
    qs = [(k, v) for k, v in qs if k not in ("matt_word", "matt_tool")]
    qs += [("matt_word", word), ("matt_tool", tool)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(qs), ""))


def ml_buscar(cfg):
    word, tool = os.getenv("ML_MATT_WORD"), os.getenv("ML_MATT_TOOL")
    if not word or not tool:
        log("Mercado Livre: sem ML_MATT_WORD / ML_MATT_TOOL (seus códigos de afiliada), pulando.")
        return None
    try:
        tok = ml_token()
    except Exception as e:
        log(f"Mercado Livre: não consegui o token ({e}).")
        return None
    if not tok:
        log("Mercado Livre: sem ML_CLIENT_ID / ML_CLIENT_SECRET, pulando.")
        return None
    mc = cfg["mercado_livre"]
    out = []
    for termo in cfg["geral"]["buscas"]:
        params = {"q": termo, "category": mc.get("categoria", "MLB1246"), "limit": 50}
        url = f"{ML_API}/sites/MLB/search?{urllib.parse.urlencode(params)}"
        try:
            r = http("GET", url, headers={"Authorization": f"Bearer {tok}"})
        except Exception as e:
            log(f"Mercado Livre ('{termo}'): {e}")
            continue
        for it in r.get("results", []):
            por, de = num(it.get("price")), num(it.get("original_price"))
            if not por or not it.get("permalink"):
                continue
            off = round((de - por) / de * 100) if de and de > por else 0
            inst = it.get("installments") or {}
            parc = ""
            if inst.get("quantity") and inst.get("amount"):
                parc = f"{inst['quantity']}x {brl(inst['amount'])}" + (" sem juros" if not inst.get("rate") else "")
            ship = it.get("shipping") or {}
            if mc.get("so_lojas_oficiais") and not it.get("official_store_id"):
                continue
            if mc.get("so_full") and ship.get("logistic_type") != "fulfillment":
                continue
            img = (it.get("thumbnail") or "").replace("http://", "https://").replace("-I.jpg", "-O.jpg")
            out.append({
                "id": f"ml-{it['id']}",
                "loja": "ml",
                "titulo": (it.get("title") or "").strip(),
                "de": de if off else None, "por": por, "off": off,
                "img": img,
                "link": ml_link(it["permalink"], word, tool),
                "vendedor": (it.get("official_store_name") or ""),
                "oficial": bool(it.get("official_store_id")),
                "full": ship.get("logistic_type") == "fulfillment",
                "nota": None, "vendidos": 0,
                "parc": parc,
            })
        time.sleep(0.4)
    log(f"Mercado Livre: {len(out)} produtos recebidos.")
    return out


# ───────────────────────── AMAZON (Creators API) ─────────────────────────
AMZ_API = "https://creatorsapi.amazon/catalog/v1/searchItems"
AMZ_MARKET = "www.amazon.com.br"
AMZ_TOKEN = {  # endpoint de login por "versão" da credencial
    "3.1": "https://api.amazon.com/auth/o2/token",
    "3.2": "https://api.amazon.co.uk/auth/o2/token",
    "3.3": "https://api.amazon.co.jp/auth/o2/token",
    "2.1": "https://creatorsapi.auth.us-east-1.amazoncognito.com/oauth2/token",
    "2.2": "https://creatorsapi.auth.eu-south-2.amazoncognito.com/oauth2/token",
    "2.3": "https://creatorsapi.auth.us-west-2.amazoncognito.com/oauth2/token",
}
AMZ_RECURSOS = ["itemInfo.title", "images.primary.large", "offersV2.listings.price", "offersV2.listings.merchantInfo"]


def amazon_token(cid, sec, versao):
    url = AMZ_TOKEN.get(versao)
    if not url:
        raise RuntimeError(f"versão de credencial desconhecida: {versao}")
    if versao.startswith("3."):
        corpo = json.dumps({"grant_type": "client_credentials", "client_id": cid,
                            "client_secret": sec, "scope": "creatorsapi::default"})
        r = http("POST", url, headers={"Content-Type": "application/json"}, data=corpo, tentativas=2)
    else:
        corpo = urllib.parse.urlencode({"grant_type": "client_credentials", "client_id": cid,
                                        "client_secret": sec, "scope": "creatorsapi/default"})
        r = http("POST", url, headers={"Content-Type": "application/x-www-form-urlencoded"}, data=corpo, tentativas=2)
    return r["access_token"]


def _pega(d, *caminho):
    for c in caminho:
        if isinstance(d, list):
            d = d[0] if d else None
        if not isinstance(d, dict):
            return None
        d = d.get(c)
    return d


def amazon_link(url, tag):
    p = urllib.parse.urlsplit(url)
    qs = [(k, v) for k, v in urllib.parse.parse_qsl(p.query) if k != "tag"] + [("tag", tag)]
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(qs), ""))


def amazon_buscar(cfg):
    ac = cfg.get("amazon", {})
    if not ac.get("ligado"):
        return None
    cid, sec = os.getenv("AMAZON_CREDENTIAL_ID"), os.getenv("AMAZON_CREDENTIAL_SECRET")
    versao = (os.getenv("AMAZON_VERSION") or "3.1").strip().lstrip("vV").strip()
    tag = (os.getenv("AMAZON_TAG") or ac.get("tag") or "").strip()
    if not cid or not sec:
        log("Amazon: sem AMAZON_CREDENTIAL_ID / AMAZON_CREDENTIAL_SECRET, pulando.")
        return None
    if not tag:
        log("Amazon: falta a sua tag de associada (ex: coolgirls-20) no config.toml, pulando.")
        return None
    try:
        tok = amazon_token(cid, sec, versao)
    except Exception as e:
        log(f"Amazon: não consegui entrar com as credenciais ({e}).")
        return None
    auth = f"Bearer {tok}" if versao.startswith("3.") else f"Bearer {tok}, Version {versao}"
    hdr = {"Authorization": auth, "Content-Type": "application/json", "x-marketplace": AMZ_MARKET}
    g = cfg["geral"]
    out, usar_filtro = [], True
    for termo in g["buscas"]:
        corpo = {"keywords": termo, "marketplace": AMZ_MARKET, "partnerTag": tag,
                 "itemCount": 10, "resources": AMZ_RECURSOS}
        if ac.get("indice"):
            corpo["searchIndex"] = ac["indice"]
        if usar_filtro:
            corpo["minSavingPercent"] = int(g["desconto_minimo"])
        try:
            r = http("POST", AMZ_API, headers=hdr, data=json.dumps(corpo), tentativas=2)
        except Exception as e:
            if usar_filtro and "HTTP 400" in str(e):
                usar_filtro = False  # a API não aceitou o filtro de desconto: segue sem ele
                corpo.pop("minSavingPercent", None)
                try:
                    r = http("POST", AMZ_API, headers=hdr, data=json.dumps(corpo), tentativas=2)
                except Exception as e2:
                    log(f"Amazon ('{termo}'): {e2}")
                    continue
            else:
                log(f"Amazon ('{termo}'): {e}")
                continue
        itens = _pega(r, "searchResult", "items") or r.get("items") or []
        for it in itens:
            preco = _pega(it, "offersV2", "listings", "price")
            por = num(_pega(preco, "money", "amount"))
            url = it.get("detailPageURL")
            if not por or not url:
                continue
            de = num(_pega(preco, "savingBasis", "money", "amount"))
            off = int(num(_pega(preco, "savings", "percentage")) or 0)
            if not off and de and de > por:
                off = round((de - por) / de * 100)
            out.append({
                "id": f"amz-{it.get('asin')}",
                "loja": "amz",
                "titulo": (_pega(it, "itemInfo", "title", "displayValue") or "").strip(),
                "de": de if de and de > por else None, "por": por, "off": off,
                "img": _pega(it, "images", "primary", "large", "url") or "",
                "link": amazon_link(url, tag),
                "vendedor": _pega(it, "offersV2", "listings", "merchantInfo", "name") or "",
                "oficial": False, "nota": None, "vendidos": 0, "parc": "",
            })
        time.sleep(1.1)  # a Amazon aceita ~1 pedido por segundo
    log(f"Amazon: {len(out)} produtos recebidos.")
    return out


# ───────────────────────── FILTRO + MENSAGEM ─────────────────────────
def passa(o, g, favs_ids, so_oficial_shopee):
    t = sem_acento(o["titulo"])
    if any(sem_acento(p) in t for p in g.get("palavras_proibidas", [])):
        return False
    fav = o["loja"] == "shopee" and o.get("shop_id") in favs_ids
    o["fav"] = fav
    if not (g["preco_minimo"] <= o["por"] <= g["preco_maximo"]):
        return False
    if o["off"] < (g.get("desconto_minimo_favoritas", 10) if fav else g["desconto_minimo"]):
        return False
    if o.get("nota") and o["nota"] < g.get("nota_minima", 0):
        return False
    if o["loja"] == "shopee" and so_oficial_shopee and not (o["oficial"] or fav):
        return False
    return True


NOME_LOJA = {"shopee": "🧡 *SHOPEE*", "ml": "🛒 *MERCADO LIVRE*", "amz": "📦 *AMAZON*"}


def mensagem(o, g):
    L = [NOME_LOJA[o["loja"]], ""]
    if o.get("baixou"):
        L += ["🚨 *BAIXOU AINDA MAIS!*", ""]
    L.append(f"🛍️ *{o['titulo']}*")
    if o.get("fav"):
        L.append(f"🇰🇷 Loja oficial {o['vendedor']}")
    L.append("")
    if o.get("de"):
        L.append(f"~De {brl(o['de'])}~")
    L.append(f"💸 *Por {brl(o['por'])}*" + (f" ({o['off']}% OFF)" if o["off"] else ""))
    if o.get("parc"):
        L.append(f"💳 {o['parc']}")
    if o.get("oficial") and not o.get("fav"):
        L.append("✅ Loja oficial")
    L += ["", f"💰 *LINK PARA COMPRAR:* {o['link']}", "", f"⏳ _{g['frase_urgencia']}_"]
    if g.get("link_do_grupo"):
        L += ["", f"💖 Chama as amigas pro {g['nome_do_grupo']}: {g['link_do_grupo']}"]
    L.append(g.get("aviso_afiliada", "#publi"))
    return "\n".join(L)


# ───────────────────────── CUPONS ─────────────────────────
def ler_cupons(g):
    if not CUPONS.exists():
        return []
    try:
        lista = tomllib.loads(CUPONS.read_text(encoding="utf-8")).get("cupom", [])
    except Exception as e:
        log(f"cupons.toml com erro de digitação, cupons não atualizados: {e}")
        return None
    hoje = time.strftime("%Y-%m-%d", time.localtime(AGORA - 3 * 3600))  # horário de Brasília
    out = []
    for i, c in enumerate(lista):
        if c.get("exemplo") or not c.get("loja") or not c.get("titulo"):
            continue
        link = str(c.get("link") or "")
        if not link.startswith("https://"):
            log(f"Cupom '{c.get('titulo')}' sem link https, ignorado.")
            continue
        val = str(c.get("validade") or "")
        if val and val < hoje:
            continue
        cp = {
            "id": "cp-" + hashlib.sha1(f"{c['loja']}|{c.get('codigo','')}|{c['titulo']}".encode()).hexdigest()[:10],
            "loja": str(c["loja"]).strip(), "codigo": str(c.get("codigo") or "").strip().upper(),
            "titulo": str(c["titulo"]).strip(), "regra": str(c.get("regra") or "").strip(),
            "link": link, "validade": val, "destaque": bool(c.get("destaque")), "ordem": i,
        }
        L = [f"🎟️ *CUPOM {cp['loja'].upper()}*", "", f"✨ *{cp['titulo']}*"]
        if cp["regra"]:
            L.append(cp["regra"])
        if cp["codigo"]:
            L += ["", f"🔑 Código: *{cp['codigo']}*"]
        if val:
            d = val.split("-")
            L.append(f"📅 Válido até {d[2]}/{d[1]}")
        L += ["", f"👉 {'Use aqui' if cp['codigo'] else 'Resgate aqui'}: {link}", "", g.get("aviso_afiliada", "#publi")]
        cp["msg"] = "\n".join(L)
        out.append(cp)
    out.sort(key=lambda c: (not c["destaque"], c["ordem"]))
    log(f"Cupons: {len(out)} válidos.")
    return out


# ───────────────────────── PRINCIPAL ─────────────────────────
def main():
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    g = cfg["geral"]
    sc = cfg.get("shopee", {})

    antigo, cupons_antigos, conhecidos = {}, [], {}
    if SAIDA.exists():
        try:
            velho_json = json.loads(SAIDA.read_text(encoding="utf-8"))
            antigo = {o["id"]: o for o in velho_json.get("ofertas", [])}
            cupons_antigos = velho_json.get("cupons", [])
            conhecidos = velho_json.get("lojas_conhecidas", {}) or {}
        except Exception:
            log("ofertas.json antigo ilegível; começando do zero.")

    todas_favs = sc.get("lojas_favoritas", [])
    if sc.get("ligado"):
        shopee_descobrir_lojas(todas_favs, conhecidos)
    favs = [l for l in todas_favs if int(l.get("shop_id") or 0) > 0]
    favs_ids = {int(l["shop_id"]) for l in favs}
    cupons = ler_cupons(g)
    if cupons is None:
        cupons = cupons_antigos

    fontes = {
        "shopee": shopee_buscar(cfg, favs_ids) if sc.get("ligado") else None,
        "ml": ml_buscar(cfg) if cfg.get("mercado_livre", {}).get("ligado") else None,
        "amz": amazon_buscar(cfg),
    }

    novas = {}
    for loja, lista in fontes.items():
        for o in lista or []:
            if o["id"] in novas or not passa(o, g, favs_ids, sc.get("so_lojas_oficiais", True)):
                continue
            o["cat"] = categoria(o["titulo"])
            velho = antigo.get(o["id"])
            o["visto_em"] = AGORA
            o["desde"] = velho["desde"] if velho else AGORA
            o["baixou"] = bool(velho and o["por"] < velho["por"] - 0.009)
            if o["baixou"]:
                o["desde"] = AGORA  # sobe pro topo como novidade
            o["msg"] = mensagem(o, g)
            novas[o["id"]] = o

    # ofertas que sumiram nesta rodada continuam até completar o prazo
    limite = AGORA - int(g["horas_ate_sair"]) * 3600
    fontes_ok = {k for k, v in fontes.items() if v is not None}
    for oid, o in antigo.items():
        if oid in novas:
            continue
        if o.get("loja") in fontes_ok and o.get("visto_em", 0) < limite:
            continue
        if o.get("loja") not in fontes_ok and o.get("visto_em", 0) < AGORA - 72 * 3600:
            continue  # fonte fora do ar há 3 dias: limpa
        novas[oid] = o

    lista = sorted(novas.values(), key=lambda o: (o["desde"], o["off"]), reverse=True)[: int(g["maximo_de_ofertas"])]
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    SAIDA.write_text(json.dumps({
        "atualizado_em": AGORA,
        "grupo": g["nome_do_grupo"],
        "link_do_grupo": g.get("link_do_grupo", ""),
        "instagram": g.get("instagram", ""),
        "tiktok": g.get("tiktok", ""),
        "cupons": cupons,
        "lojas_favoritas": [{"nome": l["nome"], "shop_id": int(l["shop_id"])} for l in favs],
        "lojas_conhecidas": conhecidos,
        "fontes": {k: (v is not None) for k, v in fontes.items()},
        "ofertas": lista,
    }, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    novos = sum(1 for o in lista if o["desde"] == AGORA)
    log(f"Pronto: {len(lista)} ofertas no catálogo, {novos} novidade(s) nesta rodada.")
    if not fontes_ok:
        log("Nenhuma loja conectada ainda. Confira os Secrets no GitHub (veja o LEIAME).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
