"""Guardian de originalidad: impide repetir temas, ganchos, guiones, titulos,
escenas y fragmentos de video entre videos madre y Shorts.

Todo se guarda en datos/originalidad.db (SQLite). Cada comando imprime JSON
para que los agentes lo lean.

Uso:
  python herramientas/originalidad.py texto-check --tipo gancho --texto "..."
  python herramientas/originalidad.py texto-registrar --tipo gancho --id 20261109-1 --texto "..."
  python herramientas/originalidad.py video-check --id 20261109-1-s2 --archivo short.mp4 --madre 20261109-1
  python herramientas/originalidad.py video-registrar --id 20261109-1-s2 --archivo short.mp4 --madre 20261109-1
  python herramientas/originalidad.py estado
"""
import argparse
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

import numpy as np
from PIL import Image

BASE = Path(__file__).resolve().parent.parent
DATOS = Path(os.environ.get("OFICINA_DATOS", BASE / "datos"))  # carpeta de datos (cambiable para pruebas)
DB = DATOS / "originalidad.db"
CONFIG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
UMBRAL = CONFIG["originalidad"]

# ---------------------------------------------------------------- base de datos

def conectar():
    DB.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB)
    con.executescript(
        """
        CREATE TABLE IF NOT EXISTS textos(
            id INTEGER PRIMARY KEY, tipo TEXT, item_id TEXT, texto TEXT,
            motor TEXT, vector BLOB, creado REAL);
        CREATE INDEX IF NOT EXISTS ix_textos_tipo ON textos(tipo);
        CREATE TABLE IF NOT EXISTS videos(
            item_id TEXT PRIMARY KEY, madre_id TEXT, archivo TEXT,
            duracion REAL, creado REAL);
        CREATE TABLE IF NOT EXISTS fotogramas(
            item_id TEXT, madre_id TEXT, t REAL, phash INTEGER);
        CREATE INDEX IF NOT EXISTS ix_fot_item ON fotogramas(item_id);
        """
    )
    return con

# ---------------------------------------------------------------- texto

_modelo = None


def _normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", texto).split()


def _vector_trigramas(texto):
    """Respaldo sin IA: trigramas de caracteres en un vector hash de 4096."""
    v = np.zeros(4096, dtype=np.float32)
    s = " " + " ".join(_normalizar(texto)) + " "
    for i in range(len(s) - 2):
        v[_h(s[i:i + 3])] += 1.0
    n = np.linalg.norm(v)
    return v / n if n else v


def _h(s):
    # hash estable entre ejecuciones (hash() de Python cambia por proceso)
    h = 2166136261
    for c in s.encode("utf-8"):
        h = ((h ^ c) * 16777619) & 0xFFFFFFFF
    return h % 4096


def vectorizar(texto):
    """Devuelve (motor, vector normalizado)."""
    global _modelo
    if _modelo is None:
        try:
            from sentence_transformers import SentenceTransformer
            _modelo = SentenceTransformer(CONFIG["modelo_embeddings"])
        except Exception:
            _modelo = False
    if _modelo:
        v = _modelo.encode([texto], normalize_embeddings=True)[0].astype(np.float32)
        return "st", v
    return "trigramas", _vector_trigramas(texto)


def texto_check(con, tipo, texto, excluir_id=None):
    motor, v = vectorizar(texto)
    umbral = UMBRAL["texto"][tipo]
    if motor == "trigramas":
        umbral = UMBRAL["texto_respaldo"][tipo]
    filas = con.execute(
        "SELECT item_id, texto, vector FROM textos WHERE tipo=? AND motor=?",
        (tipo, motor),
    ).fetchall()
    mejor = (0.0, None, None)
    for item_id, otro, blob in filas:
        if excluir_id and item_id == excluir_id:
            continue
        s = float(np.dot(v, np.frombuffer(blob, dtype=np.float32)))
        if s > mejor[0]:
            mejor = (s, item_id, otro)
    return {
        "tipo": tipo,
        "repetido": mejor[0] >= umbral,
        "similitud": round(mejor[0], 3),
        "umbral": umbral,
        "motor": motor,
        "mas_parecido_id": mejor[1],
        "mas_parecido_texto": mejor[2],
        "comparado_con": len(filas),
    }


def texto_registrar(con, tipo, item_id, texto):
    motor, v = vectorizar(texto)
    con.execute(
        "INSERT INTO textos(tipo,item_id,texto,motor,vector,creado) VALUES(?,?,?,?,?,?)",
        (tipo, item_id, texto, motor, v.tobytes(), time.time()),
    )
    con.commit()
    return {"registrado": True, "tipo": tipo, "id": item_id, "motor": motor}

# ---------------------------------------------------------------- video

_DCT = None


def _phash(img):
    """pHash de 64 bits (DCT 32x32 -> bloque 8x8), sin dependencias extra."""
    global _DCT
    if _DCT is None:
        n = 32
        k = np.arange(n)
        _DCT = np.sqrt(2 / n) * np.cos(np.pi * (2 * k[None, :] + 1) * k[:, None] / (2 * n))
        _DCT[0] /= np.sqrt(2)
    a = np.asarray(img.convert("L").resize((32, 32), Image.LANCZOS), dtype=np.float64)
    d = (_DCT @ a @ _DCT.T)[:8, :8]
    bits = (d > np.median(np.delete(d.ravel(), 0))).ravel()  # sin el termino DC
    valor = 0
    for b in bits:
        valor = (valor << 1) | int(b)
    return valor - (1 << 63)  # cabe en INTEGER con signo de SQLite


