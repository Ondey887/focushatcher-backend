from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import sqlite3
import random
import os

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

@app.get("/")
def read_root():
    return {"status": "Focus Hatcher Backend is Running!"}

@app.post("/api/party/create")
def create_party(data: PlayerData):
    conn = get_db()
    c = conn.cursor()
    code = str(random.randint(1000, 9999))
    c.execute("INSERT INTO parties (code, boss_hp, boss_max_hp) VALUES (?, ?, ?)", (code, 10000, 10000))
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
    c.execute("SELECT boss_hp, boss_max_hp FROM parties WHERE code=?", (code,))
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
        "players": players
    }

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

@app.post("/api/party/leave")
def leave_party(data: PlayerData):
    conn = get_db()
    c = conn.cursor()
    c.execute("DELETE FROM players WHERE user_id=?", (data.user_id,))
    conn.commit()
    conn.close()
    return {"status": "success"}
