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
    
    # Создаем базовые таблицы, если их нет
    c.execute('''CREATE TABLE IF NOT EXISTS parties (
                    code TEXT PRIMARY KEY, 
                    boss_hp INTEGER,
                    boss_max_hp INTEGER
                 )''')
    c.execute('''CREATE TABLE IF NOT EXISTS players (
                    user_id TEXT PRIMARY KEY, 
                    party_code TEXT, 
                    name TEXT, 
                    avatar TEXT
                 )''')
    
    # Железобетонное обновление базы: проверяем и добавляем КАЖДУЮ колонку отдельно
    columns_to_add = [
        ("parties", "mega_progress", "INTEGER DEFAULT 0"),
        ("parties", "mega_target", "INTEGER DEFAULT 36000"),
        ("parties", "expedition_end", "INTEGER DEFAULT 0"),
        ("parties", "expedition_score", "INTEGER DEFAULT 0"),
        ("parties", "leader_id", "TEXT DEFAULT ''"),
        ("parties", "active_game", "TEXT DEFAULT 'none'")
    ]
    
    for table, col_name, col_type in columns_to_add:
        try:
            c.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_type}")
        except sqlite3.OperationalError:
            # Если колонка уже есть, база выдаст ошибку, мы ее просто игнорируем и идем к следующей
            pass

    conn.commit()
    conn.close()

init_db()

class PlayerData(BaseModel):
    user_id: str
    name: str
    avatar: str

class JoinData(PlayerData):
    code: str

class DamageData(BaseModel):
    code: str
    damage: int

class TimeData(BaseModel):
    code: str
    seconds: int

class CodeOnly(BaseModel):
    code: str

class SetGameData(BaseModel):
    code: str
    user_id: str
    game_name: str

@app.get("/")
def read_root():
    return {"status": "Focus Hatcher Backend v2 - Multiplayer Sync Active!"}

@app.post("/api/party/create")
def create_party(data: PlayerData):
    conn = get_db()
    c = conn.cursor()
    code = str(random.randint(1000, 9999))
    c.execute("INSERT INTO parties (code, boss_hp, boss_max_hp, mega_progress, mega_target, expedition_end, expedition_score, leader_id, active_game) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", 
              (code, 10000, 10000, 0, 36000, 0, 0, data.user_id, 'none'))
    c.execute("DELETE FROM players WHERE user_id=?", (data.user_id,))
    c.execute("INSERT INTO players (user_id, party_code, name, avatar) VALUES (?, ?, ?, ?)", 
              (data.user_id, code, data.name, data.avatar))
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
    c.execute("INSERT INTO players (user_id, party_code, name, avatar) VALUES (?, ?, ?, ?)", 
              (data.user_id, data.code, data.name, data.avatar))
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
    c.execute("SELECT name, avatar FROM players WHERE party_code=?", (code,))
    players = [dict(row) for row in c.fetchall()]
    conn.close()
    return {
        "boss_hp": party["boss_hp"],
        "boss_max_hp": party["boss_max_hp"],
        "mega_progress": party["mega_progress"],
        "mega_target": party["mega_target"],
        "expedition_end": party["expedition_end"],
        "expedition_score": party["expedition_score"],
        "leader_id": party["leader_id"],
        "active_game": party["active_game"],
        "players": players
    }

@app.post("/api/party/set_game")
def set_game(data: SetGameData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT leader_id FROM parties WHERE code=?", (data.code,))
    party = c.fetchone()
    if party and party["leader_id"] == data.user_id:
        c.execute("UPDATE parties SET active_game=? WHERE code=?", (data.game_name, data.code))
        if data.game_name == 'tap_boss':
            c.execute("UPDATE parties SET boss_hp=boss_max_hp WHERE code=?", (data.code,))
        conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/damage")
def deal_damage(data: DamageData):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT boss_hp FROM parties WHERE code=?", (data.code,))
    party = c.fetchone()
    if not party:
        conn.close()
        return {"status": "error"}
    new_hp = max(0, party["boss_hp"] - data.damage)
    c.execute("UPDATE parties SET boss_hp=? WHERE code=?", (new_hp, data.code))
    conn.commit()
    conn.close()
    return {"status": "success", "new_hp": new_hp}

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
def start_expedition(data: CodeOnly):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT avatar FROM players WHERE party_code=?", (data.code,))
    players = c.fetchall()
    
    score = 0
    legendary = ["unicorn", "dragon", "alien", "robot", "dino", "fireball", "god"]
    rare = ["fox", "panda", "tiger", "lion", "cow", "pig", "monkey", "owl"]
    for p in players:
        av = p["avatar"]
        if av in legendary: score += 10
        elif av in rare: score += 3
        else: score += 1
        
    end_time = int(time.time()) + (4 * 3600)
    c.execute("UPDATE parties SET expedition_end=?, expedition_score=? WHERE code=?", (end_time, score, data.code))
    conn.commit()
    conn.close()
    return {"status": "success", "end_time": end_time}

@app.post("/api/party/expedition/claim")
def claim_expedition(data: CodeOnly):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE parties SET expedition_end=0, expedition_score=0 WHERE code=?", (data.code,))
    conn.commit()
    conn.close()
    return {"status": "success"}

@app.post("/api/party/leave")
def leave_party(data: PlayerData):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM players WHERE user_id=?", (data.user_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}
