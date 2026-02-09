import discord
from discord.ext import commands
import json
import os
import random
import uuid
from keep_alive import keep_alive

TOKEN = os.getenv("DISCORD_TOKEN")  # nombre de la variable
if not TOKEN:
    raise RuntimeError("❌ Falta la variable de entorno DISCORD_TOKEN")
# =============================
# CONFIG
# =============================
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# =============================
# DATA - REV
# =============================
def load_data():
    if not os.path.exists(DATA_FILE):
        base = {
            "rol_admin_torneo_id": None,
            "rol_streamer_id": None,
            "torneos": {},       # (legacy) 1 torneo por guild
            "servidores": {}     # (nuevo) multi torneos por guild
        }
        ensure_schema(base)
        return base

    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # asegurar llaves nuevas sin romper lo viejo
    data.setdefault("rol_admin_torneo_id", None)
    data.setdefault("rol_streamer_id", None)
    data.setdefault("torneos", {})
    data.setdefault("servidores", {})

    # migración suave a esquema multi
    ensure_schema(data)
    return data

# =============================
# Def ensure schema - REV
# =============================
def ensure_schema(data: dict):
    """
    Garantiza estructura multi-servidor/multi-torneo.
    Migra el esquema viejo data["torneos"][guild_id] -> servidores[guild]["torneos"]["DEFAULT"]
    SOLO si ese DEFAULT aún no existe.
    """
    data.setdefault("servidores", {})
    data.setdefault("torneos", {})  # legacy (puede existir)

    # Migración suave y NO destructiva
    if isinstance(data["torneos"], dict):
        for gid, torneo_obj in list(data["torneos"].items()):
            # solo migra si la key parece guild_id (int o str numérica)
            if not (isinstance(gid, int) or (isinstance(gid, str) and gid.isdigit())):
                continue

            gid_str = str(gid)

            srv = data["servidores"].setdefault(gid_str, {})
            torneos_srv = srv.setdefault("torneos", {})

            # Solo crear DEFAULT si no existe ya
            if "DEFAULT" not in torneos_srv:
                torneos_srv["DEFAULT"] = torneo_obj

            srv.setdefault("activo", "DEFAULT")
# =============================
# Def Save Data - REV
# =============================
def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

# ✅ IMPORTANTE: esta línea debe ir DESPUÉS de ensure_schema
data = load_data()
# =============================
# Def Get Torneo - REV
# =============================
def get_torneo(data, torneo_id):
    data.setdefault("torneos", {})

    if torneo_id not in data["torneos"]:
        data["torneos"][torneo_id] = {
            "nombre": None,
            "equipos": [],
            "partidos": [],
            "formato_partidos": None,
            "tabla": {},
        }

    return data["torneos"][torneo_id]
# =============================
# Def Set Torneo Activo (WRAPPER) -REV
# =============================
def set_torneo_activo(data, torneo_id):
    torneo = get_torneo(data, torneo_id)
    data["torneo"] = torneo
    return torneo
# =============================
# Compat: set_torneo_activo para multi - REV
# =============================
def set_torneo_activo_multi(data, guild_id: int, torneo_uid: str):
    set_activo(data, guild_id, torneo_uid)
    torneo = get_torneo_v2(data, guild_id, torneo_uid)

    # Para compatibilidad con rutas viejas que usan data["torneo"]
    data["torneo"] = torneo
    return torneo
# =============================
# Def get_server - REV
# =============================
def get_server(data: dict, guild_id: int) -> dict:
    ensure_schema(data)
    gid = str(guild_id)
    srv = data["servidores"].setdefault(gid, {})
    srv.setdefault("torneos", {})
    srv.setdefault("activo", "DEFAULT")
    return srv
# =============================
# Def new torneo - REV
# =============================
def new_torneo_uid() -> str:
    return uuid.uuid4().hex[:6].upper()
# =============================
# Def get torneo v2 - REV
# =============================
def get_torneo_v2(data: dict, guild_id: int, torneo_uid: str | None = None) -> dict:
    """
    Devuelve el torneo del server. Si no se pasa uid, usa el activo.
    Crea si no existe.
    """
    srv = get_server(data, guild_id)
    if not torneo_uid:
        torneo_uid = srv.get("activo", "DEFAULT")

    torneos = srv.setdefault("torneos", {})
    torneo = torneos.get(torneo_uid)
    if torneo is None:
        torneo = {}
        torneos[torneo_uid] = torneo

    # Campo útil dentro del torneo
    torneo.setdefault("torneo_uid", torneo_uid)

    # ✅ estructura mínima (igual que tu get_torneo legacy)
    torneo.setdefault("nombre", None)
    torneo.setdefault("equipos", [])
    torneo.setdefault("partidos", [])
    torneo.setdefault("formato_partidos", None)
    torneo.setdefault("tabla", {})

    return torneo
# =============================
# Def ensure schema - REV
# =============================
def set_activo(data: dict, guild_id: int, torneo_uid: str):
    srv = get_server(data, guild_id)
    srv["activo"] = torneo_uid
# =============================
# DEF ENSURE MULTI TORNEO SCHEMA - REV
# =============================
def ensure_multi_torneo_schema(data: dict, guild_id: int):
    # Alias: usa tu esquema actual
    return get_server(data, guild_id)
# =============================
# DEF SET TORNEO ACTIVO UID - REV
# =============================
def set_torneo_activo_uid(data: dict, guild_id: int, uid: str):
    # Alias: activa un UID
    return set_activo(data, guild_id, uid)
# =============================
# DEF GET TORNEO MULTI -REV
# =============================
def get_torneo_multi(data: dict, guild_id: int, uid: str | None = None) -> dict:
    # Alias: obtiene torneo por UID (o activo)
    return get_torneo_v2(data, guild_id, uid)
# =============================
# Torneo activo por defecto (fallback) - REV
# =============================
# Si por alguna razón no existe data["torneo"], apuntamos al torneo ACTIVO del server actual.
# (En callbacks/slash siempre recargas data y llamas set_torneo_activo_multi con guild_id)
if "torneo" not in data:
    data["torneo"] = {}
# =============================
# DEFAULTS DEL TORNEO - REV
# =============================
data.setdefault("torneo", {})
data["torneo"].setdefault("formato_partidos", None)
# =============================
# EXTRAS TORNEO-REV (MULTI) - REV
# =============================
def init_tabla_multi(guild_id: int, torneo_uid: str | None = None):
    """
    Inicializa tabla del torneo indicado (UID) o del torneo ACTIVO del servidor.
    """
    global data
    data = load_data()

    torneo = get_torneo_v2(data, guild_id, torneo_uid)

    tabla = {}
    for e in torneo.get("equipos", []):
        tabla[e["nombre"]] = {
            "pj": 0,
            "pg": 0,
            "pp": 0,
            "pts": 0
        }

    torneo["tabla"] = tabla
    save_data(data)
# =============================
# async def Crear categoria y canal-REV1 (TRACK)
# =============================
async def crear_categoria_y_canal(guild, categoria_nombre, canal_nombre, torneo_uid: str | None = None):
    # ✅ cargar data para poder trackear recursos
    global data
    data = load_data()

    # ✅ resolver UID si no viene (usa torneo activo del server)
    if not torneo_uid:
        try:
            torneo_uid = get_server(data, guild.id).get("activo", "DEFAULT")
        except:
            torneo_uid = "DEFAULT"

    # ✅ obtener torneo correcto y dejarlo activo (compat)
    try:
        set_torneo_activo_multi(data, guild.id, torneo_uid)
        torneo = get_torneo_v2(data, guild.id, torneo_uid)
    except:
        torneo = None

    # ======== TU LÓGICA ORIGINAL (NO SE CAMBIA) ========
    categoria = discord.utils.get(guild.categories, name=categoria_nombre)
    if not categoria:
        categoria = await guild.create_category(categoria_nombre)

    canal = discord.utils.get(categoria.text_channels, name=canal_nombre)
    if not canal:
        canal = await guild.create_text_channel(canal_nombre, category=categoria)

    # ======== ✅ NUEVO: TRACK RECURSOS (SIN AFECTAR LÓGICA) ========
    try:
        if torneo is not None:
            # registrar categoría y canal
            track_recurso_torneo(torneo, categoria_id=categoria.id)
            track_recurso_torneo(torneo, canal_id=canal.id)
            # compat: dejar apuntando data["torneo"] al torneo correcto
            set_torneo_activo_multi(data, guild.id, torneo_uid)
            save_data(data)
    except:
        pass

    return canal
# =============================
# EXTRAS ELIMINATORIAS-REV (MULTI) - REV1
# =============================
def generar_brackets_eliminatoria_multi(guild_id: int, torneo_uid: str | None = None):
    global data
    data = load_data()

    torneo = get_torneo_v2(data, guild_id, torneo_uid)

    tabla = torneo.get("tabla", {})
    ordenados = sorted(tabla.items(), key=lambda x: x[1]["pts"], reverse=True)
    equipos = [e[0] for e in ordenados]

    brackets = []
    pid = 1

    for i in range(0, len(equipos), 2):
        if i + 1 < len(equipos):
            brackets.append({
                "id": pid,
                "a": equipos[i],
                "b": equipos[i + 1],
                "resultado": None,
                "ganador": None,
                "bloqueado": False
            })
            pid += 1

    torneo["eliminatorias"] = brackets
    save_data(data)
# =============================
# MODALES-REV
# =============================
class NombreTorneoModal(discord.ui.Modal):
    def __init__(self, torneo_uid: str):
        super().__init__(title="Definir nombre del torneo")
        self.torneo_uid = torneo_uid

        self.nombre = discord.ui.TextInput(
            label="Nombre del torneo",
            placeholder="Ej: TNL 18vs18"
        )

        self.logo = discord.ui.TextInput(
            label="Logo del torneo (Imgur directo opcional)",
            placeholder="https://i.imgur.com/xxxx.png",
            required=False
        )

        self.add_item(self.nombre)
        self.add_item(self.logo)

    async def callback(self, interaction: discord.Interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        torneo["creador"] = interaction.user.id

        logo = self.logo.value.strip() if self.logo.value else None

        if logo:
            if not logo.startswith("https://i.imgur.com/"):
                await interaction.response.send_message(
                    "❌ El logo debe ser un link directo de Imgur (i.imgur.com)",
                    ephemeral=True
                )
                return

            if not logo.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                await interaction.response.send_message(
                    "❌ El logo debe terminar en .png, .jpg, .jpeg o .webp",
                    ephemeral=True
                )
                return

        torneo["nombre"] = self.nombre.value
        torneo["logo"] = logo

        # ✅ compat: apunta data["torneo"] al torneo correcto
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)

        save_data(data)

        await interaction.response.send_message(
            "✅ Nombre y logo guardados correctamente",
            ephemeral=True
        )
# =============================
# MODAL Equipo-REV - REV
# =============================
class EquipoModal(discord.ui.Modal):
    def __init__(self, torneo_uid: str):
        super().__init__(title="Añadir equipo")
        self.torneo_uid = torneo_uid

        self.nombre = discord.ui.TextInput(
            label="Nombre del equipo",
            placeholder="Ej: Team Alpha"
        )

        self.logo = discord.ui.TextInput(
            label="Logo del equipo (Imgur directo opcional)",
            placeholder="https://i.imgur.com/xxxx.png",
            required=False
        )

        self.add_item(self.nombre)
        self.add_item(self.logo)

    async def callback(self, interaction: discord.Interaction):
        logo = self.logo.value.strip() if self.logo.value else None

        if logo:
            if not logo.startswith("https://i.imgur.com/"):
                await interaction.response.send_message(
                    "❌ El logo debe ser un link directo de Imgur",
                    ephemeral=True
                )
                return

            if not logo.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                await interaction.response.send_message(
                    "❌ El logo debe terminar en .png, .jpg, .jpeg o .webp",
                    ephemeral=True
                )
                return

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        torneo["equipos"].append({
            "nombre": self.nombre.value,
            "logo": logo
        })

        # ✅ compat: apunta data["torneo"] al torneo correcto
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)

        save_data(data)

        await interaction.response.send_message(
            f"✅ Equipo **{self.nombre.value}** añadido",
            ephemeral=True
        )