_TABLA = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint8)


def _popcount(x):
    """Bits a 1 de cada uint64 (distancia de Hamming tras un XOR)."""
    if hasattr(np, "bitwise_count"):
        return np.bitwise_count(x)
    return _TABLA[x.view(np.uint8)].reshape(-1, 8).sum(axis=1)


def duracion(archivo):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(archivo)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def fotogramas(archivo):
    """Un fotograma por segundo (config: fps_muestreo) -> lista de (t, phash)."""
    fps = UMBRAL["video"]["fps_muestreo"]
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(archivo), "-vf",
             f"fps={fps},scale=160:-2", os.path.join(tmp, "f_%05d.png")],
            check=True,
        )
        res = []
        for i, f in enumerate(sorted(Path(tmp).glob("f_*.png"))):
            with Image.open(f) as img:
                res.append((i / fps, _phash(img)))
    return res


def video_check(con, item_id, archivo, madre_id=None):
    """Compara el video con TODOS los registrados excepto el mismo id y su
    propia madre (un Short se corta de su madre, pero no puede solaparse con
    otro Short ni con otros videos)."""
    u = UMBRAL["video"]
    propios = fotogramas(archivo)
    filas = con.execute(
        "SELECT item_id, madre_id, t, phash FROM fotogramas WHERE item_id != ?",
        (item_id,),
    ).fetchall()
    otros = [(i, t, h) for i, m, t, h in filas if not (madre_id and i == madre_id)]
    coincidencias = {}
    gancho_repetido = None
    iguales = 0
    if otros:
        ids = [o[0] for o in otros]
        tiempos = [o[1] for o in otros]
        hashes = (np.array([o[2] for o in otros], dtype=np.int64)).view(np.uint64)
    for t, h in propios:
        if not otros:
            break
        dist = _popcount(hashes ^ np.array([h], dtype=np.int64).view(np.uint64)[0])
        j = int(np.argmin(dist))
        if dist[j] <= u["distancia_hamming"]:
            iguales += 1
            coincidencias[ids[j]] = coincidencias.get(ids[j], 0) + 1
            if t < u["segundos_gancho"] and not gancho_repetido:
                gancho_repetido = {"t": t, "video": ids[j], "t_otro": tiempos[j]}
    proporcion = iguales / len(propios) if propios else 0.0
    repetido = proporcion > u["max_proporcion_repetida"] or (
        u["gancho_debe_ser_unico"] and gancho_repetido is not None)
    return {
        "id": item_id,
        "repetido": repetido,
        "proporcion_repetida": round(proporcion, 3),
        "max_permitida": u["max_proporcion_repetida"],
        "gancho_visual_repetido": gancho_repetido,
        "videos_que_coinciden": dict(sorted(coincidencias.items(), key=lambda x: -x[1])[:5]),
        "fotogramas_analizados": len(propios),
    }


def video_registrar(con, item_id, archivo, madre_id=None):
    propios = fotogramas(archivo)
    con.execute("DELETE FROM fotogramas WHERE item_id=?", (item_id,))
    con.executemany(
        "INSERT INTO fotogramas(item_id,madre_id,t,phash) VALUES(?,?,?,?)",
        [(item_id, madre_id, t, h) for t, h in propios],
    )
    con.execute(
        "INSERT OR REPLACE INTO videos(item_id,madre_id,archivo,duracion,creado) VALUES(?,?,?,?,?)",
        (item_id, madre_id, str(archivo), duracion(archivo), time.time()),
    )
    con.commit()
    return {"registrado": True, "id": item_id, "fotogramas": len(propios)}

# ---------------------------------------------------------------- CLI

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    tipos = list(UMBRAL["texto"].keys())
    for nombre in ("texto-check", "texto-registrar"):
        s = sub.add_parser(nombre)
        s.add_argument("--tipo", required=True, choices=tipos)
        s.add_argument("--texto", required=True)
        s.add_argument("--id", required=(nombre == "texto-registrar"))
    for nombre in ("video-check", "video-registrar"):
        s = sub.add_parser(nombre)
        s.add_argument("--id", required=True)
        s.add_argument("--archivo", required=True)
        s.add_argument("--madre")
    sub.add_parser("estado")
    a = p.parse_args(argv)
    con = conectar()
    if a.cmd == "texto-check":
        r = texto_check(con, a.tipo, a.texto, a.id)
    elif a.cmd == "texto-registrar":
        r = texto_registrar(con, a.tipo, a.id, a.texto)
    elif a.cmd == "video-check":
        r = video_check(con, a.id, a.archivo, a.madre)
    elif a.cmd == "video-registrar":
        r = video_registrar(con, a.id, a.archivo, a.madre)
    else:
        r = {
            "textos": dict(con.execute("SELECT tipo, COUNT(*) FROM textos GROUP BY tipo").fetchall()),
            "videos": con.execute("SELECT COUNT(*) FROM videos").fetchone()[0],
            "fotogramas": con.execute("SELECT COUNT(*) FROM fotogramas").fetchone()[0],
        }
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 1 if r.get("repetido") else 0


if __name__ == "__main__":
    sys.exit(main())
