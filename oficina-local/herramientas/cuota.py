"""Libro de cuota de la API de YouTube.

La cuota es POR PROYECTO de Google Cloud, no por canal: todos los canales que
usan el mismo client_secret.json comparten las mismas unidades diarias. Este
libro (datos/cuota.json) cuenta lo gastado hoy, en el dia del Pacifico de EE. UU.
(a esa hora se reinicia la cuota de Google), para no chocar con quotaExceeded.

Uso:
  python herramientas/cuota.py estado
  python herramientas/cuota.py puede --accion subida [--cantidad 1]
  python herramientas/cuota.py gastar --accion busqueda [--cantidad 1]
  python herramientas/cuota.py agotada          # marca el dia como agotado

Es una estimacion local: si Google cambia los costes, edita config.json -> cuota.
Si algo ajeno al sistema usa el mismo proyecto, la cuota real sera menor.
"""
import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))
Q = CFG["cuota"]
DATOS = Path(os.environ.get("OFICINA_DATOS", BASE / "datos"))
LIBRO = DATOS / "cuota.json"


def hoy():
    return dt.datetime.now(ZoneInfo(Q["zona"])).date().isoformat()


def cargar():
    if LIBRO.exists():
        d = json.loads(LIBRO.read_text(encoding="utf-8"))
        if d.get("dia") == hoy():
            return d
    return {"dia": hoy(), "usadas": 0, "agotada": False, "detalle": {}}


def guardar(d):
    LIBRO.parent.mkdir(parents=True, exist_ok=True)
    tmp = LIBRO.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, indent=2), encoding="utf-8")
    tmp.replace(LIBRO)


def coste(accion, cantidad=1):
    return Q["coste"][accion] * cantidad


def disponible(d=None):
    d = d or cargar()
    return 0 if d["agotada"] else max(0, Q["limite_diario"] - d["usadas"])


def puede(accion, cantidad=1):
    """Una subida con miniatura cuenta subida + miniatura."""
    extra = Q["coste"]["miniatura"] if accion == "subida" else 0
    return disponible() >= coste(accion, cantidad) + extra


def gastar(accion, cantidad=1):
    d = cargar()
    u = coste(accion, cantidad)
    d["usadas"] += u
    d["detalle"][accion] = d["detalle"].get(accion, 0) + u
    guardar(d)
    return d


def marcar_agotada():
    d = cargar()
    d["agotada"] = True
    guardar(d)


def estado():
    d = cargar()
    sub = Q["coste"]["subida"] + Q["coste"]["miniatura"]
    return {
        "dia_pacifico": d["dia"], "limite": Q["limite_diario"], "usadas": d["usadas"],
        "disponibles": disponible(d), "agotada": d["agotada"],
        "subidas_aun_posibles_hoy": disponible(d) // sub, "detalle": d["detalle"],
        "nota": "Estimacion local. Se reinicia a medianoche hora del Pacifico (05:00 en Argentina).",
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("estado")
    sub.add_parser("agotada")
    for n in ("puede", "gastar"):
        s = sub.add_parser(n)
        s.add_argument("--accion", required=True, choices=list(Q["coste"]))
        s.add_argument("--cantidad", type=int, default=1)
    a = p.parse_args(argv)
    if a.cmd == "estado":
        r = estado()
    elif a.cmd == "agotada":
        marcar_agotada()
        r = estado()
    elif a.cmd == "puede":
        r = {"puede": puede(a.accion, a.cantidad), **estado()}
    else:
        gastar(a.accion, a.cantidad)
        r = estado()
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("puede", True) else 1


if __name__ == "__main__":
    sys.exit(main())
