import os
import json
import threading
from datetime import datetime

import discord
from flask import Flask
from dotenv import load_dotenv
from mistralai import Mistral

# =========================
# FLASK (Render alive)
# =========================

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

# =========================
# ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

mistral = Mistral(api_key=MISTRAL_API_KEY)

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

client = discord.Client(intents=intents)

# =========================
# CONFIG
# =========================

SALON_REPORT = 1513274703572373504
SALONS_SURVEILLES = {1499033414358142977, 1500213292403134486}

JSON_FILE = "toxicite.json"

# =========================
# JSON SAFE
# =========================

def charger_scores():
    if not os.path.exists(JSON_FILE):
        return {}

    with open(JSON_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except:
            return {}

def sauvegarder_scores(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =========================
# IA MISTRAL (RESTORE)
# =========================

def analyser_message(contenu):
    try:
        prompt = f"""
Analyse ce message Discord :

{contenu}

Réponds uniquement en JSON :
{{
 "delete": true/false,
 "score": 0 à 3,
 "reason": "courte raison"
}}

score:
0 = ok
1 = insulte
2 = harcèlement
3 = grave
"""

        response = mistral.chat.complete(
            model="mistral-small-latest",
            messages=[
                {"role": "system", "content": "Tu es un modérateur strict."},
                {"role": "user", "content": prompt}
            ]
        )

        texte = response.choices[0].message.content

        debut = texte.find("{")
        fin = texte.rfind("}") + 1

        return json.loads(texte[debut:fin])

    except Exception as e:
        print("Erreur IA:", e)
        return None

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print("Bot connecté :", client.user)

@client.event
async def on_message(message):

    if message.author.bot:
        return

    if message.channel.id not in SALONS_SURVEILLES:
        return

    result = analyser_message(message.content)

    if not result:
        return

    if not result.get("delete"):
        return

    score = float(result.get("score", 0))
    reason = result.get("reason", "inconnue")

    # delete message
    try:
        await message.delete()
    except Exception as e:
        print("Suppression impossible:", e)

    # update JSON
    scores = charger_scores()
    uid = str(message.author.id)

    scores[uid] = scores.get(uid, 0) + score
    sauvegarder_scores(scores)

    # report
    channel = client.get_channel(SALON_REPORT)

    if channel:
        embed = discord.Embed(
            title="🚨 Message supprimé",
            description=reason,
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="User", value=str(message.author), inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=False)
        embed.add_field(name="Score ajouté", value=str(score), inline=True)

        await channel.send(embed=embed)

# =========================
# RUN BOT
# =========================

def run_bot():
    client.run(DISCORD_TOKEN)

if __name__ == "__main__":
    threading.Thread(target=run_bot).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
