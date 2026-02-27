import discord
from discord import app_commands
from flask import Flask, request, jsonify
import sqlite3
import hashlib
import secrets
import time
import threading
import os

TOKEN = os.getenv("TOKEN")
GUILD_ID = 1476362814330241125 # your server ID
REQUIRED_ROLE = "Verified Member"      # role required to generate token

# ---------- DATABASE ---------- #

def init_db():
    conn = sqlite3.connect("tokens.db")
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            user_id TEXT,
            token_hash TEXT,
            expires_at INTEGER
        )
    """)
    conn.commit()
    conn.close()

def store_token(user_id, token_hash, expires):
    conn = sqlite3.connect("tokens.db")
    c = conn.cursor()
    c.execute("INSERT INTO tokens VALUES (?, ?, ?)",
              (user_id, token_hash, expires))
    conn.commit()
    conn.close()

def verify_token(raw_token):
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    now = int(time.time())

    conn = sqlite3.connect("tokens.db")
    c = conn.cursor()

    c.execute("SELECT * FROM tokens WHERE token_hash=?", (token_hash,))
    result = c.fetchone()

    if result:
        user_id, stored_hash, expires = result
        if now <= expires:
            c.execute("DELETE FROM tokens WHERE token_hash=?", (token_hash,))
            conn.commit()
            conn.close()
            return True
        else:
            c.execute("DELETE FROM tokens WHERE token_hash=?", (token_hash,))
            conn.commit()

    conn.close()
    return False

# ---------- DISCORD BOT ---------- #

class Bot(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        await self.tree.sync(guild=discord.Object(id=GUILD_ID))

bot = Bot()

@bot.tree.command(name="generate_token", description="Generate portal access token",
                  guild=discord.Object(id=GUILD_ID))
async def generate_token(interaction: discord.Interaction):
    roles = [role.name for role in interaction.user.roles]
    if REQUIRED_ROLE not in roles:
        await interaction.response.send_message(
            "You do not have permission to generate a token.",
            ephemeral=True
        )
        return

    raw_token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    expires = int(time.time()) + 600  # 10 minutes

    store_token(str(interaction.user.id), token_hash, expires)

    await interaction.response.send_message(
        "Token generated. Check your DMs.",
        ephemeral=True
    )

    await interaction.user.send(
        f"Your portal token (valid 10 minutes):\n\n{raw_token}"
    )

# ---------- FLASK API ---------- #

app = Flask(__name__)

@app.route("/verify", methods=["POST"])
def verify():
    data = request.json
    token = data.get("token")

    if not token:
        return jsonify({"valid": False})

    if verify_token(token):
        return jsonify({"valid": True})
    else:
        return jsonify({"valid": False})

# ---------- RUN BOTH ---------- #

def run_flask():
    app.run(host="0.0.0.0", port=8000)

if __name__ == "__main__":
    init_db()
    threading.Thread(target=run_flask).start()
    bot.run(TOKEN)
