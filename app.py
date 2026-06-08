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

@app.route("/ping")
def ping():
    return "ok"

# =========================
# CONFIG
# =========================

SALON_REPORT = 1513274703572373504

SALONS_SURVEILLES = {
    1499033414358142977,
    1500213292403134486
}

JSON_FILE = "toxicite.json"

MISTRAL_MODEL = "mistral-small-latest"

# =========================
# ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

client = discord.Client(intents=intents)

# =========================
# CACHE REPORT CHANNEL
# =========================

report_channel_cache = None

async def get_report_channel():
    global report_channel_cache

    if report_channel_cache is not None:
        return report_channel_cache

    try:
        channel = await client.fetch_channel(SALON_REPORT)
        report_channel_cache = channel
        return channel
    except Exception as e:
        print("❌ Erreur fetch_channel report:", e)
        return None

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
# NORMALISATION
# =========================

def normaliser_texte(text: str):
    text = text.lower()
    text = ''.join(
        c for c in unicodedata.normalize('NFD', text)
        if unicodedata.category(c) != 'Mn'
    )
    text = re.sub(r"[^a-zàâçéèêëîïôûùüÿñæœ\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()

# =========================
# FILTRE SIMPLE (SECURITE RAPIDE)
# =========================

HATE = [
    "connard", "fdp", "pute", "encule",
    "sale noir", "sale blanc",
    "vous les noirs", "vous les blancs",
    "les noirs sont", "les blancs sont",
    "retourne dans ton pays"
]

def hard_filter(text):
    t = normaliser_texte(text)
    return any(x in t for x in HATE)

# =========================
# IA MISTRAL
# =========================

def analyser_message_ia(content: str):

    if not MISTRAL_API_KEY:
        return None

    try:
        headers = {
            "Authorization": f"Bearer {MISTRAL_API_KEY}",
            "Content-Type": "application/json"
        }

        system_prompt = """
Tu es un modérateur Discord.

Répond UNIQUEMENT en JSON valide:
{
  "delete": true/false,
  "score": 0-3,
  "reason": "courte raison"
}

Règles:
- delete=true si haine, insultes, harcèlement, discrimination
- score 3 = très grave
- score 1-2 = léger
- score 0 = ok
"""

        payload = {
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content}
            ],
            "temperature": 0.2
        }

        r = requests.post(
            "https://api.mistral.ai/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=10
        )

        data = r.json()
        text = data["choices"][0]["message"]["content"]

        return json.loads(text)

    except Exception as e:
        print("❌ IA Mistral erreur:", e)
        return None

# =========================
# ANALYSE PRINCIPALE
# =========================

def analyser_message(content: str):

    # sécurité locale immédiate
    if hard_filter(content):
        return {
            "delete": True,
            "score": 3,
            "reason": "contenu haineux (filtre local)"
        }

    # IA
    result = analyser_message_ia(content)

    if result:
        return result

    # fallback
    return {
        "delete": False,
        "score": 0,
        "reason": "clean (fallback)"
    }

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

    if message.channel.id not in SALONS_SURVEILLES:
        return

    scores = charger_scores()
    uid = str(message.author.id)

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

    report = await get_report_channel()

    if report:
        try:
            embed = discord.Embed(
                title="🚨 MODÉRATION IA",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(name="Utilisateur", value=str(message.author), inline=False)
            embed.add_field(name="Raison", value=result["reason"], inline=False)
            embed.add_field(name="Score total", value=str(total), inline=True)
            embed.add_field(name="Message", value=message.content[:1000], inline=False)

            await report.send(embed=embed)

        except Exception as e:
            print("❌ Erreur report:", e)

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
