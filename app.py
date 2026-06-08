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

# 👑 FONDATEURS (REMPLACE PAR TES IDS)
FONDATEURS = {
    123456789012345678
}

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
# REPORT CACHE
# =========================

report_channel_cache = None

async def get_report_channel():
    global report_channel_cache

    if report_channel_cache:
        return report_channel_cache

    try:
        channel = await client.fetch_channel(SALON_REPORT)
        report_channel_cache = channel
        return channel
    except Exception as e:
        print("❌ report channel error:", e)
        return None

# =========================
# JSON
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
# FILTRE RAPIDE
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
Répond UNIQUEMENT en JSON:

{
  "delete": true/false,
  "score": 0-3,
  "reason": "courte raison"
}

Règles:
- delete=true si haine / harcèlement / discrimination
- score 3 = grave
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
        print("❌ IA error:", e)
        return None

# =========================
# ANALYSE
# =========================

def analyser_message(content: str):

    if hard_filter(content):
        return {"delete": True, "score": 3, "reason": "filtre local"}

    result = analyser_message_ia(content)

    if result:
        return result

    return {"delete": False, "score": 0, "reason": "fallback"}

# =========================
# BOT
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

    content = message.content.strip()
    uid = str(message.author.id)

    scores = charger_scores()

    # =========================
    # COMMANDES ADMIN
    # =========================

    if content.lower().startswith("!reset"):

        if message.author.id not in FONDATEURS:
            await message.channel.send("❌ Pas permission.")
            return

        args = content.split()

        if len(args) == 1:
            scores[uid] = 0
            sauvegarder_scores(scores)
            await message.channel.send("✅ Ton score reset.")
            return

        if len(args) == 2:
            try:
                target = args[1].replace("<@", "").replace(">", "")
                scores[target] = 0
                sauvegarder_scores(scores)
                await message.channel.send("✅ Score user reset.")
            except:
                await message.channel.send("❌ erreur")
            return

    if content.lower() == "!score":

        if message.author.id not in FONDATEURS:
            await message.channel.send("❌ Pas permission.")
            return

        if not scores:
            await message.channel.send("📊 Aucun score.")
            return

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        msg = "📊 Scores :\n"

        for user_id, score in sorted_scores[:15]:
            msg += f"- <@{user_id}> : {score}\n"

        await message.channel.send(msg)
        return

    # =========================
    # MODÉRATION
    # =========================

    result = analyser_message(content)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except:
        pass

    scores[uid] = scores.get(uid, 0) + result["score"]
    sauvegarder_scores(scores)

    report = await get_report_channel()

    if report:
        try:
            embed = discord.Embed(
                title="🚨 MODÉRATION IA",
                color=discord.Color.red(),
                timestamp=datetime.utcnow()
            )

            embed.add_field(name="User", value=str(message.author), inline=False)
            embed.add_field(name="Raison", value=result["reason"], inline=False)
            embed.add_field(name="Score", value=str(scores[uid]), inline=True)
            embed.add_field(name="Message", value=content[:1000], inline=False)

            await report.send(embed=embed)

        except Exception as e:
            print("❌ report error:", e)

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
