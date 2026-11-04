#!/usr/bin/env python3
"""
Publicador multi-red: conecta tus cuentas una vez (inicio de sesión en el navegador)
y publica el mismo texto, imagen o video desde tu PC en todas a la vez.

Redes: Facebook (Página), Instagram (cuenta profesional), X, LinkedIn y Telegram.

Uso:
  Doble clic (sin argumentos)  -> abre la ventana
  python publicar.py "Texto" --archivo C:\\fotos\\foto.jpg --link https://...
  python publicar.py "Texto" --redes facebook,x --simular
  python publicar.py --conectar facebook|x|linkedin
"""
import argparse
import base64
import hashlib
import http.server
import json
import mimetypes
import os
import secrets
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path

import requests

VERSION_GRAPH = "v21.0"
GRAPH = f"https://graph.facebook.com/{VERSION_GRAPH}"
GRAPH_VIDEO = f"https://graph-video.facebook.com/{VERSION_GRAPH}"
PUERTO = 8765
REDIRECT = f"http://localhost:{PUERTO}/callback"
TIMEOUT = 120

EXT_IMAGEN = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
EXT_VIDEO = {".mp4", ".mov", ".m4v"}


class ErrorRed(Exception):
    pass


def _check(resp):
    if resp.status_code >= 400:
        raise ErrorRed(f"HTTP {resp.status_code}: {resp.text[:400]}")
    try:
        return resp.json() if resp.content else {}
    except ValueError:
        return {}


