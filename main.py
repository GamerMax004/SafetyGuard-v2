import discord
from discord import app_commands
from discord.ext import commands, tasks
import json
import os
from datetime import datetime
import logging
import random
import string
import pytz
import asyncio
import io
import zipfile
from typing import Optional

# ═══════════════════════════════════════════════════════
#   ADMIN KONFIGURATION
# ═══════════════════════════════════════════════════════
ADMIN_USER_IDS = [1211683189186105434]

GERMANY_TZ = pytz.timezone('Europe/Berlin')

def get_now() -> datetime:
    return datetime.now(GERMANY_TZ)

def make_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return GERMANY_TZ.localize(dt)
    return dt.astimezone(GERMANY_TZ)

# ═══════════════════════════════════════════════════════
#   LOGGING
# ═══════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('safety_guard.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('SafetyGuard')

# ═══════════════════════════════════════════════════════
#   BOT SETUP
# ═══════════════════════════════════════════════════════
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)

BG_DATA_FILE = "bg_data.json"

# ═══════════════════════════════════════════════════════
#   FARBEN & KONSTANTEN
# ═══════════════════════════════════════════════════════
COLOR_PRIMARY = 0x1B4332
COLOR_SUCCESS = 0x005418
COLOR_WARNING = 0x4f3e01
COLOR_ERROR   = 0x610900
COLOR_INFO    = 0x003457

MITARBEITER_ROLE_IDS   = [1408800823571513537, 1495094890298871874]
LEITUNGSEBENE_ROLE_IDS = [1408797319134187601, 1495094890307256559]

FOOTER_ICON  = "https://media.discordapp.net/attachments/1501962625238696032/1501962897796890756/SGv2.png?ex=69fdfb73&is=69fca9f3&hm=f58514bf4dd23e28818d4463bf53086f88205dd126517d534f00d6bb7fd5b6a8&=&format=webp&quality=lossless&width=625&height=625"
AUTOMOD_ICON = "https://media.discordapp.net/attachments/1473692441726029874/1473692787156455474/1072-automod.png?ex=699722dc&is=6995d15c&hm=08ad340d3673e1f1076cbf73d235ea3b0e8ef10b07abb8d24ea66d85c6b59edb&=&format=webp&quality=lossless&width=250&height=250"

# ═══════════════════════════════════════════════════════
#   GEFAHRKLASSEN
# ═══════════════════════════════════════════════════════
BG_GEFAHRKLASSEN = {
    1:  {"label": "Stufe 1",  "multiplikator": 1.0,  "beschreibung": "Minimales Risiko (Büro, Verwaltung)"},
    2:  {"label": "Stufe 2",  "multiplikator": 1.3,  "beschreibung": "Sehr niedriges Risiko (Handel, Gastronomie)"},
    3:  {"label": "Stufe 3",  "multiplikator": 1.6,  "beschreibung": "Niedriges Risiko (Handwerk, Logistik)"},
    4:  {"label": "Stufe 4",  "multiplikator": 2.0,  "beschreibung": "Leicht erhöhtes Risiko (Bank, Fahrschule)"},
    5:  {"label": "Stufe 5",  "multiplikator": 2.5,  "beschreibung": "Mittleres Risiko (HARS/ADAC, Rettungsdienst)"},
    6:  {"label": "Stufe 6",  "multiplikator": 3.0,  "beschreibung": "Hohes Risiko (Sicherheitsdienst)"},
    7:  {"label": "Stufe 7",  "multiplikator": 3.8,  "beschreibung": "Sehr hohes Risiko (Polizei)"},
    8:  {"label": "Stufe 8",  "multiplikator": 4.5,  "beschreibung": "Extremes Risiko (SEK / Spezialeinheiten)"},
    9:  {"label": "Stufe 9",  "multiplikator": 5.5,  "beschreibung": "Sehr extremes Risiko (Feuerwehr, THW)"},
    10: {"label": "Stufe 10", "multiplikator": 7.0,  "beschreibung": "Maximales Risiko (Katastrophenschutz)"},
}

# ═══════════════════════════════════════════════════════
#   DATENSTRUKTUR
# ═══════════════════════════════════════════════════════
DEFAULT_BG_CONFIG = {
    "bg_forum_channel_id":   None,
    "bg_log_channel_id":     None,
    "bg_kassenwart_role_id": None,
    "bg_category_id":        None,
}

DEFAULT_BG_DATA = {
    "fraktionen":   {},
    "einzahlungen": {},
    "auszahlungen": {},
    "schaden":      {},
    "bg_config":    DEFAULT_BG_CONFIG.copy(),
    "logs":         [],
}

def load_bg_data() -> dict:
    if os.path.exists(BG_DATA_FILE):
        with open(BG_DATA_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        for key in DEFAULT_BG_DATA:
            if key not in d:
                d[key] = DEFAULT_BG_DATA[key]
        return d
    return json.loads(json.dumps(DEFAULT_BG_DATA))

def save_bg_data(d: dict):
    with open(BG_DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=4, ensure_ascii=False)

bg_data = load_bg_data()

# ═══════════════════════════════════════════════════════
#   ID GENERATOREN
#   FIX: k=6 statt k=4 für weniger Kollisionsrisiko
# ═══════════════════════════════════════════════════════
def _rand(k=6) -> str:
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=k))

def generate_bg_einzahlung_id() -> str:
    return f"BGE-{get_now().strftime('%y%m')}-{_rand()}"

def generate_bg_auszahlung_id() -> str:
    return f"BGA-{get_now().strftime('%y%m')}-{_rand()}"

def generate_bg_schaden_id() -> str:
    return f"SCH-{get_now().strftime('%y%m')}-{_rand()}"

# ═══════════════════════════════════════════════════════
#   HILFSFUNKTIONEN
# ═══════════════════════════════════════════════════════
def add_log_entry(action: str, user_id: int, details: dict):
    bg_data["logs"].append({
        "timestamp": get_now().isoformat(),
        "action":    action,
        "user_id":   user_id,
        "details":   details
    })
    save_bg_data(bg_data)

def get_fraktion_beitrag(fraktion_key: str) -> float:
    """
    FIX: Formel war basis * multiplikator / gefahrklasse — Division entfernt.
    Korrekt: Basisbeitrag × Multiplikator (pro Mitglied).
    """
    frak = bg_data["fraktionen"].get(fraktion_key)
    if not frak:
        return 0.0
    gk = BG_GEFAHRKLASSEN.get(frak["gefahrklasse"], {})
    return round(frak["basis_beitrag"] * gk.get("multiplikator", 1.0), 2)

def create_zip_buffer() -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if os.path.exists(BG_DATA_FILE):
            zf.write(BG_DATA_FILE, arcname="bg_data.json")
    buf.seek(0)
    return buf

async def send_to_bg_log(guild: discord.Guild, embed: discord.Embed):
    cfg   = bg_data.get("bg_config", {})
    ch_id = cfg.get("bg_log_channel_id")
    if ch_id:
        try:
            ch = guild.get_channel(ch_id)
            if ch:
                await ch.send(embed=embed)
        except Exception as e:
            logger.error(f"Log Fehler: {e}")

# ═══════════════════════════════════════════════════════
#   BERECHTIGUNGSPRÜFUNGEN
# ═══════════════════════════════════════════════════════
def is_admin(interaction: discord.Interaction) -> bool:
    return interaction.user.id in ADMIN_USER_IDS

def is_mitarbeiter(interaction: discord.Interaction) -> bool:
    for role_id in MITARBEITER_ROLE_IDS + LEITUNGSEBENE_ROLE_IDS:
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True
    return is_admin(interaction)

def is_leitungsebene(interaction: discord.Interaction) -> bool:
    for role_id in LEITUNGSEBENE_ROLE_IDS:
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True
    return is_admin(interaction)

def is_bg_kassenwart(interaction: discord.Interaction) -> bool:
    cfg     = bg_data.get("bg_config", {})
    role_id = cfg.get("bg_kassenwart_role_id")
    if role_id:
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True
    return is_leitungsebene(interaction)

def is_fraktion_leitung(interaction: discord.Interaction, frak_key: str) -> bool:
    frak    = bg_data["fraktionen"].get(frak_key, {})
    role_id = frak.get("leitungs_role_id")
    if role_id:
        role = interaction.guild.get_role(role_id)
        if role and role in interaction.user.roles:
            return True
    return is_bg_kassenwart(interaction)

def build_error_embed(title: str, description: str, needed_permission: Optional[str] = None) -> discord.Embed:
    e = discord.Embed(title=title, description=f"> {description}", color=COLOR_ERROR)
    e.set_author(name="Automatische Berechtigungsprüfung", icon_url=AUTOMOD_ICON)
    if needed_permission:
        e.add_field(name="Benötigte Berechtigung", value=f"> `{needed_permission}`", inline=False)
    e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    return e

# ═══════════════════════════════════════════════════════
#   EMBED BUILDER
# ═══════════════════════════════════════════════════════
def build_fraktion_embed(frak_key: str, frak: dict) -> discord.Embed:
    gk_num  = frak.get("gefahrklasse", 1)
    gk      = BG_GEFAHRKLASSEN.get(gk_num, {})
    beitrag = get_fraktion_beitrag(frak_key)
    status  = "<:3518checkmark:1501936312205316106> Aktiv" if frak.get("aktiv") else "<:3518crossmark:1501936313300029440> Inaktiv"
    typ_str = "🏭 Firma" if frak.get("typ") == "firma" else "🏢 Fraktion"

    total_eingezahlt = sum(e["betrag"] for e in bg_data.get("einzahlungen", {}).values() if e.get("fraktion") == frak_key)
    total_ausgezahlt = sum(a["betrag"] for a in bg_data.get("auszahlungen", {}).values() if a.get("fraktion") == frak_key and a.get("status") == "bestaetigt")
    saldo            = total_eingezahlt - total_ausgezahlt

    embed = discord.Embed(
        title=f"{frak['name']} — Akte",
        color=0x383940,
        timestamp=get_now(),
    )
    mitglieder_discord = len(frak.get("discord_mitglieder", []))
    embed.add_field(
        name="__Allgemeine Informationen__",
        value=(
            f"> `-` **Typ:** {typ_str}\n"
            f"> `-` **Name:** {frak['name']} (`{frak_key}`)\n"
            f"> `-` **Gefahrklasse:** `{gk.get('label', '—')}` — {gk.get('beschreibung', '—')}\n"
            f"> `-` **Multiplikator:** `× {gk.get('multiplikator', 1.0)}`\n"
            f"> `-` **Status:** {status}"
        ),
        inline=False,
    )
    embed.add_field(name="__Beitragsberechnung__", value=
                    f"> `-` **Basisbeitrag:** `{frak['basis_beitrag']:,.2f} €` pro Mitarbeiter\n"
                    f"> `-` **Multiplikator:** `× {gk.get('multiplikator', 1.0)}`\n"
                    f"> `-` **Mitarbeiter:** `× {mitglieder_discord}`\n"
                    , inline=False)
    embed.add_field(name="Monatlicher Beitrag", value=f"> `{beitrag * mitglieder_discord:,.2f} €`", inline=False)
    embed.add_field(
        name="__Finanzübersicht__",
        value=(
            f"> `-` **Eingezahlt:** `{total_eingezahlt:,.2f} €`\n"
            f"> `-` **Ausgezahlt:** `{total_ausgezahlt:,.2f} €`\n"
            f"> `-` **Saldo:** `{saldo:,.2f} €`"
        ),
        inline=False,
    )
    if frak.get("erstellt_am"):
        try:
            ts = make_aware(datetime.fromisoformat(frak["erstellt_am"])).strftime("%d.%m.%Y um %H:%M Uhr")
        except Exception:
            ts = "—"
        embed.add_field(name="__Aufgenommen am__", value=f"> `{ts}`", inline=True)

    embed.set_image(url="https://media.discordapp.net/attachments/1501962625238696032/1501963832405524550/image.png?ex=69fdfc52&is=69fcaad2&hm=29a5bdc60b18e102a9e60914e17a521dc0db05777fa35d9d4c180a1468d55351&=&format=webp&quality=lossless&width=1409&height=256")
    embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    return embed

# ═══════════════════════════════════════════════════════
#   FORUM / THREAD HELPERS
# ═══════════════════════════════════════════════════════
async def update_fraktion_forum_post(guild: discord.Guild, frak_key: str):
    frak = bg_data["fraktionen"].get(frak_key)
    if not frak:
        return
    thread_id = frak.get("forum_info_thread_id") or frak.get("forum_thread_id")
    if not thread_id:
        return
    try:
        thread = guild.get_thread(thread_id)
        if not thread:
            thread = await guild.fetch_channel(thread_id)
        async for msg in thread.history(limit=5, oldest_first=True):
            if msg.author.id == (guild.me.id if guild.me else bot.user.id) and msg.embeds:
                await msg.edit(embed=build_fraktion_embed(frak_key, frak))
                return
    except Exception as e:
        logger.error(f"BG Forum-Post Update Fehler ({frak_key}): {e}")

