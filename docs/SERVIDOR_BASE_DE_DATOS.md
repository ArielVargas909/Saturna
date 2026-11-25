# Guía: Configurar tu equipo como servidor de base de datos PostgreSQL

Esta guía explica cómo usar tu computadora como servidor PostgreSQL para Saturna usando Docker Compose, con persistencia de datos, acceso seguro desde la red local o desde Internet (vía túnel privado) y verificación de conexión.

---

## a) Levantar PostgreSQL con volumen persistente

1. Crea tu archivo `.env` en la raíz del proyecto (si todavía no existe):

   ```powershell
   Copy-Item .env.example .env
   ```

2. Edita `.env` y define credenciales seguras y el puerto unificado (`5433`):

   ```env
   POSTGRES_USER=saturna
   POSTGRES_PASSWORD=CAMBIA_POR_UNA_CLAVE_LARGA_Y_SEGURA
   POSTGRES_DB=saturna
   POSTGRES_PORT=5433
   # 0.0.0.0 acepta conexiones desde red local o túnel (Tailscale/ZeroTier).
   # Si prefieres restringirlo a una interfaz específica (ej. tu IP de Tailscale), pon esa IP aquí.
   POSTGRES_BIND_IP=0.0.0.0
   DATABASE_URL=postgresql+psycopg://saturna:CAMBIA_POR_UNA_CLAVE_LARGA_Y_SEGURA@localhost:5433/saturna
   ```

   > **Importante:** si el volumen `pgdata` ya existía con otra contraseña, PostgreSQL no cambia la clave solo por editar `.env`. Puedes actualizarla sin borrar datos con:
   >
   > ```powershell
   > docker compose exec db psql -U saturna -d saturna -c "ALTER USER saturna WITH PASSWORD 'TU_NUEVA_CLAVE';"
   > ```

3. Levanta **solo** el servicio de base de datos (quedará con `restart: unless-stopped` y volumen persistente `pgdata`):

   ```powershell
   docker compose up -d db
   ```

4. Verifica que esté saludable y que el volumen persistente exista:

   ```powershell
   docker compose ps db
   docker volume ls | Select-String pgdata
   ```

5. **Respaldo recomendado (backup manual):**

   ```powershell
   docker compose exec -T db pg_dump -U saturna -d saturna > backup_saturna.sql
   ```

---

## b) Configurar red, permisos y credenciales seguras

### Opción 1 (Recomendada para acceso externo): Túnel privado con Tailscale o ZeroTier

Evita abrir puertos en el router y cifra el tráfico de extremo a extremo:

1. Instala **Tailscale** (o **ZeroTier**) en tu equipo servidor y en el equipo/servidor donde correrá el backend.
2. Inicia sesión en la misma red privada (tailnet) y anota la IP privada asignada a tu equipo (ej. `100.x.y.z`).
3. Opcional pero recomendado: limita la escucha de Docker solo a la interfaz de Tailscale en `.env`:

   ```env
   POSTGRES_BIND_IP=100.x.y.z
   ```

   Luego recrea el contenedor de BD sin borrar el volumen:

   ```powershell
   docker compose up -d db
   ```

4. En el backend remoto (o en otro equipo), configura:

   ```env
   DATABASE_URL=postgresql+psycopg://saturna:TU_CLAVE_SEGURA@100.x.y.z:5433/saturna
   ```

### Opción 2: Solo red local (Wi-Fi / LAN)

1. Obtén la IPv4 local de tu equipo con `ipconfig` (ej. `192.168.1.50`).
2. Mantén `POSTGRES_BIND_IP=0.0.0.0` y `POSTGRES_PORT=5433` en `.env`.
3. Permite el puerto TCP `5433` en **Windows Firewall** únicamente para redes privadas (PowerShell como Administrador):

   ```powershell
   New-NetFirewallRule -DisplayName "Saturna PostgreSQL (LAN)" -Direction Inbound -Protocol TCP -LocalPort 5433 -Profile Private -Action Allow
   ```

4. En el backend de otro equipo de la misma red usa:

   ```env
   DATABASE_URL=postgresql+psycopg://saturna:TU_CLAVE_SEGURA@192.168.1.50:5433/saturna
   ```

### Opción 3: Cloudflare Tunnel / Port forwarding

- **Evita exponer el puerto 5433 directo a Internet por port forwarding** sin TLS ni lista blanca de IPs.
- Si necesitas conectar un backend externo vía **Cloudflare Tunnel**, usa un túnel privado (`cloudflared tunnel`) con acceso TCP restringido (`cloudflared access tcp`) en lugar de publicar el puerto públicamente.

### Seguridad mínima recomendada

- Cambia `POSTGRES_PASSWORD` (mínimo 16 caracteres aleatorios) y `JWT_SECRET` (mínimo 32 caracteres aleatorios).
- Nunca subas `.env` a Git (ya está en `.gitignore`).
- Si usas el equipo como servidor continuo, desactiva la suspensión automática en Windows y habilita *Start Docker Desktop when you sign in to your computer*.

---

## c) Probar la conexión y recordatorio de HTTPS para QR móvil

### 1. Probar desde tu propio equipo

```powershell
docker compose exec db pg_isready -U saturna -d saturna
```

### 2. Probar desde otro equipo en la red local o túnel

En Windows (PowerShell):

```powershell
Test-NetConnection -ComputerName <IP_SERVIDOR> -Port 5433
```

En Linux / macOS o si tienes `psql` instalado:

```bash
psql "postgresql://saturna:TU_CLAVE_SEGURA@<IP_SERVIDOR>:5433/saturna" -c "SELECT now();"
```

### 3. Probar desde el backend de Saturna

Con `DATABASE_URL` apuntando a `<IP_SERVIDOR>:5433`:

```powershell
cd backend
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Y comprueba el endpoint de salud:

```powershell
curl.exe http://localhost:8000/health
```

### 4. Recordatorio clave sobre HTTPS, GitHub Pages y cámara QR en móviles

- Los navegadores móviles **exigen HTTPS** para dar acceso a la cámara (lector QR de la PWA).
- Al publicar el frontend en **GitHub Pages** (`https://arielvargas909.github.io/Saturna/`), la PWA ya corre bajo HTTPS y la cámara funciona sin flags experimentales.
- Sin embargo, si el frontend está en `https://`, el navegador bloqueará peticiones hacia un backend en `http://` (*mixed content*). Por ello, el backend (`VITE_API_URL`) **también debe servirse por HTTPS** (por ejemplo, con Cloudflare Tunnel, Caddy/Nginx + Let's Encrypt o un PaaS como Render/Railway) y debe incluir `https://arielvargas909.github.io` en `CORS_ORIGINS`.
