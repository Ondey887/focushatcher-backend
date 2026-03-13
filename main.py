from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import uuid
import time
import random
import string

app = FastAPI(title="Focus Hatcher API")

# ==========================================
# НАСТРОЙКА CORS (ОЧЕНЬ ВАЖНО ДЛЯ TELEGRAM WEB APP)
# ==========================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Разрешаем запросы откуда угодно
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==========================================
# МОДЕЛИ ДАННЫХ (Pydantic)
# ==========================================
class MarketLot(BaseModel):
    seller_id: str
    seller_name: str
    pet_id: str
    pet_stars: int
    price: int
    currency: str

class BuyRequest(BaseModel):
    lot_id: str
    buyer_id: str

class UserSync(BaseModel):
    user_id: str
    name: str
    avatar: str
    level: int
    earned: int
    hatched: int

class PartyCreate(BaseModel):
    user_id: str
    name: str
    avatar: str
    egg_skin: str

class PartyJoin(BaseModel):
    code: Optional[str] = ""
    user_id: str
    name: str
    avatar: str
    egg_skin: str

class DamageReq(BaseModel):
    code: str
    user_id: str
    damage: int

class PromoCreate(BaseModel):
    password: str
    code: str
    type: str
    val: int
    max_uses: int

class PromoActivate(BaseModel):
    user_id: str
    code: str

# ==========================================
# БАЗЫ ДАННЫХ (В памяти для прототипа)
# ==========================================
market_listings = []
users_db = {}
parties = {}
promocodes = {
    "TEST": {"type": "money", "val": 5000, "uses": 100} # Базовый промокод для теста
}
friends_db = {} 
invites_db = {} 

# ==========================================
# 1. РЫНОК (ГЛОБАЛЬНАЯ ТОРГОВЛЯ)
# ==========================================
@app.post("/api/market/sell")
async def sell_pet(lot: MarketLot):
    lot_data = lot.dict()
    lot_data["lot_id"] = str(uuid.uuid4())
    market_listings.append(lot_data)
    return {"status": "success", "lot_id": lot_data["lot_id"]}

@app.get("/api/market/list")
async def get_market():
    # Возвращаем список лотов, новые сверху
    return {"lots": list(reversed(market_listings))}

@app.post("/api/market/buy")
async def buy_pet(req: BuyRequest):
    global market_listings
    for lot in market_listings:
        if lot["lot_id"] == req.lot_id:
            if lot["seller_id"] == req.buyer_id:
                return {"status": "error", "detail": "Нельзя купить своего пета!"}
            
            # Удаляем лот с рынка
            market_listings.remove(lot)
            
            # В реальном проекте тут нужно начислить деньги продавцу (seller_id) в БД.
            
            return {"status": "success", "lot": lot}
            
    return {"status": "error", "detail": "Лот уже куплен или не существует!"}

# ==========================================
# 2. ПРОФИЛЬ И FORBES
# ==========================================
@app.post("/users/sync")
async def sync_user(user: UserSync):
    users_db[user.user_id] = user.dict()
    if user.user_id not in friends_db:
        friends_db[user.user_id] = []
    return {"status": "success"}

@app.get("/forbes/{user_id}")
async def get_forbes(user_id: str):
    # Сортируем всех пользователей по заработанным монетам (earned)
    sorted_users = sorted(users_db.values(), key=lambda x: x.get("earned", 0), reverse=True)
    top_100 = sorted_users[:100]
    return {"global": top_100}

# ==========================================
# 3. МУЛЬТИПЛЕЕР (ПАТИ И БОССЫ)
# ==========================================
def generate_party_code():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=5))

@app.post("/party/create")
async def create_party(req: PartyCreate):
    code = generate_party_code()
    parties[code] = {
        "leader_id": req.user_id,
        "active_game": "none",
        "boss_hp": 10000,
        "boss_max_hp": 10000,
        "mega_progress": 0,
        "mega_target": 36000, 
        "expedition_end": 0,
        "expedition_score": 1,
        "expedition_location": "forest",
        "wolf_hp": 0,
        "wolf_max_hp": 100,
        "mega_radar": 0,
        "players": [{
            "user_id": req.user_id,
            "name": req.name,
            "avatar": req.avatar,
            "egg_skin": req.egg_skin,
            "boss_hp": 0
        }]
    }
    return {"status": "success", "partyCode": code}

@app.post("/party/join")
async def join_party(req: PartyJoin):
    code = req.code.upper()
    if code not in parties:
        raise HTTPException(status_code=404, detail="Пати не найдено")
    
    party = parties[code]
    
    # Проверяем, есть ли игрок уже в пати
    player_exists = False
    for p in party["players"]:
        if p["user_id"] == req.user_id:
            p["name"] = req.name
            p["avatar"] = req.avatar
            p["egg_skin"] = req.egg_skin
            player_exists = True
            break
            
    if not player_exists:
        party["players"].append({
            "user_id": req.user_id,
            "name": req.name,
            "avatar": req.avatar,
            "egg_skin": req.egg_skin,
            "boss_hp": 0
        })
        
    return {"status": "success"}

