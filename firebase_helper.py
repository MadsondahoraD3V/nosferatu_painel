# -*- coding: utf-8 -*-
"""
Integração Firebase Admin SDK para o painel Nosferatu.
Segurança: a service account NUNCA vai pro app nem pro GitHub —
fica apenas em st.secrets do Streamlit Cloud.
"""
import json
import os
import time
import urllib.request
import urllib.error

# ===== Acesso às credenciais (seguras, só servidor) =====
def _service_account_dict():
    """Lê a service account: st.secrets (cloud) ou arquivo local (dev)."""
    try:
        import streamlit as st
        sa = st.secrets.get("firebase", None)
        if sa is not None:
            return dict(sa)
    except Exception:
        pass
    # dev local
    path = os.environ.get("NOSFERATU_SA_PATH", "")
    if path and os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    local = os.path.join(os.path.dirname(__file__), "serviceAccountKey.json")
    if os.path.exists(local):
        with open(local, "r", encoding="utf-8") as f:
            return json.load(f)
    raise RuntimeError("Service account não encontrada. Configure st.secrets['firebase'] "
                       "ou a env NOSFERATU_SA_PATH.")

_TOKEN_CACHE = {"token": None, "exp": 0}

def _access_token():
    """Token OAuth2 curto (1h) a partir da service account."""
    now = time.time()
    if _TOKEN_CACHE["token"] and now < _TOKEN_CACHE["exp"] - 60:
        return _TOKEN_CACHE["token"]
    sa = _service_account_dict()
    # JWT RS256
    import base64
    import hashlib
    header = {"alg": "RS256", "typ": "JWT"}
    def b64url(d):
        return base64.urlsafe_b64encode(json.dumps(d, separators=(",", ":")).encode()).rstrip(b"=").decode()
    iat = int(now)
    exp = iat + 3600
    scope = "https://www.googleapis.com/auth/firebase.messaging https://www.googleapis.com/auth/datastore https://www.googleapis.com/auth/cloud-platform"
    claim = {
        "iss": sa["client_email"],
        "scope": scope,
        "aud": sa["token_uri"],
        "iat": iat,
        "exp": exp,
    }
    signing_input = b64url(header) + "." + b64url(claim)
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding
    # ====== PEM robusta: reconstrói de QUALQUER mangling ======
    # st.secrets (Streamlit Cloud) costuma quebrar a private_key:
    # - \\n literal (2 chars) em vez de quebra real
    # - key inteira numa linha só (sem quebras)
    # - espaços/aspas/tabs em volta
    # Estratégia: extrai só o corpo base64 (entre BEGIN/END), remove tudo que
    # não é base64, re-quebra em linhas de 64 chars e remonta BEGIN/END.
    pk = sa["private_key"]
    if not pk or "PRIVATE KEY" not in pk:
        raise RuntimeError("private_key ausente ou sem 'PRIVATE KEY' no st.secrets — " 
                           "recole o bloco do serviceAccountKey.json em Secrets do Streamlit.")
    # 1) tenta quebras literais primeiro (caso mais comum: \\n dentro de string)
    if "\\n" in pk:
        pk = pk.replace("\\r\\n", "\n").replace("\\n", "\n")
    # 2) remove tudo que não é BEGIN/END/base64 (espaços, aspas, tabs, lixo)
    import re as _re
    m = _re.search(r"-----BEGIN ([A-Z ]+?)-----", pk)
    if not m:
        raise RuntimeError("PEM sem cabeçalho BEGIN PRIVATE KEY — confira a private_key no st.secrets")
    hdr = m.group(1)
    corpo = pk.split(f"-----BEGIN {hdr}-----", 1)[1]
    corpo = corpo.split(f"-----END {hdr}-----", 1)[0]
    # mantém só base64 (A-Za-z0-9+/=)
    corpo = _re.sub(r"[^A-Za-z0-9+/=]", "", corpo)
    # re-quebra em 64 chars (PEM padrão)
    linhas = [corpo[i:i+64] for i in range(0, len(corpo), 64)]
    pk_final = f"-----BEGIN {hdr}-----\n" + "\n".join(linhas) + f"\n-----END {hdr}-----\n"
    # 3) se ainda falhar, dá erro claro com diagnóstico
    try:
        key = serialization.load_pem_private_key(pk_final.encode(), password=None)
    except Exception as e:
        raise RuntimeError(
            f"Falha ao carregar private_key mesmo após reconstrução ({len(corpo)} chars base64). "
            f"Causa: {e}. Verifique se o st.secrets['firebase']['private_key'] está COMPLETO "
            f"(começa com '-----BEGIN PRIVATE KEY-----' e termina com '-----END PRIVATE KEY-----')."
        )
    sig = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    jwt = signing_input + "." + base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    body = "grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=" + jwt
    req = urllib.request.Request(sa["token_uri"], data=body.encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=30) as r:
        resp = json.loads(r.read().decode())
    _TOKEN_CACHE["token"] = resp["access_token"]
    _TOKEN_CACHE["exp"] = iat + resp.get("expires_in", 3600)
    return resp["access_token"]

def _api(url, data=None, method=None):
    tok = _access_token()
    headers = {"Authorization": "Bearer " + tok, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=json.dumps(data).encode() if data is not None else None,
                                 headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500]
        raise RuntimeError(f"HTTP {e.code}: {body}")

def project_id():
    return _service_account_dict()["project_id"]

# ===== Firestore (REST) =====
def fs_get(collection, doc_id=None):
    base = f"https://firestore.googleapis.com/v1/projects/{project_id()}/databases/nosferatu-database/documents"
    if doc_id:
        return _api(f"{base}/{collection}/{doc_id}")
    # listar
    return _api(f"{base}/{collection}?pageSize=300")

