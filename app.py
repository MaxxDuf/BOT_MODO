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

FONDATEURS = {
    "1275136312935977013",
    "1272599276538691750"
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
# REPORT CHANNEL
# =========================

report_channel_cache = None

async def get_report_channel():
    global report_channel_cache

    if report_channel_cache:
        return report_channel_cache

    try:
        report_channel_cache = await client.fetch_channel(SALON_REPORT)
        return report_channel_cache
    except:
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
# TEXT CLEAN
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

HATE = ["connard", "fdp", "pute", "encule"]

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

        payload = {
            "model": MISTRAL_MODEL,
            "messages": [
                {"role": "system", "content": "Répond uniquement JSON {delete,score,reason}"},
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

    except:
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
# READY
# =========================

@client.event
async def on_ready():
    print("BOT CONNECTÉ ✔")
    print(client.user)

# =========================
# MAIN LOGIC
# =========================

@client.event
async def on_message(message):

    if message.author.bot:
        return

    content = (message.content or "").strip()
    uid = str(message.author.id)

    scores = charger_scores()

    # =========================
    # 1) MODÉRATION (PRIORITÉ ABSOLUE)
    # =========================
    if message.channel.id in SALONS_SURVEILLES:

        result = analyser_message(content)

        if result and result.get("delete"):

            try:
                await message.delete()
            except:
                pass

            scores[uid] = scores.get(uid, 0) + int(result.get("score", 0))
            sauvegarder_scores(scores)

            report = await get_report_channel()

            if report:
                try:
                    embed = discord.Embed(
                        title="📢MODÉRATION⚠️",
                        color=discord.Color.bleu(),
                        timestamp=datetime.utcnow()
                    )

                    embed.add_field(name="User", value=str(message.author), inline=False)
                    embed.add_field(name="Raison", value=result.get("reason", "unknown"), inline=False)
                    embed.add_field(name="Score", value=str(scores[uid]), inline=True)
                    embed.add_field(name="Message", value=content[:1000], inline=False)

                    await report.send(embed=embed)

                except:
                    pass

            return

    # =========================
    # 2) COMMANDES (UNIQUEMENT SALON REPORT)
    # =========================
    if message.channel.id != SALON_REPORT:
        return

    # 📊 SCORE
    if content.lower() == "!score":

        if not scores:
            await message.channel.send("📊 Aucun score.")
            return

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        msg = "📊 **Classement :**\n"

        for user_id, score in sorted_scores[:15]:
            msg += f"- <@{user_id}> : {score}\n"

        await message.channel.send(msg)
        return

    # 🧹 RESET
    if content.lower().startswith("!reset"):

        if str(message.author.id) not in FONDATEURS:
            await message.channel.send("🔒")
            return

        args = content.split()

        if len(args) == 1:
            scores[uid] = 0
            sauvegarder_scores(scores)
            await message.channel.send("🗘remise a zéro confirmer🗘")
            return

        if len(args) == 2:
            try:
                target = args[1].replace("<@", "").replace(">", "").replace("!", "")
                scores[target] = 0
                sauvegarder_scores(scores)
                await message.channel.send("🗘remise a zéro confirmer🗘")
            except:
                await message.channel.send("📢❗🚨 erreur")
            return

# =========================
# RUN
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=port)
