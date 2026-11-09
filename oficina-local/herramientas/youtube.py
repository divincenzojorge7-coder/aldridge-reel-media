"""Acceso directo a la API de YouTube: subir y programar, curva de retencion
real (para la alarma del segundo 3) y busqueda de outliers (10x la media).

Primera vez:  python herramientas/youtube.py auth
  (necesita datos/client_secret.json, ver README)

Uso:
  python herramientas/youtube.py subir --archivo s.mp4 --titulo "..." --descripcion "..." \
         [--miniatura m.jpg] [--publicar-en 2026-11-10T18:00:00-03:00] [--etiquetas a,b]
  python herramientas/youtube.py retencion --video VIDEO_ID
  python herramientas/youtube.py outliers --consulta "curiosidades historia" [--dias 7] [--max 25]
  python herramientas/youtube.py mis-videos [--max 50]

Cuota diaria por defecto: 10.000 unidades. Subir ~1.600, buscar 100, el resto ~1.
"""
import argparse
import datetime as dt
import json
import re
import statistics
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
SECRETO = BASE / "datos" / "client_secret.json"
TOKEN = BASE / "datos" / "token_youtube.json"
SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]


def credenciales(interactivo=False):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    cred = Credentials.from_authorized_user_file(str(TOKEN), SCOPES) if TOKEN.exists() else None
    if cred and cred.expired and cred.refresh_token:
        cred.refresh(Request())
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
    if not cred or not cred.valid:
        if not interactivo:
            sys.exit(json.dumps({"ok": False, "error": "Sin token de YouTube. Ejecuta: python herramientas/youtube.py auth"}))
        from google_auth_oauthlib.flow import InstalledAppFlow
        cred = InstalledAppFlow.from_client_secrets_file(str(SECRETO), SCOPES).run_local_server(port=0)
        TOKEN.write_text(cred.to_json(), encoding="utf-8")
    return cred


def api(nombre="youtube", version="v3"):
    from googleapiclient.discovery import build
    return build(nombre, version, credentials=credenciales(), cache_discovery=False)


def segundos_iso(d):
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", d or "")
    if not m:
        return 0
    dd, h, mi, s = (int(x or 0) for x in m.groups())
    return dd * 86400 + h * 3600 + mi * 60 + s


def subir(archivo, titulo, descripcion, miniatura=None, publicar_en=None, etiquetas=None):
    from googleapiclient.http import MediaFileUpload
    yt = api()
    status = {
        "privacyStatus": "private" if publicar_en else "public",
        "selfDeclaredMadeForKids": False,
        "containsSyntheticMedia": CFG["youtube"]["contiene_contenido_sintetico"],
    }
    if publicar_en:
        status["publishAt"] = publicar_en
    cuerpo = {
        "snippet": {"title": titulo[:100], "description": descripcion[:5000],
                    "tags": etiquetas or [], "categoryId": CFG["youtube"]["categoria_id"],
                    "defaultLanguage": CFG["idioma"], "defaultAudioLanguage": CFG["idioma"]},
        "status": status,
    }
    req = yt.videos().insert(part="snippet,status", body=cuerpo,
                             media_body=MediaFileUpload(str(archivo), chunksize=-1, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    vid = resp["id"]
    r = {"ok": True, "video_id": vid, "url": f"https://youtube.com/shorts/{vid}",
         "programado_para": publicar_en}
    if miniatura:
        try:
            yt.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(miniatura))).execute()
            r["miniatura"] = "ok"
        except Exception as e:  # los canales sin verificar no pueden subir miniaturas
            r["miniatura"] = f"no aplicada: {e}"
    return r


def retencion(video_id):
    yt = api()
    v = yt.videos().list(part="contentDetails,statistics,snippet", id=video_id).execute()["items"]
    if not v:
        return {"ok": False, "error": "video no encontrado"}
    dur = segundos_iso(v[0]["contentDetails"]["duration"])
    publicado = v[0]["snippet"]["publishedAt"][:10]
    hoy = dt.date.today().isoformat()
    ya = api("youtubeAnalytics", "v2")
    curva = ya.reports().query(
        ids="channel==MINE", startDate=publicado, endDate=hoy,
        metrics="audienceWatchRatio,relativeRetentionPerformance",
        dimensions="elapsedVideoTimeRatio", filters=f"video=={video_id}",
    ).execute().get("rows", [])
    gen = ya.reports().query(
        ids="channel==MINE", startDate=publicado, endDate=hoy,
        metrics="views,averageViewDuration,averageViewPercentage",
        filters=f"video=={video_id}",
    ).execute().get("rows", [[None, None, None]])[0]
    r = {"ok": True, "video_id": video_id, "duracion_seg": dur,
         "vistas": gen[0], "duracion_media_vista_seg": gen[1], "porcentaje_medio_visto": gen[2],
         "curva": [{"seg": round(x * dur, 1), "retencion": round(y, 3)} for x, y, _ in curva]}
    if curva and dur:
        objetivo = 3 / dur
        punto = min(curva, key=lambda f: abs(f[0] - objetivo))
        r["retencion_seg3"] = round(punto[1], 3)
        r["caida_seg3"] = punto[1] < CFG["youtube"]["umbral_caida_seg3"]
    else:
        r["retencion_seg3"] = None
        r["caida_seg3"] = None
        r["nota"] = "YouTube aun no tiene curva para este video (suele tardar 24-48 h o requerir mas vistas)"
    return r