# ======================================================================= Archivos
def carpeta_app():
    """Carpeta del programa (junto al .exe si está compilado)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_EJEMPLO = {
    "_ayuda": "Datos de tus apps de desarrollador (se crean una sola vez). Ver LEEME.md",
    "meta": {"app_id": "", "app_secret": ""},
    "x": {"client_id": "", "client_secret": ""},
    "linkedin": {"client_id": "", "client_secret": "", "version": "202510"},
    "telegram": {"bot_token": "", "chat_id": "@tu_canal"},
}


class Almacen:
    """config.json = datos de las apps; cuentas.json = sesiones iniciadas (tokens)."""

    def __init__(self, carpeta=None):
        c = Path(carpeta or carpeta_app())
        self.ruta_config = c / "config.json"
        self.ruta_cuentas = c / "cuentas.json"
        self.config_nueva = not self.ruta_config.exists()
        if self.config_nueva:
            self.ruta_config.write_text(json.dumps(CONFIG_EJEMPLO, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
        self.recargar()

    def recargar(self):
        self.config = json.loads(self.ruta_config.read_text(encoding="utf-8"))
        self.cuentas = (json.loads(self.ruta_cuentas.read_text(encoding="utf-8"))
                        if self.ruta_cuentas.exists() else {})

    def guardar_cuentas(self):
        self.ruta_cuentas.write_text(json.dumps(self.cuentas, indent=2, ensure_ascii=False),
                                     encoding="utf-8")

    def app(self, nombre, *campos):
        datos = self.config.get(nombre, {})
        falta = [c for c in campos if not datos.get(c)]
        if falta:
            raise ErrorRed(f"Falta {', '.join(falta)} de '{nombre}' en config.json "
                           f"(pulsa 'Datos de apps' y rellénalo; ver LEEME.md)")
        return datos

    def conectada(self, red):
        if red == "telegram":
            t = self.config.get("telegram", {})
            return bool(t.get("bot_token") and t.get("chat_id"))
        return red in self.cuentas

    def descripcion(self, red):
        if red == "telegram":
            return f"canal {self.config['telegram']['chat_id']}" if self.conectada(red) else ""
        c = self.cuentas.get(red)
        if not c:
            return ""
        txt = c.get("nombre", "conectada")
        if c.get("expira") and c["expira"] < time.time() and not c.get("refresh_token"):
            txt += " (sesión caducada: vuelve a conectar)"
        return txt


def tipo_archivo(ruta):
    ext = Path(ruta).suffix.lower()
    if ext in EXT_IMAGEN:
        return "imagen"
    if ext in EXT_VIDEO:
        return "video"
    raise ErrorRed(f"Tipo de archivo no admitido: {ext} (usa JPG/PNG o MP4/MOV)")


def mime(ruta):
    return mimetypes.guess_type(str(ruta))[0] or "application/octet-stream"


# ======================================================================= Inicio de sesión (OAuth)
def esperar_codigo(url_autorizacion, estado, espera=300):
    """Abre el navegador y espera a que la red nos devuelva a localhost con ?code=..."""
    resultado = {}

    class Manejador(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if urllib.parse.urlparse(self.path).path != "/callback":
                self.send_response(404); self.end_headers(); return
            resultado.update({k: v[0] for k, v in q.items()})
            ok = "code" in q and q.get("state", [""])[0] == estado
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = ("Listo, ya puedes cerrar esta pestaña y volver al Publicador." if ok else
                   "No se pudo iniciar sesión. Vuelve al Publicador e inténtalo de nuevo.")
            self.wfile.write(f"<html><body style='font-family:sans-serif;padding:40px'>"
                             f"<h2>{msg}</h2></body></html>".encode())

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", PUERTO), Manejador)
    except OSError:
        raise ErrorRed(f"El puerto {PUERTO} está ocupado. Cierra otras ventanas del Publicador.")
    srv.timeout = 1
    webbrowser.open(url_autorizacion)
    fin = time.time() + espera
    try:
        while "code" not in resultado and "error" not in resultado and time.time() < fin:
            srv.handle_request()
    finally:
        srv.server_close()
    if "error" in resultado:
        raise ErrorRed(f"Inicio de sesión cancelado: {resultado.get('error_description') or resultado['error']}")
    if "code" not in resultado:
        raise ErrorRed("Se agotó el tiempo esperando el inicio de sesión.")
    if resultado.get("state") != estado:
        raise ErrorRed("Respuesta de inicio de sesión no válida (state distinto).")
    return resultado["code"]


def login_meta(alm):
    """Devuelve la lista de Páginas (con su Instagram vinculado) para que el usuario elija."""
    app = alm.app("meta", "app_id", "app_secret")
    estado = secrets.token_urlsafe(16)
    permisos = ("pages_show_list,pages_manage_posts,pages_read_engagement,business_management,"
                "instagram_basic,instagram_content_publish")
    url = (f"https://www.facebook.com/{VERSION_GRAPH}/dialog/oauth?" + urllib.parse.urlencode({
        "client_id": app["app_id"], "redirect_uri": REDIRECT, "state": estado, "scope": permisos}))
    code = esperar_codigo(url, estado)
    corto = _check(requests.get(f"{GRAPH}/oauth/access_token", params={
        "client_id": app["app_id"], "client_secret": app["app_secret"],
        "redirect_uri": REDIRECT, "code": code}, timeout=TIMEOUT))["access_token"]
    largo = _check(requests.get(f"{GRAPH}/oauth/access_token", params={
        "grant_type": "fb_exchange_token", "client_id": app["app_id"],
        "client_secret": app["app_secret"], "fb_exchange_token": corto}, timeout=TIMEOUT))["access_token"]
    paginas = _check(requests.get(f"{GRAPH}/me/accounts", params={
        "fields": "id,name,access_token,instagram_business_account{id,username}",
        "access_token": largo}, timeout=TIMEOUT)).get("data", [])
    if not paginas:
        raise ErrorRed("Tu cuenta no administra ninguna Página de Facebook (Meta solo permite "
                       "publicar en Páginas, no en perfiles personales).")
    return paginas


def guardar_pagina_meta(alm, pagina):
    alm.cuentas["facebook"] = {"page_id": pagina["id"], "token": pagina["access_token"],
                               "nombre": f"Página «{pagina['name']}»"}
    ig = pagina.get("instagram_business_account")
    if ig:
        alm.cuentas["instagram"] = {"ig_user_id": ig["id"], "token": pagina["access_token"],
                                    "page_id": pagina["id"], "nombre": f"@{ig.get('username', ig['id'])}"}
    else:
        alm.cuentas.pop("instagram", None)
    alm.guardar_cuentas()
    return bool(ig)


def login_linkedin(alm):
    app = alm.app("linkedin", "client_id", "client_secret")
    estado = secrets.token_urlsafe(16)
    url = "https://www.linkedin.com/oauth/v2/authorization?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": app["client_id"], "redirect_uri": REDIRECT,
        "state": estado, "scope": "openid profile w_member_social"})
    code = esperar_codigo(url, estado)
    tok = _check(requests.post("https://www.linkedin.com/oauth/v2/accessToken", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": REDIRECT,
        "client_id": app["client_id"], "client_secret": app["client_secret"]}, timeout=TIMEOUT))
    yo = _check(requests.get("https://api.linkedin.com/v2/userinfo", timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {tok['access_token']}"}))
    alm.cuentas["linkedin"] = {"token": tok["access_token"], "author_urn": f"urn:li:person:{yo['sub']}",
                               "expira": time.time() + int(tok.get("expires_in", 5184000)),
                               "nombre": yo.get("name", "perfil")}
    alm.guardar_cuentas()


def login_x(alm):
    app = alm.app("x", "client_id")
    estado = secrets.token_urlsafe(16)
    verificador = secrets.token_urlsafe(48)
    reto = base64.urlsafe_b64encode(hashlib.sha256(verificador.encode()).digest()).rstrip(b"=").decode()
    url = "https://x.com/i/oauth2/authorize?" + urllib.parse.urlencode({
        "response_type": "code", "client_id": app["client_id"], "redirect_uri": REDIRECT,
        "scope": "tweet.read tweet.write users.read media.write offline.access",
        "state": estado, "code_challenge": reto, "code_challenge_method": "S256"})
    code = esperar_codigo(url, estado)
    tok = _x_token(app, {"grant_type": "authorization_code", "code": code,
                         "redirect_uri": REDIRECT, "code_verifier": verificador})
    yo = _check(requests.get("https://api.x.com/2/users/me", timeout=TIMEOUT,
                             headers={"Authorization": f"Bearer {tok['access_token']}"}))
    alm.cuentas["x"] = {"token": tok["access_token"], "refresh_token": tok.get("refresh_token"),
                        "expira": time.time() + int(tok.get("expires_in", 7200)) - 60,
                        "nombre": "@" + yo["data"]["username"]}
    alm.guardar_cuentas()


def _x_token(app, datos):
    datos = dict(datos, client_id=app["client_id"])
    auth = (app["client_id"], app["client_secret"]) if app.get("client_secret") else None
    return _check(requests.post("https://api.x.com/2/oauth2/token", data=datos, auth=auth,
                                timeout=TIMEOUT))


def _x_token_vigente(alm):
    c = alm.cuentas["x"]
    if c["expira"] < time.time():
        if not c.get("refresh_token"):
            raise ErrorRed("La sesión de X caducó: vuelve a conectar")
        tok = _x_token(alm.app("x", "client_id"),
                       {"grant_type": "refresh_token", "refresh_token": c["refresh_token"]})
        c.update(token=tok["access_token"], refresh_token=tok.get("refresh_token", c["refresh_token"]),
                 expira=time.time() + int(tok.get("expires_in", 7200)) - 60)
        alm.guardar_cuentas()
    return c["token"]


LOGINS = {"facebook": login_meta, "instagram": login_meta, "x": login_x, "linkedin": login_linkedin}


# ======================================================================= Publicar
def _esperar(cond, intentos=60, pausa=5, que="el procesamiento"):
    for _ in range(intentos):
        r = cond()
        if r:
            return r
        time.sleep(pausa)
    raise ErrorRed(f"Se agotó el tiempo esperando {que}")


def publicar_facebook(alm, post, simular):
    c = alm.cuentas["facebook"]
    page, token, archivo = c["page_id"], c["token"], post["archivo"]
    if not archivo:
        datos = {"message": post["texto"], "access_token": token}
        if post["link"]:
            datos["link"] = post["link"]
        if simular:
            return "publicaría texto en el muro de la Página"
        return "id " + _check(requests.post(f"{GRAPH}/{page}/feed", data=datos, timeout=TIMEOUT))["id"]
    tipo = tipo_archivo(archivo)
    if simular:
        return f"subiría {tipo} {Path(archivo).name}"
    with open(archivo, "rb") as f:
        if tipo == "imagen":
            r = requests.post(f"{GRAPH}/{page}/photos", timeout=600,
                              data={"caption": post["texto_con_link"], "access_token": token},
                              files={"source": (Path(archivo).name, f, mime(archivo))})
        else:
            r = requests.post(f"{GRAPH_VIDEO}/{page}/videos", timeout=3600,
                              data={"description": post["texto_con_link"], "access_token": token},
                              files={"source": (Path(archivo).name, f, mime(archivo))})
    r = _check(r)
    return "id " + str(r.get("post_id") or r.get("id"))


def publicar_instagram(alm, post, simular):
    c = alm.cuentas["instagram"]
    ig, token, archivo = c["ig_user_id"], c["token"], post["archivo"]
    if not archivo:
        raise ErrorRed("Instagram necesita una imagen o un video")
    tipo = tipo_archivo(archivo)
    if simular:
        return f"subiría {tipo} {Path(archivo).name}"
    if tipo == "imagen":
        # Instagram solo acepta imágenes por URL pública: la subimos a la Página como foto
        # no publicada y usamos su dirección.
        with open(archivo, "rb") as f:
            foto = _check(requests.post(f"{GRAPH}/{c['page_id']}/photos", timeout=600,
                                        data={"published": "false", "temporary": "true",
                                              "access_token": token},
                                        files={"source": (Path(archivo).name, f, mime(archivo))}))
        url_img = _check(requests.get(f"{GRAPH}/{foto['id']}", timeout=TIMEOUT, params={
            "fields": "images", "access_token": token}))["images"][0]["source"]
        cont = _check(requests.post(f"{GRAPH}/{ig}/media", timeout=TIMEOUT, data={
            "image_url": url_img, "caption": post["texto_con_link"], "access_token": token}))
    else:
        cont = _check(requests.post(f"{GRAPH}/{ig}/media", timeout=TIMEOUT, data={
            "media_type": "REELS", "upload_type": "resumable",
            "caption": post["texto_con_link"], "access_token": token}))
        tam = os.path.getsize(archivo)
        with open(archivo, "rb") as f:
            _check(requests.post(f"https://rupload.facebook.com/ig-api-upload/{VERSION_GRAPH}/{cont['id']}",
                                 data=f, timeout=3600, headers={
                                     "Authorization": f"OAuth {token}", "offset": "0",
                                     "file_size": str(tam)}))

    def listo():
        st = _check(requests.get(f"{GRAPH}/{cont['id']}", timeout=TIMEOUT, params={
            "fields": "status_code", "access_token": token})).get("status_code")
        if st == "ERROR":
            raise ErrorRed("Instagram no pudo procesar el archivo (revisa formato y duración)")
        return st == "FINISHED"
    _esperar(listo, que="a que Instagram procese el archivo")
    r = _check(requests.post(f"{GRAPH}/{ig}/media_publish", timeout=TIMEOUT, data={
        "creation_id": cont["id"], "access_token": token}))
    return "id " + r["id"]


def publicar_x(alm, post, simular):
    texto = post["texto_con_link"]
    if len(texto) > 280:
        texto = texto[:277] + "..."
    archivo = post["archivo"]
    if simular:
        return f"publicaría {len(texto)} caracteres" + (f" + {Path(archivo).name}" if archivo else "")
    token = _x_token_vigente(alm)
    h = {"Authorization": f"Bearer {token}"}
    cuerpo = {"text": texto}
    if archivo:
        cuerpo["media"] = {"media_ids": [_x_subir(archivo, h)]}
    r = _check(requests.post("https://api.x.com/2/tweets", json=cuerpo, headers=h, timeout=TIMEOUT))
    return "id " + r["data"]["id"]


def _x_subir(archivo, h):
    base = "https://api.x.com/2/media/upload"
    tipo = tipo_archivo(archivo)
    if tipo == "imagen":
        with open(archivo, "rb") as f:
            r = _check(requests.post(base, headers=h, timeout=600,
                                     data={"media_category": "tweet_image"},
                                     files={"media": (Path(archivo).name, f, mime(archivo))}))
        return r["data"]["id"]
    tam = os.path.getsize(archivo)
    mid = _check(requests.post(f"{base}/initialize", headers=h, timeout=TIMEOUT, json={
        "media_type": mime(archivo), "total_bytes": tam, "media_category": "tweet_video"}))["data"]["id"]
    with open(archivo, "rb") as f:
        i = 0
        while trozo := f.read(4 * 1024 * 1024):
            _check(requests.post(f"{base}/{mid}/append", headers=h, timeout=600,
                                 data={"segment_index": i}, files={"media": ("trozo", trozo)}))
            i += 1
    info = _check(requests.post(f"{base}/{mid}/finalize", headers=h, timeout=TIMEOUT))
    proc = info.get("data", {}).get("processing_info")
    while proc and proc.get("state") in ("pending", "in_progress"):
        time.sleep(proc.get("check_after_secs", 5))
        proc = _check(requests.get(base, headers=h, timeout=TIMEOUT, params={
            "command": "STATUS", "media_id": mid})).get("data", {}).get("processing_info")
    if proc and proc.get("state") == "failed":
        raise ErrorRed("X no pudo procesar el video")
    return mid


def publicar_linkedin(alm, post, simular):
    c = alm.cuentas["linkedin"]
    if c.get("expira", 0) < time.time():
        raise ErrorRed("La sesión de LinkedIn caducó (duran 60 días): vuelve a conectar")
    archivo = post["archivo"]
    if simular:
        return "publicaría en tu perfil" + (f" con {Path(archivo).name}" if archivo else "")
    h = {"Authorization": f"Bearer {c['token']}",
         "LinkedIn-Version": alm.config.get("linkedin", {}).get("version", "202510"),
         "X-Restli-Protocol-Version": "2.0.0"}
    cuerpo = {
        "author": c["author_urn"], "commentary": post["texto"], "visibility": "PUBLIC",
        "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [],
                         "thirdPartyDistributionChannels": []},
        "lifecycleState": "PUBLISHED", "isReshareDisabledByAuthor": False,
    }
    if archivo:
        cuerpo["content"] = {"media": {"id": _linkedin_subir(archivo, c["author_urn"], h),
                                       "title": Path(archivo).stem}}
        if post["link"]:
            cuerpo["commentary"] = post["texto_con_link"]
    elif post["link"]:
        cuerpo["content"] = {"article": {"source": post["link"], "title": post["link"]}}
    r = requests.post("https://api.linkedin.com/rest/posts", json=cuerpo, headers=h, timeout=TIMEOUT)
    _check(r)
    return "id " + r.headers.get("x-restli-id", "ok")


def _linkedin_subir(archivo, owner, h):
    tam = os.path.getsize(archivo)
    if tipo_archivo(archivo) == "imagen":
        v = _check(requests.post("https://api.linkedin.com/rest/images?action=initializeUpload",
                                 headers=h, timeout=TIMEOUT,
                                 json={"initializeUploadRequest": {"owner": owner}}))["value"]
        with open(archivo, "rb") as f:
            _check(requests.put(v["uploadUrl"], data=f, timeout=600,
                                headers={"Authorization": h["Authorization"]}))
        return v["image"]
    v = _check(requests.post("https://api.linkedin.com/rest/videos?action=initializeUpload",
                             headers=h, timeout=TIMEOUT, json={"initializeUploadRequest": {
                                 "owner": owner, "fileSizeBytes": tam,
                                 "uploadCaptions": False, "uploadThumbnail": False}}))["value"]
    etags = []
    with open(archivo, "rb") as f:
        for parte in v["uploadInstructions"]:
            f.seek(parte["firstByte"])
            datos = f.read(parte["lastByte"] - parte["firstByte"] + 1)
            r = requests.put(parte["uploadUrl"], data=datos, timeout=600,
                             headers={"Content-Type": "application/octet-stream"})
            _check(r)
            etags.append(r.headers.get("etag") or r.headers.get("ETag"))
    _check(requests.post("https://api.linkedin.com/rest/videos?action=finalizeUpload", headers=h,
                         timeout=TIMEOUT, json={"finalizeUploadRequest": {
                             "video": v["video"], "uploadToken": v.get("uploadToken", ""),
                             "uploadedPartIds": etags}}))
    urn = urllib.parse.quote(v["video"], safe="")

    def listo():
        st = _check(requests.get(f"https://api.linkedin.com/rest/videos/{urn}", headers=h,
                                 timeout=TIMEOUT)).get("status")
        if st == "PROCESSING_FAILED":
            raise ErrorRed("LinkedIn no pudo procesar el video")
        return st == "AVAILABLE"
    _esperar(listo, que="a que LinkedIn procese el video")
    return v["video"]


def publicar_telegram(alm, post, simular):
    t = alm.config["telegram"]
    base = f"https://api.telegram.org/bot{t['bot_token']}"
    archivo = post["archivo"]
    if simular:
        return f"enviaría al canal {t['chat_id']}" + (f" con {Path(archivo).name}" if archivo else "")
    if not archivo:
        r = requests.post(f"{base}/sendMessage", timeout=TIMEOUT,
                          data={"chat_id": t["chat_id"], "text": post["texto_con_link"]})
    else:
        metodo, campo = (("sendPhoto", "photo") if tipo_archivo(archivo) == "imagen"
                         else ("sendVideo", "video"))
        with open(archivo, "rb") as f:
            r = requests.post(f"{base}/{metodo}", timeout=3600, files={campo: f},
                              data={"chat_id": t["chat_id"], "caption": post["texto_con_link"][:1024]})
    return "mensaje " + str(_check(r)["result"]["message_id"])


REDES = {
    "facebook": publicar_facebook,
    "instagram": publicar_instagram,
    "x": publicar_x,
    "linkedin": publicar_linkedin,
    "telegram": publicar_telegram,
}
NOMBRES = {"facebook": "Facebook", "instagram": "Instagram", "x": "X", "linkedin": "LinkedIn",
           "telegram": "Telegram"}


def publicar_todo(alm, texto, archivo, link, redes, simular, log=print):
    if archivo:
        if not Path(archivo).is_file():
            log(f"X  No encuentro el archivo {archivo}"); return 1
        tipo_archivo(archivo)
    post = {"texto": texto, "archivo": archivo or None, "link": link or None,
            "texto_con_link": f"{texto}\n\n{link}" if link else texto}
    fallos = 0
    for red in redes:
        if red not in REDES:
            log(f"?  {red}: red desconocida"); fallos += 1; continue
        if not alm.conectada(red):
            log(f"-  {NOMBRES[red]}: no conectada, se salta"); continue
        if red == "instagram" and not archivo:
            log("-  Instagram: se salta (solo publica imágenes o videos)"); continue
        try:
            log(f"…  {NOMBRES[red]}: publicando…" if not simular else f"…  {NOMBRES[red]}:")
            log(f"OK {NOMBRES[red]}: {REDES[red](alm, post, simular)}")
        except (ErrorRed, requests.RequestException, KeyError, OSError) as e:
            fallos += 1
            log(f"X  {NOMBRES[red]}: {e}")
    return fallos


# ======================================================================= Ventana
def abrir_ventana():
    import subprocess
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext

    alm = Almacen()
    win = tk.Tk()
    win.title("Publicador multi-red")
    win.geometry("680x760")
    pad = {"padx": 10, "pady": 4}

    # ---------- Cuentas
    marco = tk.LabelFrame(win, text=" Mis cuentas ")
    marco.pack(fill="x", padx=10, pady=8)
    filas = {}
    for i, red in enumerate(REDES):
        tk.Label(marco, text=NOMBRES[red], width=10, anchor="w",
                 font=("Segoe UI", 10, "bold")).grid(row=i, column=0, sticky="w", padx=6, pady=2)
        estado = tk.Label(marco, anchor="w", width=44)
        estado.grid(row=i, column=1, sticky="w")
        boton = tk.Button(marco, width=12)
        boton.grid(row=i, column=2, padx=6, pady=2)
        filas[red] = (estado, boton)

    marcas = {}

    def refrescar():
        alm.recargar()
        for red, (estado, boton) in filas.items():
            if alm.conectada(red):
                estado.config(text="✔ " + alm.descripcion(red), fg="#1a7f37")
            else:
                estado.config(text="✖ no conectada", fg="#b42318")
            if red == "telegram":
                boton.config(text="Configurar", command=abrir_config)
            elif red == "instagram":
                boton.config(text="Reconectar" if alm.conectada(red) else "Conectar",
                             command=lambda: conectar("facebook"))
            else:
                boton.config(text="Reconectar" if alm.conectada(red) else "Conectar",
                             command=lambda r=red: conectar(r))
            if red in marcas:
                marcas[red].set(alm.conectada(red))

    def conectar(red):
        log(f"Abriendo el navegador para iniciar sesión en {NOMBRES[red]}…")

        def trabajo():
            try:
                res = LOGINS[red](alm)
                win.after(0, lambda: tras_login(red, res))
            except (ErrorRed, requests.RequestException, KeyError) as e:
                msg = str(e)
                win.after(0, lambda: (log(f"X  {NOMBRES[red]}: {msg}"),
                                      messagebox.showerror("No se pudo conectar", msg)))
        threading.Thread(target=trabajo, daemon=True).start()

    def tras_login(red, res):
        if red in ("facebook", "instagram"):
            pagina = elegir_pagina(res)
            if not pagina:
                return
            con_ig = guardar_pagina_meta(alm, pagina)
            log(f"OK Facebook conectado: {pagina['name']}")
            log("OK Instagram conectado" if con_ig else
                "!  Esa Página no tiene una cuenta de Instagram profesional vinculada")
        else:
            log(f"OK {NOMBRES[red]} conectado")
        refrescar()

    def elegir_pagina(paginas):
        if len(paginas) == 1:
            return paginas[0]
        dlg = tk.Toplevel(win); dlg.title("Elige la Página"); dlg.grab_set()
        tk.Label(dlg, text="¿En qué Página de Facebook quieres publicar?").pack(padx=10, pady=8)
        lista = tk.Listbox(dlg, width=50, height=min(10, len(paginas)))
        for p in paginas:
            ig = p.get("instagram_business_account")
            lista.insert("end", p["name"] + (f"  (Instagram @{ig.get('username')})" if ig else ""))
        lista.selection_set(0); lista.pack(padx=10)
        elegido = {}
        tk.Button(dlg, text="Aceptar", command=lambda: (
            elegido.update(p=paginas[lista.curselection()[0]]), dlg.destroy())).pack(pady=8)
        win.wait_window(dlg)
        return elegido.get("p")

    def abrir_config():
        ruta = alm.ruta_config
        if sys.platform.startswith("win"):
            os.startfile(ruta)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(ruta)])
        else:
            subprocess.Popen(["xdg-open", str(ruta)])

    f_cfg = tk.Frame(marco); f_cfg.grid(row=len(REDES), column=0, columnspan=3, sticky="w", pady=4)
    tk.Button(f_cfg, text="Datos de apps (config.json)", command=abrir_config).pack(side="left", padx=6)
    tk.Button(f_cfg, text="Actualizar", command=lambda: refrescar()).pack(side="left")

    # ---------- Publicación
    tk.Label(win, text="Texto de la publicación:").pack(anchor="w", **pad)
    caja = scrolledtext.ScrolledText(win, height=7, wrap="word")
    caja.pack(fill="x", **pad)

    f_arch = tk.Frame(win); f_arch.pack(fill="x", **pad)
    archivo = tk.StringVar()
    tk.Button(f_arch, text="Elegir imagen o video…", command=lambda: archivo.set(
        filedialog.askopenfilename(title="Elige una imagen o un video", filetypes=[
            ("Imágenes y videos", " ".join("*" + e for e in sorted(EXT_IMAGEN | EXT_VIDEO))),
            ("Todos", "*.*")]) or archivo.get())).pack(side="left")
    tk.Label(f_arch, textvariable=archivo, anchor="w", fg="#444").pack(side="left", padx=8)
    tk.Button(f_arch, text="Quitar", command=lambda: archivo.set("")).pack(side="right")

    f_link = tk.Frame(win); f_link.pack(fill="x", **pad)
    tk.Label(f_link, text="Enlace (opcional):", width=16, anchor="w").pack(side="left")
    e_link = tk.Entry(f_link); e_link.pack(side="left", fill="x", expand=True)

    tk.Label(win, text="Publicar en:").pack(anchor="w", **pad)
    f_redes = tk.Frame(win); f_redes.pack(fill="x", padx=10)
    for red in REDES:
        marcas[red] = tk.BooleanVar()
        tk.Checkbutton(f_redes, text=NOMBRES[red], variable=marcas[red]).pack(side="left")

    simular = tk.BooleanVar(value=False)
    tk.Checkbutton(win, text="Solo simular (no publica nada)", variable=simular).pack(anchor="w", **pad)
    btn = tk.Button(win, text="Publicar en todas", width=20, font=("Segoe UI", 10, "bold"))
    btn.pack(anchor="w", **pad)

    salida = scrolledtext.ScrolledText(win, height=10, state="disabled")
    salida.pack(fill="both", expand=True, **pad)

    def log(linea):
        def _w():
            salida.config(state="normal"); salida.insert("end", linea + "\n")
            salida.see("end"); salida.config(state="disabled")
        win.after(0, _w)

    def publicar():
        texto = caja.get("1.0", "end").strip()
        elegidas = [r for r, v in marcas.items() if v.get()]
        if not texto and not archivo.get():
            messagebox.showwarning("Falta contenido", "Escribe un texto o elige un archivo."); return
        if not elegidas:
            messagebox.showwarning("Sin redes", "Marca al menos una red."); return
        if not simular.get() and not messagebox.askyesno(
                "Confirmar", "¿Publicar ahora en: " + ", ".join(NOMBRES[r] for r in elegidas) + "?"):
            return
        btn.config(state="disabled")
        log("— " + ("Simulando" if simular.get() else "Publicando") + " —")

        def trabajo():
            fallos = publicar_todo(alm, texto, archivo.get(), e_link.get().strip(),
                                   elegidas, simular.get(), log)
            log("Terminado sin errores." if not fallos else f"Terminado con {fallos} error(es).")
            win.after(0, lambda: btn.config(state="normal"))
        threading.Thread(target=trabajo, daemon=True).start()

    btn.config(command=publicar)
    refrescar()
    if alm.config_nueva:
        log("Bienvenido. Antes de conectar tus cuentas, pulsa 'Datos de apps' y pega los "
            "identificadores de tus apps (se hace una sola vez, ver LEEME.md).")
    win.mainloop()


# ======================================================================= Línea de comandos
def main():
    if len(sys.argv) == 1:
        return abrir_ventana()
    ap = argparse.ArgumentParser(description="Publica en varias redes sociales a la vez")
    ap.add_argument("texto", nargs="?", default="", help="Texto de la publicación")
    ap.add_argument("--archivo", help="Imagen o video de tu PC")
    ap.add_argument("--link", help="Enlace a compartir")
    ap.add_argument("--redes", help="Lista separada por comas (por defecto: todas las conectadas)")
    ap.add_argument("--carpeta", help="Carpeta de config.json y cuentas.json")
    ap.add_argument("--simular", action="store_true", help="No publica, solo muestra qué haría")
    ap.add_argument("--conectar", choices=["facebook", "x", "linkedin"], help="Iniciar sesión en una red")
    a = ap.parse_args()
    alm = Almacen(a.carpeta)

    if a.conectar:
        res = LOGINS[a.conectar](alm)
        if a.conectar == "facebook":
            for i, p in enumerate(res):
                print(f"{i + 1}. {p['name']}")
            n = int(input("Número de la Página: ") or 1) if len(res) > 1 else 1
            guardar_pagina_meta(alm, res[n - 1])
        print("Conectado.")
        return
    redes = a.redes.split(",") if a.redes else list(REDES)
    sys.exit(1 if publicar_todo(alm, a.texto, a.archivo, a.link, redes, a.simular) else 0)


if __name__ == "__main__":
    main()
