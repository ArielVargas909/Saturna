"""Agente por reglas: mismo conjunto de herramientas, sin modelo de lenguaje.
Sirve para desarrollo/demo sin API key y como respaldo si el LLM falla."""
import re

from app.modules.ai_agent import tools

CODE = re.compile(r"SAT-[A-Z0-9]{6}", re.I)
SCHEDULE_HINT = re.compile(
    r"(agend|coordin|cita|paso |pasar[eé]|voy a |ir[eé] |puedo pasar|puedo ir|"
    r"(hoy|ma[ñn]ana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado).*\d{1,2}(:\d{2})?|"
    r"a las \d{1,2}(:\d{2})?)",
    re.I,
)
TIME_EXPR = re.compile(
    r"((?:hoy|ma[ñn]ana|pasado ma[ñn]ana|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado)"
    r"(?:\s+(?:a las\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm|hrs?)?|\s+(?:por la )?(?:ma[ñn]ana|tarde|noche))?"
    r"|(?:a las\s+)?\d{1,2}(?::\d{2})?\s*(?:am|pm|hrs?)|\b\d{1,2}:\d{2}\b)",
    re.I,
)


def _lines(items: list[dict]) -> str:
    return "\n".join(f"• {i['codigo']}: {i['estado']} (hasta {i['plazo_hasta']})" for i in items)


def _fee_suffix(r: dict) -> str:
    if "cobro_estimado_bs" not in r:
        return ""
    if r.get("dias_de_retraso", 0) > 0:
        return (
            f" Cobro estimado: Bs {r['cobro_estimado_bs']:.2f} "
            f"(incluye recargo por {r['dias_de_retraso']} día(s) de demora)."
        )
    return f" Cobro estimado: Bs {r['cobro_estimado_bs']:.2f}."


def _code_from_history(history: list[dict] | None) -> str:
    for item in reversed(history or []):
        content = item.get("content")
        if isinstance(content, str):
            m = CODE.search(content)
            if m:
                return m.group(0).upper()
    return ""


def respond(ctx: tools.Ctx, text: str, history: list[dict] | None = None) -> tuple[str, list[str]]:
    t = text.lower()
    m = CODE.search(text)
    code = m.group(0).upper() if m else ""
    history_code = "" if code else _code_from_history(history)
    used: list[str] = []

    def call(name: str, **kw) -> dict:
        used.append(name)
        return tools.execute(ctx, name, kw)

    if ctx.role == "owner" and re.search(r"cobr|ingres|cu[aá]nto (gan|hice|vend)", t):
        periodo = "semana" if "semana" in t else "mes" if "mes" in t else "hoy"
        r = call("resumen_cobros", periodo=periodo)
        if "error" in r:
            return r["error"], used
        return (
            f"Cobros de {r['periodo']}: Bs {r['total_cobrado_bs']:.2f} "
            f"(efectivo Bs {r['efectivo_bs']:.2f}, QR Bs {r['qr_bs']:.2f}) en {r['cantidad_de_cobros']} cobros. "
            "Son cobros registrados, no utilidad."
        ), used

    if ctx.role == "owner" and re.search(r"estanc|vencer|venc|atrasad", t):
        r = call("paquetes_estancados")
        if "error" in r:
            return r["error"], used
        return (
            ("Paquetes por vencer o estancados:\n" + _lines(r["paquetes"]))
            if r["paquetes"]
            else "No hay paquetes por vencer. ¡Todo al día!"
        ), used

    if re.search(r"ubicaci|mapa|gps|d[oó]nde (est[aá]n|queda|quedan)|c[oó]mo lleg", t):
        r = call("enviar_ubicacion", codigo=code or history_code)
        if "error" in r:
            return r["error"], used
        lines = []
        for u in r["ubicaciones"]:
            map_txt = f" Mapa: {u['maps_url']}" if u["maps_url"] else ""
            lines.append(f"{u['nombre']}: {u['direccion']} (Horario: {u['horario']}).{map_txt}")
        return "\n".join(lines), used

    if ctx.role == "buyer" and SCHEDULE_HINT.search(text) and not re.search(r"\bqr\b", t):
        target_code = code or history_code
        if not target_code:
            r = call("listar_mis_paquetes")
            if len(r["paquetes"]) == 1:
                target_code = r["paquetes"][0]["codigo"]
            else:
                return "¿Para qué paquete quieres agendar el retiro? Envíame el código (ej. SAT-AB12CD).", used
        tm = TIME_EXPR.search(text)
        slot = tm.group(0).strip() if tm else ""
        if not slot:
            return f"¿Qué día y hora aproximada pasarás por {target_code}? (Ej: Mañana 16:00).", used
        r = call("agendar_retiro", codigo=target_code, horario=slot)
        if "error" in r:
            return r["error"], used
        return (
            f"¡Listo! Anotamos tu retiro para {r['codigo']}: {r['horario_acordado']} en {r['paqueteria']} "
            f"(atención: {r['horario_atencion']}). Cuando vayas, escríbeme “QR {r['codigo']}”."
        ), used

    if re.search(r"horario|atienden|abren|abre|direcci|condici|requisit|tarifa|cu[aá]nto cuesta|recargo|c[oó]mo retir", t):
        target_code = code or history_code
        if target_code and re.search(r"recargo|tarifa|cuesta|pagar|costo", t):
            r = call("consultar_estado_paquete", codigo=target_code)
            if "error" in r:
                return r["error"], used
            return (
                f"Tu paquete {r['codigo']} en {r['paqueteria']}: {r['estado']}. "
                f"Plazo hasta {r['plazo_custodia_hasta']}.{_fee_suffix(r)}"
            ), used
        r = call("horario_de_atencion", codigo=target_code)
        if not r["paqueterias"]:
            return "No encuentro paquetes asociados a tu número.", used
        lines = []
        for p in r["paqueterias"]:
            lines.append(
                f"{p['nombre']}: {p['horario']} — {p['direccion']}. "
                f"Custodia: {p['dias_custodia']} día(s), tarifa Bs {p['tarifa_custodia_bs']:.2f} "
                f"(recargo Bs {p['recargo_diario_bs']:.2f}/día). {p['condiciones_retiro']}"
            )
        return "\n".join(lines), used

    if re.search(r"\bqr\b|retir|recoger|recojo", t):
        target_code = code or history_code
        if not target_code:
            r = call("listar_mis_paquetes")
            if len(r["paquetes"]) == 1:
                target_code = r["paquetes"][0]["codigo"]
            else:
                return "¿De qué paquete? Envíame el código (ej. SAT-AB12CD).", used
        r = call("solicitar_qr_retiro", codigo=target_code)
        if "error" in r:
            return r["error"], used
        return (
            f"Listo, te envié tu QR de retiro para {r['codigo']}. "
            f"Vence el {r['vence']} y sirve una sola vez.{_fee_suffix(r)}"
        ), used

    if code:
        r = call("consultar_estado_paquete", codigo=code)
        if "error" in r:
            return r["error"], used
        cita = f" Retiro agendado: {r['horario_retiro_acordado']}." if r.get("horario_retiro_acordado") else ""
        return (
            f"Tu paquete {r['codigo']} en {r['paqueteria']}: {r['estado']}. "
            f"Llegó el {r['llego']}; plazo hasta {r['plazo_custodia_hasta']}.{cita}{_fee_suffix(r)}"
        ), used

    r = call("listar_mis_paquetes")
    if not r["paquetes"]:
        return "No encuentro paquetes pendientes asociados a tu número.", used
    return "Tus paquetes:\n" + _lines(r["paquetes"]) + "\nEscribe “QR” + el código para retirarlo.", used
