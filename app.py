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

# =========================
# DISCORD
# =========================

intents = discord.Intents.default()
intents.message_content = True

client = discord.Client(intents=intents)

# =========================
# REPORT CHANNEL
# =========================

report_channel = None

async def get_report_channel():
    global report_channel
    if report_channel:
        return report_channel
    try:
        report_channel = await client.fetch_channel(SALON_REPORT)
        print("REPORT OK")
        return report_channel
    except Exception as e:
        print("REPORT ERROR:", e)
        return None

# =========================
# IA MODERATION
# =========================

def analyze_message(content: str):

    if not MISTRAL_API_KEY:
        return {"delete": False, "score": 0, "reason": "no_api_key"}

    prompt = f"""
Tu es une IA de modération Discord.

Détecte :
- insultes
- racisme
- harcèlement
- moqueries agressives
- propos haineux directs ou indirects

Message:
\"\"\"{content}\"\"\"

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

        text = r.json()["choices"][0]["message"]["content"]
        result = json.loads(text)

        return {
            "delete": result.get("delete", False),
            "score": float(result.get("score", 0)),
            "reason": result.get("reason", "IA")
        }

    except Exception as e:
        print("IA ERROR:", e)
        return {"delete": False, "score": 0, "reason": "error"}

# =========================
# EVENTS
# =========================

@client.event
async def on_ready():
    print("BOT CONNECTÉ :", client.user)

@client.event
async def on_message(message):

    if message.author.bot:
        return

    print("MESSAGE:", message.content)

    result = analyze_message(message.content)

    print("IA:", result)

    if not result["delete"]:
        return

    try:
        await message.delete()
    except:
        pass

    report = await get_report_channel()

    if report:
        embed = discord.Embed(
            title="MODERATION IA",
            color=discord.Color.red(),
            timestamp=datetime.utcnow()
        )

        embed.add_field(name="User", value=str(message.author), inline=False)
        embed.add_field(name="Reason", value=result["reason"], inline=False)
        embed.add_field(name="Score", value=str(result["score"]), inline=True)
        embed.add_field(name="Message", value=message.content[:1000], inline=False)

        await report.send(embed=embed)

# =========================
# RUN
# =========================

client.run(DISCORD_TOKEN)