def fs_set(collection, doc_id, data, merge=True):
    base = f"https://firestore.googleapis.com/v1/projects/{project_id()}/databases/nosferatu-database/documents"
    fields = {}
    for k, v in data.items():
        if isinstance(v, bool):
            fields[k] = {"booleanValue": v}
        elif isinstance(v, int):
            fields[k] = {"integerValue": str(v)}
        elif isinstance(v, float):
            fields[k] = {"doubleValue": v}
        else:
            fields[k] = {"stringValue": str(v)}
    # Verifica se o doc existe: se não, usa POST (create) em vez de PATCH (update)
    existe = True
    try:
        _api(f"{base}/{collection}/{doc_id}", method="GET")
    except Exception:
        existe = False
    if not existe:
        url = f"{base}/{collection}?documentId={doc_id}"
        return _api(url, {"fields": fields}, method="POST")
    url = f"{base}/{collection}/{doc_id}?updateMask.fieldPaths={','.join(data.keys())}" if merge else f"{base}/{collection}/{doc_id}"
    return _api(url, {"fields": fields}, method="PATCH" if merge else "POST")

def fs_delete(collection, doc_id):
    base = f"https://firestore.googleapis.com/v1/projects/{project_id()}/databases/nosferatu-database/documents"
    return _api(f"{base}/{collection}/{doc_id}", method="DELETE")

def fs_doc_to_dict(doc):
    """Converte documento Firestore REST p/ dict simples."""
    fields = doc.get("fields", {})
    out = {}
    for k, v in fields.items():
        if "stringValue" in v: out[k] = v["stringValue"]
        elif "integerValue" in v: out[k] = int(v["integerValue"])
        elif "doubleValue" in v: out[k] = v["doubleValue"]
        elif "booleanValue" in v: out[k] = v["booleanValue"]
        elif "timestampValue" in v: out[k] = v["timestampValue"]
        elif "arrayValue" in v: out[k] = [fs_doc_to_dict({"fields": x.get("mapValue", {}).get("fields", {})}) for x in v["arrayValue"].get("values", [])] if v["arrayValue"].get("values") else []
        elif "mapValue" in v: out[k] = fs_doc_to_dict({"fields": v["mapValue"].get("fields", {})})
    return out

# ===== FCM Push (HTTP v1) =====
def enviar_push(token, titulo, corpo, tipo="aviso", incubo=None, dados_extra=None):
    """Envia notificação push para um device token."""
    msg = {
        "message": {
            "token": token,
            "data": {
                "titulo": titulo,
                "mensagem": corpo,
                "tipo": tipo or "aviso",
            },
        }
    }
    if incubo:
        msg["message"]["data"]["incubo"] = incubo
    if dados_extra:
        msg["message"]["data"].update({str(k): str(v) for k, v in dados_extra.items()})
    url = f"https://fcm.googleapis.com/v1/projects/{project_id()}/messages:send"
    return _api(url, msg)

# ===== Lógica de negócio do painel =====
import hashlib
import secrets as _secrets

def _hash_senha(senha):
    """SHA-256(senha + salt). A senha em claro NUNCA vai pro Firestore."""
    salt = _secrets.token_hex(8)
    return hashlib.sha256((senha + salt).encode("utf-8")).hexdigest(), salt

def criar_usuario(uid, nome, senha, lidos_max=10):
    """Cria usuário com hash de senha (seguro)."""
    h, salt = _hash_senha(senha)
    data = {
        "uid": uid, "nome": nome,
        "senha_hash": h, "senha_salt": salt,
        "lidos_max": int(lidos_max),
        "paginas_liberadas": "todas", "grimorio": "liberado",
        "nivel_extra": 0, "ativo": True, "fcm_token": "",
        "pontos": 0, "nivel": 1, "livrosLidos": 0, "paginasLidas": 0,
    }
    fs_set("usuarios", uid, data)
    return True

def usuario(uid):
    """Retorna doc do usuário ou default."""
    try:
        d = fs_get("usuarios", uid)
        return fs_doc_to_dict(d)
    except Exception:
        return {"uid": uid, "nome": uid, "lidos_max": 10, "paginas_liberadas": "todas",
                "grimorio": "liberado", "nivel_extra": 0, "ativo": True, "fcm_token": ""}

def salvar_usuario(uid, data):
    fs_set("usuarios", uid, data)

def registrar_incubo_proxima_abertura(uid):
    """Marca íncubo p/ aparecer na próxima abertura do app (via push 'proxima')."""
    u = usuario(uid)
    tok = u.get("fcm_token", "")
    if tok:
        enviar_push(tok, "🜏 O íncubo aguarda…",
                    "Um pacto foi selado para você. Abra o app para invocá-lo.",
                    tipo="incubo", incubo="proxima")
    # fallback: flag no Firestore (app checa na abertura)
    salvar_usuario(uid, {**u, "incubo_na_proxima": True})
    return True

def disparar_meta(uid, titulo, corpo):
    u = usuario(uid)
    tok = u.get("fcm_token", "")
    if not tok:
        raise RuntimeError("Usuário sem fcm_token registrado (app ainda não abriu com Firebase).")
    enviar_push(tok, titulo, corpo, tipo="meta")
    return True

def disparar_desafio(uid, titulo, corpo):
    u = usuario(uid)
    tok = u.get("fcm_token", "")
    if not tok:
        raise RuntimeError("Usuário sem fcm_token registrado (app ainda não abriu com Firebase).")
    enviar_push(tok, titulo, corpo, tipo="desafio")
    return True
