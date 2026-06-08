import os
import json
import threading
import re
import unicodedata
import requests
from datetime import datetime

import discord
from flask import Flask
from dotenv import load_dotenv

# =========================
# FLASK
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

# =========================
# CONFIG
# =========================

SALON_REPORT = 1513274703572373504

SALONS_SURVEILLES = {
    1499033414358142977,
    1500213292403134486
}

SEUIL_ALERTE = 10
SEUIL_CRITIQUE = 20

JSON_FILE = "toxicite.json"

# =========================
# ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-small")

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# JSON SAFE
# =========================

def charger_scores():
    if not os.path.exists(JSON_FILE):
        return {}

    try:
        with open(JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def sauvegarder_scores(data):
    try:
        with open(JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except:
        pass

# =========================
# NORMALISATION ANTI-CONTOURNEMENT
# =========================

def normaliser_texte(text: str):
    text = text.lower()

    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )

    text = text.replace("@", "a").replace("0", "o").replace("1", "i").replace("$", "s").replace("3", "e")

    text = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()

# =========================
# HATE PATTERNS (RACISME + GENERALISATION)
# =========================

HATE_PATTERNS = [
    # insultes directes
    "sale noir", "sale blanc", "sale arabe", "sale juif",
    "nigger", "nigga", "fdp", "connard", "encule", "pute",

    # racisme implicite
    "vous les noirs", "vous les blanc", "vous les arabes",
    "les noirs sont", "les blancs sont", "les arabes sont",

    # généralisations
    "vous etes tous des voleurs",
    "ils sont tous des voleurs",
    "vous etes tous pareils",
    "ils sont tous pareils",

    # exclusion
    "retourne dans ton pays",
    "vous n avez rien a faire ici"
]

# =========================
# HARD FILTER
# =========================

def hard_filter(text):
    t = normaliser_texte(text)
    return any(p in t for p in HATE_PATTERNS)

# =========================
# FALLBACK
# =========================

def fallback():
    return {"delete": False, "score": 0, "reason": "fallback"}

# =========================
# IA MODERATION
# =========================

def analyser_message(contenu: str):

    t = normaliser_texte(contenu)

    # 🔥 OVERRIDE ABSOLU LOCAL
    if hard_filter(contenu):
        return {
            "delete": True,
            "score": 3,
            "reason": "contenu haineux détecté"
        }

    if not MISTRAL_API_KEY:
        return fallback()

    prompt = f"""
Tu es une IA de modération Discord ULTRA STRICTE.

Tu dois détecter :
- insultes
- racisme direct ou implicite
- généralisations sur des groupes ("vous les X êtes tous...")
- stéréotypes
- humiliation
- provocations

RÈGLE :
Si doute → DELETE = TRUE

Message :
\"\"\"{contenu}\"\"\"

Réponds UNIQUEMENT JSON :
{{
  "delete": true/false,
  "score": 0.5 à 3,
  "reason": "catégorie"
}}
"""

    try:
        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {MISTRAL_API_KEY}",
                "Content-Type": "application/json"
            },
            json={
                "model": MISTRAL_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            },
            timeout=6
        )

        data = r.json()
        content = data["choices"][0]["message"]["content"]

        result = json.loads(content)

        if result.get("delete") and float(result.get("score", 0)) < 1:
            result["score"] = 1.5

        return {
            "delete": bool(result.get("delete", False)),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except:
        return fallback()

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print(f"Connecté : {client.user}")

@client.event
async def on_message(message):

    if message.author.bot:
        return

    scores = charger_scores()
    uid = str(message.author.id)

    # =========================
    # COMMANDES RESET / SCORE
    # =========================

    if message.content.startswith("!reset"):
        if not message.mentions:
            await message.channel.send("❌ Mentionne un utilisateur")
            return

        for m in message.mentions:
            scores[str(m.id)] = 0

        sauvegarder_scores(scores)
        await message.channel.send("✅ Reset effectué")
        return

    if message.content.startswith("!score"):
        if message.mentions:
            u = str(message.mentions[0].id)
            await message.channel.send(f"📊 Score: {scores.get(u, 0)}")
        return

    # =========================
    # FILTRE SALONS
    # =========================

    if message.channel.id not in SALONS_SURVEILLES:
        return

    result = analyser_message(message.content)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except:
        pass

    scores[uid] = scores.get(uid, 0) + result["score"]
    total = scores[uid]

    sauvegarder_scores(scores)

    report = client.get_channel(SALON_REPORT)

    if report:
        embed = discord.Embed(
            title="🛡️MODÉRATION🛡️",
            color=discord.Color.bleu(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="Utilisateur", value=str(message.author), inline=False)
        embed.add_field(name="Raison", value=result["reason"], inline=False)
        embed.add_field(name="Score ajouté", value=str(result["score"]), inline=True)
        embed.add_field(name="Score total", value=str(total), inline=True)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        if total >= SEUIL_CRITIQUE:
            embed.add_field(name="⚠️ CRITIQUE", value="Utilisateur très toxique", inline=False)
        elif total >= SEUIL_ALERTE:
            embed.add_field(name="⚠️ ALERTE", value="Surveillance", inline=False)

        await report.send(embed=embed)

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