@app.get("/party/status/{code}")
async def get_party_status(code: str):
    code = code.upper()
    if code not in parties:
        raise HTTPException(status_code=404, detail="Пати не найдено")
    
    party = parties[code]
    party["server_time"] = int(time.time())
    return party

@app.post("/party/leave")
async def leave_party(req: PartyJoin):
    for code, party in list(parties.items()):
        party["players"] = [p for p in party["players"] if p["user_id"] != req.user_id]
        if not party["players"]:
            del parties[code] # Удаляем пустое пати
    return {"status": "success"}

@app.post("/party/set_game")
async def set_game(req: dict):
    code = req.get("code", "").upper()
    if code in parties:
        parties[code]["active_game"] = req.get("game_name", "none")
        if req.get("game_name") == "tap_boss":
            parties[code]["boss_hp"] = 10000 * len(parties[code]["players"])
            parties[code]["boss_max_hp"] = parties[code]["boss_hp"]
            for p in parties[code]["players"]:
                p["boss_hp"] = 0
        return {"status": "success"}
    return {"status": "error"}

@app.post("/party/damage")
async def party_damage(req: DamageReq):
    code = req.code.upper()
    if code in parties:
        parties[code]["boss_hp"] -= req.damage
        for p in parties[code]["players"]:
            if p["user_id"] == req.user_id:
                p["boss_hp"] += req.damage
        return {"status": "success"}
    return {"status": "error"}

# Заглушки для мини-игр
@app.post("/party/mega_egg/add")
async def mega_egg_add(req: dict): return {"status": "success"}
@app.post("/party/mega_egg/claim")
async def mega_egg_claim(req: dict): return {"status": "success"}
@app.post("/party/radar")
async def party_radar(req: dict): return {"status": "success"}
@app.post("/party/expedition/start")
async def exp_start(req: dict): return {"status": "success"}
@app.post("/party/expedition/wolf_damage")
async def exp_wolf(req: dict): return {"status": "success"}
@app.post("/party/expedition/claim")
async def exp_claim(req: dict): return {"status": "success"}

# ==========================================
# 4. ПРОМОКОДЫ И ОПЛАТА
# ==========================================
@app.post("/promo/activate")
async def activate_promo(req: PromoActivate):
    code = req.code.upper()
    if code in promocodes and promocodes[code]["uses"] > 0:
        promocodes[code]["uses"] -= 1
        return {"status": "success", "type": promocodes[code]["type"], "val": promocodes[code]["val"]}
    return {"status": "error", "detail": "Неверный или просроченный код!"}

@app.post("/admin/promo/create")
async def create_promo(req: PromoCreate):
    if req.password != "1234": # СЕКРЕТНЫЙ ПАРОЛЬ АДМИНА
        return {"status": "error", "detail": "Неверный пароль!"}
    promocodes[req.code] = {"type": req.type, "val": req.val, "uses": req.max_uses}
    return {"status": "success"}

@app.post("/payment/invoice")
async def create_invoice(req: dict):
    return {"status": "success", "invoice_link": "https://t.me/"}

# ==========================================
# 5. ДРУЗЬЯ И ПРИГЛАШЕНИЯ
# ==========================================
@app.post("/friends/add")
async def add_friend(req: dict):
    uid = req.get("user_id")
    fid = req.get("friend_id")
    if fid not in users_db:
        return {"status": "error", "detail": "Игрок не найден в базе!"}
    
    if uid not in friends_db:
        friends_db[uid] = []
    if fid not in friends_db[uid]:
        friends_db[uid].append(fid)
    return {"status": "success"}

@app.get("/friends/list/{user_id}")
async def get_friends(user_id: str):
    flist = friends_db.get(user_id, [])
    result = []
    for fid in flist:
        if fid in users_db:
            result.append(users_db[fid])
    return {"friends": result}

@app.post("/invites/send")
async def send_invite(req: dict):
    receiver = req.get("receiver_id")
    sender = req.get("sender_id")
    code = req.get("party_code")
    
    if receiver in users_db and sender in users_db:
        invites_db[receiver] = {
            "id": str(uuid.uuid4()),
            "sender_id": sender,
            "sender_name": users_db[sender].get("name", "Игрок"),
            "sender_avatar": users_db[sender].get("avatar", "default"),
            "party_code": code
        }
    return {"status": "success"}

@app.get("/invites/check/{user_id}")
async def check_invites(user_id: str):
    if user_id in invites_db:
        return {"has_invite": True, "invite": invites_db[user_id]}
    return {"has_invite": False}

@app.post("/invites/clear")
async def clear_invites(req: dict):
    for uid, inv in list(invites_db.items()):
        if inv["id"] == req.get("code"):
            del invites_db[uid]
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    # Запуск сервера
    uvicorn.run(app, host="0.0.0.0", port=8000)