# =============================
#  MODAL FECHA + ESTADO - Rev (MULTI)
# =============================
class FechaEstadoModal(discord.ui.Modal):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(title=f"Actualizar Partido {partido_id}")
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid

        self.fecha = discord.ui.TextInput(
            label="Fecha y hora",
            placeholder="Ej: 15/01/2026 20:00"
        )

        self.estado = discord.ui.TextInput(
            label="Estado del partido",
            placeholder="🕒 Pendiente / 🟢 En juego / 🔴 Finalizado"
        )

        self.add_item(self.fecha)
        self.add_item(self.estado)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo.get("partidos", []):
            if str(p.get("id")) == str(self.partido_id):
                p["fecha"] = self.fecha.value
                p["estado"] = self.estado.value

                # compat
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await actualizar_todos_los_mensajes_partido(interaction.guild, p)
                await actualizar_mensaje_publico_partido(interaction.guild, p)

                await interaction.followup.send(
                    "✅ Partido actualizado correctamente",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
#  MODAL EDITAR SOLO FECHA - Rev (MULTI)
# =============================
class EditarFechaModal(discord.ui.Modal):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(title=f"Editar fecha - Partido {partido_id}")
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid

        self.fecha = discord.ui.TextInput(
            label="Nueva fecha y hora",
            placeholder="Ej: 18/01/2026 21:00"
        )

        self.add_item(self.fecha)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo.get("partidos", []):
            if str(p.get("id")) == str(self.partido_id):
                p["fecha"] = self.fecha.value

                # compat
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await actualizar_todos_los_mensajes_partido(interaction.guild, p)
                await actualizar_mensaje_publico_partido(interaction.guild, p)

                await interaction.followup.send(
                    "✅ Fecha actualizada correctamente",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# MODAL EDITAR SOLO ESTADO - MULTI
# =============================
class EditarEstadoModal(discord.ui.Modal):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(title=f"Editar estado - Partido {partido_id}")
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid

        self.estado = discord.ui.TextInput(
            label="Estado del partido",
            placeholder="🕒 Pendiente / 🟢 En juego / 🔴 Finalizado"
        )

        self.add_item(self.estado)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo.get("partidos", []):
            if str(p.get("id")) == str(self.partido_id):
                p["estado"] = self.estado.value

                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await actualizar_todos_los_mensajes_partido(interaction.guild, p)
                await actualizar_mensaje_publico_partido(interaction.guild, p)

                await interaction.followup.send(
                    "✅ Estado actualizado correctamente",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# MODAL Resultado - REV (FIX)  [MULTI]
# =============================
class ResultadoModal(discord.ui.Modal):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(title=f"Resultado Partido {partido_id}")
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

        self.resultado = discord.ui.TextInput(
            label="Resultado (Ej: 2-1)"
        )
        self.add_item(self.resultado)

    async def callback(self, interaction: discord.Interaction):
        # ✅ responder rápido para evitar 10062
        await interaction.response.defer(ephemeral=True)

        res = self.resultado.value.split("-")
        if len(res) != 2:
            await interaction.followup.send("❌ Formato inválido. Usa 2-1", ephemeral=True)
            return

        try:
            g1, g2 = int(res[0]), int(res[1])
        except ValueError:
            await interaction.followup.send("❌ Formato inválido. Usa números (Ej: 2-1)", ephemeral=True)
            return

        # ✅ MULTI: cargar data y tomar torneo por UID
        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if str(p.get("id")) == str(self.partido_id):

                # ===== GUARDAR RESULTADO Y BLOQUEAR =====
                p["resultado"] = self.resultado.value
                p["estado"] = "🔴 Finalizado"
                p["bloqueado"] = True
                save_data(data)

                await actualizar_todos_los_mensajes_partido(interaction.guild, p)
                await actualizar_mensaje_publico_partido(interaction.guild, p)

                # ===== TABLA =====
                # ✅ FIX 1: si tabla NO existe o está vacía -> inicializar
                if not torneo.get("tabla"):
                    init_tabla_multi(guild_id, self.torneo_uid)

                    # ✅ FIX 2: recargar data/torneo porque init_tabla_multi carga/guarda internamente
                    data = load_data()
                    torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

                tabla = torneo.setdefault("tabla", {})

                # ✅ FIX 3: blindaje por si faltan equipos en tabla (evita KeyError)
                def row():
                    return {"pj": 0, "pg": 0, "pp": 0, "pts": 0}

                tabla.setdefault(p["a"], row())
                tabla.setdefault(p["b"], row())

                tabla[p["a"]]["pj"] += 1
                tabla[p["b"]]["pj"] += 1

                if g1 > g2:
                    tabla[p["a"]]["pg"] += 1
                    tabla[p["a"]]["pts"] += 3
                    tabla[p["b"]]["pp"] += 1
                else:
                    tabla[p["b"]]["pg"] += 1
                    tabla[p["b"]]["pts"] += 3
                    tabla[p["a"]]["pp"] += 1

                # ✅ compat: deja data["torneo"] apuntando al torneo correcto
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await interaction.followup.send(
                    "🏁 Resultado registrado, partido cerrado y mensajes actualizados",
                    ephemeral=True
                )

                # ===== CREAR TABLA FINAL SI TODO TERMINÓ =====
                if all(pp.get("bloqueado") for pp in torneo["partidos"]):
                    guild = interaction.guild
                    canal_tabla = await crear_categoria_y_canal(
                        guild,
                        f"📊 CLASIFICACIÓN - {self.torneo_uid}",
                        f"tabla-{self.torneo_uid.lower()}"
                    )

                    # ✅ NUEVO: TRACK de canal + categoría para borrado total por UID (aunque cambien nombres)
                    try:
                        track_recurso_torneo(torneo, canal_id=canal_tabla.id)
                        if getattr(canal_tabla, "category", None):
                            track_recurso_torneo(torneo, categoria_id=canal_tabla.category.id)
                        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                        save_data(data)
                    except:
                        pass

                    embed = discord.Embed(
                        title="📊 Tabla de posiciones",
                        color=discord.Color.green()
                    )

                    for eq, d in sorted(tabla.items(), key=lambda x: x[1]["pts"], reverse=True):
                        embed.add_field(
                            name=eq,
                            value=f"PJ {d['pj']} | PG {d['pg']} | PP {d['pp']} | PTS {d['pts']}",
                            inline=False
                        )

                    await canal_tabla.send(embed=embed)

                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# MODAL Añadir streamers - REV (FIX) [MULTI]
# =============================
class AñadirStreamerModal(discord.ui.Modal):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(title="Añadir streamers (máx 2)")
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid

        self.ids = discord.ui.TextInput(
            label="IDs a aprobar (máx 2, separados por coma)",
            placeholder="123456789,987654321"
        )

        self.canal = discord.ui.TextInput(
            label="Canal del stream (URL o #canal)",
            placeholder="https://twitch.tv/usuario"
        )

        self.add_item(self.ids)
        self.add_item(self.canal)

    async def callback(self, interaction: discord.Interaction):
        # ✅ responder rápido para evitar 10062
        await interaction.response.defer(ephemeral=True)

        ids = [
            int(i.strip())
            for i in self.ids.value.split(",")
            if i.strip().isdigit()
        ]

        if len(ids) > 2:
            await interaction.followup.send(
                "❌ Solo se permiten **2 streamers máximo**",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            # ✅ FIX: tolerante a str/int
            if str(p.get("id")) == str(self.partido_id):

                p.setdefault("streamers_postulados", [])
                p.setdefault("streamers_aprobados", [])
                p.setdefault("streamers", [])

                for uid in ids:
                    if uid not in p["streamers_postulados"]:
                        continue

                    if uid not in p["streamers_aprobados"]:
                        p["streamers_aprobados"].append(uid)
                        p["streamers"].append(
                            f"<@{uid}> — {self.canal.value}"
                        )

                # limpiar postulados aceptados
                p["streamers_postulados"] = [
                    u for u in p["streamers_postulados"]
                    if u not in p["streamers_aprobados"]
                ]

                # compat
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await actualizar_mensaje_publico_partido(interaction.guild, p)
                await actualizar_todos_los_mensajes_partido(interaction.guild, p)

                await interaction.followup.send(
                    "✅ Streamers aprobados y asignados correctamente",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# MODAL Asignar Capitán - REV  [MULTI]
# =============================
class AsignarCapitanModal(discord.ui.Modal):
    def __init__(self, partido_id, equipo, torneo_uid: str):
        super().__init__(title=f"Asignar Capitán Equipo {equipo}")
        self.partido_id = partido_id
        self.equipo = equipo
        self.torneo_uid = torneo_uid

        self.usuario = discord.ui.InputText(
            label="ID del usuario capitán",
            placeholder="1234567890"
        )
        self.add_item(self.usuario)

    async def callback(self, interaction: discord.Interaction):
        # ✅ RESPONDER RÁPIDO PARA EVITAR 10062 (Unknown interaction)
        await interaction.response.defer(ephemeral=True)

        try:
            user_id = int(self.usuario.value)
        except ValueError:
            await interaction.followup.send("❌ ID inválido", ephemeral=True)
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if str(p.get("id")) == str(self.partido_id):

                # 🔒 INICIALIZAR ESTRUCTURA SI NO EXISTE
                p.setdefault(
                    "equipos",
                    {
                        "A": {"capitanes": []},
                        "B": {"capitanes": []}
                    }
                )

                capitanes = p["equipos"][self.equipo].setdefault(
                    "capitanes", []
                )

                if user_id in capitanes:
                    await interaction.followup.send(
                        "⚠️ Ese usuario ya es capitán",
                        ephemeral=True
                    )
                    return

                capitanes.append(user_id)

                # compat
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await actualizar_todos_los_mensajes_partido(
                    interaction.guild, p
                )
                await actualizar_mensaje_publico_partido(
                    interaction.guild, p
                )

                await interaction.followup.send(
                    f"✅ Capitán asignado al **Equipo {self.equipo}**",
                    ephemeral=True
                )

                # 🔄 REFRESCAR SOLO EL MENSAJE DE ELECCIÓN DE BAN
                canal = interaction.guild.get_channel(
                    p.get("canal_partido_id")
                )
                mensaje_id = p.get("mensaje_coinflip_id")

                if canal and mensaje_id:
                    try:
                        msg = await canal.fetch_message(mensaje_id)
                        await msg.edit(
                            # ✅ AQUÍ estaba tu anotación:
                            # antes: ElegirTipoBanView(torneo_id, p["id"])
                            # ahora: pasamos guild_id + torneo_uid + partido_id
                            view=ElegirTipoBanView(guild_id, self.torneo_uid, p["id"])
                        )
                    except:
                        pass

                return

        # ✅ si no se encontró el partido
        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# MODAL Quitar capitan - REV (FIX SIN BORRAR LÓGICA) [MULTI]
# =============================
class QuitarCapitanModal(discord.ui.Modal):
    def __init__(self, partido_id, equipo, torneo_uid: str):
        super().__init__(title=f"Quitar Capitán Equipo {equipo}")
        self.partido_id = partido_id
        self.equipo = equipo
        self.torneo_uid = torneo_uid

        self.usuario = discord.ui.InputText(
            label="ID del usuario a quitar",
            placeholder="1234567890"
        )
        self.add_item(self.usuario)

    async def callback(self, interaction: discord.Interaction):
        # ✅ RESPONDER RÁPIDO PARA EVITAR 10062 (Unknown interaction)
        await interaction.response.defer(ephemeral=True)

        try:
            user_id = int(self.usuario.value)
        except ValueError:
            await interaction.followup.send("❌ ID inválido", ephemeral=True)
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if str(p.get("id")) == str(self.partido_id):

                # 🔒 ASEGURAR ESTRUCTURA (NO CAMBIA LÓGICA)
                if "equipos" not in p:
                    p["equipos"] = {
                        "A": {"capitanes": []},
                        "B": {"capitanes": []}
                    }
                    save_data(data)

                # ✅ si no existe la clave capitanes, blindaje mínimo
                p["equipos"].setdefault("A", {}).setdefault("capitanes", [])
                p["equipos"].setdefault("B", {}).setdefault("capitanes", [])

                if user_id in p["equipos"][self.equipo]["capitanes"]:
                    p["equipos"][self.equipo]["capitanes"].remove(user_id)

                    # compat
                    set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                    save_data(data)

                    await actualizar_todos_los_mensajes_partido(interaction.guild, p)
                    await actualizar_mensaje_publico_partido(interaction.guild, p)

                    await interaction.followup.send(
                        "🗑️ Capitán removido correctamente",
                        ephemeral=True
                    )
                    return

                # si encontró el partido pero ese user no es capitán
                await interaction.followup.send("❌ Ese usuario no es capitán", ephemeral=True)
                return

        # si no encontró el partido
        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# MODAL Map Pool - REV  [MULTI]
# =============================
class MapPoolModal(discord.ui.Modal):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(title="Pool de mapas")
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid

        self.mapas = discord.ui.InputText(
            label="Mapas del pool (uno por línea)",
            placeholder="Omaha\nCarentan\nUtah\nHurtgen",
            style=discord.InputTextStyle.long
        )

        self.add_item(self.mapas)

    async def callback(self, interaction: discord.Interaction):
        # ✅ responder rápido para que no expire la interacción del modal
        await interaction.response.defer(ephemeral=True)

        mapas = [m.strip() for m in self.mapas.value.split("\n") if m.strip()]

        if len(mapas) < 3:
            await interaction.followup.send(
                "🚫 Deben haber al menos 3 mapas",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if p["id"] != self.partido_id:
                continue

            # 🎲 COINFLIP
            ganador = random.choice(["A", "B"])
            perdedor = "B" if ganador == "A" else "A"

            p["fase_baneo"] = {
                "activa": True,
                "coinflip": {
                    "ganador": ganador,
                    "eleccion": None
                },
                "equipos": {
                    ganador: {
                        "tipo": None,
                        "baneos_restantes": 0
                    },
                    perdedor: {
                        "tipo": None,
                        "baneos_restantes": 0
                    }
                },
                "turno_actual": ganador,
                "map_pool": mapas,
                "mapa_actual": mapas[0],
                "baneados": [],
                "historial": [],
                "max_baneos": len(mapas) - 1,
                "mapas": {
                    m: {
                        "baneado": False,
                        "lado_baneado": None,
                        "lado_forzado": None
                    } for m in mapas
                },
                "historial_baneos": []
            }

            # compat
            set_torneo_activo_multi(data, guild_id, self.torneo_uid)
            save_data(data)

            # =============================
            # 📢 CANAL DEL PARTIDO
            # =============================
            canal = interaction.guild.get_channel(p.get("canal_partido_id"))

            if canal:
                nombre_ganador = p["a"] if ganador == "A" else p["b"]
                await canal.send(
                    f"🎲 **Coinflip realizado**\n"
                    f"🏆 Ganador: **{nombre_ganador}**\n\n"
                    f"👉 Elige tu ventaja:",
                    view=ElegirTipoBanView(guild_id, self.torneo_uid, self.partido_id)
                )

                embed = discord.Embed(
                    title="🪙 Coinflip realizado",
                    description=f"⚔️ **{p['a']} vs {p['b']}**",
                    color=discord.Color.gold()
                )

                embed.add_field(
                    name="🏆 Ganador del coinflip",
                    value=f"**{nombre_ganador}**",
                    inline=False
                )

                embed.add_field(
                    name="🔀 Elección",
                    value="Debe elegir **Extra Ban** o **Final Ban**",
                    inline=False
                )

                embed.set_footer(text="Fase de baneo iniciada automáticamente")
                await canal.send(embed=embed)

            # =============================
            # ✅ CONFIRMACIÓN ADMIN
            # =============================
            await interaction.followup.send(
                "✅ Coinflip realizado y publicado en el canal del partido",
                ephemeral=True
            )
            return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
# 📝 MODAL RESULTADO ELIMINATORIO - REV [MULTI]
# =============================
class ResultadoEliminatoriaModal(discord.ui.Modal):
    def __init__(self, torneo_uid: str):
        super().__init__(title="Resultado eliminatorio")
        self.torneo_uid = torneo_uid

        self.match_id = discord.ui.TextInput(label="ID del match")
        self.ganador = discord.ui.TextInput(label="Equipo ganador")

        self.add_item(self.match_id)
        self.add_item(self.ganador)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        try:
            mid = int(self.match_id.value)
        except ValueError:
            await interaction.followup.send("❌ ID inválido", ephemeral=True)
            return

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for b in torneo.get("eliminatorias", []):
            if b["id"] == mid:

                if b.get("bloqueado"):
                    await interaction.followup.send("🔒 Match cerrado", ephemeral=True)
                    return

                b["ganador"] = self.ganador.value
                b["resultado"] = "Finalizado"
                b["bloqueado"] = True

                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await interaction.followup.send(
                    "🏁 Resultado eliminatorio registrado",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Match no encontrado", ephemeral=True)
# =============================
# VIEWS ADMIN CONFIG - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class PanelConfig(discord.ui.View):
    def __init__(self, creador_id, torneo_uid: str | None = None):
        super().__init__(timeout=None)
        self.creador_id = creador_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO (si viene None, se resuelve por torneo activo)

    async def interaction_check(self, interaction: discord.Interaction):
        return interaction.user.id == self.creador_id

    # =============================
    # BOTÓN NOMBRE / LOGO
    # =============================
    @discord.ui.button(
        label="🏷️ Nombre / Logo",
        style=discord.ButtonStyle.primary
    )
    async def nombre(self, button, interaction: discord.Interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        uid = self.torneo_uid or get_server(data, guild_id).get("activo", "DEFAULT")

        await interaction.response.send_modal(NombreTorneoModal(uid))

    # =============================
    # BOTÓN AÑADIR EQUIPO
    # =============================
    @discord.ui.button(
        label="➕ Añadir equipo",
        style=discord.ButtonStyle.success
    )
    async def equipo(self, button, interaction: discord.Interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        uid = self.torneo_uid or get_server(data, guild_id).get("activo", "DEFAULT")

        await interaction.response.send_modal(EquipoModal(uid))

    # =============================
    # BOTÓN VER EQUIPOS
    # =============================
    @discord.ui.button(
        label="📋 Ver equipos",
        style=discord.ButtonStyle.secondary
    )
    async def ver_equipos(self, button, interaction: discord.Interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        uid = self.torneo_uid or get_server(data, guild_id).get("activo", "DEFAULT")

        torneo = get_torneo_v2(data, guild_id, uid)

        equipos = torneo.get("equipos", [])

        if not equipos:
            await interaction.response.send_message(
                "❌ No hay equipos inscritos todavía",
                ephemeral=True
            )
            return

        for e in equipos:
            embed = discord.Embed(
                title=f"🛡️ {e['nombre']}",
                color=discord.Color.blue()
            )
            if e.get("logo"):
                embed.set_thumbnail(url=e["logo"])

            await interaction.channel.send(embed=embed)

        await interaction.response.send_message(
            "📋 Equipos publicados correctamente",
            ephemeral=True
        )

    # =============================
    # BOTÓN INICIAR TORNEO ✅
    # =============================
    @discord.ui.button(
        label="🚀 Iniciar torneo",
        style=discord.ButtonStyle.danger
    )
    async def iniciar(self, button, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        global data
        data = load_data()

        guild_id = interaction.guild.id
        uid = self.torneo_uid or get_server(data, guild_id).get("activo", "DEFAULT")

        torneo = get_torneo_v2(data, guild_id, uid)

        if not torneo.get("nombre") or len(torneo.get("equipos", [])) < 2:
            await interaction.followup.send(
                "❌ Debes definir nombre y al menos 2 equipos",
                ephemeral=True
            )
            return

        # =============================
        # MENSAJE PRINCIPAL
        # =============================
        embed = discord.Embed(
            title=f"🏆 {torneo['nombre']}",
            description="Torneo iniciado oficialmente",
            color=discord.Color.gold()
        )

        if torneo.get("logo"):
            embed.set_thumbnail(url=torneo["logo"])

        await interaction.channel.send(embed=embed)

        for e in torneo["equipos"]:
            e_embed = discord.Embed(
                title=f"🛡️ {e['nombre']}",
                color=discord.Color.blue()
            )
            if e.get("logo"):
                e_embed.set_thumbnail(url=e["logo"])

            await interaction.channel.send(embed=e_embed)

        await interaction.channel.send(
            "🎮 Panel del torneo",
            # ✅ MULTI: llamado correcto -> (guild_id, admin_id, torneo_uid)
            view=(PanelTorneo(guild_id, torneo.get("creador"), uid)
                  if True else PanelTorneo(guild_id, torneo.get("creador"), uid))
        )

        # =============================
        # CREACIÓN DE CANALES  (AISLADOS POR UID)
        # =============================
        guild = interaction.guild
        nombre_torneo = torneo["nombre"]

        canal_info = await crear_categoria_y_canal(
            guild,
            f"🏆 TORNEO - {nombre_torneo} - {uid}",     # ✅ sufijo UID
            f"info-general-{uid.lower()}"              # ✅ sufijo UID
        )

        # ✅ AÑADIDO: track canal + categoría (para poder borrar TODO por UID)
        try:
            if canal_info:
                track_recurso_torneo(torneo, canal_id=canal_info.id)
                if getattr(canal_info, "category", None):
                    track_recurso_torneo(torneo, categoria_id=canal_info.category.id)
        except:
            pass

        canal_equipos = await crear_categoria_y_canal(
            guild,
            f"🏆 TORNEO - {nombre_torneo} - {uid}",     # ✅ sufijo UID
            f"equipos-{uid.lower()}"                   # ✅ sufijo UID
        )

        # ✅ AÑADIDO: track canal + categoría
        try:
            if canal_equipos:
                track_recurso_torneo(torneo, canal_id=canal_equipos.id)
                if getattr(canal_equipos, "category", None):
                    track_recurso_torneo(torneo, categoria_id=canal_equipos.category.id)
        except:
            pass

        # ✅ AÑADIDO: guardar recursos trackeados inmediatamente
        try:
            save_data(data)
        except:
            pass

        embed_info = discord.Embed(
            title=f"🏆 {nombre_torneo}",
            description="Torneo iniciado oficialmente",
            color=discord.Color.gold()
        )

        if torneo.get("logo"):
            embed_info.set_thumbnail(url=torneo["logo"])

        await canal_info.send(embed=embed_info)

        for e in torneo["equipos"]:
            embed_equipo = discord.Embed(
                title=f"🛡️ {e['nombre']}",
                color=discord.Color.blue()
            )
            if e.get("logo"):
                embed_equipo.set_thumbnail(url=e["logo"])

            await canal_equipos.send(embed=embed_equipo)

        # ✅ compat: data["torneo"] apunta a este UID
        set_torneo_activo_multi(data, guild_id, uid)
        save_data(data)

        await interaction.followup.send(
            "✅ Torneo publicado correctamente",
            ephemeral=True
        )
# =============================
#  BOTÓN ADMIN FECHA / ESTADO - REV (FIX) [MULTI]
# =============================
class EditarPartidoButton(discord.ui.Button):
    def __init__(self, admin_id, partido_id, torneo_uid: str):
        super().__init__(
            label=f"🕒 Partido {partido_id}",
            style=discord.ButtonStyle.success
        )
        self.admin_id = admin_id
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if str(p.get("id")) == str(self.partido_id):  # ✅ FIX str/int
                if p.get("bloqueado"):
                    await interaction.response.send_message(
                        "🔒 Este partido ya fue cerrado y no se puede modificar.",
                        ephemeral=True
                    )
                    return

        await interaction.response.send_modal(
            FechaEstadoModal(self.partido_id, self.torneo_uid)  # ✅ ahora pide UID
        )
# =============================
# View Formato Partidos - REV  [MULTI]
# =============================
class FormatoPartidosView(discord.ui.View):
    def __init__(self, admin_id, torneo_uid: str):
        super().__init__(timeout=60)
        self.admin_id = admin_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def interaction_check(self, interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo el administrador puede elegir.",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(
        label="⚔️ Partido único",
        style=discord.ButtonStyle.primary
    )
    async def unico(self, button, interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        torneo["formato_partidos"] = "UNICO"

        # ✅ compat: apunta data["torneo"] al torneo correcto
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        save_data(data)

        await interaction.response.edit_message(
            content="✅ Formato seleccionado: **Partido único**",
            view=None
        )

        await ejecutar_sorteo(interaction)

    @discord.ui.button(
        label="🔁 Ida y vuelta",
        style=discord.ButtonStyle.success
    )
    async def ida_vuelta(self, button, interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        torneo["formato_partidos"] = "IDA_VUELTA"

        # ✅ compat: apunta data["torneo"] al torneo correcto
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        save_data(data)

        await interaction.response.edit_message(
            content="✅ Formato seleccionado: **Ida y vuelta**",
            view=None
        )

        await ejecutar_sorteo(interaction)
# =============================
#  Boton Sorteo - REV (multi-torneo)  [MULTI REAL]
# =============================
class SorteoButton(discord.ui.Button):
    def __init__(self, torneo_uid: str, admin_id):
        super().__init__(
            label="🎲 Sortear partidos",
            style=discord.ButtonStyle.primary
        )
        self.torneo_uid = torneo_uid  # ✅ antes era torneo_id
        self.admin_id = admin_id

    async def callback(self, interaction):
        await interaction.response.defer(ephemeral=True)

        if interaction.user.id != self.admin_id:
            await interaction.followup.send(
                "❌ Solo admin",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        if torneo.get("partidos"):
            await interaction.followup.send(
                "❌ Los partidos ya fueron sorteados",
                ephemeral=True
            )
            return

        # ✅ SOLO preguntar formato (amarrado al UID correcto)
        await interaction.followup.send(
            "⚙️ ¿Cómo se jugarán los partidos?",
            view=FormatoPartidosView(self.admin_id, self.torneo_uid),
            ephemeral=True
        )
# =============================
#  Def Ejecutar Sorteo - REV  [MULTI SIN BORRAR LÓGICA]  (FIX PERSISTENCIA IDS)
# =============================
async def ejecutar_sorteo(interaction):
    global data
    data = load_data()

    guild_id = interaction.guild.id
    uid = get_server(data, guild_id).get("activo", "DEFAULT")

    torneo = get_torneo_v2(data, guild_id, uid)

    equipos = torneo["equipos"].copy()
    random.shuffle(equipos)

    partidos = []
    pid = 1
    formato = torneo["formato_partidos"]

    for i in range(0, len(equipos), 2):
        if i + 1 < len(equipos):
            a = equipos[i]["nombre"]
            b = equipos[i + 1]["nombre"]

            # 🟢 PARTIDO ÚNICO
            partidos.append({
                "id": pid,
                "a": a,
                "b": b,
                "fecha": "⏰ Sin definir",
                "estado": "🕒 Pendiente",

                # ✅ MULTI: amarrar partido a su torneo
                "torneo_uid": uid
            })
            pid += 1

            # 🔁 IDA Y VUELTA
            if formato == "IDA_VUELTA":
                partidos.append({
                    "id": pid,
                    "a": b,
                    "b": a,
                    "fecha": "⏰ Sin definir",
                    "estado": "🕒 Pendiente",

                    # ✅ MULTI: amarrar partido a su torneo
                    "torneo_uid": uid
                })
                pid += 1

    torneo["partidos"] = partidos

    # ✅ compat: apunta data["torneo"] al torneo correcto
    set_torneo_activo_multi(data, guild_id, uid)
    save_data(data)

    guild = interaction.guild

    # 📺 Canal público de partidos (aislado por UID)
    canal_partidos = await crear_categoria_y_canal(
        guild,
        f"⚔️ PARTIDOS - {uid}",
        f"partidos-a-disputar-{uid.lower()}"
    )

    # ✅ AÑADIDO: TRACK categoría/canal público (para borrado por IDs)
    try:
        track_recurso_torneo(
            torneo,
            canal_id=canal_partidos.id,
            categoria_id=getattr(canal_partidos, "category_id", None)
        )
        set_torneo_activo_multi(data, guild_id, uid)
        save_data(data)
    except:
        pass

    # 🛠️ Canal ADMIN (aislado por UID)
    canal_admin = await crear_categoria_y_canal(
        guild,
        f"⚙️ ADMIN TORNEO - {uid}",
        f"admin-partidos-{uid.lower()}"
    )

    # ✅ AÑADIDO: TRACK categoría/canal admin (para borrado por IDs)
    try:
        track_recurso_torneo(
            torneo,
            canal_id=canal_admin.id,
            categoria_id=getattr(canal_admin, "category_id", None)
        )
        set_torneo_activo_multi(data, guild_id, uid)
        save_data(data)
    except:
        pass

    # =============================
    # PUBLICAR PARTIDOS (PÚBLICO)
    # =============================
    for p in torneo["partidos"]:
        embed = build_partido_embed(p)
        view_publica = discord.ui.View(timeout=None)

        rol_streamer_id = data.get("rol_streamer_id")
        if rol_streamer_id:
            view_publica.add_item(
                # ✅ MULTI: el botón público debe llevar uid
                PostularStreamerButton(p["id"], rol_streamer_id, uid)
            )

        mensaje = await canal_partidos.send(
            embed=embed,
            view=view_publica
        )

        # ✅ (tu guardado local se mantiene)
        p["canal_publico_id"] = canal_partidos.id
        p["mensaje_publico_id"] = mensaje.id
        p["torneo_uid"] = uid

        # ✅✅ AÑADIDO CLAVE: persistir sobre el PARTIDO REAL del data.json (evita None None)
        try:
            data = load_data()
            torneo_real = get_torneo_v2(data, guild_id, uid)

            for pp in torneo_real.get("partidos", []):
                if str(pp.get("id")) == str(p.get("id")):
                    pp["canal_publico_id"] = canal_partidos.id
                    pp["mensaje_publico_id"] = mensaje.id
                    pp["torneo_uid"] = uid
                    break

            set_torneo_activo_multi(data, guild_id, uid)
            save_data(data)
        except Exception as e:
            print("⚠️ No pude persistir ids públicos:", repr(e))

        # ✅ AÑADIDO: re-track por si el canal/categoría cambió o venía vacío
        try:
            track_recurso_torneo(
                torneo,
                canal_id=canal_partidos.id,
                categoria_id=getattr(canal_partidos, "category_id", None)
            )
        except:
            pass

        set_torneo_activo_multi(data, guild_id, uid)
        save_data(data)

    # =============================
    # PANEL ADMIN
    # =============================
    admin_id = interaction.user.id

    for p in torneo["partidos"]:
        view = discord.ui.View(timeout=None)

        # ✅ TODOS estos botones ahora deben recibir uid (torneo_uid)
        view.add_item(EditarPartidoButton(admin_id, p["id"], uid))
        view.add_item(EditarFechaButton(admin_id, p["id"], uid))
        view.add_item(EditarEstadoButton(admin_id, p["id"], uid))
        view.add_item(ResultadoButton(admin_id, p["id"], uid))
        view.add_item(CrearCanalPartidoButton(admin_id, p["id"], uid))
        view.add_item(AñadirStreamerButton(p["id"], uid))
        view.add_item(IniciarFaseBaneoButton(p["id"], uid))

        await canal_admin.send(
            f"🛠️ **Panel administrador – Partido #{p['id']}**\n"
            f"⚔️ **{p['a']} vs {p['b']}**",
            view=view
        )

        # ✅ AÑADIDO: asegurar que el canal admin y su categoría estén trackeados
        try:
            track_recurso_torneo(
                torneo,
                canal_id=canal_admin.id,
                categoria_id=getattr(canal_admin, "category_id", None)
            )
            set_torneo_activo_multi(data, guild_id, uid)
            save_data(data)
        except:
            pass

    await interaction.followup.send(
        "✅ Partidos creados correctamente según el formato elegido",
        ephemeral=True
    )
# =============================
#  Boton Editar Fecha - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class EditarFechaButton(discord.ui.Button):
    def __init__(self, admin_id, partido_id, torneo_uid: str):
        super().__init__(
            label="✏️ Editar fecha",
            style=discord.ButtonStyle.secondary
        )
        self.admin_id = admin_id
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ nuevo

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if p["id"] != self.partido_id:
                continue

            # 🔒 Partido cerrado
            if p.get("bloqueado"):
                await interaction.response.send_message(
                    "🔒 Este partido ya está cerrado. No se puede editar la fecha.",
                    ephemeral=True
                )
                return

            # ⚠️ Fecha no definida previamente
            if p["fecha"] == "⏰ Sin definir":
                await interaction.response.send_message(
                    "⚠️ Primero debes definir la fecha desde **Partido "
                    f"{self.partido_id}**",
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(
                EditarFechaModal(self.partido_id, self.torneo_uid)  # ✅ ahora pide UID
            )
            return
# =============================
#  Boton Editar Estado - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class EditarEstadoButton(discord.ui.Button):
    def __init__(self, admin_id, partido_id, torneo_uid: str):
        super().__init__(
            label="🟢 Editar estado",
            style=discord.ButtonStyle.success
        )
        self.admin_id = admin_id
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ nuevo

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if p["id"] != self.partido_id:
                continue

            if p.get("bloqueado"):
                await interaction.response.send_message(
                    "🔒 Este partido ya está cerrado. No se puede editar el estado.",
                    ephemeral=True
                )
                return

            await interaction.response.send_modal(
                EditarEstadoModal(self.partido_id, self.torneo_uid)  # ✅ ahora pide UID
            )
            return
# =============================
#  Boton Ver partidos - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class VerPartidosButton(discord.ui.Button):
    def __init__(self, torneo_uid: str):
        super().__init__(
            label="📅 Ver partidos",
            style=discord.ButtonStyle.secondary
        )
        self.torneo_uid = torneo_uid  # ✅ nuevo

    async def callback(self, interaction: discord.Interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        partidos = torneo.get("partidos", [])

        if not partidos:
            await interaction.response.send_message(
                "❌ No hay partidos",
                ephemeral=True
            )
            return

        await interaction.response.defer()

        for p in partidos:
            embed = discord.Embed(
                title=f"⚔️ Partido {p['id']}",
                description=f"{p['a']} 🆚 {p['b']}",
                color=discord.Color.blue()
            )

            embed.add_field(
                name="Fecha",
                value=p.get("fecha", "⏰ Sin definir"),
                inline=False
            )

            embed.add_field(
                name="Estado",
                value=p.get("estado", "🕒 Pendiente"),
                inline=False
            )

            await interaction.channel.send(embed=embed)
# =============================
#  Boton Resultado - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class ResultadoButton(discord.ui.Button):
    def __init__(self, admin_id, partido_id, torneo_uid: str):
        super().__init__(
            label="🏁 Resultado",
            style=discord.ButtonStyle.success
        )
        self.admin_id = admin_id
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):

        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo admin",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        partido = next(
            (p for p in torneo.get("partidos", []) if p["id"] == self.partido_id),
            None
        )

        if not partido:
            await interaction.response.send_message(
                "❌ Partido no encontrado",
                ephemeral=True
            )
            return

        if partido.get("bloqueado"):
            await interaction.response.send_message(
                "🔒 Este partido ya fue finalizado",
                ephemeral=True
            )
            return

        # ✅ ABRIR MODAL (ahora pide UID)
        await interaction.response.send_modal(
            ResultadoModal(self.partido_id, self.torneo_uid)
        )
# =============================
#  BOTÓN CREAR CANAL DE PARTIDO - REV (FIX) [MULTI SIN BORRAR LÓGICA]
# =============================
class CrearCanalPartidoButton(discord.ui.Button):
    def __init__(self, admin_id, partido_id, torneo_uid: str):
        super().__init__(
            label="📺 Crear canal del partido",
            style=discord.ButtonStyle.primary
        )
        self.admin_id = admin_id
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo.get("partidos", []):
            # ✅ FIX: tolerante a str/int
            if str(p.get("id")) == str(self.partido_id):

                if p.get("canal_partido_id"):
                    await interaction.followup.send(
                        "❌ El canal del partido ya fue creado",
                        ephemeral=True
                    )
                    return

                guild = interaction.guild

                # =============================
                # 📁 OBTENER / CREAR CATEGORÍA (aislada por UID)
                # =============================
                categoria_nombre = f"📛 CANALES FASE DE BANEO - {self.torneo_uid}"
                categoria = discord.utils.get(
                    guild.categories,
                    name=categoria_nombre
                )

                if categoria is None:
                    categoria = await guild.create_category(categoria_nombre)

                # ✅ NUEVO: TRACK categoría (aunque ya existiera)
                try:
                    track_recurso_torneo(torneo, categoria_id=categoria.id)
                    set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                    save_data(data)
                except:
                    pass

                nombre_canal = (
                    f"partido-{p['id']}-{self.torneo_uid.lower()}-"
                    f"{p['a'].lower().replace(' ', '-')}-vs-"
                    f"{p['b'].lower().replace(' ', '-')}"
                )

                # 📺 CANAL DENTRO DE LA CATEGORÍA
                canal = await guild.create_text_channel(
                    nombre_canal,
                    category=categoria
                )

                # ✅ NUEVO: TRACK canal (ID real para borrado total)
                try:
                    track_recurso_torneo(torneo, canal_id=canal.id)
                    set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                    save_data(data)
                except:
                    pass

                # 📌 MENSAJE PRINCIPAL DEL PARTIDO
                embed = build_partido_embed(p)
                mensaje = await canal.send(embed=embed)

                # ✅ GUARDADO (IGUAL QUE ANTES)
                p["canal_partido_id"] = canal.id
                p["mensaje_partido_id"] = mensaje.id

                # compat
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                # =============================
                # 🧑‍✈️ MENSAJE PARA ASIGNAR CAPITANES
                # =============================
                await canal.send(
                    "🧑‍✈️ **Asignación de capitanes**\n"
                    "Solo administradores pueden asignar capitanes.\n\n"
                    "🔒 Estos capitanes serán los únicos que podrán:\n"
                    "• Elegir Extra / Final Ban\n"
                    "• Banear mapas",
                    view=AsignarCapitanesView(guild_id, self.torneo_uid, p["id"])
                )

                await interaction.followup.send(
                    f"✅ Canal creado: {canal.mention}",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
#  Boton postular streamers - REV (FIX)  [MULTI SIN BORRAR LÓGICA]
# =============================
class PostularStreamerButton(discord.ui.Button):
    def __init__(self, partido_id, rol_streamer_id, torneo_uid: str):
        super().__init__(
            label="📡 Quiero streamear",
            style=discord.ButtonStyle.secondary
        )
        self.partido_id = partido_id
        self.rol_streamer_id = rol_streamer_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):
        # ✅ responder rápido (evita 10062 si algo tarda)
        await interaction.response.defer(ephemeral=True)

        # 🔒 Solo streamers
        if self.rol_streamer_id not in [r.id for r in interaction.user.roles]:
            await interaction.followup.send(
                "❌ Solo streamers pueden postularse",
                ephemeral=True
            )
            return

        global data
        data = load_data()

        # ✅ MULTI: torneo por UID
        guild_id = interaction.guild.id
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo.get("partidos", []):
            # ✅ FIX: tolerante a str/int
            if str(p.get("id")) == str(self.partido_id):

                p.setdefault("streamers_postulados", [])
                p.setdefault("streamers_aprobados", [])

                if interaction.user.id in p["streamers_postulados"]:
                    await interaction.followup.send(
                        "⚠️ Ya estás postulado para este partido",
                        ephemeral=True
                    )
                    return

                p["streamers_postulados"].append(interaction.user.id)

                # compat
                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)
                print("DEBUG publico ids:", p.get("canal_publico_id"), p.get("mensaje_publico_id"), "postulados:", p.get("streamers_postulados"))

                # 🔄 actualizar embeds
                await actualizar_mensaje_publico_partido(interaction.guild, p)
                await actualizar_todos_los_mensajes_partido(interaction.guild, p)

                await interaction.followup.send(
                    "✅ Postulación enviada al admin",
                    ephemeral=True
                )
                return

        await interaction.followup.send("❌ Partido no encontrado", ephemeral=True)
# =============================
#  Boton añadir Streamers - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class AñadirStreamerButton(discord.ui.Button):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(
            label="➕ Añadir Streamers",
            style=discord.ButtonStyle.primary
        )
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):

        global data
        data = load_data()

        # ✅ MULTI: fijar torneo correcto (compat)
        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)

        # 🔍 OBTENER PARTIDO CORRECTO
        p = None
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for partido in torneo["partidos"]:
            if partido["id"] == self.partido_id:
                p = partido
                break

        if not p:
            await interaction.response.send_message(
                "❌ Partido no encontrado",
                ephemeral=True
            )
            return

        # 🏁 BLOQUEAR SI YA TIENE RESULTADO
        if p.get("resultado"):
            await interaction.response.send_message(
                "🏁 Este partido ya fue finalizado, no se pueden añadir streamers",
                ephemeral=True
            )
            return

        # 🚫 BLOQUEAR SI YA HAY 2 STREAMERS
        if len(p.get("streamers_aprobados", [])) >= 2:
            await interaction.response.send_message(
                "🚫 Este partido ya tiene 2 streamers añadidos",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(
            AñadirStreamerModal(self.partido_id, self.torneo_uid)  # ✅ ahora pide UID
        )
# =============================
#  Boton Iniciar Fase Baneo - REV (FIX id str/int)  [MULTI SIN BORRAR LÓGICA]
# =============================
class IniciarFaseBaneoButton(discord.ui.Button):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(
            label="🚫 Iniciar fase de baneo",
            style=discord.ButtonStyle.danger
        )
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):
        global data
        data = load_data()

        # ✅ MULTI: fijar torneo correcto (compat)
        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)

        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            # ✅ FIX: tolerante a str/int
            if str(p.get("id")) == str(self.partido_id):

                if p.get("resultado"):
                    await interaction.response.send_message(
                        "🏁 El partido ya finalizó",
                        ephemeral=True
                    )
                    return

                if p.get("fase_baneo", {}).get("activa"):
                    await interaction.response.send_message(
                        "🚫 La fase de baneo ya está activa",
                        ephemeral=True
                    )
                    return

                if not hay_capitanes(p):
                    await interaction.response.send_message(
                        "🔒 No se puede iniciar la fase de baneo.\n"
                        "❌ Ambos equipos deben tener al menos un capitán asignado.",
                        ephemeral=True
                    )
                    return

                await interaction.response.send_modal(
                    MapPoolModal(self.partido_id, self.torneo_uid)  # ✅ ahora pide UID
                )
                return
# =============================
# Def mISMO ID
# ============================= 
def mismo_id(a, b) -> bool:
    return str(a) == str(b)
# =============================
# Def Cambiar Turno - REV NO TOCA
# =============================                 
def cambiar_turno(fase):
    actual = fase["turno_actual"]
    tipo = fase["equipos"][actual]["tipo"]

    if tipo == "extra":
        # Extra ban banea DOS VECES
        fase.setdefault("contador_extra", 0)
        fase["contador_extra"] += 1

        if fase["contador_extra"] >= 2:
            fase["contador_extra"] = 0
            fase["turno_actual"] = "A" if actual == "B" else "B"

    else:
        # Final ban banea UNA VEZ
        fase["turno_actual"] = "A" if actual == "B" else "B"
# =============================
# Ban Mapas View - FIX (MULTI)
# =============================
class BanMapasView(discord.ui.View):
    def __init__(self, torneo_id, partido_id, torneo_uid: str):
        super().__init__(timeout=None)

        global data
        data = load_data()  # ✅ para evitar data viejo en views persistentes

        # ✅ MULTI: fijar torneo correcto (compat)
        guild_id = torneo_id  # torneo_id aquí realmente es guild_id (como ya lo usas)
        set_torneo_activo_multi(data, guild_id, torneo_uid)

        torneo = get_torneo_v2(data, guild_id, torneo_uid)

        # 🔎 buscar partido (tolerante a str/int)
        partido = None
        for p in torneo.get("partidos", []):
            if str(p.get("id")) == str(partido_id):
                partido = p
                break

        if not partido:
            ids = [str(x.get("id")) for x in torneo.get("partidos", [])]
            self.add_item(discord.ui.Button(
                label=f"⚠️ Partido no encontrado (busqué {partido_id})",
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            print("❌ BanMapasView no encontró partido_id:", partido_id, "IDs en torneo:", ids)
            return

        fase = partido.get("fase_baneo")
        if not fase:
            self.add_item(discord.ui.Button(
                label="⚠️ Sin fase de baneo",
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        # ✅ asegurar mapa_actual
        mapa_actual = fase.get("mapa_actual")
        if (not mapa_actual) and fase.get("map_pool"):
            fase["mapa_actual"] = fase["map_pool"][0]
            fase["mapa_vista"] = fase["map_pool"][0]
            mapa_actual = fase["mapa_actual"]
            save_data(data)

        if not mapa_actual:
            self.add_item(discord.ui.Button(
                label="⚠️ Sin mapa actual",
                style=discord.ButtonStyle.secondary,
                disabled=True
            ))
            return

        # ✅ IMPORTANTÍSIMO: NO convertir a int
        pid = str(partido.get("id"))

        # ✅ BOTONES (AHORA PASAN torneo_uid PARA MULTITORNEO)
        self.add_item(BanMapaButton(pid, mapa_actual, "Axis", torneo_uid))
        self.add_item(BanMapaButton(pid, mapa_actual, "Allies", torneo_uid))
        self.add_item(NextMapButton(pid, torneo_uid))
# =============================
# DEF facciones_vivas_en_mapa
# ============================= 
def facciones_vivas_en_mapa(fase, mapa):
    vivas = set()
    if f"{mapa} Axis" not in fase["baneados"]:
        vivas.add("Axis")
    if f"{mapa} Allies" not in fase["baneados"]:
        vivas.add("Allies")
    return vivas
# =============================
# DEF mapas_vivos - REV NO TOCA
# ============================= 
def mapas_vivos(fase):
    vivos = []
    for m in fase["map_pool"]:
        if len(facciones_vivas_en_mapa(fase, m)) > 0:
            vivos.append(m)
    return vivos
# =============================
# DEF evaluar_cierre_fase - REV NO TOCA
# ============================= 
def evaluar_cierre_fase(fase):
    """
    Retorna:
    - None → NO se puede cerrar aún
    - dict con resultado → cerrar fase
    """

    mapas = mapas_vivos(fase)

    # ============================
    # 🟢 RUTA 2 — 1 MAPA / 2 FACCIONES
    # Final Ban decide FACCIÓN
    # ============================
    if len(mapas) == 1:
        mapa = mapas[0]
        facciones = facciones_vivas_en_mapa(fase, mapa)

        # 1 mapa / 1 facción → cierre automático (NO Final Ban real)
        if len(facciones) == 1:
            faccion_final = next(iter(facciones))
            equipo_final = fase["coinflip"]["ganador"]
            equipo_opuesto = "B" if equipo_final == "A" else "A"

            return {
                "ruta": "RUTA_2_AUTO",
                "mapa_final": mapa,
                "facciones_finales": {
                    equipo_final: faccion_final,
                    equipo_opuesto: "Axis" if faccion_final == "Allies" else "Allies"
                }
            }

        # 1 mapa / 2 facciones → ESPERAR Final Ban
        if len(facciones) == 2:
            return {
                "ruta": "RUTA_2_FINAL_BAN",
                "accion": "esperar_final_ban_faccion",
                "mapa": mapa
            }

    # ============================
    # 🟢 RUTA 1 — 2 MAPAS / 1 FACCIÓN CADA UNO
    # Final Ban decide MAPA
    # ============================
    if len(mapas) == 2:
        facciones_por_mapa = {
            m: facciones_vivas_en_mapa(fase, m)
            for m in mapas
        }

        # cada mapa tiene exactamente 1 facción viva
        if all(len(v) == 1 for v in facciones_por_mapa.values()):
            return {
                "ruta": "RUTA_1_FINAL_BAN",
                "accion": "esperar_final_ban_mapa",
                "mapas": mapas,
                "facciones_por_mapa": facciones_por_mapa
            }

    # ============================
    # ❌ NO HAY CIERRE POSIBLE
    # ============================
    return 
# ============================
#  Boton Ban Mapa - FIX (NO followup.edit_message)  [MULTI SIN BORRAR LÓGICA]
# ============================
class BanMapaButton(discord.ui.Button):
    def __init__(self, partido_id, mapa, faccion, torneo_uid: str):
        self.partido_id = partido_id
        self.mapa = mapa
        self.faccion = faccion
        self.torneo_uid = torneo_uid  # ✅ NUEVO

        mapa_key = str(mapa).replace(" ", "_")
        faccion_key = str(faccion)
        super().__init__(
            label=f"🚫 Ban {faccion}",
            style=discord.ButtonStyle.danger,
            custom_id=f"ban_{mapa_key}_{faccion_key}"
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            # ✅ SIEMPRE responder rápido para que no expire
            if not interaction.response.is_done():
                await interaction.response.defer()

            global data
            data = load_data()  # ✅ para evitar data viejo

            # ✅ MULTI: fijar torneo correcto (compat)
            guild_id = interaction.guild.id
            set_torneo_activo_multi(data, guild_id, self.torneo_uid)

            torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

            # ✅ buscar partido
            partido = None
            for p in torneo.get("partidos", []):
                if str(p.get("id")) == str(self.partido_id):
                    partido = p
                    break

            if not partido:
                await interaction.followup.send(
                    "⚠️ Partido no encontrado para este botón.",
                    ephemeral=True
                )
                return

            fase = partido.get("fase_baneo")
            if not fase:
                await interaction.followup.send(
                    "⚠️ Este partido no tiene fase de baneo.",
                    ephemeral=True
                )
                return

            # ==============================
            # 🔐 SOLO CAPITANES EN TURNO
            # ==============================
            equipo_turno = fase["turno_actual"]
            capitanes = obtener_ids_equipo(partido, equipo_turno)

            if interaction.user.id not in capitanes:
                await interaction.followup.send(
                    "⛔ Solo el capitán del equipo en turno puede usar este botón.",
                    ephemeral=True
                )
                return

            # ==============================
            # 🚫 VALIDAR FASE ACTIVA
            # ==============================
            if not fase.get("activa", True):
                await interaction.followup.send(
                    "⛔ La fase de baneo ya finalizó.",
                    ephemeral=True
                )
                return

            # ==============================
            # 📍 MAPA ACTUAL REAL
            # ==============================
            mapa_actual = fase.get("mapa_actual")
            if not mapa_actual:
                await interaction.followup.send(
                    "⛔ No hay un mapa activo para banear.",
                    ephemeral=True
                )
                return

            fase.setdefault("baneados", [])
            fase.setdefault("historial", [])

            # ==============================
            # 🚫 VALIDAR BAN REPETIDO
            # ==============================
            resultado = fase.get("resultado")
            if resultado and resultado.get("ruta") in ("RUTA_1_FINAL_BAN", "RUTA_2_FINAL_BAN"):
                if fase.get("final_ban_resuelto"):
                    await interaction.followup.send(
                        "⚠️ La fase de baneo ya fue definida por el Final Ban.",
                        ephemeral=True
                    )
                    return

            clave_ban = f"{mapa_actual} {self.faccion}"
            if clave_ban in fase["baneados"]:
                await interaction.followup.send(
                    "⚠️ Esa facción ya fue baneada.",
                    ephemeral=True
                )
                return

            # ==============================
            # 🧨 APLICAR BAN
            # ==============================
            fase["baneados"].append(clave_ban)
            fase["baneos_realizados"] = fase.get("baneos_realizados", 0) + 1

            nombre_equipo = partido["a"] if equipo_turno == "A" else partido["b"]
            fase["historial"].append(
                f"🚫 **{nombre_equipo}** baneó {self.faccion} en **{mapa_actual}**"
            )

            recalcular_mapa_actual(fase)

            # ==============================
            # 🧠 EVALUAR CIERRE GLOBAL
            # ==============================
            resultado = evaluar_cierre_fase(fase)

            # ✅ construir embed siempre (para refrescar UI)
            embed = construir_embed_map_pool(fase, partido)

            # ==================================================
            # 🟢 RUTA 2 AUTO → CIERRE REAL AUTOMÁTICO
            # ==================================================
            if resultado and resultado.get("ruta") == "RUTA_2_AUTO":
                fase["activa"] = False
                fase["mapa_final"] = resultado["mapa_final"]
                fase["facciones_finales"] = resultado["facciones_finales"]
                fase["resultado"] = normalizar_resultado_json(resultado)

                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                await interaction.message.edit(
                    content=(
                        "🏁 **Fase de baneo finalizada**\n\n"
                        f"🗺️ **Mapa final:** `{fase['mapa_final']}`\n\n"
                        f"🎖️ **{partido['a']}** → `{fase['facciones_finales'].get('A')}`\n"
                        f"🎖️ **{partido['b']}** → `{fase['facciones_finales'].get('B')}`"
                    ),
                    embed=embed,
                    view=None
                )
                return

            # ==================================================
            # 🟡 FINAL BAN → NO SE CIERRA (solo prepara decisión)
            # ==================================================
            if resultado and resultado.get("ruta") in ("RUTA_1_FINAL_BAN", "RUTA_2_FINAL_BAN"):

                equipo_finalban = None
                try:
                    if fase.get("equipos", {}).get("A", {}).get("tipo") == "final":
                        equipo_finalban = "A"
                    elif fase.get("equipos", {}).get("B", {}).get("tipo") == "final":
                        equipo_finalban = "B"
                except:
                    equipo_finalban = None

                if not equipo_finalban:
                    equipo_finalban = fase["coinflip"]["ganador"]

                fase["turno_actual"] = equipo_finalban
                fase["estado"] = "FINAL_BAN"
                fase["resultado"] = normalizar_resultado_json(resultado)

                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                embed = construir_embed_map_pool(fase, partido)

                await interaction.message.edit(
                    embed=embed,
                    view=BanMapasView(guild_id, self.partido_id, self.torneo_uid)  # ✅ ahora pasa UID
                )
                return

            # ==============================
            # 🔁 CAMBIAR TURNO
            # ==============================
            if fase.get("estado", "NORMAL") == "NORMAL":
                cambiar_turno(fase)

            set_torneo_activo_multi(data, guild_id, self.torneo_uid)
            save_data(data)

            embed = construir_embed_map_pool(fase, partido)

            await interaction.message.edit(
                embed=embed,
                view=BanMapasView(guild_id, self.partido_id, self.torneo_uid)  # ✅ ahora pasa UID
            )

        except Exception as e:
            print("❌ ERROR BanMapaButton:", repr(e))
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(
                        "❌ Error interno en el botón (revisa la consola).",
                        ephemeral=True
                    )
                else:
                    await interaction.response.send_message(
                        "❌ Error interno en el botón (revisa la consola).",
                        ephemeral=True
                    )
            except:
                pass
# =============================
# Def RECALCULAR MAPA ACTUAL - REV NO TOCA
# =============================          
def recalcular_mapa_actual(fase):
    mapas_validos = obtener_mapas_validos(fase)

    if not mapas_validos:
        fase["mapa_actual"] = None
        fase["mapa_vista"] = None
        return

    actual = fase.get("mapa_actual")

    # si el mapa actual sigue vivo, no tocar
    if actual in mapas_validos:
        return

    # si murió, saltar al primer mapa vivo
    fase["mapa_actual"] = mapas_validos[0]
    fase["mapa_vista"] = mapas_validos[0]
# =============================
# Def normalizar resultados json - REV NO TOCA
# =============================    
def normalizar_resultado_json(obj):
    if isinstance(obj, set):
        return list(obj)
    if isinstance(obj, dict):
        return {k: normalizar_resultado_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalizar_resultado_json(v) for v in obj]
    return obj
# =============================
# Def Obtener mapas Validos - REV NO TOCA
# =============================        
def obtener_mapas_validos(fase):
    mapas_validos = []

    for m in fase["map_pool"]:
        bans_m = [b for b in fase["baneados"] if b.startswith(m)]
        if len(bans_m) < 2:
            mapas_validos.append(m)

    return mapas_validos
# =============================
# Botón Next Map - FIX DATA SYNC  [MULTI SIN BORRAR LÓGICA]
# =============================
class NextMapButton(discord.ui.Button):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(
            label="➡️ Next Map",
            style=discord.ButtonStyle.secondary
        )
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):
        try:
            global data
            data = load_data()  # ✅ para evitar data viejo en views persistentes

            # ✅ MULTI: fijar torneo correcto
            guild_id = interaction.guild.id
            set_torneo_activo_multi(data, guild_id, self.torneo_uid)
            torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

            # ✅ buscar partido en el torneo correcto
            partido = None
            for p in torneo.get("partidos", []):
                if str(p.get("id")) == str(self.partido_id):
                    partido = p
                    break

            if not partido:
                await interaction.response.send_message(
                    "⚠️ Partido no encontrado para este botón.",
                    ephemeral=True
                )
                return

            fase = partido.get("fase_baneo")

            # ==============================
            # 🚫 VALIDAR FASE ACTIVA
            # ==============================
            if not fase or not fase.get("activa"):
                await interaction.response.send_message(
                    "⚠️ La fase de baneo no está activa.",
                    ephemeral=True
                )
                return

            # ==============================
            # 🔐 SOLO CAPITANES EN TURNO
            # ==============================
            equipo_turno = fase["turno_actual"]
            if interaction.user.id not in obtener_ids_equipo(partido, equipo_turno):
                await interaction.response.send_message(
                    "❌ No es tu turno o no eres capitán.",
                    ephemeral=True
                )
                return

            # ==============================
            # 🗺️ MAPAS VIVOS REALES
            # ==============================
            mapas_validos = obtener_mapas_validos(fase)

            if not mapas_validos:
                await interaction.response.send_message(
                    "⚠️ No hay mapas disponibles.",
                    ephemeral=True
                )
                return

            mapa_actual = fase.get("mapa_actual")

            # ==============================
            # 🔄 ROTAR SOLO ENTRE MAPAS VIVOS
            # ==============================
            if mapa_actual in mapas_validos:
                idx = mapas_validos.index(mapa_actual)
                fase["mapa_actual"] = mapas_validos[(idx + 1) % len(mapas_validos)]
            else:
                fase["mapa_actual"] = mapas_validos[0]

            # compat
            set_torneo_activo_multi(data, guild_id, self.torneo_uid)
            save_data(data)

            embed = construir_embed_map_pool(fase, partido)

            # ✅ refrescar mensaje con la misma view (ahora pasa UID)
            await interaction.response.edit_message(
                embed=embed,
                view=BanMapasView(guild_id, self.partido_id, self.torneo_uid)
            )

        except Exception as e:
            print("❌ ERROR NextMapButton:", repr(e))
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ Error interno en el botón (revisa la consola).",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Error interno en el botón (revisa la consola).",
                    ephemeral=True
                )
# =============================
# Def calcular Resultado Final- REV NO TOCA
# =============================
def calcular_resultado_final(fase):

    # 🔒 BLINDAJE: asegurar mapa_final
    if "mapa_final" not in fase or not fase["mapa_final"]:
        mapas_validos = []
        for m in fase.get("map_pool", []):
            bans_m = [b for b in fase.get("baneados", []) if b.startswith(m)]
            if len(bans_m) < 2:
                mapas_validos.append(m)

        if len(mapas_validos) == 1:
            fase["mapa_final"] = mapas_validos[0]
        else:
            return  # aún no se puede calcular

    mapa = fase["mapa_final"]
    baneados = fase["baneados"]

    axis_baneado = f"{mapa} Axis" in baneados
    allies_baneado = f"{mapa} Allies" in baneados

    # 🔒 BLINDAJE: asegurar equipo_final
    equipo_final = fase.get("equipo_final")
    if not equipo_final:
        equipo_final = fase.get("coinflip", {}).get("ganador")
        fase["equipo_final"] = equipo_final

    equipo_opuesto = "B" if equipo_final == "A" else "A"

    facciones = {}

    # 🟢 SOLO QUEDA ALLIES
    if axis_baneado and not allies_baneado:
        facciones[equipo_final] = "Allies"
        facciones[equipo_opuesto] = "Axis"

    # 🟢 SOLO QUEDA AXIS
    elif allies_baneado and not axis_baneado:
        facciones[equipo_final] = "Axis"
        facciones[equipo_opuesto] = "Allies"

    # 🟡 QUEDAN LAS DOS → FINAL BAN DECIDE
    else:
        faccion_elegida = fase.get("faccion_final")
        if not faccion_elegida:
            faccion_elegida = "Allies"  # fallback defensivo

        facciones[equipo_final] = faccion_elegida
        facciones[equipo_opuesto] = "Axis" if faccion_elegida == "Allies" else "Allies"

    fase["facciones_finales"] = facciones
# =============================
# VIEW Elegir Tipo de Ban - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class ElegirTipoBanView(discord.ui.View):
    def __init__(self, torneo_id, torneo_uid: str, partido):
        super().__init__(timeout=None)

        global data
        data = load_data()

        guild_id = torneo_id  # torneo_id aquí es guild_id
        set_torneo_activo_multi(data, guild_id, torneo_uid)
        torneo = get_torneo_v2(data, guild_id, torneo_uid)

        # 🔒 SI VIENE UN ID, BUSCAR EL PARTIDO (tolerante str/int)
        if not isinstance(partido, dict):
            partido_obj = None
            for p in torneo.get("partidos", []):
                if str(p.get("id")) == str(partido):
                    partido_obj = p
                    break
            if not partido_obj:
                return  # partido no encontrado
            partido = partido_obj

        # 🔒 DEFENSIVO
        if not isinstance(partido, dict):
            return

        bloqueado = not hay_capitanes(partido)

        # ✅ Pasar UID a los botones (para que no se mezclen)
        extra = ExtraBanButton(partido["id"], torneo_uid)
        final = FinalBanButton(partido["id"], torneo_uid)

        extra.disabled = bloqueado
        final.disabled = bloqueado

        self.add_item(extra)
        self.add_item(final)

        if not partido.get("fase_baneo"):
            return
# =============================
# VIEW Asignar Capitanes - FIX (nombres reales) ✅ USA DATA GLOBAL  [MULTI]
# =============================
class AsignarCapitanesView(discord.ui.View):
    def __init__(self, torneo_id, torneo_uid: str, partido_id):
        super().__init__(timeout=None)
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid

        global data
        data = load_data()

        guild_id = torneo_id  # torneo_id aquí es guild_id
        set_torneo_activo_multi(data, guild_id, torneo_uid)
        torneo = get_torneo_v2(data, guild_id, torneo_uid)

        partido = None
        for p in torneo.get("partidos", []):
            if str(p.get("id")) == str(partido_id):
                partido = p
                break

        # DEBUG (solo para probar)
        print(
            "🧩 AsignarCapitanesView guild_id:", guild_id,
            "uid:", torneo_uid,
            "partido_id:", partido_id,
            "encontrado:", bool(partido),
            "ids:", [str(x.get("id")) for x in torneo.get("partidos", [])]
        )

        nombre_a = partido["a"] if partido else "Equipo A"
        nombre_b = partido["b"] if partido else "Equipo B"

        # ✅ Pasar UID a botones (luego ajustamos sus clases si aún no lo aceptan)
        self.add_item(AsignarCapitanButton(guild_id, partido_id, "A", nombre_a, torneo_uid))
        self.add_item(QuitarCapitanButton(guild_id, partido_id, "A", nombre_a, torneo_uid))

        self.add_item(AsignarCapitanButton(guild_id, partido_id, "B", nombre_b, torneo_uid))
        self.add_item(QuitarCapitanButton(guild_id, partido_id, "B", nombre_b, torneo_uid))
# =============================
# UTILIDAD: obtener ids de capitanes por equipo - REV NO TOCA
# =============================
def obtener_ids_equipo(partido, equipo):

    if "equipos" not in partido:
        return []

    if equipo not in partido["equipos"]:
        return []

    return partido["equipos"][equipo].get("capitanes", [])
# =============================
# UTILIDAD: HAY CAPITANES - REV NO TOCA
# =============================
def hay_capitanes(partido):

    # 🔒 BLINDAR ESTRUCTURA DEL PARTIDO
    if "equipos" not in partido:
        partido["equipos"] = {
            "A": {"capitanes": []},
            "B": {"capitanes": []}
        }
        save_data(data)

    if "capitanes" not in partido["equipos"]["A"]:
        partido["equipos"]["A"]["capitanes"] = []

    if "capitanes" not in partido["equipos"]["B"]:
        partido["equipos"]["B"]["capitanes"] = []

    return (
        len(partido["equipos"]["A"]["capitanes"]) > 0 and
        len(partido["equipos"]["B"]["capitanes"]) > 0
    )
# =============================
# def construir embed map pool - REV NO TOCA
# =============================
def construir_embed_map_pool(fase, p):
    embed = discord.Embed(
        title="🗺️ Map Ban Phase",
        color=discord.Color.orange()
    )

    # Equipo A y B reales
    equipo_a = p["a"]
    equipo_b = p["b"]

    baneados = fase.get("baneados", [])

    descripcion = []

    for mapa in fase["map_pool"]:
        axis_baneado = f"{mapa} Axis" in baneados
        allies_baneado = f"{mapa} Allies" in baneados

        # Estados visuales
        axis_icon = "🟥" if axis_baneado else "🟩"
        allies_icon = "🟥" if allies_baneado else "🟩"

                # Mapa totalmente muerto
        if axis_baneado and allies_baneado:
            descripcion.append(
                f"~~**{mapa}**~~ ❌\n"
                f"🟥 Axis | 🟥 Allies\n"
            )
        else:
            descripcion.append(
                f"**{mapa}**\n"
                f"{axis_icon} Axis | {allies_icon} Allies\n"
            )

    embed.description = "\n".join(descripcion)

    # Footer con mapa actual
    if fase.get("mapa_actual"):
        equipo_turno = fase["turno_actual"]
        nombre_turno = p["a"] if equipo_turno == "A" else p["b"]

        embed.set_footer(
            text=f"🎯 Mapa actual: {fase['mapa_actual']} | Turno {nombre_turno}"
        )
    else:
        embed.set_footer(text="⏳ Calculando resultado final...")

    return embed
# =============================
#  BOTON EXTRA Ban - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class ExtraBanButton(discord.ui.Button):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(
            label="➕ Extra Ban (2 baneos)",
            style=discord.ButtonStyle.success
        )
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):

        global data
        data = load_data()

        # ✅ MULTI: torneo correcto por UID
        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if str(p.get("id")) != str(self.partido_id):
                continue

            fase = p.get("fase_baneo")
            if not fase or not fase.get("activa"):
                return

            if not hay_capitanes(p):
                await interaction.response.send_message(
                    "🔒 No se puede iniciar la fase de baneo.\n"
                    "❌ Ambos equipos deben tener al menos un capitán asignado.",
                    ephemeral=True
                )
                return

            if fase["coinflip"].get("eleccion"):
                await interaction.response.send_message(
                    "⚠️ La elección ya fue realizada",
                    ephemeral=True
                )
                return

            ganador = fase["coinflip"]["ganador"]
            perdedor = "B" if ganador == "A" else "A"

            if interaction.user.id not in obtener_ids_equipo(p, ganador):
                await interaction.response.send_message(
                    "❌ Solo el capitán del equipo ganador puede elegir",
                    ephemeral=True
                )
                return

            fase["coinflip"]["eleccion"] = "extra"
            fase["equipos"][ganador]["tipo"] = "extra"
            fase["equipos"][ganador]["baneos_restantes"] = 2
            fase["equipos"][perdedor]["tipo"] = "final"
            fase["equipos"][perdedor]["baneos_restantes"] = 1
            fase["turno_actual"] = perdedor

            fase.setdefault("baneados", [])
            fase.setdefault("historial", [])
            fase.setdefault("max_baneos", 3)
            fase["mapa_actual"] = fase["map_pool"][0]

            set_torneo_activo_multi(data, guild_id, self.torneo_uid)
            save_data(data)

            nombre_ganador = p["a"] if ganador == "A" else p["b"]
            nombre_perdedor = p["a"] if perdedor == "A" else p["b"]

            await interaction.response.edit_message(
                content=(
                    f"🎲 **Elección realizada**\n\n"
                    f"🏆 **{nombre_perdedor}**: Final Ban (1)\n"
                    f"⚔️ **{nombre_ganador}**: Extra Ban (2)\n\n"
                    f"➡️ Inicia el baneo de mapas"
                ),
                view=None
            )

            embed = construir_embed_map_pool(fase, p)

            await interaction.channel.send(
                embed=embed,
                view=BanMapasView(guild_id, str(self.partido_id), self.torneo_uid)  # ✅ NO int()
            )
            return
# =============================
#  BOTON Final Ban - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class FinalBanButton(discord.ui.Button):
    def __init__(self, partido_id, torneo_uid: str):
        super().__init__(
            label="🚫 Final Ban (1 baneo)",
            style=discord.ButtonStyle.danger
        )
        self.partido_id = partido_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction: discord.Interaction):

        global data
        data = load_data()

        # ✅ MULTI: torneo correcto por UID
        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        for p in torneo["partidos"]:
            if str(p.get("id")) == str(self.partido_id):

                fase = p.get("fase_baneo")
                if not fase or not fase.get("activa"):
                    return

                if not hay_capitanes(p):
                    await interaction.response.send_message(
                        "🔒 No se puede iniciar la fase de baneo.\n"
                        "❌ Ambos equipos deben tener al menos un capitán asignado.",
                        ephemeral=True
                    )
                    return

                if fase["coinflip"].get("eleccion"):
                    await interaction.response.send_message(
                        "⚠️ La elección ya fue realizada",
                        ephemeral=True
                    )
                    return

                ganador = fase["coinflip"]["ganador"]
                perdedor = "B" if ganador == "A" else "A"

                if interaction.user.id not in obtener_ids_equipo(p, ganador):
                    await interaction.response.send_message(
                        "❌ Solo el capitán del equipo ganador puede elegir",
                        ephemeral=True
                    )
                    return

                fase["coinflip"]["eleccion"] = "final"
                fase["equipos"][ganador]["tipo"] = "final"
                fase["equipos"][ganador]["baneos_restantes"] = 1

                fase["equipos"][perdedor]["tipo"] = "extra"
                fase["equipos"][perdedor]["baneos_restantes"] = 2

                fase["turno_actual"] = ganador

                # 🔧 BLINDAJE DE FASE
                fase["mapa_actual"] = fase["map_pool"][0]
                fase.setdefault("baneados", [])
                fase.setdefault("historial", [])
                fase.setdefault("max_baneos", 3)  # 1 + 2

                if not fase.get("mapa_actual") and fase.get("map_pool"):
                    fase["mapa_actual"] = fase["map_pool"][0]

                set_torneo_activo_multi(data, guild_id, self.torneo_uid)
                save_data(data)

                nombre_ganador = p["a"] if ganador == "A" else p["b"]
                nombre_perdedor = p["a"] if perdedor == "A" else p["b"]

                await interaction.response.edit_message(
                    content=(
                        f"🎲 **Elección realizada**\n\n"
                        f"🏆 **{nombre_ganador}**: Final Ban (1)\n"
                        f"⚔️ **{nombre_perdedor}**: Extra Ban (2)\n\n"
                        f"➡️ Inicia el baneo de mapas"
                    ),
                    view=None
                )

                embed = construir_embed_map_pool(fase, p)

                await interaction.channel.send(
                    embed=embed,
                    view=BanMapasView(guild_id, str(self.partido_id), self.torneo_uid)  # ✅ NO int()
                )
                return
# =============================
# BOTON Asignar Capitan - FIX DEFINITIVO (nombre real) [MULTI]
# =============================
class AsignarCapitanButton(discord.ui.Button):
    def __init__(self, torneo_id, partido_id, equipo, nombre_equipo=None, torneo_uid: str = "DEFAULT"):

        # =============================
        # 🔒 NORMALIZAR EQUIPO (NO SE TOCA)
        # =============================
        if equipo not in ("A", "B"):
            if str(equipo).endswith("A"):
                equipo = "A"
            elif str(equipo).endswith("B"):
                equipo = "B"

        # =============================
        # 🔎 RESPETAR NOMBRE REAL SI VIENE
        # =============================
        if not nombre_equipo:
            data = load_data()
            set_torneo_activo_multi(data, torneo_id, torneo_uid)  # ✅ MULTI

            nombre_equipo = f"Equipo {equipo}"  # fallback seguro

            torneo = get_torneo_v2(data, torneo_id, torneo_uid)  # ✅ MULTI
            for p in torneo.get("partidos", []):
                if str(p.get("id")) == str(partido_id):
                    nombre_equipo = p["a"] if equipo == "A" else p["b"]
                    break

        super().__init__(
            label=f"Asignar Capitán {nombre_equipo}",
            style=discord.ButtonStyle.primary
        )

        self.partido_id = partido_id
        self.equipo = equipo
        self.torneo_id = torneo_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction):
        # ✅ USAR EL TORNEO DEL BOTÓN (NO recalcular)
        data = load_data()
        set_torneo_activo_multi(data, self.torneo_id, self.torneo_uid)  # ✅ MULTI

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        # ✅ Si tu modal ya acepta UID, se lo pasamos; si no, cae al viejo sin romper
        try:
            await interaction.response.send_modal(
                AsignarCapitanModal(self.partido_id, self.equipo, self.torneo_uid)
            )
        except TypeError:
            await interaction.response.send_modal(
                AsignarCapitanModal(self.partido_id, self.equipo)
            )
# =============================
# BOTON Quitar Capitan - FIX DEFINITIVO (nombre real) [MULTI]
# =============================
class QuitarCapitanButton(discord.ui.Button):
    def __init__(self, torneo_id, partido_id, equipo, nombre_equipo=None, torneo_uid: str = "DEFAULT"):
        self.partido_id = partido_id
        self.torneo_id = torneo_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

        # =============================
        # 🔒 NORMALIZAR EQUIPO (FIX REAL)
        # =============================
        if equipo not in ("A", "B"):
            if str(equipo).endswith("A"):
                equipo = "A"
            elif str(equipo).endswith("B"):
                equipo = "B"

        self.equipo = equipo

        # =============================
        # 🔎 RESPETAR NOMBRE REAL SI VIENE
        # =============================
        if not nombre_equipo:
            data = load_data()
            set_torneo_activo_multi(data, self.torneo_id, self.torneo_uid)  # ✅ MULTI

            nombre_equipo = f"Equipo {equipo}"  # fallback seguro

            torneo = get_torneo_v2(data, self.torneo_id, self.torneo_uid)  # ✅ MULTI
            for p in torneo.get("partidos", []):
                if str(p.get("id")) == str(partido_id):
                    nombre_equipo = p["a"] if equipo == "A" else p["b"]
                    break

        super().__init__(
            label=f"Quitar Capitán {nombre_equipo}",
            style=discord.ButtonStyle.danger
        )

    async def callback(self, interaction):
        data = load_data()
        set_torneo_activo_multi(data, self.torneo_id, self.torneo_uid)  # ✅ MULTI

        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        # ✅ Si tu modal ya acepta UID, se lo pasamos; si no, cae al viejo sin romper
        try:
            await interaction.response.send_modal(
                QuitarCapitanModal(self.partido_id, self.equipo, self.torneo_uid)
            )
        except TypeError:
            await interaction.response.send_modal(
                QuitarCapitanModal(self.partido_id, self.equipo)
            )
# =============================
#  Embed Build partido - REV NO TOCAR
# =============================
def build_partido_embed(p):
    embed = discord.Embed(
        title=f"⚔️ {p['a']} vs {p['b']}",
        color=discord.Color.blue()
    )

    embed.add_field(
        name="⏰ Fecha",
        value=p.get("fecha", "⏰ Sin definir"),
        inline=False
    )

    embed.add_field(
        name="📌 Estado",
        value=p.get("estado", "🕒 Pendiente"),
        inline=False
    )

    # ⚠️ SE DEJA TAL CUAL (NO SE BORRA NI CAMBIA)
    streamers = "\n".join(p.get("streamers", [])) or "No definidos"
    embed.add_field(
        name="🎥 Streamers",
        value=streamers,
        inline=False
    )

    # 📝 STREAMERS POSTULADOS
    if p.get("streamers_postulados"):
        postulados = []
        for uid in p["streamers_postulados"]:
            postulados.append(f"<@{uid}> (`{uid}`)")

        embed.add_field(
            name="📝 Streamers Postulados",
            value="\n".join(postulados),
            inline=False
        )
    else:
        embed.add_field(
            name="📝 Streamers Postulados",
            value="Nadie se ha postulado",
            inline=False
        )

    if p.get("resultado"):
        embed.add_field(
            name="🏁 Resultado",
            value=p["resultado"],
            inline=False
        )

    # =============================
    # 🧑‍✈️ CAPITANES (PROTEGIDO)
    # =============================
    equipos = p.get("equipos", {})

    equipo_a = equipos.get("A", {})
    equipo_b = equipos.get("B", {})

    capitanes_a = equipo_a.get("capitanes", [])
    capitanes_b = equipo_b.get("capitanes", [])

    texto_a = "\n".join(f"<@{uid}>" for uid in capitanes_a) if capitanes_a else "—"
    texto_b = "\n".join(f"<@{uid}>" for uid in capitanes_b) if capitanes_b else "—"

    embed.add_field(
        name=f"🧑‍✈️ Capitanes {p['a']}",
        value=texto_a,
        inline=True
    )

    embed.add_field(
        name=f"🧑‍✈️ Capitanes {p['b']}",
        value=texto_b,
        inline=True
    )

    # ✅ AÑADIDO: identificador único por torneo+partido (NO rompe nada)
    try:
        _uid = (p.get("torneo_uid") or "DEFAULT")
        _pid = p.get("id")
        _tag = f" | UID:{_uid} | PID:{_pid}"
    except:
        _tag = ""

    embed.set_footer(text="Este mensaje se actualiza automáticamente" + _tag)
    return embed
# =============================
#  DEF get channel safe
# =============================
async def _get_channel_safe(guild: discord.Guild, channel_id: int):
    ch = None
    try:
        ch = guild.get_channel(channel_id)
    except:
        ch = None

    if ch is None:
        try:
            ch = await guild.fetch_channel(channel_id)
        except:
            ch = None

    return ch
# =============================
#  DEF fetch message safe
# =============================
async def _fetch_message_safe(channel, message_id: int):
    try:
        return await channel.fetch_message(message_id)
    except:
        return None
# =============================
#  Embed actualizar_todos_los_mensajes_partido - REV NO TOCA
# =============================
async def actualizar_todos_los_mensajes_partido(guild, partido):
    embed = build_partido_embed(partido)

    # ==========================
    # Canal del partido
    # ==========================
    if partido.get("canal_partido_id") and partido.get("mensaje_partido_id"):
        canal = await _get_channel_safe(guild, int(partido["canal_partido_id"]))  # ✅ añadido
        if canal:
            try:
                msg = await _fetch_message_safe(canal, int(partido["mensaje_partido_id"]))  # ✅ añadido
                if msg:
                    await msg.edit(embed=embed)
            except Exception as e:
                print("❌ actualizar_todos_los_mensajes_partido canal_partido:", e)  # ✅ añadido

    # ==========================
    # Mensaje en "Ver Partidos"
    # ==========================
    if partido.get("mensaje_ver_partidos_id"):
        for canal in guild.text_channels:
            try:
                msg = await canal.fetch_message(int(partido["mensaje_ver_partidos_id"]))
                await msg.edit(embed=embed)
                break
            except:
                continue
# =============================
#  Embed actualizar_mensaje_publico_partido - REV (MULTI) + FIX RECUPERAR IDS
# =============================
async def actualizar_mensaje_publico_partido(guild, partido):
    global data
    data = load_data()

    embed = build_partido_embed(partido)

    # ✅ helper para ids que a veces quedan como str/None
    def _to_int(x):
        try:
            return int(x)
        except:
            return None

    canal_id = _to_int(partido.get("canal_publico_id"))
    msg_id   = _to_int(partido.get("mensaje_publico_id"))

    # ✅ MULTI: UID del partido (o activo)
    uid = (partido.get("torneo_uid") or get_server(data, guild.id).get("activo", "DEFAULT"))
    uid = (uid or "DEFAULT").upper().strip()
    uid_low = uid.lower()

    # ======================================================
    # ✅ NUEVO: FALLBACK si faltan IDs -> buscar canal/mensaje
    # ======================================================
    if not canal_id or not msg_id:
        try:
            # canal esperado: partidos-a-disputar-<uid>
            nombre_canal = f"partidos-a-disputar-{uid_low}"

            canal_fallback = None
            for ch in getattr(guild, "text_channels", []):
                try:
                    if (ch.name or "").lower() == nombre_canal:
                        canal_fallback = ch
                        break
                except:
                    pass

            if canal_fallback:
                # buscar mensaje por heurística (id + equipos)
                async for m in canal_fallback.history(limit=80, oldest_first=False):
                    try:
                        if not m.embeds:
                            continue
                        e = m.embeds[0]

                        # heurísticas: que aparezca el id y/o equipos
                        t = (e.title or "")
                        d = (e.description or "")
                        texto = f"{t}\n{d}".lower()

                        ok_id = str(partido.get("id")) in texto
                        ok_eq = (str(partido.get("a", "")).lower() in texto) and (str(partido.get("b", "")).lower() in texto)

                        if ok_id or ok_eq:
                            partido["canal_publico_id"] = canal_fallback.id
                            partido["mensaje_publico_id"] = m.id

                            # ✅ guardar para que ya no vuelva a ser None
                            try:
                                guild_id = guild.id
                                set_torneo_activo_multi(data, guild_id, uid)
                                save_data(data)
                            except:
                                pass

                            canal_id = canal_fallback.id
                            msg_id = m.id
                            break
                    except:
                        continue
        except Exception as e:
            print("⚠️ Fallback buscar IDs público falló:", repr(e))

    # ======================================================
    # ✅ Actualización normal (si ya hay IDs)
    # ======================================================
    if canal_id and msg_id:
        canal = guild.get_channel(canal_id)
        if canal:
            try:
                msg = await canal.fetch_message(msg_id)

                # ✅ recrear la view pública con el botón
                view_publica = None
                rol_streamer_id = data.get("rol_streamer_id")  # OJO: aquí es data, no torneo

                if rol_streamer_id:
                    try:
                        view_publica = discord.ui.View(timeout=None)
                        view_publica.add_item(
                            PostularStreamerButton(partido["id"], rol_streamer_id, uid)
                        )
                    except Exception as e:
                        print("⚠️ Error creando view_publica/botón streamer:", repr(e))
                        view_publica = None

                await msg.edit(embed=embed, view=view_publica)

            except Exception as e:
                print("⚠️ Error actualizando mensaje público partido:", repr(e))
    else:
        # ✅ NUEVO: si sigue sin ids, al menos lo vemos en consola
        print("DEBUG publico ids:", canal_id, msg_id, "postulados:", partido.get("streamers_postulados"))
# =============================
#  Boton Tabla - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class TablaButton(discord.ui.Button):
    def __init__(self, torneo_uid: str):
        super().__init__(
            label="📊 Tabla de posiciones",
            style=discord.ButtonStyle.primary
        )
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)  # ✅ compat
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)   # ✅ torneo correcto

        tabla = torneo.get("tabla")
        if not tabla:
            await interaction.response.send_message(
                "❌ Aún no hay resultados",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="📊 Tabla de posiciones",
            color=discord.Color.green()
        )

        for eq, d in sorted(tabla.items(), key=lambda x: x[1]["pts"], reverse=True):
            embed.add_field(
                name=eq,
                value=f"PJ {d['pj']} | PG {d['pg']} | PP {d['pp']} | PTS {d['pts']}",
                inline=False
            )

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message(
            "📊 Tabla publicada",
            ephemeral=True
        )
# =============================
# 🏆 BOTÓN ADMIN INICIAR ELIMINATORIAS - REV  [MULTI SIN BORRAR LÓGICA]
# =============================
class IniciarEliminatoriasButton(discord.ui.Button):
    def __init__(self, admin_id, torneo_uid: str):
        super().__init__(
            label="🏆 Iniciar eliminatorias",
            style=discord.ButtonStyle.danger
        )
        self.admin_id = admin_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)  # ✅ compat
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)   # ✅ torneo correcto

        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        if not torneo.get("tabla"):
            await interaction.response.send_message(
                "❌ Aún no hay tabla de posiciones",
                ephemeral=True
            )
            return

        # ✅ brackets para ESTE torneo (nota: tu función usa get_torneo legacy)
        generar_brackets_eliminatoria_multi(guild_id, self.torneo_uid) # por ahora queda igual
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        save_data(data)

        await interaction.channel.send(
            "🏆 **FASE ELIMINATORIA INICIADA**",
            view=PanelEliminatorias(self.admin_id)  # luego la hacemos multi si hace falta
        )

        await interaction.response.send_message(
            "✅ Eliminatorias creadas",
            ephemeral=True
        )
# =============================
# 🧩 BOTÓN ADMIN RESULTADO ELIMINATORIO - REV  [MULTI]
# =============================
class ResultadoEliminatoriaButton(discord.ui.Button):
    def __init__(self, admin_id, torneo_uid: str):
        super().__init__(
            label="🏁 Resultado eliminatoria",
            style=discord.ButtonStyle.success
        )
        self.admin_id = admin_id
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        if interaction.user.id != self.admin_id:
            await interaction.response.send_message(
                "❌ Solo administradores",
                ephemeral=True
            )
            return

        # ✅ si tu modal ya acepta uid, se lo pasamos; si no, cae al viejo sin romper
        try:
            await interaction.response.send_modal(
                ResultadoEliminatoriaModal(self.torneo_uid)
            )
        except TypeError:
            await interaction.response.send_modal(
                ResultadoEliminatoriaModal()
            )
# =============================
# Ver brackets Button - REV  [MULTI]
# =============================
class VerBracketsButton(discord.ui.Button):
    def __init__(self, torneo_uid: str):
        super().__init__(
            label="👀 Ver brackets",
            style=discord.ButtonStyle.secondary
        )
        self.torneo_uid = torneo_uid  # ✅ NUEVO

    async def callback(self, interaction):
        global data
        data = load_data()

        guild_id = interaction.guild.id
        set_torneo_activo_multi(data, guild_id, self.torneo_uid)
        torneo = get_torneo_v2(data, guild_id, self.torneo_uid)

        brackets = torneo.get("eliminatorias", [])

        if not brackets:
            await interaction.response.send_message(
                "❌ No hay eliminatorias",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="🏆 Brackets eliminatorios",
            color=discord.Color.gold()
        )

        for b in brackets:
            estado = "🔒 Cerrado" if b.get("bloqueado") else "🟢 Activo"
            resultado = b.get("resultado") or "Pendiente"

            embed.add_field(
                name=f"⚔️ Match {b.get('id')}",
                value=f"{b.get('a')} 🆚 {b.get('b')}\n"
                      f"📊 {resultado}\n"
                      f"🏅 Ganador: {b.get('ganador', '—')}\n"
                      f"{estado}",
                inline=False
            )

        await interaction.channel.send(embed=embed)
        await interaction.response.send_message(
            "👀 Brackets publicados",
            ephemeral=True
        )
# =============================
# 🎮 PANEL ELIMINATORIAS - REV  [MULTI] ✅ (COMPAT 2/3 args)
# =============================
class PanelEliminatorias(discord.ui.View):
    def __init__(self, *args, **kwargs):
        """
        Soporta:
        - PanelEliminatorias(torneo_id, admin_id, torneo_uid)
        - PanelEliminatorias(admin_id, torneo_uid)   (compat con llamadas viejas)
        - PanelEliminatorias(admin_id=..., torneo_uid=..., torneo_id=...)
        """
        super().__init__(timeout=None)

        # --------- parse args / kwargs (sin romper llamadas viejas) ----------
        torneo_id = kwargs.get("torneo_id", None)
        admin_id = kwargs.get("admin_id", None)
        torneo_uid = kwargs.get("torneo_uid", kwargs.get("uid", "DEFAULT"))

        if len(args) == 3:
            torneo_id, admin_id, torneo_uid = args
        elif len(args) == 2:
            admin_id, torneo_uid = args
        elif len(args) == 1:
            admin_id = args[0]

        self.admin_id = admin_id
        self.torneo_id = torneo_id
        self.torneo_uid = torneo_uid or "DEFAULT"

        # ✅ estos botones reciben UID
        self.add_item(VerBracketsButton(self.torneo_uid))
        self.add_item(ResultadoEliminatoriaButton(self.admin_id, self.torneo_uid))
# =============================
# PANEL TORNEO PUBLICO - REV  [MULTI]
# =============================
class PanelTorneo(discord.ui.View):
    def __init__(self, torneo_id, admin_id, torneo_uid: str):
        super().__init__(timeout=None)
        self.admin_id = admin_id
        self.torneo_id = torneo_id
        self.torneo_uid = torneo_uid

        if admin_id:
            # ✅ SorteoButton ahora recibe (torneo_uid, admin_id)
            self.add_item(SorteoButton(self.torneo_uid, admin_id))

        # ✅ estos ahora son multi
        self.add_item(VerPartidosButton(self.torneo_uid))
        self.add_item(TablaButton(self.torneo_uid))

        if admin_id:
            self.add_item(IniciarEliminatoriasButton(admin_id, self.torneo_uid))
# =============================
# Def Next partido ID
# =============================
def _next_partido_id(torneo: dict) -> int:
    partidos = torneo.get("partidos", [])

    usados = []
    for p in partidos:
        try:
            pid = int(str(p.get("id")))
            usados.append(pid)
        except (TypeError, ValueError):
            pass

    # ✅ siempre devuelve un entero válido
    return (max(usados) + 1) if usados else 1
# =============================
# Def Asegurar Equipo en torneo y tabla
# =============================
def _asegurar_equipo_en_torneo_y_tabla(torneo: dict, nombre_equipo: str):
    # ✅ blindajes de estructura
    torneo.setdefault("equipos", [])
    torneo.setdefault("tabla", {})

    nombre_equipo = (nombre_equipo or "").strip()
    if not nombre_equipo:
        return

    # ✅ si el equipo no existe en torneo["equipos"], lo agregamos (logo None)
    existe_en_lista = False
    for e in torneo["equipos"]:
        if isinstance(e, dict) and (e.get("nombre") or "").strip() == nombre_equipo:
            existe_en_lista = True
            break

    if not existe_en_lista:
        torneo["equipos"].append({"nombre": nombre_equipo, "logo": None})

    # ✅ si no existe en tabla, lo agregamos
    if nombre_equipo not in torneo["tabla"]:
        torneo["tabla"][nombre_equipo] = {"pj": 0, "pg": 0, "pp": 0, "pts": 0}
# =============================
# track_recurso_torneo
# =============================
def track_recurso_torneo(
    torneo: dict,
    *,
    canal_id: int | None = None,
    categoria_id: int | None = None
):
    # 🔒 blindaje estructura
    torneo.setdefault("recursos", {})
    torneo["recursos"].setdefault("canales", [])
    torneo["recursos"].setdefault("categorias", [])

    # ✅ normalizar ids (por si llegan como str)
    try:
        canal_id = int(canal_id) if canal_id is not None else None
    except:
        canal_id = None

    try:
        categoria_id = int(categoria_id) if categoria_id is not None else None
    except:
        categoria_id = None

    # ✅ evitar ids inválidos
    if canal_id and canal_id not in torneo["recursos"]["canales"]:
        torneo["recursos"]["canales"].append(canal_id)

    if categoria_id and categoria_id not in torneo["recursos"]["categorias"]:
        torneo["recursos"]["categorias"].append(categoria_id)

    # (opcional) return para debug
    return torneo["recursos"]
# =============================
# SLASH COMMANDS - REV 
# =============================
# =============================
# /admin_create
# =============================
@bot.slash_command(name="admin_create", description="Asignar rol creador de torneos")
async def admin_create(ctx, rol: discord.Role):
    global data
    data = load_data()

    if not ctx.author.guild_permissions.administrator:
        await ctx.respond("❌ Solo admins", ephemeral=True)
        return

    data["rol_admin_torneo_id"] = rol.id
    save_data(data)

    await ctx.respond(f"✅ Rol **{rol.name}** autorizado", ephemeral=True)
# =============================
# /Iniciar_Torneo
# =============================
@bot.slash_command(name="iniciar_torneo", description="Abrir panel admin del torneo")
async def iniciar_torneo(ctx: discord.ApplicationContext):
    global data
    data = load_data()

    rol_id = data.get("rol_admin_torneo_id")

    if not rol_id or not any(r.id == rol_id for r in ctx.author.roles):
        await ctx.respond("❌ No tienes permisos", ephemeral=True)
        return

    guild_id = ctx.guild.id

    # ✅ MULTI: usa el torneo ACTIVO del servidor
    torneo = get_torneo_v2(data, guild_id)
    uid = torneo.get("torneo_uid", "DEFAULT")

    # mantener tu misma intención (inicializar/asegurar estructura)
    torneo.setdefault("creador", ctx.author.id)
    torneo.setdefault("logo", None)

    # ✅ compat: data["torneo"] apunta al torneo activo
    set_torneo_activo_multi(data, guild_id, uid)

    save_data(data)

    await ctx.respond(
        f"⚙️ Panel de configuración del torneo (UID: `{uid}`)",
        view=PanelConfig(ctx.author.id, uid),  # ✅ PASAR UID para que no mezcle torneos
        ephemeral=True
    )
# =============================
# /add_streamer_role
# =============================
@bot.slash_command(
    name="add_streamer_role",
    description="Define el rol de streamer del torneo",
)
@discord.default_permissions(administrator=True)
async def add_streamer_role(
    ctx: discord.ApplicationContext,
    rol: discord.Role
):
    global data
    data = load_data()

    data["rol_streamer_id"] = rol.id
    save_data(data)

    await ctx.respond(
        f"🎥 Rol de **Streamer** configurado correctamente:\n{rol.mention}",
        ephemeral=True
    )
# =============================
# /torneo_crear
# =============================
@bot.slash_command(name="torneo_crear", description="Crea un torneo nuevo en este servidor")
async def torneo_crear(ctx: discord.ApplicationContext):
    global data
    data = load_data()

    guild_id = ctx.guild.id
    uid = new_torneo_uid()

    # crea torneo vacío y lo marca activo
    get_torneo_multi(data, guild_id, uid)
    set_torneo_activo_uid(data, guild_id, uid)

    save_data(data)

    await ctx.respond(
        f"✅ Torneo creado. UID: `{uid}` (ahora es el activo).",
        ephemeral=True
    )
# =============================
# /torneo_listar
# =============================
@bot.slash_command(name="torneo_listar", description="Lista los torneos (UID) del servidor")
async def torneo_listar(ctx: discord.ApplicationContext):
    global data
    data = load_data()

    guild_id = ctx.guild.id
    srv = ensure_multi_torneo_schema(data, guild_id)

    activo = srv.get("activo", "DEFAULT")
    uids = list(srv.get("torneos", {}).keys())
    if not uids:
        uids = ["DEFAULT"]

    texto = "\n".join([f"- `{u}`{' ⭐' if u == activo else ''}" for u in uids])
    await ctx.respond(f"📋 Torneos en este servidor:\n{texto}", ephemeral=True)
# =============================
# /torneo_usar
# =============================
@bot.slash_command(name="torneo_usar", description="Selecciona el torneo activo por UID")
async def torneo_usar(ctx: discord.ApplicationContext, uid: str):
    global data
    data = load_data()

    guild_id = ctx.guild.id
    srv = ensure_multi_torneo_schema(data, guild_id)
    uid = uid.upper()

    if uid not in srv.get("torneos", {}):
        await ctx.respond("❌ Ese UID no existe en este servidor. Usa /torneo_listar", ephemeral=True)
        return

    set_torneo_activo_uid(data, guild_id, uid)
    save_data(data)

    await ctx.respond(f"✅ Torneo activo cambiado a `{uid}`.", ephemeral=True)
# =============================
# /partido_Crear
# =============================
@bot.slash_command(
    name="partido_crear",
    description="Crea un partido extra manualmente en un torneo (multi)."
)
async def partido_crear(
    ctx: discord.ApplicationContext,
    torneo_uid: str,
    equipo_a: str,
    equipo_b: str,
    fecha: str = "⏰ Sin definir"
):
    await ctx.defer(ephemeral=True)

    global data
    data = load_data()

    guild_id = ctx.guild.id
    uid = (torneo_uid or "").upper().strip()

    # ✅ validar UID existe
    srv = ensure_multi_torneo_schema(data, guild_id)
    if uid not in srv.get("torneos", {}):
        await ctx.respond(
            "❌ Ese UID no existe en este servidor. Usa /torneo_listar",
            ephemeral=True
        )
        return

    # ✅ fijar torneo correcto
    set_torneo_activo_multi(data, guild_id, uid)
    torneo = get_torneo_v2(data, guild_id, uid)

    # ✅ asegurar equipos/tabla (por si es un partido extra con nombre nuevo)
    _asegurar_equipo_en_torneo_y_tabla(torneo, equipo_a)
    _asegurar_equipo_en_torneo_y_tabla(torneo, equipo_b)

    # ✅ crear partido completo
    pid = _next_partido_id(torneo)

    partido = {
        "id": pid,
        "a": equipo_a.strip(),
        "b": equipo_b.strip(),
        "fecha": fecha if fecha else "⏰ Sin definir",
        "estado": "🕒 Pendiente",
        "resultado": None,
        "bloqueado": False,

        # para embeds / vistas
        "equipos": {
            "A": {"capitanes": []},
            "B": {"capitanes": []}
        },

        # streamers
        "streamers": [],
        "streamers_postulados": [],
        "streamers_aprobados": [],

        # ✅ MUY IMPORTANTE para que actualizar_mensaje_publico_partido
        # reconstruya el botón con el UID correcto:
        "torneo_uid": uid
    }

    torneo.setdefault("partidos", [])
    torneo["partidos"].append(partido)

    # ✅ guardar
    set_torneo_activo_multi(data, guild_id, uid)
    save_data(data)

    guild = ctx.guild

    # 📺 Canal público de partidos (aislado por UID)
    canal_partidos = await crear_categoria_y_canal(
        guild,
        f"⚔️ PARTIDOS - {uid}",
        f"partidos-a-disputar-{uid.lower()}"
    )

    # ✅ AÑADIDO: track canal + categoría (por ID) para borrado total
    try:
        track_recurso_torneo(torneo, canal_id=canal_partidos.id)
        if getattr(canal_partidos, "category_id", None):
            track_recurso_torneo(torneo, categoria_id=canal_partidos.category_id)
        set_torneo_activo_multi(data, guild_id, uid)
        save_data(data)
    except:
        pass

    # 🛠️ Canal ADMIN (aislado por UID)
    canal_admin = await crear_categoria_y_canal(
        guild,
        f"⚙️ ADMIN TORNEO - {uid}",
        f"admin-partidos-{uid.lower()}"
    )

    # ✅ AÑADIDO: track canal + categoría (por ID) para borrado total
    try:
        track_recurso_torneo(torneo, canal_id=canal_admin.id)
        if getattr(canal_admin, "category_id", None):
            track_recurso_torneo(torneo, categoria_id=canal_admin.category_id)
        set_torneo_activo_multi(data, guild_id, uid)
        save_data(data)
    except:
        pass

    # =============================
    # PUBLICAR PARTIDO (PÚBLICO)
    # =============================
    embed = build_partido_embed(partido)

    view_publica = discord.ui.View(timeout=None)
    rol_streamer_id = data.get("rol_streamer_id")
    if rol_streamer_id:
        view_publica.add_item(
            PostularStreamerButton(partido["id"], rol_streamer_id, uid)
        )

    mensaje = await canal_partidos.send(embed=embed, view=view_publica)

    partido["canal_publico_id"] = canal_partidos.id
    partido["mensaje_publico_id"] = mensaje.id

    set_torneo_activo_multi(data, guild_id, uid)
    save_data(data)

    # =============================
    # PANEL ADMIN DEL PARTIDO
    # =============================
    admin_id = ctx.author.id

    view_admin = discord.ui.View(timeout=None)
    view_admin.add_item(EditarPartidoButton(admin_id, partido["id"], uid))
    view_admin.add_item(EditarFechaButton(admin_id, partido["id"], uid))
    view_admin.add_item(EditarEstadoButton(admin_id, partido["id"], uid))
    view_admin.add_item(ResultadoButton(admin_id, partido["id"], uid))
    view_admin.add_item(CrearCanalPartidoButton(admin_id, partido["id"], uid))
    view_admin.add_item(AñadirStreamerButton(partido["id"], uid))
    view_admin.add_item(IniciarFaseBaneoButton(partido["id"], uid))

    await canal_admin.send(
        f"🛠️ **Panel administrador – Partido #{partido['id']}**\n"
        f"⚔️ **{partido['a']} vs {partido['b']}**\n"
        f"🧩 Torneo UID: `{uid}`",
        view=view_admin
    )

    await ctx.respond(
        f"✅ Partido extra creado (ID `{pid}`) en torneo `{uid}`.\n"
        f"📌 Público: {canal_partidos.mention}\n"
        f"🛠️ Admin: {canal_admin.mention}",
        ephemeral=True
    )
# =============================
# Borrar recursis torneo
# =============================
import discord

async def borrar_recursos_torneo(guild: discord.Guild, torneo: dict, uid: str):
    """
    Borra canales/categorías del torneo.
    - Primero intenta por IDs guardados (torneo["recursos"])
    - Si no existen, usa fallback por nombres que contengan el UID
    """
    borrados_canales = 0
    borrados_categorias = 0

    # ✅ NUEVO: sets para evitar doble borrado
    borrados_ids = set()

    # ✅ NUEVO: normalizar uid para comparaciones seguras
    uid = (uid or "").upper().strip()
    uid_low = uid.lower()

    # ============
    # 1) BORRADO POR IDS (RECOMENDADO)
    # ============
    recursos = torneo.get("recursos", {})
    canales_ids = list(dict.fromkeys(recursos.get("canales", [])))  # unique
    categorias_ids = list(dict.fromkeys(recursos.get("categorias", [])))

    # ✅ NUEVO: helper para borrar threads si el canal los soporta
    async def _borrar_threads_de_canal(ch):
        try:
            # TextChannel / ForumChannel tienen .threads (threads activos)
            threads = getattr(ch, "threads", None)
            if threads:
                for th in list(threads):
                    try:
                        await th.delete(reason=f"Borrado torneo {uid}")
                    except:
                        pass
        except:
            pass

    # ✅ NUEVO: helper para borrar un canal (con threads)
    async def _borrar_canal(ch, reason: str):
        nonlocal borrados_canales
        try:
            if not ch:
                return
            if ch.id in borrados_ids:
                return
            await _borrar_threads_de_canal(ch)
            await ch.delete(reason=reason)
            borrados_canales += 1
            borrados_ids.add(ch.id)
        except:
            pass

    # borrar canales por id
    for cid in canales_ids:
        ch = guild.get_channel(cid)
        if ch:
            await _borrar_canal(ch, f"Borrado torneo {uid}")

    # borrar categorías por id (al final)
    for catid in categorias_ids:
        cat = discord.utils.get(guild.categories, id=catid)
        if cat:
            try:
                if catid in borrados_ids:
                    continue

                # ✅ NUEVO: borrar threads dentro (si hay foros/text)
                for ch in list(cat.channels):
                    await _borrar_threads_de_canal(ch)

                # borrar canales dentro de la categoría
                for ch in list(cat.channels):
                    await _borrar_canal(ch, f"Borrado torneo {uid}")

                # borrar categoría
                try:
                    await cat.delete(reason=f"Borrado torneo {uid}")
                    borrados_categorias += 1
                    borrados_ids.add(catid)
                except:
                    pass
            except:
                pass

    # ============
    # 2) FALLBACK POR NOMBRES (SI NO SE GUARDARON IDS)
    # ============
    patrones_categoria = [
        f"🏆 TORNEO - ",
        f"⚔️ PARTIDOS - {uid}",
        f"⚙️ ADMIN TORNEO - {uid}",
        f"📛 CANALES FASE DE BANEO - {uid}",
        f"📊 CLASIFICACIÓN - {uid}",
    ]

    # ✅ NUEVO: patrones “seguros” para canales
    # Ej: "tabla-abc123", "admin-partidos-abc123", "partidos-a-disputar-abc123"
    def _match_canal_seguro(nombre: str) -> bool:
        n = (nombre or "").lower()
        return (
            n.endswith(f"-{uid_low}")
            or f"-{uid_low}-" in n
            or n.startswith(f"tabla-{uid_low}")
            or n.startswith(f"admin-partidos-{uid_low}")
            or n.startswith(f"partidos-a-disputar-{uid_low}")
            or n.startswith(f"info-general-{uid_low}")
            or n.startswith(f"equipos-{uid_low}")
        )

    # 2.1 borrar canales sueltos (texto/voz/foro/stage) fuera de categorías
    # ✅ NUEVO: incluir más tipos además de text_channels
    canales_fuera = []

    # ✅ CORRECCIÓN: en discord.py algunas props pueden no existir; usamos getattr defensivo
    try:
        canales_fuera.extend(list(getattr(guild, "text_channels", [])))
    except:
        pass
    try:
        canales_fuera.extend(list(getattr(guild, "voice_channels", [])))
    except:
        pass
    try:
        canales_fuera.extend(list(getattr(guild, "forum_channels", [])))  # discord.py 2.x
    except:
        pass
    try:
        canales_fuera.extend(list(getattr(guild, "stage_channels", [])))
    except:
        pass

    # ✅ NUEVO: no borrar canales que estén dentro de categorías (solo “sueltos”)
    for ch in canales_fuera:
        try:
            if not ch:
                continue

            # ✅ NUEVO: si ya se borró por ID, saltar
            if ch.id in borrados_ids:
                continue

            # ✅ NUEVO: solo canales “fuera de categoría”
            if getattr(ch, "category_id", None) is not None:
                continue

            # solo borrar si match “seguro”
            if _match_canal_seguro(getattr(ch, "name", "")):
                await _borrar_canal(ch, f"Borrado torneo {uid} (fallback)")
        except:
            pass

    # 2.2 borrar categorías del torneo (y lo que contengan)
    for cat in list(guild.categories):
        cname = cat.name or ""

        # ✅ (tu lógica original se mantiene)
        es_uid = (
            cname.endswith(f"- {uid}")
            or any(p in cname for p in patrones_categoria)
            or (uid in cname)
        )

        if es_uid:
            try:
                # ✅ NUEVO: evitar borrar si ya se borró por ID
                if cat.id in borrados_ids:
                    continue

                for ch in list(cat.channels):
                    try:
                        if ch.id in borrados_ids:
                            continue

                        # ✅ NUEVO: borrar threads dentro si hay
                        await _borrar_threads_de_canal(ch)

                        await _borrar_canal(ch, f"Borrado torneo {uid} (fallback)")
                    except:
                        pass

                try:
                    await cat.delete(reason=f"Borrado torneo {uid} (fallback)")
                    borrados_categorias += 1
                    borrados_ids.add(cat.id)
                except:
                    pass
            except:
                pass

    return borrados_canales, borrados_categorias
# =============================
# /torneo borrar
# =============================
@bot.slash_command(
    name="torneo_borrar",
    description="Borra un torneo por UID y elimina todos sus canales/categorías"
)
async def torneo_borrar(ctx: discord.ApplicationContext, uid: str):
    await ctx.defer(ephemeral=True)  # ✅ OK

    global data
    data = load_data()

    # ✅ NUEVO: blindaje si no hay servidor (DM)
    if ctx.guild is None:
        try:
            await ctx.followup.send("❌ Este comando solo funciona dentro de un servidor.", ephemeral=True)
        except:
            pass
        return

    # ✅ seguridad: solo admin (puedes cambiar a rol_admin_torneo_id si prefieres)
    if not ctx.author.guild_permissions.administrator:
        try:
            await ctx.followup.send("❌ Solo administradores pueden borrar torneos.", ephemeral=True)
        except:
            pass
        return

    guild_id = ctx.guild.id
    uid = (uid or "").upper().strip()

    srv = ensure_multi_torneo_schema(data, guild_id)
    torneos = srv.get("torneos", {})

    if uid not in torneos:
        try:
            await ctx.followup.send("❌ Ese UID no existe. Usa `/torneo_listar`.", ephemeral=True)
        except:
            pass
        return

    torneo = torneos[uid]

    # ✅ NUEVO: mensaje previo (por si luego se borra el canal)
    try:
        await ctx.followup.send(
            f"🗑️ Borrando torneo `{uid}`... (canales/categorías + data)",
            ephemeral=True
        )
    except:
        pass

    # 1) borrar recursos Discord
    try:
        borrados_canales, borrados_categorias = await borrar_recursos_torneo(ctx.guild, torneo, uid)
    except Exception:
        borrados_canales, borrados_categorias = 0, 0

    # 2) borrar del data.json
    try:
        del torneos[uid]
    except:
        pass

    # 3) si era el activo, cambiar a otro
    if srv.get("activo") == uid:
        nuevo_activo = next(iter(torneos.keys()), "DEFAULT")
        srv["activo"] = nuevo_activo

    save_data(data)

    # ✅ NUEVO: intentar followup; si el canal fue borrado, mandar DM como fallback
    msg_final = (
        f"✅ Torneo `{uid}` eliminado.\n"
        f"📌 Canales borrados: `{borrados_canales}` | Categorías borradas: `{borrados_categorias}`"
    )

    try:
        await ctx.followup.send(msg_final, ephemeral=True)
    except:
        try:
            await ctx.author.send(msg_final)
        except:
            pass
# =============================
# READY
# =============================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")

keep_alive()  # ⬅️ antes de bot.run
bot.run(TOKEN)
