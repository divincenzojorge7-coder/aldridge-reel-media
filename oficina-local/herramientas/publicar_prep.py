"""Prepara un Short para publicarlo por Metricool sin pasar por la API de YouTube.

Metricool descarga el video desde un enlace (por ejemplo, de Google Drive). Esta
herramienta copia el Short a la carpeta local que Google Drive para escritorio
sincroniza (config.json -> publicacion.carpeta_drive), ordenado por canal, y
devuelve el nombre exacto del archivo para que el agente Studio lo localice en
Drive con el conector y lo pase a Metricool.

Uso:
  python herramientas/publicar_prep.py copiar --archivo short.mp4 --canal canal1 --id 20261112-canal1-1-s2
  python herramientas/publicar_prep.py limpiar --canal canal1 --dias 7   # borra copias ya publicadas
"""
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
CFG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))


def carpeta(canal):
    raiz = (CFG["publicacion"].get("carpeta_drive") or "").strip()
    if not raiz:
        raise SystemExit(json.dumps({"ok": False, "error": "Falta publicacion.carpeta_drive en config.json (carpeta sincronizada con Google Drive)."}))
    p = Path(raiz)
    if not p.is_dir():
        raise SystemExit(json.dumps({"ok": False, "error": f"La carpeta {p} no existe. Instala Google Drive para escritorio."}))
    d = p / canal
    d.mkdir(exist_ok=True)
    return d


def copiar(archivo, canal, item_id):
    origen = Path(archivo)
    if not origen.is_file():
        return {"ok": False, "error": f"No existe {origen}"}
    destino = carpeta(canal) / f"{item_id}.mp4"
    if destino.exists() and destino.stat().st_size == origen.stat().st_size:
        return {"ok": True, "ya_estaba": True, "nombre": destino.name, "canal": canal, "ruta": str(destino)}
    tmp = destino.with_suffix(".mp4.tmp")
    shutil.copy2(origen, tmp)
    tmp.replace(destino)   # Drive no sube el archivo hasta que tiene su nombre final
    return {"ok": True, "ya_estaba": False, "nombre": destino.name, "canal": canal, "ruta": str(destino),
            "nota": "Drive tarda de segundos a minutos en subirlo; busca el archivo por nombre con el conector de Drive."}


def limpiar(canal, dias):
    d = carpeta(canal)
    limite = time.time() - dias * 86400
    borrados = []
    for f in d.glob("*.mp4"):
        if f.stat().st_mtime < limite:
            f.unlink()
            borrados.append(f.name)
    return {"ok": True, "borrados": borrados}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("copiar")
    s.add_argument("--archivo", required=True)
    s.add_argument("--canal", required=True)
    s.add_argument("--id", required=True)
    s = sub.add_parser("limpiar")
    s.add_argument("--canal", required=True)
    s.add_argument("--dias", type=int, default=7)
    a = p.parse_args(argv)
    r = copiar(a.archivo, a.canal, a.id) if a.cmd == "copiar" else limpiar(a.canal, a.dias)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