def outliers(consulta, dias=7, maximo=25):
    yt = api()
    desde = (dt.datetime.utcnow() - dt.timedelta(days=dias)).strftime("%Y-%m-%dT%H:%M:%SZ")
    res = yt.search().list(part="snippet", q=consulta, type="video", order="viewCount",
                           publishedAfter=desde, maxResults=min(maximo, 50),
                           relevanceLanguage=CFG["idioma"]).execute()
    ids = [i["id"]["videoId"] for i in res.get("items", [])]
    if not ids:
        return {"ok": True, "videos": []}
    vids = yt.videos().list(part="statistics,snippet,contentDetails", id=",".join(ids)).execute()["items"]
    medias = {}
    for cid in {v["snippet"]["channelId"] for v in vids}:
        ch = yt.channels().list(part="contentDetails", id=cid).execute()["items"]
        if not ch:
            continue
        up = ch[0]["contentDetails"]["relatedPlaylists"]["uploads"]
        ult = yt.playlistItems().list(part="contentDetails", playlistId=up, maxResults=20).execute()
        uids = [i["contentDetails"]["videoId"] for i in ult.get("items", [])]
        st = yt.videos().list(part="statistics", id=",".join(uids)).execute()["items"] if uids else []
        vistas = [int(s["statistics"].get("viewCount", 0)) for s in st]
        medias[cid] = statistics.median(vistas) if vistas else None
    salida = []
    for v in vids:
        vistas = int(v["statistics"].get("viewCount", 0))
        media = medias.get(v["snippet"]["channelId"])
        mult = round(vistas / media, 1) if media else None
        salida.append({
            "video_id": v["id"], "titulo": v["snippet"]["title"], "canal": v["snippet"]["channelTitle"],
            "url": f"https://youtube.com/watch?v={v['id']}", "vistas": vistas,
            "mediana_canal": media, "multiplo": mult, "alarma_10x": bool(mult and mult >= 10),
            "duracion_seg": segundos_iso(v["contentDetails"]["duration"]),
        })
    salida.sort(key=lambda x: -(x["multiplo"] or 0))
    return {"ok": True, "consulta": consulta, "videos": salida,
            "nota": "multiplo = vistas / mediana de los ultimos 20 videos del canal"}


def mis_videos(maximo=50):
    yt = api()
    ch = yt.channels().list(part="contentDetails,snippet", mine=True).execute()["items"][0]
    up = ch["contentDetails"]["relatedPlaylists"]["uploads"]
    it = yt.playlistItems().list(part="contentDetails,snippet", playlistId=up, maxResults=min(maximo, 50)).execute()
    return {"ok": True, "canal": ch["snippet"]["title"],
            "videos": [{"video_id": i["contentDetails"]["videoId"], "titulo": i["snippet"]["title"],
                        "publicado": i["contentDetails"].get("videoPublishedAt")} for i in it.get("items", [])]}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth")
    s = sub.add_parser("subir")
    s.add_argument("--archivo", required=True)
    s.add_argument("--titulo", required=True)
    s.add_argument("--descripcion", required=True)
    s.add_argument("--miniatura")
    s.add_argument("--publicar-en", help="ISO 8601 con zona, p. ej. 2026-11-10T18:00:00-03:00")
    s.add_argument("--etiquetas", default="")
    s = sub.add_parser("retencion")
    s.add_argument("--video", required=True)
    s = sub.add_parser("outliers")
    s.add_argument("--consulta", required=True)
    s.add_argument("--dias", type=int, default=7)
    s.add_argument("--max", type=int, default=25)
    s = sub.add_parser("mis-videos")
    s.add_argument("--max", type=int, default=50)
    a = p.parse_args(argv)
    if a.cmd == "auth":
        credenciales(interactivo=True)
        r = {"ok": True, "token": str(TOKEN)}
    elif a.cmd == "subir":
        r = subir(a.archivo, a.titulo, a.descripcion, a.miniatura, a.publicar_en,
                  [e.strip() for e in a.etiquetas.split(",") if e.strip()])
    elif a.cmd == "retencion":
        r = retencion(a.video)
    elif a.cmd == "outliers":
        r = outliers(a.consulta, a.dias, a.max)
    else:
        r = mis_videos(a.max)
    print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
