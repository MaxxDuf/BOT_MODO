import os
import json
import requests
import discord
from dotenv import load_dotenv
from datetime import datetime

# =========================
# ENV
# =========================

load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")

SALON_REPORT = 1513274703572373504
JSON_FILE = "toxicite.json"

# =========================
# DISCORD INTENTS (IMPORTANT)
# =========================

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# =========================
# DATA
# =========================

def load_data():
    if not os.path.exists(JSON_FILE):
        return {}
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_data(data):
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =========================
# IA MODERATION (MISTRAL)
# =========================

def analyze_text(text):

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no_api_key"}

    prompt = f"""
Tu es une IA de modération Discord très stricte.

Détecte :
- insultes
- racisme
- haine directe ou indirecte
- moqueries humiliantes
- propos violents ou dégradants
- sous-entendus offensants

IMPORTANT : même les doubles sens doivent être détectés.

Message:
{text}

Répond UNIQUEMENT en JSON :
{{
  "delete": true/false,
  "score": 0.5,
  "reason": "court"
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
                "model": "mistral-small",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2
            },
            timeout=10
        )

        result_text = r.json()["choices"][0]["message"]["content"]
        result = json.loads(result_text)

        return {
            "delete": result.get("delete", False),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except Exception as e:
        print("IA ERROR:", e)
        return {"delete": False, "score": 0, "reason": "error"}

# =========================
# READY
# =========================

@client.event
async def on_ready():
    print("BOT CONNECTÉ :", client.user)

# =========================
# MESSAGE HANDLER
# =========================

@client.event
async def on_message(message):

    if message.author.bot:
        return

    print("MESSAGE RECU:", message.content)

    data = load_data()
    user_id = str(message.author.id)

    # =========================
    # COMMAND RESET
    # =========================

    if message.content.startswith("!reset"):
        if user_id in data:
            data[user_id] = 0
            save_data(data)
            await message.channel.send("✅ Score remis à 0.")
        return

    # =========================
    # IA ANALYSIS
    # =========================

    result = analyze_text(message.content)

    print("IA RESULT:", result)

    if not result["delete"]:
        return

    # DELETE MESSAGE
    try:
        await message.delete()
    except:
        pass

    # SCORE UPDATE
    if user_id not in data:
        data[user_id] = 0

    data[user_id] += result["score"]
    save_data(data)

    # REPORT
    try:
        channel = await client.fetch_channel(SALON_REPORT)

        embed = discord.Embed(
            title="🚨 MODERATION IA",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="User", value=str(message.author), inline=False)
        embed.add_field(name="Score ajouté", value=str(result["score"]), inline=True)
        embed.add_field(name="Score total", value=str(data[user_id]), inline=True)
        embed.add_field(name="Raison", value=result["reason"], inline=False)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        await channel.send(embed=embed)

    except Exception as e:
        print("REPORT ERROR:", e)

# =========================
# RUN
# =========================

client.run(DISCORD_TOKEN)
