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
FILE = "data.json"

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# =========================
# DATA
# =========================

def load():
    if not os.path.exists(FILE):
        return {}
    with open(FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save(data):
    with open(FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

# =========================
# IA (MISTRAL)
# =========================

def ia_check(text):

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no_key"}

    prompt = f"""
Tu es une IA de modération Discord.

Détecte insultes, haine, racisme, harcèlement, moqueries.

Message:
{text}

Répond JSON uniquement:
{{"delete": true, "score": 0.5, "reason": "court"}}
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

        text = r.json()["choices"][0]["message"]["content"]
        result = json.loads(text)

        return {
            "delete": result.get("delete", False),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "ia")
        }

    except Exception as e:
        print("IA ERROR:", e)
        return {"delete": False, "score": 0, "reason": "error"}

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print("BOT ONLINE :", client.user)

@client.event
async def on_message(message):

    if message.author.bot:
        return

    print("MSG:", message.content)

    result = ia_check(message.content)
    print("IA:", result)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except:
        pass

    data = load()
    uid = str(message.author.id)

    if uid not in data:
        data[uid] = 0

    data[uid] += result["score"]
    save(data)

    try:
        channel = await client.fetch_channel(SALON_REPORT)

        embed = discord.Embed(
            title="MODERATION IA",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="User", value=str(message.author), inline=False)
        embed.add_field(name="Score", value=str(result["score"]), inline=True)
        embed.add_field(name="Total", value=str(data[uid]), inline=True)
        embed.add_field(name="Reason", value=result["reason"], inline=False)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        await channel.send(embed=embed)

    except Exception as e:
        print("REPORT ERROR:", e)

client.run(DISCORD_TOKEN)
