# ===== keep-alive =====
from flask import Flask
from threading import Thread
import os

app = Flask(__name__)

@app.route("/")
def home():
    return "✅ Bot is alive!"

def _run():
    port = int(os.environ.get("PORT", 8080))
    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    except OSError:
        pass

_keep_alive_started = False
def keep_alive():
    global _keep_alive_started
    if _keep_alive_started: return
    _keep_alive_started = True
    Thread(target=_run, daemon=True).start()

# ===== Discord bot =====
import discord
from discord.ext import commands
from discord.utils import get
from datetime import datetime
import pytz

DEBUG = True

intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.messages = True
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ===== IDs =====
SOURCE_CHANNEL_ID = 1381641217657536632   # ينسخ ويحذف منه
TARGET_CHANNEL_ID = 1401287433332588574   # يحط فيه النسخة

def dbg(msg): 
    if DEBUG: print(msg)

def perms_ok(member: discord.Member, channel: discord.abc.GuildChannel):
    p = channel.permissions_for(member)
    return {
        "view": p.view_channel,
        "read_history": p.read_message_history,
        "send": p.send_messages,
        "manage": p.manage_messages,
        "embed_links": p.embed_links,
        "attach_files": p.attach_files,
    }

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user} (id={bot.user.id})")
    for g in bot.guilds:
        print(f"• Guild: {g.name} ({g.id}) — me: {g.me}")
        src = g.get_channel(SOURCE_CHANNEL_ID)
        dst = g.get_channel(TARGET_CHANNEL_ID)
        print(f"  SRC: {getattr(src,'name',None)} ({SOURCE_CHANNEL_ID})")
        print(f"  DST: {getattr(dst,'name',None)} ({TARGET_CHANNEL_ID})")
        if src:
            print("  SRC perms:", perms_ok(g.me, src))
        if dst:
            print("  DST perms:", perms_ok(g.me, dst))

# ===== نقل الرسائل من المصدر للهدف + حذف بالأصل =====
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user:
        return
    await bot.process_commands(message)

    if message.guild is None:
        dbg("DM -> تجاهل")
        return

    if message.channel.id != SOURCE_CHANNEL_ID:
        return

    # تشخيص
    dbg(f"[HIT] on_message in SRC: msg_id={message.id} author={message.author} content_len={len(message.content) if message.content else 0} embeds={len(message.embeds)} atts={len(message.attachments)}")

    dest = message.guild.get_channel(TARGET_CHANNEL_ID)
    if dest is None:
        print("⚠️ TARGET_CHANNEL_ID غير صحيح أو البوت ما يشوف القناة.")
        return

    # فحص صلاحيات مهمة
    src_perms = perms_ok(message.guild.me, message.channel)
    dst_perms = perms_ok(message.guild.me, dest)
    dbg("SRC perms: " + str(src_perms))
    dbg("DST perms: " + str(dst_perms))

    if not (dst_perms["send"] and dst_perms["view"]):
        print("❌ ما أقدر أرسل في القناة الهدف. عدّل صلاحيات Send/View.")
        return
    if not (src_perms["view"] and src_perms["read_history"]):
        print("❌ ما أقدر أقرأ في قناة المصدر. عدّل View/Read History.")
        return

    # جهّز نص
    parts = [f"🎶 رسالة من {message.author.mention} في {message.channel.mention}:"]
    if message.content and message.content.strip():
        content = message.content
        if len(content) > 1800:
            content = content[:1800] + "…"
        parts.append(f"📄 النص:\n```{content}```")
    txt = "\n".join(parts).strip()

    # أرسل النص
    if txt:
        try:
            await dest.send(txt)
            dbg("-> sent text")
        except Exception as e:
            print("❌ فشل إرسال النص:", e)
            return

    # أرسل الإيمبدات (نعيد بناءها لضمان التوافق)
    for emb in message.embeds:
        try:
            rebuilt = discord.Embed.from_dict(emb.to_dict())
            await dest.send(embed=rebuilt)
            dbg("-> sent embed")
        except Exception as e:
            print("⚠️ فشل إرسال Embed:", e)

    # أرسل المرفقات كرابط (أضمن)
    for a in message.attachments:
        try:
            await dest.send(f"📎 {a.filename}: {a.url}")
            dbg("-> sent attachment link")
        except Exception as e:
            print("⚠️ فشل إرسال مرفق:", e)

    # احذف الأصل (لو عندي صلاحية)
    try:
        await message.delete()
        dbg("-> deleted source message")
    except discord.Forbidden:
        print("⚠️ ما عندي Manage Messages لحذف الرسالة في المصدر.")
    except discord.HTTPException as e:
        print("⚠️ حذف الرسالة فشل:", e)

# ===== أوامر تشخيص =====
@bot.command()
async def ids(ctx):
    """يبين لك ID القناة الحالية والسيرفر"""
    await ctx.send(f"Guild: `{ctx.guild.name}` ({ctx.guild.id})\nChannel: `{ctx.channel.name}` ({ctx.channel.id})\nSRC={SOURCE_CHANNEL_ID}  DST={TARGET_CHANNEL_ID}")

@bot.command()
async def diag(ctx):
    """يفحص الصلاحيات ويطبعها"""
    src = ctx.guild.get_channel(SOURCE_CHANNEL_ID)
    dst = ctx.guild.get_channel(TARGET_CHANNEL_ID)
    me = ctx.guild.me
    msg = []
    msg.append(f"Me: {me} ({me.id})")
    msg.append(f"SRC: {getattr(src,'name',None)} ({SOURCE_CHANNEL_ID}) perms={perms_ok(me, src) if src else 'N/A'}")
    msg.append(f"DST: {getattr(dst,'name',None)} ({TARGET_CHANNEL_ID}) perms={perms_ok(me, dst) if dst else 'N/A'}")
    msg.append(f"Intents.message_content={bot.intents.message_content}")
    await ctx.send("```\n" + "\n".join(map(str,msg)) + "\n```")

@bot.command()
async def simulate(ctx):
    """يرسل رسالة اختبارية للهدف للتأكد من الإرسال"""
    dst = ctx.guild.get_channel(TARGET_CHANNEL_ID)
    if not dst:
        await ctx.send("TARGET_CHANNEL_ID غير صحيح أو القناة غير مرئية.")
        return
    try:
        await dst.send("🧪 Test: إذا شفت هذي الرسالة فالإرسال شغال.")
        await ctx.send("✅ تم الإرسال للهدف.")
    except Exception as e:
        await ctx.send(f"❌ فشل الإرسال: {e}")

# ===== تشغيل =====
keep_alive()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    print("❌ ما لقيت TOKEN في Secrets باسم TOKEN.")
else:
    try:
        bot.run(TOKEN)
    except discord.errors.PrivilegedIntentsRequired:
        print("❌ فعّل Message Content + Server Members من Developer Portal.")
    except discord.errors.LoginFailure:
        print("❌ التوكن غير صحيح.")
