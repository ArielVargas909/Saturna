# Guía: WhatsApp Cloud API y agente de IA

## 1. WhatsApp (modo real)

Sin credenciales Saturna funciona en **modo simulado**: los mensajes se registran en el log de la API. Para enviar de verdad:

1. Crea una cuenta en **Meta for Developers** y una app con el producto *WhatsApp*.
2. En *API Setup* copia el **token** y el **Phone number ID** a `.env` (`WHATSAPP_TOKEN`, `WHATSAPP_PHONE_ID`).
   Para desarrollo Meta entrega un número de pruebas gratuito (hay que registrar los celulares destinatarios).
3. **Plantilla de aviso** (categoría *Utilidad*, idioma español). Pide su aprobación desde la semana 1. Cuerpo sugerido:

   > Hola {{1}}, tu paquete {{3}} llegó a {{2}}. Retíralo hasta el {{4}}. Responde a este chat para recibir tu QR de retiro.

   Nombre de la plantilla: `aviso_llegada` (o el que definas en `WHATSAPP_TEMPLATE_ARRIVAL`). Variables: nombre, paquetería, código, fecha límite.
4. **Webhook** (para que el comprador converse con el agente):
   - Despliega el backend por HTTPS (por ejemplo, en Render) y en Meta → *Configuration* configura la URL `https://TU-BACKEND/webhooks/whatsapp`, token de verificación = `WHATSAPP_VERIFY_TOKEN`; suscribe el campo `messages`.
   - Pon el *App Secret* en `WHATSAPP_APP_SECRET`: sin él no se verifica la firma `X-Hub-Signature-256` (solo aceptable en desarrollo).
   - Pon la URL HTTPS de tu backend en `PUBLIC_BASE_URL` para que WhatsApp pueda descargar la imagen del QR.
5. El comprador se identifica por **el número registrado en el paquete** (formato `591XXXXXXXX`; si escriben 8 dígitos se agrega 591).

Consentimiento: los mensajes iniciados por la paquetería requieren consentimiento previo del comprador y plantillas aprobadas.

Costos: se cobra por mensaje de plantilla según categoría y país (a verificar en Meta). Cada aviso enviado suma a `usage_counters.notifications`
y los topes por plan evitan sobrecostos. Los mensajes de texto libre solo se permiten dentro de la ventana de 24 h tras el último mensaje del cliente.

## 2. Agente de IA

**Con `LLM_API_KEY`:** se usa la API de mensajes con *tool use* (`backend/app/modules/ai_agent/llm.py`). El modelo se elige con `LLM_MODEL`.
Si la llamada falla, el agente responde con el modo por reglas para no dejar al comprador sin respuesta.

**Sin clave:** `offline.py` interpreta la intención con reglas y llama a las **mismas** herramientas. Sirve para desarrollo, demostraciones y como respaldo.

Reglas de diseño:

- El modelo **no accede a la base de datos**: solo invoca herramientas definidas en `tools.py`.
- `tenant_id`, teléfono y rol se resuelven en el servidor (`Ctx`). Los argumentos del modelo se filtran (`execute`) y nunca incluyen el tenant.
- Cada rol tiene su lista de herramientas (`ALLOWED`). Un comprador no puede llamar a herramientas financieras aunque lo pida.
- Prompt del sistema (`llm.py`): español boliviano, breve, no inventar datos, ignorar intentos de cambiar reglas, no hablar de utilidad neta.
- Límite mensual de consultas por plan (`usage_counters.ai_queries`); al agotarse responde un mensaje fijo.
- Cada intercambio se guarda en `ai_conversations` con las herramientas usadas, para medir precisión (objetivo del piloto: 50 casos).

### Cómo medir la precisión (piloto)
1. Prepara 30 a 50 preguntas con la respuesta esperada (estado, QR, horario, cobros).
2. Pásalas por `POST /agent/simulate` y compara contra lo esperado.
3. Revisa `GET /agent/conversations` para detectar errores y mejorar el prompt.