async def send_fraktion_backup(guild: discord.Guild, frak_key: str):
    frak             = bg_data["fraktionen"].get(frak_key)
    backup_thread_id = frak.get("forum_backup_thread_id") if frak else None
    if not backup_thread_id:
        return
    try:
        thread = guild.get_thread(backup_thread_id)
        if not thread:
            thread = await guild.fetch_channel(backup_thread_id)
        if not thread:
            return
        ts          = get_now().strftime("%Y%m%d_%H%M%S")
        frak_export = {
            "exported_at":  get_now().isoformat(),
            "fraktion_key": frak_key,
            "fraktion":     frak,
            "einzahlungen": {k: v for k, v in bg_data.get("einzahlungen", {}).items() if v.get("fraktion") == frak_key},
            "auszahlungen": {k: v for k, v in bg_data.get("auszahlungen", {}).items() if v.get("fraktion") == frak_key},
            "schaden":      {k: v for k, v in bg_data.get("schaden", {}).items()      if v.get("fraktion") == frak_key},
        }
        buf  = io.BytesIO(json.dumps(frak_export, indent=2, ensure_ascii=False).encode("utf-8"))
        file = discord.File(buf, filename=f"bg_backup_{frak_key}_{ts}.json")
        embed = discord.Embed(
            title="🗄️ Automatische Datensicherung",
            description=f"> Aktueller Datenstand der Fraktion **{frak.get('name', frak_key)}**.",
            color=COLOR_INFO, timestamp=get_now(),
        )
        embed.add_field(name="Stand", value=f"> {get_now().strftime('%d.%m.%Y, %H:%M Uhr')}", inline=True)
        embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await thread.send(embed=embed, file=file)
    except Exception as e:
        logger.error(f"BG Backup Fehler ({frak_key}): {e}")

