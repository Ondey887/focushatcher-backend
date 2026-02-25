from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import random
import os
import time

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = "/data/party.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = get_db()
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS parties (
                    code TEXT PRIMARY KEY, boss_hp INTEGER, boss_max_hp INTEGER
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS players (
                    user_id TEXT PRIMARY KEY, party_code TEXT, name TEXT, avatar TEXT
                 )''')
    
    party_columns = [
        ("mega_progress", "INTEGER DEFAULT 0"), ("mega_target", "INTEGER DEFAULT 36000"),
        ("expedition_end", "INTEGER DEFAULT 0"), ("expedition_score", "INTEGER DEFAULT 0"),
        ("leader_id", "TEXT DEFAULT ''"), ("active_game", "TEXT DEFAULT 'none'"),
        ("expedition_location", "TEXT DEFAULT 'forest'"),
        ("wolf_hp", "INTEGER DEFAULT 0"), ("wolf_max_hp", "INTEGER DEFAULT 0")
    ]
    for col, col_type in party_columns:
        try: c.execute(f"ALTER TABLE parties ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError: pass

    player_columns = [("boss_hp", "INTEGER DEFAULT 10000"), ("egg_skin", "TEXT DEFAULT 'default'")]
    for col, col_type in player_columns:
        try: c.execute(f"ALTER TABLE players ADD COLUMN {col} {col_type}")
        except sqlite3.OperationalError: pass

    c.execute('''CREATE TABLE IF NOT EXISTS global_users (
                    user_id TEXT PRIMARY KEY, name TEXT, avatar TEXT, 
                    level INTEGER, earned INTEGER, hatched INTEGER
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS friends (
                    user_id TEXT, friend_id TEXT, UNIQUE(user_id, friend_id)
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS party_invites (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_id TEXT, receiver_id TEXT, party_code TEXT, timestamp INTEGER
                 )''')

    conn.commit()
    conn.close()

init_db()

class PlayerData(BaseModel): user_id: str; name: str; avatar: str; egg_skin: str
class JoinData(PlayerData): code: str
class DamageData(BaseModel): code: str; user_id: str; damage: int
class TimeData(BaseModel): code: str; seconds: int
class CodeOnly(BaseModel): code: str
class SetGameData(BaseModel): code: str; user_id: str; game_name: str
class GlobalUserSync(BaseModel): user_id: str; name: str; avatar: str; level: int; earned: int; hatched: int
class FriendAction(BaseModel): user_id: str; friend_id: str
class InviteData(BaseModel): sender_id: str; receiver_id: str; party_code: str
class ExpeditionStartData(BaseModel): code: str; location: str

@app.get("/")
def read_root(): return {"status": "Focus Hatcher Backend v7 - Perfect State Clean!"}

@app.post("/api/party/create")
def create_party(data: PlayerData):
    conn = get_db()
    c = conn.cursor()
    code = str(random.randint(1000, 9999))
    c.execute("INSERT INTO parties (code, boss_hp, boss_max_hp, mega_progress, mega_target, expedition_end, expedition_score, leader_id, active_game, expedition_location, wolf_hp, wolf_max_hp) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (code, 10000, 10000, 0, 36000, 0, 0, data.user_id, 'none', 'forest', 0, 0))
    c.execute("DELETE FROM players WHERE user_id=?", (data.user_id,))
    c.execute("INSERT INTO players (user_id, party_code, name, avatar, boss_hp, egg_skin) VALUES (?, ?, ?, ?, ?, ?)", 
              (data.user_id, code, data.name, data.avatar, 10000, data.egg_skin))
    conn.commit()
    conn.close()
    return {"status": "success", "partyCode": code}

@app.post("/api/party/join")
def join_party(data: JoinData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM parties WHERE code=?", (data.code,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Пати не найдено")
    c.execute("DELETE FROM players WHERE user_id=?", (data.user_id,))
    c.execute("INSERT INTO players (user_id, party_code, name, avatar, boss_hp, egg_skin) VALUES (?, ?, ?, ?, ?, ?)", 
              (data.user_id, data.code, data.name, data.avatar, 10000, data.egg_skin))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/party/status/{code}")
def get_party_status(code: str):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM parties WHERE code=?", (code,))
    party = c.fetchone()
    if not party:
        conn.close()
        raise HTTPException(status_code=404, detail="Пати не найдено")
    c.execute("SELECT user_id, name, avatar, boss_hp, egg_skin FROM players WHERE party_code=?", (code,))
    players = [dict(row) for row in c.fetchall()]
    conn.close()
    return {
        "boss_hp": party["boss_hp"], "boss_max_hp": party["boss_max_hp"],
        "mega_progress": party["mega_progress"], "mega_target": party["mega_target"],
        "expedition_end": party["expedition_end"], "expedition_score": party["expedition_score"],
        "expedition_location": party["expedition_location"], "wolf_hp": party["wolf_hp"], "wolf_max_hp": party["wolf_max_hp"],
        "leader_id": party["leader_id"], "active_game": party["active_game"], "players": players
    }

@app.post("/api/party/set_game")
def set_game(data: SetGameData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT leader_id FROM parties WHERE code=?", (data.code,))
    party = c.fetchone()
    if party and party["leader_id"] == data.user_id:
        c.execute("UPDATE parties SET active_game=? WHERE code=?", (data.game_name, data.code))
        
        # Если игра отменяется - СЖИГАЕМ ПРОГРЕСС
        if data.game_name == 'none':
            c.execute("UPDATE parties SET expedition_end=0, expedition_score=0, wolf_hp=0 WHERE code=?", (data.code,))
            c.execute("UPDATE players SET boss_hp=10000 WHERE party_code=?", (data.code,))
        elif data.game_name == 'tap_boss':
            c.execute("UPDATE players SET boss_hp=10000 WHERE party_code=?", (data.code,))
            
        conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/damage")
def deal_damage(data: DamageData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT boss_hp FROM players WHERE user_id=? AND party_code=?", (data.user_id, data.code))
    player = c.fetchone()
    if not player:
        conn.close()
        return {"status": "error"}
    new_hp = max(0, player["boss_hp"] - data.damage)
    c.execute("UPDATE players SET boss_hp=? WHERE user_id=? AND party_code=?", (new_hp, data.user_id, data.code))
    conn.commit()
    conn.close()
    return {"status": "success", "new_hp": new_hp}

@app.post("/api/party/expedition/wolf_damage")
def wolf_damage(data: DamageData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT wolf_hp FROM parties WHERE code=?", (data.code,))
    party = c.fetchone()
    if party and party["wolf_hp"] > 0:
        new_hp = max(0, party["wolf_hp"] - data.damage)
        c.execute("UPDATE parties SET wolf_hp=? WHERE code=?", (new_hp, data.code))
        conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/mega_egg/add")
def add_mega_egg_time(data: TimeData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT mega_progress, mega_target FROM parties WHERE code=?", (data.code,))
    party = c.fetchone()
    if party:
        new_progress = min(party["mega_target"], party["mega_progress"] + data.seconds)
        c.execute("UPDATE parties SET mega_progress=? WHERE code=?", (new_progress, data.code))
        conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/mega_egg/claim")
def claim_mega_egg(data: CodeOnly):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE parties SET mega_progress=0 WHERE code=?", (data.code,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/expedition/start")
def start_expedition(data: ExpeditionStartData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT avatar FROM players WHERE party_code=?", (data.code,))
    players = c.fetchall()
    
    score = 0; farm_count = 0; pred_count = 0
    for p in players:
        av = p["avatar"]
        if av in ["unicorn", "dragon", "alien", "robot", "dino", "fireball", "god"]: score += 10
        elif av in ["fox", "panda", "tiger", "lion", "cow", "pig", "monkey", "owl"]: score += 3
        else: score += 1
        
        if av in ["cow", "pig", "duck"]: farm_count += 1
        if av in ["kitten", "tiger", "lion", "fox"]: pred_count += 1

    if farm_count >= 3: score = int(score * 1.5)

    base_time = 25 * 60
    if data.location == 'mountains': base_time = 60 * 60
    elif data.location == 'space': base_time = 120 * 60

    if pred_count >= 2: base_time = int(base_time * 0.85)

    end_time = int(time.time()) + base_time

    wolf_hp = 0
    if random.random() < 0.40:
        wolf_hp = len(players) * 50 
    
    c.execute("UPDATE parties SET expedition_end=?, expedition_score=?, expedition_location=?, wolf_hp=?, wolf_max_hp=? WHERE code=?", 
              (end_time, score, data.location, wolf_hp, wolf_hp, data.code))
    conn.commit()
    conn.close()
    return {"status": "success", "end_time": end_time}

@app.post("/api/party/expedition/claim")
def claim_expedition(data: CodeOnly):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE parties SET expedition_end=0, expedition_score=0, wolf_hp=0 WHERE code=?", (data.code,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/leave")
def leave_party(data: PlayerData):
    conn = get_db()
    c = conn.cursor()
    
    # Проверяем, Лидер ли выходит
    c.execute("SELECT code, leader_id FROM parties WHERE code=(SELECT party_code FROM players WHERE user_id=?)", (data.user_id,))
    party = c.fetchone()
    
    if party and party["leader_id"] == data.user_id:
        # Лидер вышел -> Удаляем пати полностью
        party_code = party["code"]
        c.execute("DELETE FROM players WHERE party_code=?", (party_code,))
        c.execute("DELETE FROM parties WHERE code=?", (party_code,))
    else:
        # Обычный игрок вышел
        c.execute("DELETE FROM players WHERE user_id=?", (data.user_id,))
        
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/users/sync")
def sync_global_user(data: GlobalUserSync):
    conn = get_db()
    c = conn.cursor()
    c.execute('''INSERT INTO global_users (user_id, name, avatar, level, earned, hatched) 
                 VALUES (?, ?, ?, ?, ?, ?) 
                 ON CONFLICT(user_id) DO UPDATE SET 
                 name=excluded.name, avatar=excluded.avatar, level=excluded.level, 
                 earned=excluded.earned, hatched=excluded.hatched''', 
              (data.user_id, data.name, data.avatar, data.level, data.earned, data.hatched))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/friends/add")
def add_friend(data: FriendAction):
    if data.user_id == data.friend_id: return {"status": "error", "detail": "Нельзя добавить себя"}
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM global_users WHERE user_id=?", (data.friend_id,))
    if not c.fetchone(): return {"status": "error", "detail": "Игрок не найден"}
    try:
        c.execute("INSERT INTO friends (user_id, friend_id) VALUES (?, ?)", (data.user_id, data.friend_id))
        c.execute("INSERT INTO friends (user_id, friend_id) VALUES (?, ?)", (data.friend_id, data.user_id))
        conn.commit()
    except sqlite3.IntegrityError: pass 
    conn.close()
    return {"status": "success"}

@app.get("/api/friends/list/{user_id}")
def get_friends_list(user_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT g.* FROM friends f JOIN global_users g ON f.friend_id = g.user_id WHERE f.user_id=?''', (user_id,))
    friends = [dict(row) for row in c.fetchall()]
    conn.close()
    return {"friends": friends}

@app.post("/api/invites/send")
def send_invite(data: InviteData):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM party_invites WHERE sender_id=? AND receiver_id=?", (data.sender_id, data.receiver_id))
    c.execute("INSERT INTO party_invites (sender_id, receiver_id, party_code, timestamp) VALUES (?, ?, ?, ?)", 
              (data.sender_id, data.receiver_id, data.party_code, int(time.time())))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.get("/api/invites/check/{user_id}")
def check_invites(user_id: str):
    conn = get_db()
    c = conn.cursor()
    c.execute('''SELECT i.id, i.party_code, g.name as sender_name, g.avatar as sender_avatar 
                 FROM party_invites i JOIN global_users g ON i.sender_id = g.user_id
                 WHERE i.receiver_id=? AND (? - i.timestamp) < 300 LIMIT 1''', (user_id, int(time.time())))
    invite = c.fetchone()
    conn.close()
    if invite: return {"has_invite": True, "invite": dict(invite)}
    return {"has_invite": False}

@app.post("/api/invites/clear")
def clear_invite(data: CodeOnly):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM party_invites WHERE id=?", (data.code,)) 
    conn.commit()
    conn.close()
    return {"status": "success"}
