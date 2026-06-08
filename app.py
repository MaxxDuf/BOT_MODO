import os
import discord
from discord.ext import commands
from mistralai import Mistral

# ================= CONFIG =================
TOKEN = os.getenv("DISCORD_TOKEN")
MISTRAL_KEY = os.getenv("MISTRAL_API_KEY")

REPORT_CHANNEL_ID = 1513274703572373504
FOUNDER_ROLE_NAME = "Fondateur"

# ================= INTENTS (IMPORTANT) =================
intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.messages = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ================= STOCKAGE =================
user_scores = {}

# ================= IA =================
client = Mistral(api_key=MISTRAL_KEY) if MISTRAL_KEY else None


def fallback_score(text: str) -> float:
    """Sécurité si IA HS"""
    t = text.lower()

    bad_keywords = [
        "insulte", "idiot", "nul", "hate", "trafiq", "armes"
    ]

    if any(k in t for k in bad_keywords):
        return 2.7

    return 0.2


async def ai_moderation(text: str) -> float:
    """
    Retourne un score entre 0 et 3 :
    0 = safe
    3 = très toxique
    """

    if not client:
        return fallback_score(text)

    try:
        prompt = f"""
Tu es un système de modération.
Analyse ce message et retourne UNIQUEMENT un nombre entre 0 et 3.

Règles :
0 = clean
1 = léger doute
2 = insultes / toxicité
3 = haine / racisme / illégal / grave

Message:
{text}
"""

        res = client.chat.complete(
            model="mistral-small-latest",
            messages=[{"role": "user", "content": prompt}]
        )

        output = res.choices[0].message.content.strip()

        # sécurité parsing
        score = float("".join(c for c in output if c in "0123456789."))
        return max(0, min(3, score))

    except:
        return fallback_score(text)


# ================= MODERATION =================
async def handle_message(message: discord.Message):
    if message.author.bot:
        return

    score = await ai_moderation(message.content)

    user_id = message.author.id
    user_scores[user_id] = user_scores.get(user_id, 0) + score

    # seuil suppression
    if score >= 2.3:
        try:
            await message.delete()
        except:
            pass

        channel = bot.get_channel(REPORT_CHANNEL_ID)

        if channel:
            await channel.send(
                f"🚨 Message supprimé\n"
                f"Utilisateur: {message.author}\n"
                f"Score: {score}/3\n"
                f"Contenu: {message.content}"
            )


# ================= EVENTS =================
@bot.event
async def on_ready():
    print(f"Connecté en tant que {bot.user}")


@bot.event
async def on_message(message):
    await handle_message(message)
    await bot.process_commands(message)


# ================= COMMANDES =================
def is_fondateur(ctx):
    return any(role.name == FOUNDER_ROLE_NAME for role in ctx.author.roles)


@bot.command()
async def reset(ctx):
    if not is_fondateur(ctx):
        return await ctx.send("⛔ Accès refusé")

    global user_scores
    user_scores = {}

    await ctx.send("✅ Scores remis à zéro")


@bot.command()
async def score(ctx):
    if not is_fondateur(ctx):
        return await ctx.send("⛔ Accès refusé")

    total = user_scores.get(ctx.author.id, 0)
    await ctx.send(f"📊 Ton score: {total:.2f}")


# ================= RUN =================
bot.run(TOKEN)