# ═══════════════════════════════════════════════════════
#   DM HELPER — Versicherungsübersicht
# ═══════════════════════════════════════════════════════
async def send_insurance_dm(member: discord.Member, guild: discord.Guild):
    versicherte: list[tuple[str, dict]] = []
    for key, frak in bg_data["fraktionen"].items():
        if not frak.get("aktiv"):
            continue
        if member.id in frak.get("discord_mitglieder", []):
            versicherte.append((key, frak))
            continue
        role_id = frak.get("mitglieds_role_id")
        if role_id:
            role = guild.get_role(role_id)
            if role and role in member.roles:
                versicherte.append((key, frak))
                continue
        l_role_id = frak.get("leitungs_role_id")
        if l_role_id:
            role = guild.get_role(l_role_id)
            if role and role in member.roles:
                versicherte.append((key, frak))

    if not versicherte:
        return

    embed = discord.Embed(
        title="DVG, deine Berufsgenossenschaft!",
        description=(
            f"Herzlich Willkommen!\n"
            "> Du bist über die **Berufsgenossenschaft (BG)** gesetzlich unfallversichert. "
            "Bei Arbeitsunfällen, Verletzungen im Dienst oder Berufskrankheiten "
            "hast du Anspruch auf Leistungen der BG.\n\n"
            "**Was ist die BG?**\n"
            "> Deine Fraktion oder Firma zahlt monatlich Beiträge, "
            "damit du im Schadensfall abgesichert bist. Die Leistungen umfassen "
            "Verletztengeld, Schadensfälle, und mehr."
        ),
        color=0x383940,
        timestamp=get_now()
    )

    frak_lines = []
    for key, frak in versicherte:
        beitrag = get_fraktion_beitrag(key)
        gk      = BG_GEFAHRKLASSEN.get(frak.get("gefahrklasse", 1), {})
        typ_str = "Firma" if frak.get("typ") == "firma" else "Fraktion"
        frak_lines.append(
            f"> {frak.get('emoji', '🏢')} **{frak['name']}** ({typ_str})\n"
            f">  ├ Gefahrklasse: `{gk.get('label', '—')}`\n"
            f">  └ Monatsbeitrag: `{beitrag:,.2f} €`"
        )
    embed.add_field(name=f"__Deine Versicherungen ({len(versicherte)})__", value="\n".join(frak_lines), inline=False)
    embed.add_field(
        name="__Im Schadensfall__",
        value=(
            "> **1.** Schaden über das **Schaden-Panel** in deinem Fraktionskanal einreichen\n"
            "> **2.** Unser Team prüft und bestätigt die Auszahlung\n"
            "> **3.** Auszahlung erfolgt nach Genehmigung"
        ),
        inline=False
    )
    embed.add_field(
        name="__Leistungen der BG__",
        value=(
            "> `-` Verletztengeld bei Arbeitsunfällen\n"
            "> `-` Krankenfahrten durch die Berufsfeuerwehr Hamburg\n"
            "> `-` Sachschäden durch Arbeitsunfälle\n"
        ),
        inline=False
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1501962625238696032/1501965531224342581/image.png?ex=69fdfde7&is=69fcac67&hm=08d8261c1e3195edc84a1d0876d342726e6bde30e775b05eb4c4e4fa2068e1e5&=&format=webp&quality=lossless&width=1409&height=259")
    embed.set_footer(text=f"Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)

    try:
        await member.send(embed=embed)
        logger.info(f"Versicherungs-DM gesendet an {member} ({len(versicherte)} Fraktionen)")
    except discord.Forbidden:
        logger.warning(f"Konnte keine DM an {member} senden (DMs deaktiviert)")
    except Exception as e:
        logger.error(f"DM Fehler: {e}")

# ═══════════════════════════════════════════════════════
#   MODALS — EINZAHLUNG
# ═══════════════════════════════════════════════════════
class BGEinzahlungModal(discord.ui.Modal, title="Einzahlung erfassen"):
    betrag_input = discord.ui.TextInput(label="Betrag (€)",            placeholder="8500.00",                  required=True,  max_length=12)
    verwendung   = discord.ui.TextInput(label="Verwendungszweck",      placeholder="Monatsbeitrag April 2026", required=True,  max_length=200)
    zahlender    = discord.ui.TextInput(label="Zahlender (RP-Name)",   placeholder="Max Mustermann / Präsidium", required=True, max_length=100)
    notiz        = discord.ui.TextInput(label="Notiz (optional)",      required=False, max_length=300, style=discord.TextStyle.paragraph)

    def __init__(self, fraktion_key: str):
        super().__init__()
        self.fraktion_key = fraktion_key

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            betrag = float(self.betrag_input.value.replace(",", ".").replace("€", "").strip())
        except ValueError:
            await interaction.followup.send(embed=build_error_embed("Ungültiger Betrag!", "Bitte eine Zahl eingeben."), ephemeral=True)
            return

        ez_id = generate_bg_einzahlung_id()
        frak  = bg_data["fraktionen"][self.fraktion_key]
        bg_data["einzahlungen"][ez_id] = {
            "id":          ez_id,
            "fraktion":    self.fraktion_key,
            "betrag":      betrag,
            "verwendung":  self.verwendung.value,
            "zahlender":   self.zahlender.value,
            "notiz":       self.notiz.value or "",
            "erfasst_von": interaction.user.id,
            "erfasst_am":  get_now().isoformat(),
        }
        save_bg_data(bg_data)
        await update_fraktion_forum_post(interaction.guild, self.fraktion_key)

        thread_id = frak.get("forum_einz_thread_id") or frak.get("forum_thread_id")
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
                if thread:
                    te = discord.Embed(title="💰 Einzahlung gebucht", color=COLOR_SUCCESS, timestamp=get_now())
                    te.add_field(name="ID",          value=f"> `{ez_id}`",                 inline=True)
                    te.add_field(name="Betrag",      value=f"> **`{betrag:,.2f} €`**",      inline=True)
                    te.add_field(name="Verwendung",  value=f"> {self.verwendung.value}",    inline=False)
                    te.add_field(name="Zahlender",   value=f"> {self.zahlender.value}",     inline=True)
                    te.add_field(name="Erfasst von", value=f"> {interaction.user.mention}", inline=True)
                    if self.notiz.value:
                        te.add_field(name="Notiz",   value=f"> {self.notiz.value}",        inline=False)
                    te.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await thread.send(embed=te)
            except Exception as ex:
                logger.error(f"Einzahlung Thread-Fehler: {ex}")

        await send_fraktion_backup(interaction.guild, self.fraktion_key)
        add_log_entry("BG_EINZAHLUNG", interaction.user.id, {"fraktion": self.fraktion_key, "betrag": betrag, "ez_id": ez_id})

        log_e = discord.Embed(title="BG: Einzahlung erfasst!", color=COLOR_SUCCESS, timestamp=get_now())
        log_e.add_field(name="Fraktion",       value=f"> {frak.get('emoji', '🏢')} **{frak['name']}**", inline=True)
        log_e.add_field(name="Betrag",         value=f"> `{betrag:,.2f} €`",                           inline=True)
        log_e.add_field(name="Einzahlungs-ID", value=f"> `{ez_id}`",                                   inline=True)
        log_e.add_field(name="Erfasst von",    value=f"> {interaction.user.mention}",                  inline=False)
        log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await send_to_bg_log(interaction.guild, log_e)

        s = discord.Embed(title="Einzahlung gebucht!", color=COLOR_SUCCESS)
        s.add_field(name="Einzahlungs-ID", value=f"> `{ez_id}`",         inline=True)
        s.add_field(name="Betrag",         value=f"> `{betrag:,.2f} €`", inline=True)
        s.add_field(name="Fraktion",       value=f"> {frak['name']}",    inline=True)
        s.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.followup.send(embed=s, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   MODALS — AUSZAHLUNG
# ═══════════════════════════════════════════════════════
class BGAuszahlungModal(discord.ui.Modal, title="Auszahlung beantragen"):
    betrag_input  = discord.ui.TextInput(label="Auszahlungsbetrag (€)", placeholder="1500.00",                                   required=True,  max_length=12)
    empfaenger    = discord.ui.TextInput(label="Empfänger (RP-Name)",   placeholder="Officer John Doe",                          required=True,  max_length=100)
    grund         = discord.ui.TextInput(label="Auszahlungsgrund",      placeholder="Arbeitsunfall 12.04.2026 — Verletztenrente", required=True,  max_length=300, style=discord.TextStyle.paragraph)
    kategorie_inp = discord.ui.TextInput(label="Kategorie",             placeholder="Verletztengeld / Rente / Reha / Sonstiges",  required=True,  max_length=80)
    nachweis      = discord.ui.TextInput(label="Nachweis / Aktenzeichen", placeholder="SM-2604-XXXX oder Link",                  required=True,  max_length=200)

    def __init__(self, fraktion_key: str):
        super().__init__()
        self.fraktion_key = fraktion_key

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            betrag = float(self.betrag_input.value.replace(",", ".").replace("€", "").strip())
        except ValueError:
            await interaction.followup.send(embed=build_error_embed("Ungültiger Betrag!", "Bitte eine Zahl eingeben."), ephemeral=True)
            return

        az_id = generate_bg_auszahlung_id()
        frak  = bg_data["fraktionen"][self.fraktion_key]
        bg_data["auszahlungen"][az_id] = {
            "id":            az_id,
            "fraktion":      self.fraktion_key,
            "betrag":        betrag,
            "empfaenger":    self.empfaenger.value,
            "grund":         self.grund.value,
            "kategorie":     self.kategorie_inp.value,
            "nachweis":      self.nachweis.value,
            "status":        "ausstehend",
            "beantragt_von": interaction.user.id,
            "beantragt_am":  get_now().isoformat(),
            "bearbeitet_von": None,
            "bearbeitet_am":  None,
        }
        save_bg_data(bg_data)

        # Fraktions-Auszahlungs-Thread
        ausz_thread_id = frak.get("forum_ausz_thread_id") or frak.get("forum_thread_id")
        if ausz_thread_id:
            try:
                ausz_thread = interaction.guild.get_thread(ausz_thread_id) or await interaction.guild.fetch_channel(ausz_thread_id)
                if ausz_thread:
                    ta = discord.Embed(title="📤 Auszahlungsantrag gestellt", color=COLOR_WARNING, timestamp=get_now())
                    ta.add_field(name="Antrags-ID",    value=f"> `{az_id}`",                   inline=True)
                    ta.add_field(name="Betrag",        value=f"> **`{betrag:,.2f} €`**",        inline=True)
                    ta.add_field(name="Empfänger",     value=f"> {self.empfaenger.value}",      inline=True)
                    ta.add_field(name="Kategorie",     value=f"> {self.kategorie_inp.value}",   inline=True)
                    ta.add_field(name="Status",        value="> ⏳ Ausstehend",                  inline=True)
                    ta.add_field(name="Nachweis",      value=f"> {self.nachweis.value}",        inline=False)
                    ta.add_field(name="Beantragt von", value=f"> {interaction.user.mention}",   inline=True)
                    ta.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await ausz_thread.send(embed=ta)
            except Exception as ex:
                logger.error(f"Auszahlung Frak-Thread-Fehler: {ex}")

        # FIX: Einheitlich über send_to_bg_log + Action-View
        req_e = discord.Embed(title="Auszahlungsantrag", color=COLOR_WARNING, timestamp=get_now())
        req_e.add_field(name="Antrags-ID", value=f"> `{az_id}`",                                      inline=True)
        req_e.add_field(name="Fraktion",   value=f"> {frak.get('emoji', '🏢')} **{frak['name']}**",   inline=True)
        req_e.add_field(name="Betrag",     value=f"> **`{betrag:,.2f} €`**",                          inline=True)
        req_e.add_field(name="Empfänger",  value=f"> {self.empfaenger.value}",                        inline=True)
        req_e.add_field(name="Kategorie",  value=f"> {self.kategorie_inp.value}",                     inline=True)
        req_e.add_field(name="Grund",      value=f"> {self.grund.value}",                             inline=False)
        req_e.add_field(name="Nachweis",   value=f"> {self.nachweis.value}",                          inline=False)
        req_e.add_field(name="Beantragt von", value=f"> {interaction.user.mention}",                  inline=True)
        req_e.add_field(name="Status",     value="> ⏳ Ausstehend",                                    inline=True)
        req_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)

        cfg      = bg_data.get("bg_config", {})
        az_ch_id = cfg.get("bg_log_channel_id")
        if az_ch_id:
            try:
                az_ch = interaction.guild.get_channel(az_ch_id)
                if az_ch:
                    await az_ch.send(embed=req_e, view=BGAuszahlungActionView(az_id, self.fraktion_key))
            except Exception as ex:
                logger.error(f"Auszahlung Log-Channel-Fehler: {ex}")

        add_log_entry("BG_AUSZAHLUNG_EINGEREICHT", interaction.user.id, {"fraktion": self.fraktion_key, "betrag": betrag, "az_id": az_id})
        await send_fraktion_backup(interaction.guild, self.fraktion_key)

        s = discord.Embed(title="Auszahlungsantrag gestellt!", color=COLOR_SUCCESS)
        s.add_field(name="Antrags-ID", value=f"> `{az_id}`",         inline=True)
        s.add_field(name="Betrag",     value=f"> `{betrag:,.2f} €`", inline=True)
        s.add_field(name="Status",     value="> ⏳ Ausstehend",       inline=True)
        s.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.followup.send(embed=s, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   MODALS — SCHADENMELDUNG
# ═══════════════════════════════════════════════════════
class BGSchadenModal(discord.ui.Modal, title="Schadenmeldung einreichen"):
    schadensdatum = discord.ui.TextInput(label="Schadendatum",              placeholder="12.04.2026",                              required=True,  max_length=20)
    schadensort   = discord.ui.TextInput(label="Schadensort / Einsatz",     placeholder="Autobahn A3, Streife Nord",                required=True,  max_length=200)
    beschreibung  = discord.ui.TextInput(label="Schadensbeschreibung",      placeholder="Detaillierte Schilderung des Vorfalls...", required=True,  max_length=500, style=discord.TextStyle.paragraph)
    betrag        = discord.ui.TextInput(label="Geschätzter Schaden (€)",   placeholder="2500.00",                                 required=True,  max_length=12)
    nachweis      = discord.ui.TextInput(label="Nachweis / Aktenzeichen",   placeholder="SM-2604-XXXX oder Link zum Bericht",       required=True,  max_length=200)

    def __init__(self, fraktion_key: str):
        super().__init__()
        self.fraktion_key = fraktion_key

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            betrag_val = float(self.betrag.value.replace(",", ".").replace("€", "").strip())
        except ValueError:
            await interaction.followup.send(embed=build_error_embed("Ungültiger Betrag!", "Bitte eine Zahl eingeben."), ephemeral=True)
            return

        sch_id = generate_bg_schaden_id()
        frak   = bg_data["fraktionen"][self.fraktion_key]

        # FIX: Redundante schaden-Prüfung entfernt — load_bg_data garantiert den Key
        bg_data["schaden"][sch_id] = {
            "id":               sch_id,
            "fraktion":         self.fraktion_key,
            "betrag":           betrag_val,
            "schadensdatum":    self.schadensdatum.value,
            "schadensort":      self.schadensort.value,
            "beschreibung":     self.beschreibung.value,
            "nachweis":         self.nachweis.value,
            "status":           "ausstehend",
            "eingereicht_von":  interaction.user.id,
            "eingereicht_am":   get_now().isoformat(),
            "bearbeitet_von":   None,
            "bearbeitet_am":    None,
        }
        save_bg_data(bg_data)
        # FIX: Forum-Post nach Schadenmeldung aktualisieren
        await update_fraktion_forum_post(interaction.guild, self.fraktion_key)

        # Schaden-Thread der Fraktion
        thread_id = frak.get("forum_schaden_thread_id")
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
                if thread:
                    te = discord.Embed(title="📋 Neue Schadenmeldung", color=COLOR_WARNING, timestamp=get_now())
                    te.add_field(name="Meldungs-ID",     value=f"> `{sch_id}`",                     inline=True)
                    te.add_field(name="Betrag",          value=f"> **`{betrag_val:,.2f} €`**",       inline=True)
                    te.add_field(name="Status",          value="> ⏳ Ausstehend",                    inline=True)
                    te.add_field(name="Schadendatum",    value=f"> {self.schadensdatum.value}",      inline=True)
                    te.add_field(name="Schadensort",     value=f"> {self.schadensort.value}",        inline=True)
                    te.add_field(name="Beschreibung",    value=f"> {self.beschreibung.value}",       inline=False)
                    te.add_field(name="Nachweis",        value=f"> {self.nachweis.value}",           inline=False)
                    te.add_field(name="Eingereicht von", value=f"> {interaction.user.mention}",      inline=True)
                    te.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await thread.send(embed=te, view=BGSchadenActionView(sch_id, self.fraktion_key))
            except Exception as ex:
                logger.error(f"Schaden Thread Fehler: {ex}")

        # Log-Kanal + Kassenwart pingen
        log_e = discord.Embed(title="BG: Neue Schadenmeldung!", color=COLOR_WARNING, timestamp=get_now())
        log_e.add_field(name="Meldungs-ID",     value=f"> `{sch_id}`",                                    inline=True)
        log_e.add_field(name="Fraktion",        value=f"> {frak.get('emoji', '🏢')} **{frak['name']}**",  inline=True)
        log_e.add_field(name="Betrag",          value=f"> `{betrag_val:,.2f} €`",                         inline=True)
        log_e.add_field(name="Eingereicht von", value=f"> {interaction.user.mention}",                    inline=False)
        log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)

        cfg_inner  = bg_data.get("bg_config", {})
        kw_role_id = cfg_inner.get("bg_kassenwart_role_id")
        cfg_log_id = cfg_inner.get("bg_log_channel_id")
        if cfg_log_id:
            try:
                log_ch = interaction.guild.get_channel(cfg_log_id)
                if log_ch:
                    if kw_role_id:
                        await log_ch.send(f"<@&{kw_role_id}> — Neue Schadenmeldung eingegangen!")
                    await log_ch.send(embed=log_e)
            except Exception as ex:
                logger.error(f"Schaden Log-Kanal Fehler: {ex}")
        else:
            await send_to_bg_log(interaction.guild, log_e)

        add_log_entry("BG_SCHADEN_EINGEREICHT", interaction.user.id, {"fraktion": self.fraktion_key, "betrag": betrag_val, "sch_id": sch_id})
        await send_fraktion_backup(interaction.guild, self.fraktion_key)

        s = discord.Embed(title="Schadenmeldung eingereicht!", color=COLOR_SUCCESS)
        s.add_field(name="Meldungs-ID", value=f"> `{sch_id}`",            inline=True)
        s.add_field(name="Betrag",      value=f"> `{betrag_val:,.2f} €`", inline=True)
        s.add_field(name="Status",      value="> ⏳ Ausstehend",           inline=True)
        s.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.followup.send(embed=s, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   MODALS — MITGLIEDER VERWALTEN
# ═══════════════════════════════════════════════════════
class BGMitgliedHinzufuegenModal(discord.ui.Modal, title="Mitglied aufnehmen"):
    mitglied_id = discord.ui.TextInput(label="Discord User-ID oder @Mention", placeholder="123456789012345678", required=True, max_length=30)
    rp_name     = discord.ui.TextInput(label="RP-Name des Mitglieds",         placeholder="Max Mustermann",       required=True, max_length=100)

    def __init__(self, fraktion_key: str):
        super().__init__()
        self.fraktion_key = fraktion_key

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = self.mitglied_id.value.strip().lstrip("<@!").rstrip(">")
        try:
            user_id = int(raw)
        except ValueError:
            await interaction.followup.send(embed=build_error_embed("Ungültige User-ID!", "Bitte eine gültige Discord User-ID eingeben."), ephemeral=True)
            return

        member = interaction.guild.get_member(user_id)
        if not member:
            await interaction.followup.send(embed=build_error_embed("Nicht gefunden!", "Dieses Mitglied ist nicht auf dem Server."), ephemeral=True)
            return

        frak = bg_data["fraktionen"].get(self.fraktion_key)
        if not frak:
            await interaction.followup.send(embed=build_error_embed("Fehler!", "Fraktion nicht gefunden."), ephemeral=True)
            return

        if "discord_mitglieder" not in frak:
            frak["discord_mitglieder"] = []

        already = member.id in frak["discord_mitglieder"]
        if not already:
            frak["discord_mitglieder"].append(member.id)

        role_id = frak.get("mitglieds_role_id")
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role:
                try:
                    await member.add_roles(role, reason=f"BG: Zur {frak['name']} hinzugefügt")
                except Exception as e:
                    logger.error(f"Rolle zuweisen Fehler: {e}")

        save_bg_data(bg_data)
        await update_fraktion_forum_post(interaction.guild, self.fraktion_key)
        add_log_entry("BG_MITGLIED_HINZUGEFUEGT", interaction.user.id, {"fraktion": self.fraktion_key, "user_id": member.id, "rp_name": self.rp_name.value})

        if not already:
            try:
                await send_insurance_dm(member, interaction.guild)
            except Exception:
                pass

        status_text = "war bereits Mitglied — Rolle aktualisiert." if already else "erfolgreich aufgenommen!"
        e = discord.Embed(
            title="Mitglied aufgenommen!" if not already else "Mitglied bereits vorhanden",
            description=(
                f"> {member.mention} (`{self.rp_name.value}`) {status_text}\n"
                f"> Fraktion: **{frak['name']}**"
            ),
            color=COLOR_SUCCESS,
        )
        e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)

class BGMitgliedEntfernenModal(discord.ui.Modal, title="Mitglied entfernen"):
    mitglied_id = discord.ui.TextInput(label="Discord User-ID oder @Mention", placeholder="123456789012345678", required=True, max_length=30)

    def __init__(self, fraktion_key: str):
        super().__init__()
        self.fraktion_key = fraktion_key

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        raw = self.mitglied_id.value.strip().lstrip("<@!").rstrip(">")
        try:
            user_id = int(raw)
        except ValueError:
            await interaction.followup.send(embed=build_error_embed("Ungültige User-ID!", "Bitte eine gültige Discord User-ID eingeben."), ephemeral=True)
            return

        frak = bg_data["fraktionen"].get(self.fraktion_key)
        if not frak:
            await interaction.followup.send(embed=build_error_embed("Fehler!", "Fraktion nicht gefunden."), ephemeral=True)
            return

        mitglieder = frak.setdefault("discord_mitglieder", [])
        if user_id not in mitglieder:
            await interaction.followup.send(embed=build_error_embed("Nicht gefunden!", "Dieser Nutzer ist kein eingetragenes Mitglied dieser Fraktion."), ephemeral=True)
            return

        mitglieder.remove(user_id)

        member = interaction.guild.get_member(user_id)
        if member:
            role_id = frak.get("mitglieds_role_id")
            if role_id:
                role = interaction.guild.get_role(role_id)
                if role:
                    try:
                        await member.remove_roles(role, reason=f"BG: Aus {frak['name']} entfernt")
                    except Exception as e:
                        logger.error(f"Rolle entfernen Fehler: {e}")

        save_bg_data(bg_data)
        await update_fraktion_forum_post(interaction.guild, self.fraktion_key)
        add_log_entry("BG_MITGLIED_ENTFERNT", interaction.user.id, {"fraktion": self.fraktion_key, "user_id": user_id})

        e = discord.Embed(
            title="Mitglied entfernt!",
            description=f"> <@{user_id}> wurde aus der Fraktion **{frak['name']}** ausgetragen.",
            color=COLOR_SUCCESS,
        )
        e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   PERSISTENTE VIEWS — AUSZAHLUNG AKTIONEN
# ═══════════════════════════════════════════════════════
class BGAuszahlungActionView(discord.ui.View):
    def __init__(self, az_id: str, fraktion_key: str):
        super().__init__(timeout=None)
        self.az_id        = az_id
        self.fraktion_key = fraktion_key

    def _get_az_id(self, message: discord.Message) -> str:
        if message and message.embeds:
            for field in message.embeds[0].fields:
                if "Antrags-ID" in field.name:
                    val = field.value
                    s = val.find("`") + 1
                    e = val.rfind("`")
                    if s > 0 and e > s:
                        return val[s:e]
        return self.az_id

    @discord.ui.button(label="Genehmigen", style=discord.ButtonStyle.green,  custom_id="bg_az_genehmigen", emoji="<:3518checkmark:1501936312205316106>")
    async def genehmigen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bg_kassenwart(interaction):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur der Kassenwart.", "Kassenwart"), ephemeral=True)
            return
        az_id   = self._get_az_id(interaction.message)
        pending = bg_data.get("auszahlungen", {}).get(az_id)
        if not pending or pending.get("status") != "ausstehend":
            await interaction.response.send_message("<:3518crossmark:1501936313300029440> Bereits bearbeitet.", ephemeral=True)
            return

        bg_data["auszahlungen"][az_id].update({
            "status":         "bestaetigt",
            "bearbeitet_von": interaction.user.id,
            "bearbeitet_am":  get_now().isoformat(),
        })
        save_bg_data(bg_data)
        await update_fraktion_forum_post(interaction.guild, pending["fraktion"])

        frak      = bg_data["fraktionen"].get(pending["fraktion"], {})
        thread_id = frak.get("forum_ausz_thread_id") or frak.get("forum_thread_id")
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
                if thread:
                    te = discord.Embed(title="Auszahlung genehmigt!", color=COLOR_SUCCESS, timestamp=get_now())
                    te.add_field(name="Antrags-ID",    value=f"> `{az_id}`",                          inline=True)
                    te.add_field(name="Betrag",        value=f"> **`{pending['betrag']:,.2f} €`**",    inline=True)
                    te.add_field(name="Empfänger",     value=f"> {pending['empfaenger']}",             inline=True)
                    te.add_field(name="Genehmigt von", value=f"> {interaction.user.mention}",          inline=True)
                    te.add_field(name="Datum",         value=f"> {get_now().strftime('%d.%m.%Y • %H:%M')}", inline=True)
                    te.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await thread.send(embed=te)
            except Exception as ex:
                logger.error(f"Az-Thread-Fehler: {ex}")

        try:
            upd = interaction.message.embeds[0]
            upd.color = COLOR_SUCCESS
            for i, field in enumerate(upd.fields):
                if field.name == "Status":
                    upd.set_field_at(i, name="Status", value="<:3518checkmark:1501936312205316106> Genehmigt", inline=True)
                    break
            upd.add_field(name="Genehmigt von", value=f"{interaction.user.mention}",          inline=True)
            upd.add_field(name="Genehmigt am",  value=get_now().strftime("%d.%m.%Y • %H:%M"), inline=True)
            await interaction.message.edit(embed=upd, view=None)
        except Exception as ex:
            logger.error(f"Az-Edit-Fehler: {ex}")

        add_log_entry("BG_AUSZAHLUNG_BESTAETIGT", interaction.user.id, {"az_id": az_id, "fraktion": pending["fraktion"], "betrag": pending["betrag"]})
        log_e = discord.Embed(title="BG: Auszahlung genehmigt!", color=COLOR_SUCCESS, timestamp=get_now())
        log_e.add_field(name="Antrags-ID",    value=f"> `{az_id}`",                   inline=True)
        log_e.add_field(name="Betrag",        value=f"> `{pending['betrag']:,.2f} €`", inline=True)
        log_e.add_field(name="Genehmigt von", value=f"> {interaction.user.mention}",   inline=False)
        log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await send_to_bg_log(interaction.guild, log_e)
        await send_fraktion_backup(interaction.guild, pending["fraktion"])
        await interaction.response.send_message(f"<:3518checkmark:1501936312205316106> Auszahlung `{az_id}` genehmigt.", ephemeral=True)

    @discord.ui.button(label="Ablehnen", style=discord.ButtonStyle.danger, custom_id="bg_az_ablehnen", emoji="<:3518crossmark:1501936313300029440>")
    async def ablehnen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bg_kassenwart(interaction):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur der Kassenwart.", "Kassenwart"), ephemeral=True)
            return
        az_id   = self._get_az_id(interaction.message)
        pending = bg_data.get("auszahlungen", {}).get(az_id)
        if not pending or pending.get("status") != "ausstehend":
            await interaction.response.send_message("<:3518crossmark:1501936313300029440> Bereits bearbeitet.", ephemeral=True)
            return

        bg_data["auszahlungen"][az_id].update({
            "status":         "abgelehnt",
            "bearbeitet_von": interaction.user.id,
            "bearbeitet_am":  get_now().isoformat(),
        })
        save_bg_data(bg_data)

        frak_abl = bg_data["fraktionen"].get(pending["fraktion"], {})
        abl_tid  = frak_abl.get("forum_ausz_thread_id") or frak_abl.get("forum_thread_id")
        if abl_tid:
            try:
                abl_thr = interaction.guild.get_thread(abl_tid) or await interaction.guild.fetch_channel(abl_tid)
                if abl_thr:
                    ta = discord.Embed(title="Auszahlung abgelehnt!", color=COLOR_ERROR, timestamp=get_now())
                    ta.add_field(name="Antrags-ID",    value=f"> `{az_id}`",                    inline=True)
                    ta.add_field(name="Betrag",        value=f"> `{pending['betrag']:,.2f} €`",  inline=True)
                    ta.add_field(name="Abgelehnt von", value=f"> {interaction.user.mention}",    inline=True)
                    ta.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await abl_thr.send(embed=ta)
            except Exception as ex:
                logger.error(f"Az-Ablehnung Thread-Fehler: {ex}")

        try:
            upd = interaction.message.embeds[0]
            upd.color = COLOR_ERROR
            for i, field in enumerate(upd.fields):
                if field.name == "Status":
                    upd.set_field_at(i, name="Status", value="<:3518crossmark:1501936313300029440> Abgelehnt", inline=True)
                    break
            upd.add_field(name="Abgelehnt von", value=f"{interaction.user.mention}",          inline=True)
            upd.add_field(name="Abgelehnt am",  value=get_now().strftime("%d.%m.%Y • %H:%M"), inline=True)
            await interaction.message.edit(embed=upd, view=None)
        except Exception as ex:
            logger.error(f"Az-Edit-Fehler: {ex}")

        add_log_entry("BG_AUSZAHLUNG_ABGELEHNT", interaction.user.id, {"az_id": az_id, "fraktion": pending["fraktion"]})
        log_e = discord.Embed(title="BG: Auszahlung abgelehnt!", color=COLOR_ERROR, timestamp=get_now())
        log_e.add_field(name="Antrags-ID",    value=f"> `{az_id}`",                 inline=True)
        log_e.add_field(name="Abgelehnt von", value=f"> {interaction.user.mention}", inline=False)
        log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await send_to_bg_log(interaction.guild, log_e)
        await send_fraktion_backup(interaction.guild, pending["fraktion"])
        await interaction.response.send_message(f"<:3518crossmark:1501936313300029440> Auszahlung `{az_id}` abgelehnt.", ephemeral=True)

# ═══════════════════════════════════════════════════════
#   PERSISTENTE VIEWS — SCHADENMELDUNG AKTIONEN
# ═══════════════════════════════════════════════════════
class BGSchadenGenehmigenModal(discord.ui.Modal, title="Schadenmeldung genehmigen"):
    zahlungslink = discord.ui.TextInput(
        label="Zahlungslink / Zahlungsbeleg",
        placeholder="https://banking.example.com/beleg/12345 oder Beleg-Nr.",
        required=True,
        max_length=300,
    )
    anmerkung = discord.ui.TextInput(
        label="Anmerkung (optional)",
        placeholder="Auszahlung erfolgt innerhalb von 24h …",
        required=False,
        max_length=300,
        style=discord.TextStyle.paragraph,
    )

    def __init__(self, sch_id: str, fraktion_key: str, original_message: discord.Message):
        super().__init__()
        self.sch_id           = sch_id
        self.fraktion_key     = fraktion_key
        self.original_message = original_message

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        schaden = bg_data.get("schaden", {}).get(self.sch_id)
        if not schaden or schaden.get("status") != "ausstehend":
            await interaction.followup.send("Bereits bearbeitet.", ephemeral=True)
            return

        bg_data["schaden"][self.sch_id].update({
            "status":         "genehmigt",
            "bearbeitet_von": interaction.user.id,
            "bearbeitet_am":  get_now().isoformat(),
            "zahlungslink":   self.zahlungslink.value,
            "anmerkung":      self.anmerkung.value or "",
        })
        save_bg_data(bg_data)
        await update_fraktion_forum_post(interaction.guild, schaden["fraktion"])

        try:
            upd = self.original_message.embeds[0]
            upd.color = COLOR_SUCCESS
            for i, field in enumerate(upd.fields):
                if field.name == "Status":
                    upd.set_field_at(i, name="Status", value="<:3518checkmark:1501936312205316106> Genehmigt", inline=True)
                    break
            upd.add_field(name="Genehmigt von", value=interaction.user.mention,               inline=True)
            upd.add_field(name="Genehmigt am",  value=get_now().strftime("%d.%m.%Y • %H:%M"), inline=True)
            upd.add_field(name="Zahlungslink",  value=self.zahlungslink.value,                inline=False)
            if self.anmerkung.value:
                upd.add_field(name="Anmerkung", value=self.anmerkung.value,                   inline=False)
            await self.original_message.edit(embed=upd, view=None)
        except Exception as ex:
            logger.error(f"Schaden Edit-Fehler: {ex}")

        frak      = bg_data["fraktionen"].get(schaden["fraktion"], {})
        thread_id = frak.get("forum_schaden_thread_id")
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
                if thread:
                    te = discord.Embed(title="Schadenmeldung genehmigt!", color=COLOR_SUCCESS, timestamp=get_now())
                    te.add_field(name="Meldungs-ID",   value=f"> `{self.sch_id}`",                          inline=True)
                    te.add_field(name="Betrag",        value=f"> **`{schaden['betrag']:,.2f} €`**",          inline=True)
                    te.add_field(name="Genehmigt von", value=f"> {interaction.user.mention}",                inline=True)
                    te.add_field(name="Datum",         value=f"> {get_now().strftime('%d.%m.%Y • %H:%M')}",  inline=True)
                    te.add_field(name="Zahlungslink",  value=f"> {self.zahlungslink.value}",                 inline=False)
                    if self.anmerkung.value:
                        te.add_field(name="Anmerkung", value=f"> {self.anmerkung.value}",                   inline=False)
                    te.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await thread.send(embed=te)
            except Exception as ex:
                logger.error(f"Schaden Thread Fehler (genehmigt): {ex}")

        einreicher = interaction.guild.get_member(schaden.get("eingereicht_von", 0))
        if einreicher:
            try:
                dm_e = discord.Embed(
                    title="Deine Schadenmeldung wurde genehmigt!",
                    description=(
                        "> Deine Schadenmeldung bei der **Berufsgenossenschaft** wurde **genehmigt**.\n"
                        "> Die Auszahlung wird über den angegebenen Link veranlasst."
                    ),
                    color=COLOR_SUCCESS,
                    timestamp=get_now(),
                )
                dm_e.add_field(name="Meldungs-ID", value=f"> `{self.sch_id}`",                               inline=True)
                dm_e.add_field(name="Betrag",      value=f"> **`{schaden['betrag']:,.2f} €`**",              inline=True)
                dm_e.add_field(name="Fraktion",    value=f"> {frak.get('emoji', '🏢')} {frak.get('name', '—')}", inline=True)
                dm_e.add_field(name="Zahlungslink", value=f"> {self.zahlungslink.value}",                    inline=False)
                if self.anmerkung.value:
                    dm_e.add_field(name="Anmerkung", value=f"> {self.anmerkung.value}",                      inline=False)
                dm_e.set_footer(text=f"SafetyGuard v2 • {interaction.guild.name}", icon_url=FOOTER_ICON)
                await einreicher.send(embed=dm_e)
            except discord.Forbidden:
                logger.warning(f"Konnte keine DM an {einreicher} senden")
            except Exception as ex:
                logger.error(f"Schaden Genehmigung DM Fehler: {ex}")

        add_log_entry("BG_SCHADEN_GENEHMIGT", interaction.user.id, {
            "sch_id":       self.sch_id,
            "fraktion":     schaden["fraktion"],
            "betrag":       schaden["betrag"],
            "zahlungslink": self.zahlungslink.value,
        })
        await send_fraktion_backup(interaction.guild, schaden["fraktion"])

        log_e = discord.Embed(title="BG: Schadenmeldung genehmigt!", color=COLOR_SUCCESS, timestamp=get_now())
        log_e.add_field(name="Meldungs-ID",   value=f"> `{self.sch_id}`",              inline=True)
        log_e.add_field(name="Betrag",        value=f"> `{schaden['betrag']:,.2f} €`", inline=True)
        log_e.add_field(name="Genehmigt von", value=f"> {interaction.user.mention}",   inline=True)
        log_e.add_field(name="Zahlungslink",  value=f"> {self.zahlungslink.value}",    inline=False)
        log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await send_to_bg_log(interaction.guild, log_e)
        await interaction.followup.send(f"<:3518checkmark:1501936312205316106> Schadenmeldung `{self.sch_id}` genehmigt & Zahlungslink gespeichert.", ephemeral=True)

class BGSchadenActionView(discord.ui.View):
    def __init__(self, sch_id: str, fraktion_key: str):
        super().__init__(timeout=None)
        self.sch_id       = sch_id
        self.fraktion_key = fraktion_key

    def _get_sch_id(self, message: discord.Message) -> str:
        if message and message.embeds:
            for field in message.embeds[0].fields:
                if "Meldungs-ID" in field.name:
                    val = field.value
                    s = val.find("`") + 1
                    e = val.rfind("`")
                    if s > 0 and e > s:
                        return val[s:e]
        return self.sch_id

    @discord.ui.button(label="Genehmigen", style=discord.ButtonStyle.green,  custom_id="bg_sch_genehmigen", emoji="<:3518checkmark:1501936312205316106>")
    async def genehmigen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bg_kassenwart(interaction):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur der Kassenwart.", "Kassenwart"), ephemeral=True)
            return
        sch_id  = self._get_sch_id(interaction.message)
        schaden = bg_data.get("schaden", {}).get(sch_id)
        if not schaden or schaden.get("status") != "ausstehend":
            await interaction.response.send_message("Bereits bearbeitet.", ephemeral=True)
            return
        await interaction.response.send_modal(
            BGSchadenGenehmigenModal(sch_id, schaden["fraktion"], interaction.message)
        )

    @discord.ui.button(label="Ablehnen", style=discord.ButtonStyle.danger, custom_id="bg_sch_ablehnen", emoji="<:3518crossmark:1501936313300029440>")
    async def ablehnen(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_bg_kassenwart(interaction):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur der Kassenwart.", "Kassenwart"), ephemeral=True)
            return
        sch_id  = self._get_sch_id(interaction.message)
        schaden = bg_data.get("schaden", {}).get(sch_id)
        if not schaden or schaden.get("status") != "ausstehend":
            await interaction.response.send_message("Bereits bearbeitet.", ephemeral=True)
            return

        bg_data["schaden"][sch_id].update({
            "status":         "abgelehnt",
            "bearbeitet_von": interaction.user.id,
            "bearbeitet_am":  get_now().isoformat(),
        })
        save_bg_data(bg_data)

        try:
            upd = interaction.message.embeds[0]
            upd.color = COLOR_ERROR
            for i, field in enumerate(upd.fields):
                if field.name == "Status":
                    upd.set_field_at(i, name="Status", value="<:3518crossmark:1501936313300029440> Abgelehnt", inline=True)
                    break
            upd.add_field(name="Abgelehnt von", value=interaction.user.mention,               inline=True)
            upd.add_field(name="Abgelehnt am",  value=get_now().strftime("%d.%m.%Y • %H:%M"), inline=True)
            await interaction.message.edit(embed=upd, view=None)
        except Exception as ex:
            logger.error(f"Schaden Edit-Fehler: {ex}")

        frak      = bg_data["fraktionen"].get(schaden["fraktion"], {})
        thread_id = frak.get("forum_schaden_thread_id")
        if thread_id:
            try:
                thread = interaction.guild.get_thread(thread_id) or await interaction.guild.fetch_channel(thread_id)
                if thread:
                    ta = discord.Embed(title="Schadenmeldung abgelehnt!", color=COLOR_ERROR, timestamp=get_now())
                    ta.add_field(name="Meldungs-ID",   value=f"> `{sch_id}`",                   inline=True)
                    ta.add_field(name="Betrag",        value=f"> `{schaden['betrag']:,.2f} €`",  inline=True)
                    ta.add_field(name="Abgelehnt von", value=f"> {interaction.user.mention}",    inline=True)
                    ta.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
                    await thread.send(embed=ta)
            except Exception as ex:
                logger.error(f"Schaden Thread Fehler (abgelehnt): {ex}")

        einreicher = interaction.guild.get_member(schaden.get("eingereicht_von", 0))
        if einreicher:
            try:
                dm_e = discord.Embed(
                    title="Deine Schadenmeldung wurde abgelehnt.",
                    description=(
                        "> Deine Schadenmeldung bei der **Berufsgenossenschaft** wurde leider **abgelehnt**.\n"
                        "> Bei Rückfragen wende dich bitte an deine Fraktionsleitung oder den Kassenwart."
                    ),
                    color=COLOR_ERROR,
                    timestamp=get_now(),
                )
                dm_e.add_field(name="Meldungs-ID", value=f"> `{sch_id}`",                    inline=True)
                dm_e.add_field(name="Betrag",      value=f"> `{schaden['betrag']:,.2f} €`",  inline=True)
                dm_e.add_field(name="Fraktion",    value=f"> {frak.get('emoji', '🏢')} {frak.get('name', '—')}", inline=True)
                dm_e.set_footer(text=f"SafetyGuard v2 • {interaction.guild.name}", icon_url=FOOTER_ICON)
                await einreicher.send(embed=dm_e)
            except discord.Forbidden:
                logger.warning(f"Konnte keine DM an {einreicher} senden")
            except Exception as ex:
                logger.error(f"Schaden Ablehnung DM Fehler: {ex}")

        add_log_entry("BG_SCHADEN_ABGELEHNT", interaction.user.id, {"sch_id": sch_id, "fraktion": schaden["fraktion"]})
        await send_fraktion_backup(interaction.guild, schaden["fraktion"])

        log_e = discord.Embed(title="BG: Schadenmeldung abgelehnt!", color=COLOR_ERROR, timestamp=get_now())
        log_e.add_field(name="Meldungs-ID",   value=f"> `{sch_id}`",                inline=True)
        log_e.add_field(name="Abgelehnt von", value=f"> {interaction.user.mention}", inline=False)
        log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await send_to_bg_log(interaction.guild, log_e)
        await interaction.response.send_message(f"<:3518crossmark:1501936313300029440> Schadenmeldung `{sch_id}` abgelehnt.", ephemeral=True)

# ═══════════════════════════════════════════════════════
#   PERSISTENTE VIEWS — LEITUNGS-PANEL
# ═══════════════════════════════════════════════════════
def _extract_field_value(message: discord.Message, field_name: str) -> Optional[str]:
    if not message or not message.embeds:
        return None
    for field in message.embeds[0].fields:
        if field_name in field.name:
            return field.value.lstrip(">").strip().strip("`")
    return None

class BGLeitungPanelView(discord.ui.View):
    def __init__(self, fraktion_key: str):
        super().__init__(timeout=None)
        self.fraktion_key = fraktion_key

    def _get_key(self, message: discord.Message) -> str:
        return _extract_field_value(message, "Fraktion-Schlüssel") or self.fraktion_key

    @discord.ui.button(label="Mitglied aufnehmen", style=discord.ButtonStyle.green,     custom_id="bg_leitung_add")
    async def add_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = self._get_key(interaction.message)
        if not is_fraktion_leitung(interaction, key):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Fraktionsleitung.", "Fraktionsleitung"), ephemeral=True)
            return
        await interaction.response.send_modal(BGMitgliedHinzufuegenModal(key))

    @discord.ui.button(label="Mitglied entfernen", style=discord.ButtonStyle.danger,     custom_id="bg_leitung_remove")
    async def remove_member(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = self._get_key(interaction.message)
        if not is_fraktion_leitung(interaction, key):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Fraktionsleitung.", "Fraktionsleitung"), ephemeral=True)
            return
        await interaction.response.send_modal(BGMitgliedEntfernenModal(key))

    @discord.ui.button(label="Beitrag einzahlen",  style=discord.ButtonStyle.primary,   custom_id="bg_leitung_zahlen")
    async def zahlen(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = self._get_key(interaction.message)
        if not is_fraktion_leitung(interaction, key):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Fraktionsleitung.", "Fraktionsleitung"), ephemeral=True)
            return
        if key not in bg_data["fraktionen"]:
            await interaction.response.send_message(embed=build_error_embed("Fehler!", "Fraktion nicht gefunden."), ephemeral=True)
            return
        await interaction.response.send_modal(BGEinzahlungModal(key))

    @discord.ui.button(label="Mitgliederliste",    style=discord.ButtonStyle.secondary, custom_id="bg_leitung_liste")
    async def liste(self, interaction: discord.Interaction, button: discord.ui.Button):
        key  = self._get_key(interaction.message)
        frak = bg_data["fraktionen"].get(key)
        if not frak:
            await interaction.response.send_message(embed=build_error_embed("Fehler!", "Fraktion nicht gefunden."), ephemeral=True)
            return

        mitglieder = frak.get("discord_mitglieder", [])
        if not mitglieder:
            await interaction.response.send_message(
                embed=discord.Embed(title="Mitgliederliste", description="> Noch keine Mitglieder eingetragen.", color=COLOR_INFO),
                ephemeral=True
            )
            return

        lines = []
        for uid in mitglieder:
            m = interaction.guild.get_member(uid)
            lines.append(f"> `{uid}` — {m.mention if m else '*(nicht auf Server)*'}")

        embed = discord.Embed(
            title=f"{frak.get('emoji', '🏢')} Mitgliederliste — {frak['name']}",
            description="\n".join(lines[:20]),
            color=frak.get("farbe", COLOR_PRIMARY),
        )
        embed.set_footer(text=f"Gesamt: {len(mitglieder)} Mitglieder | SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   PERSISTENTE VIEWS — SCHADEN-PANEL
# ═══════════════════════════════════════════════════════
class BGSchadenPanelView(discord.ui.View):
    def __init__(self, fraktion_key: str):
        super().__init__(timeout=None)
        self.fraktion_key = fraktion_key

    def _get_key(self, message: discord.Message) -> str:
        return _extract_field_value(message, "Fraktion-Schlüssel") or self.fraktion_key

    def _is_member(self, interaction: discord.Interaction, key: str) -> bool:
        frak = bg_data["fraktionen"].get(key, {})
        if interaction.user.id in frak.get("discord_mitglieder", []):
            return True
        for role_id_field in ("mitglieds_role_id", "leitungs_role_id"):
            rid = frak.get(role_id_field)
            if rid:
                role = interaction.guild.get_role(rid)
                if role and role in interaction.user.roles:
                    return True
        return is_mitarbeiter(interaction)

    @discord.ui.button(label="Schaden melden", style=discord.ButtonStyle.primary, custom_id="bg_schaden_melden", emoji="📋")
    async def schaden_melden(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = self._get_key(interaction.message)
        if not self._is_member(interaction, key):
            await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Mitglieder dieser Fraktion können Schäden melden.", "Fraktionsmitglied"), ephemeral=True)
            return
        frak = bg_data["fraktionen"].get(key)
        if not frak or not frak.get("aktiv"):
            await interaction.response.send_message(embed=build_error_embed("Inaktiv!", "Diese Fraktion ist derzeit nicht aktiv."), ephemeral=True)
            return
        await interaction.response.send_modal(BGSchadenModal(key))

# ═══════════════════════════════════════════════════════
#   EVENTS
# ═══════════════════════════════════════════════════════
@bot.event
async def on_ready():
    logger.info(f'{bot.user} ist online ({bot.user.id})')
    try:
        synced = await bot.tree.sync()
        logger.info(f"on_ready: {len(synced)} Commands global synchronisiert")
    except Exception as e:
        logger.error(f"Sync Fehler: {e}")

    bot.add_view(BGAuszahlungActionView("dummy", "dummy"))
    bot.add_view(BGSchadenActionView("dummy", "dummy"))
    bot.add_view(BGLeitungPanelView("dummy"))
    bot.add_view(BGSchadenPanelView("dummy"))
    logger.info("SafetyGuard: Persistente Views registriert")

    await asyncio.sleep(1)
    if not auto_backup.is_running():
        auto_backup.start()

@bot.event
async def on_member_join(member: discord.Member):
    try:
        await send_insurance_dm(member, member.guild)
    except Exception as e:
        logger.error(f"on_member_join DM Fehler für {member}: {e}")

# ═══════════════════════════════════════════════════════
#   COMMANDS — PING
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="ping", description="Zeigt den Status und die Latenz des Bots an")
async def ping(interaction: discord.Interaction):
    ms          = round(bot.latency * 1000)
    fraktionen  = bg_data.get("fraktionen", {})
    aktive_frak = sum(1 for f in fraktionen.values() if f.get("aktiv"))
    aus_pend    = sum(1 for a in bg_data.get("auszahlungen", {}).values() if a.get("status") == "ausstehend")
    sch_pend    = sum(1 for s in bg_data.get("schaden", {}).values()      if s.get("status") == "ausstehend")
    color       = COLOR_SUCCESS if ms < 100 else (COLOR_WARNING if ms < 200 else COLOR_ERROR)
    status_val  = (
        f"> **`{ms} ms`** — Ausgezeichnete Verbindung!" if ms < 100
        else f"> **`{ms} ms`** — Stabile Verbindung!" if ms < 200
        else f"> **`{ms} ms`** — Schlechte Verbindung!"
    )
    embed = discord.Embed(title="Systemstatus SafetyGuard v2", color=color, timestamp=get_now())
    embed.add_field(name="__Verbindung__",      value=status_val,                                                                           inline=False)
    embed.add_field(name="__Fraktionen__",      value=f"> ▸ **`{aktive_frak}`** aktiv\n> ▸ **`{len(fraktionen)}`** gesamt",                 inline=True)
    embed.add_field(name="__Offene Vorgänge__", value=f"> ▸ **`{aus_pend}`** Auszahlungen\n> ▸ **`{sch_pend}`** Schadenmeldungen",          inline=True)
    embed.add_field(name="__Serverzeit__",      value=f"> `{get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}`",                                inline=False)
    embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — BACKUP & RELOAD
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="backup", description="Erstellt ein Backup der Datenbank")
async def backup_download(interaction: discord.Interaction):
    if not is_leitungsebene(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Leitungsebene.", "Leitungsebene"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        buf  = create_zip_buffer()
        file = discord.File(buf, filename=f"bg_backup_{get_now().strftime('%Y%m%d_%H%M%S')}.zip")
        await interaction.followup.send("## SafetyGuard v2 — Datenbank-Export", file=file, ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"Fehler: {e}", ephemeral=True)

@bot.tree.command(name="reload", description="Stellt die Datenbank (bg_data.json) wieder her")
@app_commands.describe(datei="bg_data.json")
async def reload_backup(interaction: discord.Interaction, datei: discord.Attachment):
    if not is_leitungsebene(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Leitungsebene.", "Leitungsebene"), ephemeral=True)
        return
    if not datei.filename.endswith('.json'):
        await interaction.response.send_message(embed=build_error_embed("Falscher Dateityp!", "Nur `.json` Dateien erlaubt."), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        content  = await datei.read()
        json_obj = json.loads(content.decode('utf-8'))
        # FIX: Alle Pflichtfelder prüfen statt nur zwei
        required = {"fraktionen", "einzahlungen", "auszahlungen", "schaden", "bg_config"}
        if required.issubset(json_obj.keys()):
            global bg_data
            bg_data = json_obj
            for key in DEFAULT_BG_DATA:
                if key not in bg_data:
                    bg_data[key] = DEFAULT_BG_DATA[key]
            save_bg_data(bg_data)
            await interaction.followup.send("<:3518checkmark:1501936312205316106> `bg_data.json` erfolgreich wiederhergestellt.", ephemeral=True)
        else:
            fehlend = required - json_obj.keys()
            await interaction.followup.send(f"<:3518crossmark:1501936313300029440> Unbekanntes Dateiformat. Fehlende Felder: `{', '.join(fehlend)}`", ephemeral=True)
    except Exception as e:
        await interaction.followup.send(f"<:3518crossmark:1501936313300029440> Fehler: {e}", ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — LOGS
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="logs-anzeigen", description="Zeigt die letzten Aktivitäten an")
@app_commands.describe(anzahl="Anzahl der Einträge (Standard: 10)")
async def show_logs(interaction: discord.Interaction, anzahl: int = 10):
    if not is_leitungsebene(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Leitungsebene.", "Leitungsebene"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    logs = bg_data.get("logs", [])
    if not logs:
        await interaction.followup.send(embed=discord.Embed(title="Keine Logs vorhanden!", color=COLOR_INFO), ephemeral=True)
        return
    anzahl = max(1, min(anzahl, 25))
    recent = list(reversed(logs[-anzahl:]))
    action_map = {
        "BG_FRAKTION_ERSTELLT":       ("🏢", "Fraktion erstellt"),
        "BG_FRAKTION_BEARBEITET":     ("✏️", "Fraktion bearbeitet"),
        "BG_EINZAHLUNG":              ("💰", "Einzahlung gebucht"),
        "BG_AUSZAHLUNG_EINGEREICHT":  ("📤", "Auszahlung eingereicht"),
        "BG_AUSZAHLUNG_BESTAETIGT":   ("✅", "Auszahlung genehmigt"),
        "BG_AUSZAHLUNG_ABGELEHNT":    ("❌", "Auszahlung abgelehnt"),
        "BG_SCHADEN_EINGEREICHT":     ("📋", "Schadenmeldung eingereicht"),
        "BG_SCHADEN_GENEHMIGT":       ("✅", "Schadenmeldung genehmigt"),
        "BG_SCHADEN_ABGELEHNT":       ("❌", "Schadenmeldung abgelehnt"),
        "BG_MITGLIED_HINZUGEFUEGT":   ("👤", "Mitglied aufgenommen"),
        "BG_MITGLIED_ENTFERNT":       ("👤", "Mitglied entfernt"),
        "BG_SETUP":                   ("⚙️", "Setup konfiguriert"),
    }
    embed = discord.Embed(title="Aktivitätsprotokoll", description=f"**Letzte {len(recent)} Aktivitäten**", color=COLOR_PRIMARY, timestamp=get_now())
    for log in recent:
        ts        = make_aware(datetime.fromisoformat(log['timestamp'])).strftime('%d.%m.%Y • %H:%M:%S')
        user      = interaction.guild.get_member(log['user_id']) if log.get('user_id') and log['user_id'] != 0 else None
        user_name = user.mention if user else "🤖 System"
        emoji, display = action_map.get(log['action'], ("📌", log['action']))
        details   = log.get('details', {})
        parts     = []
        if 'fraktion' in details:
            parts.append(f"Fraktion: `{details['fraktion']}`")
        if 'betrag' in details:
            parts.append(f"Betrag: `{details['betrag']:,.2f} €`")
        if 'rp_name' in details:
            parts.append(f"RP-Name: `{details['rp_name']}`")
        detail_str = "\n".join(f"> {p}" for p in parts[:3]) if parts else "> —"
        embed.add_field(name=f"{emoji} {display}", value=f"> **{ts}**\n> {user_name}\n{detail_str}", inline=False)
    embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.followup.send(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — SETUP
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="setup", description="[ADMIN] Modul konfigurieren")
@app_commands.describe(
    log_channel="Log-Kanal für Ereignisse",
    kassenwart_rolle="Rolle mit Zugriff auf Kassenfunktionen",
    kategorie="Kategorie, in der neue Fraktions-Forum-Channels erstellt werden",
)
async def bg_setup(
    interaction: discord.Interaction,
    log_channel:      Optional[discord.TextChannel]    = None,
    kassenwart_rolle: Optional[discord.Role]            = None,
    kategorie:        Optional[discord.CategoryChannel] = None,
):
    if not is_admin(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Administratoren.", "Administrator"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    if not any([log_channel, kassenwart_rolle, kategorie]):
        cfg = bg_data.get("bg_config", {})
        e   = discord.Embed(title="Aktuelle Konfiguration", color=COLOR_INFO, timestamp=get_now())
        e.add_field(name="Log",     value=f"<#{cfg.get('bg_log_channel_id')}>"       if cfg.get("bg_log_channel_id")     else "`Nicht gesetzt`", inline=True)
        e.add_field(name="Kassenwart", value=f"<@&{cfg.get('bg_kassenwart_role_id')}>"  if cfg.get("bg_kassenwart_role_id") else "`Nicht gesetzt`", inline=True)
        e.add_field(name="Kategorie",  value=f"<#{cfg.get('bg_category_id')}>"          if cfg.get("bg_category_id")        else "`Nicht gesetzt`", inline=True)
        e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        await interaction.followup.send(embed=e, ephemeral=True)
        return

    cfg     = bg_data.setdefault("bg_config", DEFAULT_BG_CONFIG.copy())
    changes = []
    if log_channel:
        cfg["bg_log_channel_id"] = log_channel.id
        changes.append(f"Log: {log_channel.mention}")
    if kassenwart_rolle:
        cfg["bg_kassenwart_role_id"] = kassenwart_rolle.id
        changes.append(f"Kassenwart-Rolle: {kassenwart_rolle.mention}")
    if kategorie:
        cfg["bg_category_id"] = kategorie.id
        changes.append(f"Kategorie: {kategorie.mention}")
    save_bg_data(bg_data)
    add_log_entry("BG_SETUP", interaction.user.id, {"changes": changes})

    e = discord.Embed(title="Konfiguration aktualisiert!", color=COLOR_SUCCESS, timestamp=get_now())
    e.add_field(name="__Änderungen__", value="\n".join(f"> {c}" for c in changes) if changes else "> Keine Änderungen", inline=False)
    e.add_field(name="Log",     value=f"<#{cfg.get('bg_log_channel_id')}>"       if cfg.get("bg_log_channel_id")     else "`Nicht gesetzt`", inline=True)
    e.add_field(name="Kassenwart", value=f"<@&{cfg.get('bg_kassenwart_role_id')}>"  if cfg.get("bg_kassenwart_role_id") else "`Nicht gesetzt`", inline=True)
    e.add_field(name="Kategorie",  value=f"<#{cfg.get('bg_category_id')}>"          if cfg.get("bg_category_id")        else "`Nicht gesetzt`", inline=True)
    e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.followup.send(embed=e, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — FRAKTION HINZUFÜGEN
#   FIX: mitglieder-Parameter entfernt — Verwaltung via Panel
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="fraktion-hinzufuegen", description="[ADMIN] Neue Fraktion oder Firma zur BG hinzufügen")
@app_commands.describe(
    name="Name der Fraktion / Firma",
    typ="Art der Organisation",
    gefahrstufe="Gefahrstufe 1–10",
    basisbeitrag="Monatlicher Basisbeitrag in € (pro Mitglied)",
    emoji="Emoji der Fraktion (optional)",
)
@app_commands.choices(
    gefahrstufe=[
        app_commands.Choice(name="Stufe 1 – Minimal",       value=1),
        app_commands.Choice(name="Stufe 2 – Sehr niedrig",  value=2),
        app_commands.Choice(name="Stufe 3 – Niedrig",       value=3),
        app_commands.Choice(name="Stufe 4 – Leicht erhöht", value=4),
        app_commands.Choice(name="Stufe 5 – Mittel",        value=5),
        app_commands.Choice(name="Stufe 6 – Hoch",          value=6),
        app_commands.Choice(name="Stufe 7 – Sehr hoch",     value=7),
        app_commands.Choice(name="Stufe 8 – Extrem",        value=8),
        app_commands.Choice(name="Stufe 9 – Sehr extrem",   value=9),
        app_commands.Choice(name="Stufe 10 – Maximum",      value=10),
    ],
    typ=[
        app_commands.Choice(name="Fraktion (Behörde / Organisation)", value="fraktion"),
        app_commands.Choice(name="Firma (Unternehmen)",               value="firma"),
    ],
)
async def bg_fraktion_hinzufuegen(
    interaction: discord.Interaction,
    name: str,
    typ: str,
    gefahrstufe: int,
    basisbeitrag: float,
    emoji: str = "🏢",
):
    if not is_admin(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Administratoren.", "Administrator"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    key = name.strip().replace(" ", "_")
    if key in bg_data["fraktionen"]:
        await interaction.followup.send(embed=build_error_embed("Bereits vorhanden!", f"Fraktion `{name}` existiert bereits."), ephemeral=True)
        return

    frak: dict = {
        "name":          name.strip(),
        "typ":           typ,
        "gefahrklasse":  gefahrstufe,
        "basis_beitrag": basisbeitrag,
        "farbe":         COLOR_PRIMARY,
        "emoji":         emoji,
        "aktiv":         True,
        "erstellt_am":   get_now().isoformat(),
        # Discord IDs
        "forum_channel_id":        None,
        "leitungs_role_id":        None,
        "mitglieds_role_id":       None,
        "forum_thread_id":         None,
        "forum_info_thread_id":    None,
        "forum_einz_thread_id":    None,
        "forum_ausz_thread_id":    None,
        "forum_schaden_thread_id": None,
        "forum_backup_thread_id":  None,
        # Mitgliederverwaltung (ausschließlich via Panel)
        "discord_mitglieder": [],
    }
    bg_data["fraktionen"][key] = frak

    cfg         = bg_data.get("bg_config", {})
    category_id = cfg.get("bg_category_id")
    category    = interaction.guild.get_channel(category_id) if category_id else None

    # ─── 1) Forum-Channel erstellen ─────────────────────────
    forum_ch = None
    try:
        ch_name  = f"{'🏭' if typ == 'firma' else '【🛡️】'}-{name.lower().replace(' ', '-')}"
        forum_ch = await interaction.guild.create_forum(
            name=ch_name,
            category=category,
            topic=f"Kanal der {'Firma' if typ == 'firma' else 'Fraktion'}: {name}",
            reason=f"SafetyGuard v2: Neue {'Firma' if typ == 'firma' else 'Fraktion'} {name}",
        )
        frak["forum_channel_id"] = forum_ch.id
        logger.info(f"Forum-Channel erstellt: {forum_ch.name} ({forum_ch.id})")
    except Exception as ex:
        logger.error(f"Forum-Channel Erstellfehler: {ex}")

    # ─── 2) Leitungsrolle erstellen ─────────────────────────
    try:
        l_role = await interaction.guild.create_role(
            name=f"{'Geschäftsführung' if typ == 'firma' else 'Leitung'} | {name}",
            mentionable=True,
            reason=f"SafetyGuard v2: Leitungsrolle für {name}",
        )
        frak["leitungs_role_id"] = l_role.id
        logger.info(f"Leitungsrolle erstellt: {l_role.name} ({l_role.id})")
    except Exception as ex:
        logger.error(f"Leitungsrolle Erstellfehler: {ex}")

    # ─── 3) Mitgliedsrolle erstellen ────────────────────────
    try:
        m_role = await interaction.guild.create_role(
            name=f"{'Angestellte:r' if typ == 'firma' else 'Mitglied'} | {name}",
            mentionable=False,
            reason=f"SafetyGuard v2: Mitgliedsrolle für {name}",
        )
        frak["mitglieds_role_id"] = m_role.id
        logger.info(f"Mitgliedsrolle erstellt: {m_role.name} ({m_role.id})")
    except Exception as ex:
        logger.error(f"Mitgliedsrolle Erstellfehler: {ex}")

    # ─── 4) Threads im Forum-Channel erstellen ───────────────
    if forum_ch:
        try:
            info_twm = await forum_ch.create_thread(name="📄 Informationen", embed=build_fraktion_embed(key, frak))
            try:
                await info_twm.message.pin()
            except Exception:
                pass
            frak["forum_info_thread_id"] = info_twm.thread.id
            frak["forum_thread_id"]      = info_twm.thread.id

            einz_e = discord.Embed(title=f"{name} — Einzahlungen", description="> Alle Beitragszahlungen dieser Organisation.", color=COLOR_SUCCESS, timestamp=get_now())
            einz_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
            einz_twm = await forum_ch.create_thread(name="📥 Einzahlungen", embed=einz_e)
            frak["forum_einz_thread_id"] = einz_twm.thread.id

            ausz_e = discord.Embed(title=f"{name} — Auszahlungen", description="> Alle Auszahlungsanträge dieser Organisation.", color=COLOR_WARNING, timestamp=get_now())
            ausz_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
            ausz_twm = await forum_ch.create_thread(name="📤 Auszahlungen", embed=ausz_e)
            frak["forum_ausz_thread_id"] = ausz_twm.thread.id

            sch_e = discord.Embed(title=f"{name} — Schadenmeldungen", description="> Alle Schadenmeldungen der Mitglieder dieser Organisation.", color=COLOR_ERROR, timestamp=get_now())
            sch_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
            sch_twm = await forum_ch.create_thread(name="📋 Schadenmeldungen", embed=sch_e)
            frak["forum_schaden_thread_id"] = sch_twm.thread.id

            bkp_e = discord.Embed(title=f"{name} — Backup", description="> Automatische Datensicherungen nach jeder Aktion.", color=COLOR_INFO, timestamp=get_now())
            bkp_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
            bkp_twm = await forum_ch.create_thread(name="🗄️ Backup", embed=bkp_e)
            frak["forum_backup_thread_id"] = bkp_twm.thread.id

        except Exception as ex:
            logger.error(f"Thread Erstellfehler: {ex}")

    save_bg_data(bg_data)

    gk      = BG_GEFAHRKLASSEN.get(gefahrstufe, {})
    beitrag = get_fraktion_beitrag(key)
    add_log_entry("BG_FRAKTION_ERSTELLT", interaction.user.id, {"fraktion": key, "betrag": beitrag, "typ": typ})

    e = discord.Embed(title=f"{'Firma' if typ == 'firma' else 'Fraktion'} hinzugefügt!", color=COLOR_SUCCESS, timestamp=get_now())
    e.add_field(name="__Stammdaten__", value=f"> {emoji} **{name}** ({typ.capitalize()})\n> Gefahrstufe: `{gk.get('label', '—')}`",        inline=False)
    e.add_field(name="__Beitrag__",    value=f"> Basis: `{basisbeitrag:,.2f} €`\n> Effektiv: **`{beitrag:,.2f} €/Mitglied/Monat`**",         inline=False)
    if frak.get("forum_channel_id"):
        e.add_field(name="__Forum-Channel__",  value=f"> <#{frak['forum_channel_id']}>",  inline=True)
    if frak.get("leitungs_role_id"):
        e.add_field(name="__Leitungsrolle__",  value=f"> <@&{frak['leitungs_role_id']}>", inline=True)
    if frak.get("mitglieds_role_id"):
        e.add_field(name="__Mitgliedsrolle__", value=f"> <@&{frak['mitglieds_role_id']}>", inline=True)
    e.add_field(
        name="__Nächste Schritte__",
        value=(
            "> 1. Leitungsrolle an Fraktionsleiter vergeben\n"
            f"> 2. `/leitung-panel {key}` im Fraktionskanal posten\n"
            f"> 3. `/schaden-panel {key}` im Fraktionskanal posten\n"
            "> 4. Mitglieder über das Leitungs-Panel aufnehmen"
        ),
        inline=False,
    )
    e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)

    log_e = discord.Embed(title=f"BG: Neue {'Firma' if typ == 'firma' else 'Fraktion'} aufgenommen!", color=COLOR_SUCCESS, timestamp=get_now())
    log_e.add_field(name="Name",            value=f"> **{name}**",               inline=True)
    log_e.add_field(name="Typ",             value=f"> `{typ.capitalize()}`",     inline=True)
    log_e.add_field(name="Gefahrstufe",     value=f"> `{gk.get('label', '—')}`", inline=True)
    log_e.add_field(name="Monatsbeitrag",   value=f"> `{beitrag:,.2f} €`",       inline=True)
    log_e.add_field(name="Hinzugefügt von", value=f"> {interaction.user.mention}", inline=False)
    log_e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await send_to_bg_log(interaction.guild, log_e)
    await interaction.followup.send(embed=e, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — FRAKTION BEARBEITEN
#   FIX: mitglieder-Parameter entfernt
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="fraktion-bearbeiten", description="[ADMIN] Gefahrstufe, Basisbeitrag oder Status einer Fraktion ändern")
@app_commands.describe(
    fraktion="Fraktion-Schlüssel",
    gefahrstufe="Neue Gefahrstufe 1–10",
    basisbeitrag="Neuer Basisbeitrag in € (pro Mitglied)",
    aktiv="Fraktion aktivieren / deaktivieren",
)
@app_commands.choices(gefahrstufe=[
    app_commands.Choice(name="Stufe 1 – Minimal",       value=1),
    app_commands.Choice(name="Stufe 2 – Sehr niedrig",  value=2),
    app_commands.Choice(name="Stufe 3 – Niedrig",       value=3),
    app_commands.Choice(name="Stufe 4 – Leicht erhöht", value=4),
    app_commands.Choice(name="Stufe 5 – Mittel",        value=5),
    app_commands.Choice(name="Stufe 6 – Hoch",          value=6),
    app_commands.Choice(name="Stufe 7 – Sehr hoch",     value=7),
    app_commands.Choice(name="Stufe 8 – Extrem",        value=8),
    app_commands.Choice(name="Stufe 9 – Sehr extrem",   value=9),
    app_commands.Choice(name="Stufe 10 – Maximum",      value=10),
])
async def bg_fraktion_bearbeiten(
    interaction: discord.Interaction,
    fraktion: str,
    gefahrstufe:  Optional[int]   = None,
    basisbeitrag: Optional[float] = None,
    aktiv:        Optional[bool]  = None,
):
    if not is_admin(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Administratoren.", "Administrator"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    if fraktion not in bg_data["fraktionen"]:
        await interaction.followup.send(embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden."), ephemeral=True)
        return

    frak    = bg_data["fraktionen"][fraktion]
    changes = []
    if gefahrstufe is not None:
        frak["gefahrklasse"] = gefahrstufe
        changes.append(f"Gefahrstufe → `{BG_GEFAHRKLASSEN[gefahrstufe]['label']}`")
    if basisbeitrag is not None:
        frak["basis_beitrag"] = basisbeitrag
        changes.append(f"Basisbeitrag → `{basisbeitrag:,.2f} €`")
    if aktiv is not None:
        frak["aktiv"] = aktiv
        changes.append(f"Status → {'<:3518checkmark:1501936312205316106> Aktiv' if aktiv else '<:3518crossmark:1501936313300029440> Inaktiv'}")

    save_bg_data(bg_data)
    await update_fraktion_forum_post(interaction.guild, fraktion)
    add_log_entry("BG_FRAKTION_BEARBEITET", interaction.user.id, {"fraktion": fraktion, "changes": changes})

    e = discord.Embed(title="Fraktion aktualisiert!", color=COLOR_SUCCESS, timestamp=get_now())
    e.add_field(name="__Fraktion__",            value=f"> {frak.get('emoji', '🏢')} **{frak['name']}**",                                inline=False)
    e.add_field(name="__Änderungen__",          value="\n".join(f"> {c}" for c in changes) if changes else "> Keine Änderungen",        inline=False)
    e.add_field(name="__Neuer Monatsbeitrag__", value=f"> **`{get_fraktion_beitrag(fraktion):,.2f} €/Mitglied`**",                      inline=False)
    e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.followup.send(embed=e, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — ÜBERSICHT & ANZEIGEN
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="uebersicht", description="Zeigt alle Fraktionen und Firmen mit Beiträgen und Saldo")
async def bg_uebersicht(interaction: discord.Interaction):
    if not is_mitarbeiter(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Mitarbeiter.", "Mitarbeiter"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    fraktionen     = bg_data.get("fraktionen", {})
    gesamt_beitrag = 0.0
    gesamt_eingez  = 0.0
    gesamt_ausgez  = 0.0
    embed = discord.Embed(title="BG — Fraktions- & Firmenübersicht", color=COLOR_PRIMARY, timestamp=get_now())
    for key, frak in fraktionen.items():
        if not frak.get("aktiv"):
            continue
        mitglieder = len(frak.get("discord_mitglieder", []))
        beitrag    = get_fraktion_beitrag(key)
        gesamt_beitrag += beitrag * mitglieder
        ein   = sum(e["betrag"] for e in bg_data.get("einzahlungen", {}).values() if e.get("fraktion") == key)
        aus   = sum(a["betrag"] for a in bg_data.get("auszahlungen", {}).values() if a.get("fraktion") == key and a.get("status") == "bestaetigt")
        gesamt_eingez += ein
        gesamt_ausgez += aus
        saldo     = ein - aus
        gk        = BG_GEFAHRKLASSEN.get(frak.get("gefahrklasse", 1), {})
        thread_id = frak.get("forum_info_thread_id") or frak.get("forum_thread_id")
        ch_id     = frak.get("forum_channel_id")
        typ_str   = "🏭" if frak.get("typ") == "firma" else "🏢"
        embed.add_field(
            name=f"{frak.get('emoji', '🏢')} {frak['name']} {typ_str}",
            value=(
                f"> GK: `{gk.get('label', '—')}`\n"
                f"> Mitglieder: `{mitglieder}`\n"
                f"> Beitrag: **`{beitrag * mitglieder:,.2f} €`**\n"
                f"> Saldo: `{saldo:,.2f} €`\n"
                + (f"> Kanal: <#{ch_id}>" if ch_id else (f"> Akte: <#{thread_id}>" if thread_id else "> Kein Kanal"))
            ),
            inline=True,
        )
    embed.add_field(
        name="__Kassenbericht__",
        value=(
            f"> Monatsbeiträge: **`{gesamt_beitrag:,.2f} €`**\n"
            f"> Einzahlungen: `{gesamt_eingez:,.2f} €`\n"
            f"> Auszahlungen: `{gesamt_ausgez:,.2f} €`\n"
            f"> **Kassensaldo: `{gesamt_eingez - gesamt_ausgez:,.2f} €`**"
        ),
        inline=False,
    )
    embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="fraktion-anzeigen", description="Zeigt die vollständige Akte einer Fraktion oder Firma")
@app_commands.describe(fraktion="Fraktion-Schlüssel (z.B. Polizei, Feuerwehr, HARS)")
async def bg_fraktion_anzeigen(interaction: discord.Interaction, fraktion: str):
    if not is_mitarbeiter(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Mitarbeiter.", "Mitarbeiter"), ephemeral=True)
        return
    if fraktion not in bg_data["fraktionen"]:
        verfuegbar = ", ".join(bg_data["fraktionen"].keys()) or "Keine"
        await interaction.response.send_message(
            embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden.\nVerfügbar: `{verfuegbar}`"),
            ephemeral=True
        )
        return
    await interaction.response.send_message(embed=build_fraktion_embed(fraktion, bg_data["fraktionen"][fraktion]), ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — EINZAHLUNG & AUSZAHLUNG (Slash)
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="einzahlung", description="Erfasst eine Einzahlung einer Fraktion in die Kasse")
@app_commands.describe(fraktion="Fraktion-Schlüssel")
async def bg_einzahlung(interaction: discord.Interaction, fraktion: str):
    if not is_bg_kassenwart(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur der Kassenwart oder die Leitungsebene.", "Kassenwart"), ephemeral=True)
        return
    if fraktion not in bg_data["fraktionen"]:
        await interaction.response.send_message(embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden."), ephemeral=True)
        return
    await interaction.response.send_modal(BGEinzahlungModal(fraktion))

@bot.tree.command(name="auszahlung", description="Stellt einen Auszahlungsantrag für eine Fraktion")
@app_commands.describe(fraktion="Fraktion-Schlüssel")
async def bg_auszahlung(interaction: discord.Interaction, fraktion: str):
    if not is_mitarbeiter(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Mitarbeiter.", "Mitarbeiter"), ephemeral=True)
        return
    if fraktion not in bg_data["fraktionen"]:
        verfuegbar = ", ".join(bg_data["fraktionen"].keys()) or "Keine"
        await interaction.response.send_message(embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden.\nVerfügbar: `{verfuegbar}`"), ephemeral=True)
        return
    await interaction.response.send_modal(BGAuszahlungModal(fraktion))

# ═══════════════════════════════════════════════════════
#   COMMANDS — PANELS POSTEN
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="leitung-panel", description="[ADMIN] Postet das Leitungs-Panel einer Fraktion/Firma in diesen Kanal")
@app_commands.describe(fraktion="Fraktion-Schlüssel")
async def bg_leitung_panel(interaction: discord.Interaction, fraktion: str):
    if not is_admin(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Administratoren.", "Administrator"), ephemeral=True)
        return
    if fraktion not in bg_data["fraktionen"]:
        verfuegbar = ", ".join(bg_data["fraktionen"].keys()) or "Keine"
        await interaction.response.send_message(embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden.\nVerfügbar: `{verfuegbar}`"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    frak    = bg_data["fraktionen"][fraktion]
    beitrag = get_fraktion_beitrag(fraktion)
    gk      = BG_GEFAHRKLASSEN.get(frak.get("gefahrklasse", 1), {})
    typ_str = "Firma" if frak.get("typ") == "firma" else "Fraktion"

    embed = discord.Embed(
        title=f"Leitungspanel — {frak['name']}",
        description=(
            f"> Dieses Panel ist für die **{'Geschäftsführung' if frak.get('typ') == 'firma' else 'Fraktionsleitung'}** von **{frak['name']}**.\n"
            f"> Hier können Mitglieder verwaltet und Beiträge eingezahlt werden."
        ),
        color=0x383940,
        timestamp=get_now()
    )
    embed.add_field(name="Fraktion-Schlüssel", value=f"> `{fraktion}`",                              inline=True)
    embed.add_field(name="Typ",                value=f"> `{typ_str}`",                              inline=True)
    embed.add_field(name="Beitrag/Mitglied",   value=f"> **`{beitrag:,.2f} €`**",                   inline=True)
    embed.add_field(
        name="__Funktionen__",
        value=(
            "> **Mitglied aufnehmen** — Neues Mitglied registrieren & Rolle vergeben\n"
            "> **Mitglied entfernen** — Mitglied austragen & Rolle entziehen\n"
            "> **Beitrag einzahlen** — Monatsbeitrag an die BG zahlen\n"
            "> **Mitgliederliste** — Alle eingetragenen Mitglieder anzeigen"
        ),
        inline=False,
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1501962625238696032/1501968299649667174/image.png?ex=69fe007b&is=69fcaefb&hm=9b10b509040760a9a1fcc4bb74245cecfe4f4fd2077e07500df1d7f853235685&=&format=webp&quality=lossless&width=1409&height=259")
    embed.set_footer(text="Copyright © SafetyGuard v2 • Nur für die Fraktionsleitung", icon_url=FOOTER_ICON)

    await interaction.channel.send(embed=embed, view=BGLeitungPanelView(fraktion))
    await interaction.followup.send("Leitungspanel wurde gesendet.", ephemeral=True)

@bot.tree.command(name="schaden-panel", description="Postet das Schaden-Panel einer Fraktion/Firma in diesen Kanal")
@app_commands.describe(fraktion="Fraktion-Schlüssel")
async def bg_schaden_panel(interaction: discord.Interaction, fraktion: str):
    if not is_mitarbeiter(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Mitarbeiter.", "Mitarbeiter"), ephemeral=True)
        return
    if fraktion not in bg_data["fraktionen"]:
        verfuegbar = ", ".join(bg_data["fraktionen"].keys()) or "Keine"
        await interaction.response.send_message(embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden.\nVerfügbar: `{verfuegbar}`"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    frak    = bg_data["fraktionen"][fraktion]
    typ_str = "Firma" if frak.get("typ") == "firma" else "Fraktion"

    embed = discord.Embed(
        title=f"Schadensmeldung — {frak['name']}",
        description=(
            f"> Als Mitglied von **{frak['name']}** ({typ_str}) kannst du hier einen Schaden bei der **Berufsgenossenschaft** einreichen.\n\n"
            f"> **Wann eine Schadenmeldung einreichen?**\n"
            f"> `-` Bei einem Arbeitsunfall im Dienst\n"
            f"> `-` Bei einer Verletzung auf der Arbeit\n"
            f"> `-` Bei einem Berufskrankheitsfall\n\n"
            f"> Für die Auszahlung wird ein Beweis in Form eines Clips benötigt, damit wir nachvollziehen können, was passiert ist."
        ),
        color=0x383940,
        timestamp=get_now()
    )
    embed.add_field(name="Fraktion-Schlüssel", value=f"> `{fraktion}`",                                          inline=True)
    embed.add_field(name="Status",             value=f"> {'<:3518checkmark:1501936312205316106> Versichert' if frak.get('aktiv') else '<:3518crossmark:1501936313300029440> Inaktiv'}", inline=True)
    embed.add_field(
        name="__Ablauf:__",
        value=(
            "> **1.** Schaltfläche unten klicken\n"
            "> **2.** Formular ausfüllen\n"
            "> **3.** Unser Team prüft deinen Antrag\n"
            "> **4.** Auszahlung nach Genehmigung"
        ),
        inline=False,
    )
    embed.set_image(url="https://media.discordapp.net/attachments/1501962625238696032/1501968000884932780/image.png?ex=69fe0034&is=69fcaeb4&hm=096610b37142ae3ac91eef45787a964ee85d84126942437c8a07e789a301aab9&=&format=webp&quality=lossless&width=1405&height=256")
    embed.set_footer(text="Copyright © SafetyGuard v2 • Für alle Mitglieder zugänglich", icon_url=FOOTER_ICON)

    await interaction.channel.send(embed=embed, view=BGSchadenPanelView(fraktion))
    await interaction.followup.send("<:3518checkmark:1501936312205316106> Schaden-Panel wurde gesendet.", ephemeral=True)

# ═══════════════════════════════════════════════════════
#   COMMANDS — TRANSAKTIONEN & STATISTIKEN
# ═══════════════════════════════════════════════════════
@bot.tree.command(name="transaktionen", description="Zeigt Einzahlungen & Auszahlungen einer Fraktion")
@app_commands.describe(fraktion="Fraktion-Schlüssel", anzahl="Max. Einträge (Standard: 10)")
async def bg_transaktionen(interaction: discord.Interaction, fraktion: str, anzahl: int = 10):
    if not is_mitarbeiter(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur Mitarbeiter.", "Mitarbeiter"), ephemeral=True)
        return
    if fraktion not in bg_data["fraktionen"]:
        await interaction.response.send_message(embed=build_error_embed("Nicht gefunden!", f"Fraktion `{fraktion}` nicht gefunden."), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    frak   = bg_data["fraktionen"][fraktion]
    anzahl = max(1, min(anzahl, 20))
    einz   = sorted([e for e in bg_data.get("einzahlungen", {}).values() if e.get("fraktion") == fraktion], key=lambda x: x.get("erfasst_am",   ""), reverse=True)[:anzahl]
    ausz   = sorted([a for a in bg_data.get("auszahlungen", {}).values() if a.get("fraktion") == fraktion], key=lambda x: x.get("beantragt_am",  ""), reverse=True)[:anzahl]
    schdn  = sorted([s for s in bg_data.get("schaden",      {}).values() if s.get("fraktion") == fraktion], key=lambda x: x.get("eingereicht_am",""), reverse=True)[:anzahl]

    embed = discord.Embed(title=f"{frak.get('emoji', '🏢')} Transaktionen — {frak['name']}", color=frak.get("farbe", COLOR_PRIMARY), timestamp=get_now())

    if einz:
        text = ""
        for e in einz:
            ts    = make_aware(datetime.fromisoformat(e["erfasst_am"])).strftime("%d.%m.%y %H:%M")
            text += f"> `{e['id']}` **+{e['betrag']:,.0f} €** — {e['verwendung'][:40]} ({ts})\n"
        embed.add_field(name="💰 Einzahlungen", value=text, inline=False)
    else:
        embed.add_field(name="💰 Einzahlungen", value="> Keine Einträge", inline=False)

    if ausz:
        text = ""
        for a in ausz:
            ts     = make_aware(datetime.fromisoformat(a["beantragt_am"])).strftime("%d.%m.%y %H:%M")
            status = {"ausstehend": "⏳", "bestaetigt": "<:3518checkmark:1501936312205316106>", "abgelehnt": "<:3518crossmark:1501936313300029440>"}.get(a.get("status", ""), "❓")
            text  += f"> `{a['id']}` {status} **-{a['betrag']:,.0f} €** — {a['empfaenger']} ({ts})\n"
        embed.add_field(name="📤 Auszahlungen", value=text, inline=False)
    else:
        embed.add_field(name="📤 Auszahlungen", value="> Keine Einträge", inline=False)

    if schdn:
        text = ""
        for s in schdn:
            ts     = make_aware(datetime.fromisoformat(s["eingereicht_am"])).strftime("%d.%m.%y %H:%M")
            status = {"ausstehend": "⏳", "genehmigt": "<:3518checkmark:1501936312205316106>", "abgelehnt": "<:3518crossmark:1501936313300029440>"}.get(s.get("status", ""), "❓")
            text  += f"> `{s['id']}` {status} **{s['betrag']:,.0f} €** — {s['schadensort'][:30]} ({ts})\n"
        embed.add_field(name="📋 Schadenmeldungen", value=text, inline=False)
    else:
        embed.add_field(name="📋 Schadenmeldungen", value="> Keine Einträge", inline=False)

    total_ein = sum(e["betrag"] for e in bg_data.get("einzahlungen", {}).values() if e.get("fraktion") == fraktion)
    total_aus = sum(a["betrag"] for a in bg_data.get("auszahlungen", {}).values() if a.get("fraktion") == fraktion and a.get("status") == "bestaetigt")
    embed.add_field(
        name="__Saldo__",
        value=f"> Eingezahlt: `{total_ein:,.2f} €` | Ausgezahlt: `{total_aus:,.2f} €` | **Saldo: `{total_ein - total_aus:,.2f} €`**",
        inline=False,
    )
    embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="statistiken", description="Zeigt vollständige Kassenstatistiken")
async def bg_statistiken(interaction: discord.Interaction):
    if not is_leitungsebene(interaction):
        await interaction.response.send_message(embed=build_error_embed("Zugriff verweigert!", "Nur die Leitungsebene.", "Leitungsebene"), ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)

    fraktionen   = bg_data.get("fraktionen", {})
    einzahlungen = bg_data.get("einzahlungen", {})
    auszahlungen = bg_data.get("auszahlungen", {})
    schaden_dict = bg_data.get("schaden", {})

    aktive_frak    = sum(1 for f in fraktionen.values() if f.get("aktiv"))
    firmen         = sum(1 for f in fraktionen.values() if f.get("typ") == "firma" and f.get("aktiv"))
    gesamt_beit    = sum(
        get_fraktion_beitrag(k) * len(f.get("discord_mitglieder", []))
        for k, f in fraktionen.items() if f.get("aktiv")
    )
    total_ein      = sum(e["betrag"] for e in einzahlungen.values())
    total_aus_best = sum(a["betrag"] for a in auszahlungen.values() if a.get("status") == "bestaetigt")
    total_aus_pend = sum(a["betrag"] for a in auszahlungen.values() if a.get("status") == "ausstehend")
    total_sch_gen  = sum(s["betrag"] for s in schaden_dict.values() if s.get("status") == "genehmigt")
    total_sch_pend = sum(s["betrag"] for s in schaden_dict.values() if s.get("status") == "ausstehend")
    sch_offen      = sum(1 for s in schaden_dict.values() if s.get("status") == "ausstehend")
    saldo          = total_ein - total_aus_best

    embed = discord.Embed(title="SafetyGuard v2 — Kassenstatistiken", color=COLOR_INFO, timestamp=get_now())
    embed.add_field(name="__Organisationen__",      value=f"> Aktiv gesamt: **`{aktive_frak}`**\n> davon Firmen: `{firmen}`\n> davon Fraktionen: `{aktive_frak - firmen}`",   inline=True)
    embed.add_field(name="__Monatsbeiträge__",      value=f"> Gesamt: **`{gesamt_beit:,.2f} €`**\n> Jahressoll: `{gesamt_beit * 12:,.2f} €`",                                 inline=True)
    embed.add_field(name="__Kasse__",               value=f"> Eingezahlt: **`{total_ein:,.2f} €`**\n> Ausgezahlt: `{total_aus_best:,.2f} €`\n> **Saldo: `{saldo:,.2f} €`**",  inline=False)
    embed.add_field(name="__Offene Auszahlungen__", value=f"> Ausstehend: **`{total_aus_pend:,.2f} €`**",                                                                       inline=True)
    embed.add_field(name="__Schadenmeldungen__",    value=f"> Genehmigt: `{total_sch_gen:,.2f} €`\n> Ausstehend: `{total_sch_pend:,.2f} €`\n> Offen: `{sch_offen}` Meldungen", inline=True)
    embed.add_field(name="__Transaktionen__",       value=f"> Einzahlungen: `{len(einzahlungen)}`\n> Auszahlungen: `{len(auszahlungen)}`\n> Schadenmeldungen: `{len(schaden_dict)}`", inline=True)
    embed.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
    await interaction.followup.send(embed=embed, ephemeral=True)

# ═══════════════════════════════════════════════════════
#   AUTOMATISCHE TASKS
# ═══════════════════════════════════════════════════════
@tasks.loop(hours=24)
async def auto_backup():
    try:
        cfg   = bg_data.get("bg_config", {})
        ch_id = cfg.get("bg_log_channel_id")
        if not ch_id:
            return
        ts  = get_now().strftime("%Y%m%d_%H%M%S")
        e   = discord.Embed(title="🗄️ Automatisches Datenbank-Backup", color=COLOR_INFO, timestamp=get_now())
        e.add_field(name="__Information__",        value="> Alle `24 Stunden` werden die Daten gesichert.", inline=False)
        e.add_field(name="__Enthaltene Dateien__", value="> - `bg_data.json`",                                 inline=False)
        e.add_field(name="__Zeitstempel__",        value=f"> {get_now().strftime('%d.%m.%Y, %H:%M:%S Uhr')}",  inline=False)
        e.set_footer(text="Copyright © SafetyGuard v2", icon_url=FOOTER_ICON)
        for guild in bot.guilds:
            ch = guild.get_channel(ch_id)
            if ch:
                buf  = create_zip_buffer()
                file = discord.File(buf, filename=f"bg_auto_backup_{ts}.zip")
                await ch.send(embed=e, file=file)
                break
    except Exception as ex:
        logger.error(f"Auto-Backup Fehler: {ex}", exc_info=True)

# ═══════════════════════════════════════════════════════
#   KEEP-ALIVE (Render.com)
# ═══════════════════════════════════════════════════════
from flask import Flask
from threading import Thread

app_flask = Flask('')

@app_flask.route('/')
def home():
    return "SafetyGuard v2 läuft!"

@app_flask.route('/health')
def health():
    fraktionen = bg_data.get("fraktionen", {})
    return {
        "status":                    "healthy",
        "bot":                       bot.user.name if bot.user else "starting",
        "version":                   "SafetyGuard v2",
        "latency_ms":                round(bot.latency * 1000) if bot.latency else None,
        "fraktionen":                len(fraktionen),
        "aktive_fraktionen":         sum(1 for f in fraktionen.values() if f.get("aktiv")),
        "firmen":                    sum(1 for f in fraktionen.values() if f.get("typ") == "firma"),
        "offene_schadenmeldungen":   sum(1 for s in bg_data.get("schaden", {}).values() if s.get("status") == "ausstehend"),
        "timestamp":                 get_now().isoformat()
    }

def run_flask():
    port = int(os.environ.get('PORT', 8081))
    app_flask.run(host='0.0.0.0', port=port, use_reloader=False)

def keep_alive():
    t = Thread(target=run_flask, daemon=True)
    t.start()

# ═══════════════════════════════════════════════════════
#   MAIN
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    keep_alive()
    token = os.getenv('DISCORD_TOKEN')
    if not token:
        logger.error("DISCORD_TOKEN nicht gefunden! Bitte als Umgebungsvariable setzen.")
    else:
        logger.info("SafetyGuard v2 wird gestartet...")
        bot.run(token)
