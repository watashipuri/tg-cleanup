# cleanup_channel.py
import os
import asyncio
from telethon import TelegramClient, errors
from telethon.tl.types import ChannelParticipantsAdmins

API_ID   = int(os.getenv("TG_API_ID"))
API_HASH = os.getenv("TG_API_HASH")
SESSION  = "cleanup_session"  # файл сессии будет восстановлен из секрета
CHANNEL  = os.getenv("CHANNEL")  # @username или -100xxxxxxxxxxxx

# опции из секретов (необязательно)
WHITELIST_ENV = os.getenv("WHITELIST", "")   # "1111,2222"
BATCH = int(os.getenv("BATCH", "20"))        # сколько киков подряд
SLEEP = int(os.getenv("SLEEP", "3"))         # пауза между партиями (сек)
DRY_RUN = os.getenv("DRY_RUN", "0") == "1"   # 1 = только показать, не удалять

def parse_id_list(s: str) -> set[int]:
    out = set()
    for part in s.replace(" ", "").split(","):
        if not part:
            continue
        try:
            out.add(int(part))
        except ValueError:
            pass
    return out

WHITELIST = parse_id_list(WHITELIST_ENV)

client = TelegramClient(SESSION, API_ID, API_HASH)

async def main():
    assert CHANNEL, "CHANNEL not set"
    print(f"Target channel: {CHANNEL}")
    print(f"Options: DRY_RUN={DRY_RUN} BATCH={BATCH} SLEEP={SLEEP}")
    if WHITELIST:
        print("Whitelist:", ", ".join(map(str, WHITELIST)))

    # добавим в белый список самого себя, чтобы не кикнуть случайно
    me = await client.get_me()
    if me and me.id:
        WHITELIST.add(me.id)

    # соберём админов канала (их никогда не трогаем)
    admins: set[int] = set()
    async for u in client.iter_participants(CHANNEL, filter=ChannelParticipantsAdmins()):
        admins.add(u.id)
    print(f"Admins detected: {len(admins)}")

    kicked = 0
    batch = 0
    candidates = 0

    async for user in client.iter_participants(CHANNEL):
        uid = user.id

        # пропуски
        if uid in admins or uid in WHITELIST:
            continue

        candidates += 1
        uname = f"@{user.username}" if user.username else ""
        line = f"candidate uid={uid} {uname}"
        if DRY_RUN:
            print("[DRY] ", line)
            continue

        try:
            await client.kick_participant(CHANNEL, uid)
            kicked += 1
            batch += 1
            print(f"[KICK] uid={uid} {uname} | total={kicked}")
        except errors.UserAdminInvalidError:
            # попытались кикнуть админа — пропускаем
            continue
        except errors.ChatAdminRequiredError:
            print("❌ Need admin rights with 'Ban users' in the channel.")
            break
        except errors.FloodWaitError as e:
            # обязательная пауза, если Телеграм попросил
            wait = int(getattr(e, 'seconds', 30))
            print(f"⏳ FLOOD_WAIT for {wait}s...")
            await asyncio.sleep(wait)
            continue
        except Exception as e:
            print("Error:", e)
            continue

        if batch >= BATCH:
            batch = 0
            print(f"Pause {SLEEP}s…")
            await asyncio.sleep(SLEEP)

    print(f"Done. Candidates={candidates}, Kicked={kicked}, Kept(admin+whitelist)=~{len(admins)+len(WHITELIST)}")

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
