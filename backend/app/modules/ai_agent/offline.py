"""Agente por reglas: mismo conjunto de herramientas, sin modelo de lenguaje.
Sirve para desarrollo/demo sin API key y como respaldo si el LLM falla."""
import re

from app.modules.ai_agent import tools

CODE = re.compile(r"SAT-[A-Z0-9]{6}", re.I)


def _lines(items: list[dict]) -> str:
    return "\n".join(f"• {i['codigo']}: {i['estado']} (hasta {i['plazo_hasta']})" for i in items)


def respond(ctx: tools.Ctx, text: str) -> tuple[str, list[str]]:
    t = text.lower()
    m = CODE.search(text)
    code = m.group(0).upper() if m else ""
    used: list[str] = []

    def call(name: str, **kw) -> dict:
        used.append(name)
        return tools.execute(ctx, name, kw)

    if ctx.role == "owner" and re.search(r"cobr|ingres|cu[aá]nto (gan|hice|vend)", t):
        periodo = "semana" if "semana" in t else "mes" if "mes" in t else "hoy"
        r = call("resumen_cobros", periodo=periodo)
        if "error" in r:
            return r["error"], used
        return (f"Cobros de {r['periodo']}: Bs {r['total_cobrado_bs']:.2f} "
                f"(efectivo Bs {r['efectivo_bs']:.2f}, QR Bs {r['qr_bs']:.2f}) en {r['cantidad_de_cobros']} cobros. "
                "Son cobros registrados, no utilidad."), used
    if ctx.role == "owner" and re.search(r"estanc|vencer|venc|atrasad", t):
        r = call("paquetes_estancados")
        if "error" in r:
            return r["error"], used
        return ("Paquetes por vencer o estancados:\n" + _lines(r["paquetes"])) if r["paquetes"] else \
            "No hay paquetes por vencer. ¡Todo al día!", used
    if re.search(r"horario|atienden|abren|abre|direcci", t):
        r = call("horario_de_atencion", codigo=code)
        if not r["paqueterias"]:
            return "No encuentro paquetes asociados a tu número.", used
        return "\n".join(f"{p['nombre']}: {p['horario']} — {p['direccion']}" for p in r["paqueterias"]), used
    if re.search(r"\bqr\b|retir|recoger|recojo", t):
        if not code:
            r = call("listar_mis_paquetes")
            if len(r["paquetes"]) == 1:
                code = r["paquetes"][0]["codigo"]
            else:
                return "¿De qué paquete? Envíame el código (ej. SAT-AB12CD).", used
        r = call("solicitar_qr_retiro", codigo=code)
        if "error" in r:
            return r["error"], used
        return f"Listo, te envié tu QR de retiro. Vence el {r['vence']} y sirve una sola vez.", used
    if code:
        r = call("consultar_estado_paquete", codigo=code)
        if "error" in r:
            return r["error"], used
        extra = f" Cobro estimado: Bs {r['cobro_estimado_bs']:.2f}." if "cobro_estimado_bs" in r else ""
        return (f"Tu paquete {r['codigo']} en {r['paqueteria']}: {r['estado']}. "
                f"Llegó el {r['llego']}; plazo hasta {r['plazo_custodia_hasta']}.{extra}"), used
    r = call("listar_mis_paquetes")
    if not r["paquetes"]:
        return "No encuentro paquetes pendientes asociados a tu número.", used
    return "Tus paquetes:\n" + _lines(r["paquetes"]) + "\nEscribe “QR” + el código para retirarlo.", used
