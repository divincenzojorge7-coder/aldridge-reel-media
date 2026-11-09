"""Corta un video madre en varios Shorts que NO se solapan entre si, los pasa
a 9:16, normaliza el audio, quema subtitulos y verifica con el guardian de
originalidad que ninguno repita contenido de otro video o Short.

Uso:
  python herramientas/shorts.py proponer --archivo madre.mp4 [--n 6]
  python herramientas/shorts.py cortar --madre 20261109-1 --archivo madre.mp4 \
         --segmentos segmentos.json [--sin-subtitulos]

segmentos.json: [{"inicio": 0.0, "fin": 22.5, "titulo": "..."}, ...]
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import originalidad as og  # noqa: E402

BASE = og.BASE
CFG = og.CONFIG


def silencios(archivo):
    """Pausas de la narracion: buenos puntos de corte."""
    r = subprocess.run(
        ["ffmpeg", "-i", str(archivo), "-af", "silencedetect=n=-32dB:d=0.35",
         "-f", "null", "-"], capture_output=True, text=True)
    fines = [float(x) for x in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return sorted(fines)


def proponer(archivo, n):
    """Reparte el video en n tramos contiguos, ajustando cada corte a la pausa
    mas cercana para no cortar frases."""
    total = og.duracion(archivo)
    lo, hi = CFG["duracion_short_seg"]
    n = max(1, min(n, int(total // lo)))
    pausas = silencios(archivo)
    cortes, inicio = [], 0.0
    for k in range(1, n):
        ideal = total * k / n
        candidatos = [p for p in pausas if inicio + lo <= p <= min(inicio + hi, total - lo)]
        corte = min(candidatos, key=lambda p: abs(p - ideal)) if candidatos else min(inicio + hi, ideal)
        cortes.append((inicio, corte))
        inicio = corte
    cortes.append((inicio, total))
    segs = [{"inicio": round(a, 2), "fin": round(b, 2)} for a, b in cortes]
    return {"duracion_total": round(total, 2), "segmentos": segs,
            "avisos": [f"tramo {i+1} dura {s['fin']-s['inicio']:.1f}s, fuera de {lo}-{hi}s"
                       for i, s in enumerate(segs) if not lo <= s["fin"] - s["inicio"] <= hi]}


def validar(segs, total):
    lo, hi = CFG["duracion_short_seg"]
    errores = []
    segs = sorted(segs, key=lambda s: s["inicio"])
    for i, s in enumerate(segs):
        d = s["fin"] - s["inicio"]
        if not lo <= d <= hi:
            errores.append(f"tramo {i+1}: dura {d:.1f}s (permitido {lo}-{hi})")
        if s["inicio"] < 0 or s["fin"] > total + 0.5:
            errores.append(f"tramo {i+1}: fuera del video")
        if i and s["inicio"] < segs[i - 1]["fin"] - 0.05:
            errores.append(f"tramo {i+1} se solapa con el tramo {i}: los Shorts no pueden repetir contenido")
    return segs, errores


def subtitulos(archivo, srt):
    """Transcribe con faster-whisper (usa la GPU si hay CUDA)."""
    from faster_whisper import WhisperModel
    try:
        modelo = WhisperModel(CFG["modelo_whisper"], device="cuda", compute_type="float16")
    except Exception:
        modelo = WhisperModel(CFG["modelo_whisper"], device="cpu", compute_type="int8")
    partes, _ = modelo.transcribe(str(archivo), language=CFG["idioma"], word_timestamps=True)

    def ts(t):
        h, r = divmod(t, 3600)
        m, s = divmod(r, 60)
        return f"{int(h):02}:{int(m):02}:{int(s):02},{int((s % 1) * 1000):03}"

    lineas, n = [], 1
    for p in partes:  # bloques cortos de 3 palabras: estilo Shorts
        palabras = p.words or []
        for i in range(0, len(palabras), 3):
            g = palabras[i:i + 3]
            texto = " ".join(w.word.strip() for w in g).upper()
            lineas.append(f"{n}\n{ts(g[0].start)} --> {ts(g[-1].end)}\n{texto}\n")
            n += 1
    Path(srt).write_text("\n".join(lineas), encoding="utf-8")


def cortar_uno(origen, destino, inicio, fin, con_subs):
    tmp = destino.with_suffix(".tmp.mp4")
    # 9:16 a 1080x1920: si el origen es horizontal se recorta el centro
    vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-ss", f"{inicio}", "-to", f"{fin}", "-i", str(origen),
         "-vf", vf, "-af", "loudnorm=I=-14:TP=-1.5:LRA=11",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-c:a", "aac", "-b:a", "160k",
         "-movflags", "+faststart", str(tmp)], check=True)
    if not con_subs:
        tmp.replace(destino)
        return
    srt = destino.with_suffix(".srt")
    subtitulos(tmp, srt)
    estilo = ("FontName=Arial,FontSize=16,Bold=1,PrimaryColour=&H00FFFFFF,"
              "OutlineColour=&H00000000,BorderStyle=1,Outline=3,Alignment=2,MarginV=90")
    # se ejecuta dentro de la carpeta para evitar el escapado de rutas de Windows (C\:)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", tmp.name, "-vf",
         f"subtitles={srt.name}:force_style='{estilo}'", "-c:a", "copy",
         "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-movflags", "+faststart",
         destino.name], check=True, cwd=destino.parent)
    tmp.unlink(missing_ok=True)


def cortar(madre_id, archivo, segmentos, con_subs):
    archivo = Path(archivo).resolve()
    total = og.duracion(archivo)
    segs, errores = validar(segmentos, total)
    if errores:
        return {"ok": False, "errores": errores}
    salida = og.DATOS / "videos" / madre_id
    salida.mkdir(parents=True, exist_ok=True)
    con = og.conectar()
    # la madre se registra para que otros videos no puedan copiarla
    og.video_registrar(con, madre_id, archivo)
    aceptados, rechazados = [], []
    for i, s in enumerate(segs, 1):
        sid = f"{madre_id}-s{i}"
        destino = salida / f"{sid}.mp4"
        cortar_uno(archivo, destino, s["inicio"], s["fin"], con_subs)
        r = og.video_check(con, sid, destino, madre_id)
        info = {"id": sid, "archivo": str(destino), "inicio": s["inicio"], "fin": s["fin"],
                "titulo": s.get("titulo", ""), "chequeo": r}
        if r["repetido"]:
            destino.rename(destino.with_suffix(".rechazado.mp4"))
            rechazados.append(info)
        else:
            og.video_registrar(con, sid, destino, madre_id)
            aceptados.append(info)
    return {"ok": True, "madre": madre_id, "aceptados": aceptados, "rechazados": rechazados}


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("proponer")
    s.add_argument("--archivo", required=True)
    s.add_argument("--n", type=int, default=CFG["shorts_por_madre"])
    s = sub.add_parser("cortar")
    s.add_argument("--madre", required=True)
    s.add_argument("--archivo", required=True)
    s.add_argument("--segmentos", required=True)
    s.add_argument("--sin-subtitulos", action="store_true")
    a = p.parse_args(argv)
    if a.cmd == "proponer":
        r = proponer(a.archivo, a.n)
    else:
        segs = json.loads(Path(a.segmentos).read_text(encoding="utf-8"))
        r = cortar(a.madre, a.archivo, segs, not a.sin_subtitulos)
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r.get("ok", True) else 1


if __name__ == "__main__":
    sys.exit(main())
