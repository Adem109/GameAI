"""Cozy Roads - main game loop, UI and AI glue."""
import math
import random
import pygame

from . import ai, settings as cfg
from .entities import CROPS, Car, Farm, NPC, Player
from .world import TILE, World

SCREEN_W, SCREEN_H = 1280, 760
MINUTES_PER_SECOND = 3.0  # one in-game day = 8 real minutes
SEEDS = ["carrot", "tomato", "pumpkin"]
SHOP = [  # key, label, seed, amount, price
    ("1", "carrot", 5),
    ("2", "tomato", 5),
    ("3", "pumpkin", 3),
]

NPC_DEFS = [
    ("Mira", "A cheerful farmer in her 60s who loves pumpkins, gives gardening tips, and sometimes "
     "asks for help with crops for her famous soups.", (19, 31), (210, 120, 160), (200, 160, 90)),
    ("Ben", "A laid-back retired mechanic who adores old cars and road trips, tells tall tales, "
     "and loves when the player drives carefully on the ring road.", (70, 47), (110, 110, 120), (60, 70, 90)),
    ("Juno", "An energetic young jogger who challenges people to races, talks about fitness and "
     "sunsets, and is secretly a great cook who wants fresh tomatoes.", (58, 33), (240, 170, 60), None),
]

UI_BG = (30, 34, 46, 215)
UI_FG = (240, 240, 235)
UI_DIM = (170, 175, 185)
UI_ACCENT = (250, 200, 90)


def wrap(font, text, width):
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] <= width:
            line = trial
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines or [""]


def panel(surf, rect, alpha_bg=UI_BG, radius=12):
    s = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(s, alpha_bg, s.get_rect(), border_radius=radius)
    surf.blit(s, rect.topleft)


class Game:
    def __init__(self, screen=None):
        pygame.init()
        pygame.display.set_caption("Cozy Roads")
        self.screen = screen or pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.small = pygame.font.Font(None, 20)
        self.big = pygame.font.Font(None, 44)

        self.settings = cfg.load_settings()
        self.ai = self._make_ai()
        self.world = World()
        sx, sy = self.world.places["plaza"]
        self.player = Player(sx - 60, sy + 70)
        self.car = Car(sx + 10, sy + 6)
        self.farm = Farm()
        self.npcs = []
        for name, persona, (tx, ty), body, hat in NPC_DEFS:
            self.npcs.append(NPC(name, persona, tx * TILE + 16, ty * TILE + 16, body, hat=hat))
        self.inventory = {"carrot_seed": 6, "tomato_seed": 2, "pumpkin_seed": 0,
                          "carrot": 0, "tomato": 0, "pumpkin": 0}
        self.coins = 30
        self.seed_idx = 0
        self.quests = []  # {"npc", "item", "amount", "reward"}
        self.challenge = None  # {"npc", "place", "time_left", "reward"}
        self.day = 1
        self.minutes = 7 * 60.0
        self.raining = False
        self.rain_left = 0.0
        self.rain_drops = [(random.randrange(SCREEN_W), random.randrange(SCREEN_H)) for _ in range(160)]
        self.toasts = []  # (text, seconds_left)
        self.mode = "play"  # play | chat | shop | menu | key | help
        self.chat_npc = None
        self.chat_input = ""
        self.chat_status = ""
        self.key_input = ""
        self.key_status = ""
        self.menu_idx = 0
        self.save_timer = 60.0
        self.running = True
        self.real_time = 0.0
        self._load()
        if not self.ai.online:
            self.toast("Tip: press Esc -> 'DeepSeek API key' to bring the villagers to life.", 8)
        self.toast("Welcome to Cozy Roads! Press H for controls.", 6)

    # -- setup / persistence --------------------------------------------------
    def _make_ai(self):
        return ai.DeepSeekClient(cfg.api_key(self.settings), self.settings["deepseek_model"],
                                 self.settings["deepseek_base_url"])

    def _load(self):
        data = cfg.load_save()
        if not data:
            return
        try:
            p = data["player"]
            self.player.x, self.player.y, self.player.in_car = p["x"], p["y"], p["in_car"]
            c = data["car"]
            self.car.x, self.car.y, self.car.angle = c["x"], c["y"], c["angle"]
            self.inventory.update({k: int(v) for k, v in data["inventory"].items() if k in self.inventory})
            self.coins = int(data["coins"])
            self.farm.load_json(data["farm"])
            self.quests = data.get("quests", [])
            self.day, self.minutes = data["day"], data["minutes"]
            for npc in self.npcs:
                n = data.get("npcs", {}).get(npc.name)
                if n:
                    npc.x, npc.y = n["x"], n["y"]
                    npc.history = n.get("history", [])[-16:]
        except (KeyError, TypeError, ValueError):
            self.toast("Save file looked damaged; starting fresh.")

    def save(self):
        cfg.write_save({
            "player": {"x": self.player.x, "y": self.player.y, "in_car": self.player.in_car},
            "car": {"x": self.car.x, "y": self.car.y, "angle": self.car.angle},
            "inventory": self.inventory,
            "coins": self.coins,
            "farm": self.farm.to_json(),
            "quests": self.quests,
            "day": self.day,
            "minutes": self.minutes,
            "npcs": {n.name: {"x": n.x, "y": n.y, "history": n.history[-16:]} for n in self.npcs},
        })

    def toast(self, text, seconds=3.5):
        self.toasts.append([text, seconds])
        self.toasts = self.toasts[-4:]

    # -- helpers -----------------------------------------------------------------
    @property
    def focus(self):
        return (self.car.x, self.car.y) if self.player.in_car else (self.player.x, self.player.y)

    def camera(self):
        fx, fy = self.focus
        w, h = self.screen.get_size()
        mw, mh = self.world.pixel_size
        return (int(max(0, min(mw - w, fx - w / 2))), int(max(0, min(mh - h, fy - h / 2))))

    def nearest_npc(self, radius=90):
        if self.player.in_car:
            return None
        best = min(self.npcs, key=lambda n: math.dist((n.x, n.y), self.focus))
        return best if math.dist((best.x, best.y), self.focus) <= radius else None

    def near_car(self):
        return math.dist((self.car.x, self.car.y), (self.player.x, self.player.y)) < 64

    def near_market(self):
        return self.world.market_rect.inflate(60, 60).collidepoint(self.focus)

    def time_str(self):
        h, m = divmod(int(self.minutes), 60)
        return f"{h:02d}:{m:02d}"

    def time_of_day(self):
        h = self.minutes / 60
        if 5 <= h < 11:
            return "morning"
        if 11 <= h < 17:
            return "afternoon"
        if 17 <= h < 21:
            return "evening"
        return "night"

    def world_state(self, npc):
        quests = [q for q in self.quests if q["npc"] == npc.name]
        return {
            "player_name": self.settings.get("player_name", "Traveler"),
            "day": self.day,
            "time": f"{self.time_str()} ({self.time_of_day()})",
            "weather": "rainy" if self.raining else "sunny",
            "player_is": "driving the car" if self.player.in_car else "on foot",
            "you_are_near": self.world.nearest_place(npc.x, npc.y),
            "player_coins": self.coins,
            "player_inventory": {k: v for k, v in self.inventory.items() if v},
            "your_open_quest_for_player": quests[0] if quests else None,
            "gifts_you_gave_today": npc.gifts_today,
            "places": list(self.world.places),
        }

    # -- AI ------------------------------------------------------------------------
    def send_chat(self, npc, text):
        npc.history.append({"role": "user", "content": text})
        npc.busy = True
        self.chat_status = f"{npc.name} is thinking..."
        if self.ai.online:
            self.ai.request(("chat", npc.name), ai.build_system_prompt(npc, self.world_state(npc)),
                            npc.history[:-1], text)
        else:
            self.ai.results.put((("chat", npc.name), ai.offline_reply(npc, text, list(self.world.places))))

    def ambient_greet(self, npc):
        npc.last_greet = self.real_time
        if self.ai.online and self.settings.get("ambient_ai_greetings", True):
            npc.busy = True
            prompt = ("(The player walks past you. Greet them or comment on what you're doing in ONE short "
                      "sentence under 15 words. action must be null.)")
            self.ai.request(("greet", npc.name), ai.build_system_prompt(npc, self.world_state(npc)),
                            npc.history[-4:], prompt, max_tokens=80)
        else:
            npc.say(random.choice(ai.OFFLINE_GREETINGS.get(npc.name, ["Hello!"])), 4)

    def handle_ai_results(self):
        for tag, result in self.ai.poll():
            kind = tag[0]
            if kind == "test":
                self.key_status = ("Connected to DeepSeek!" if result.get("reply")
                                   else result.get("error", "Something went wrong."))
                continue
            npc = next((n for n in self.npcs if n.name == tag[1]), None)
            if npc is None:
                continue
            npc.busy = False
            if result.get("error"):
                self.toast(result["error"], 5)
                if kind == "chat":
                    result = ai.offline_reply(npc, npc.history[-1]["content"] if npc.history else "",
                                              list(self.world.places))
                else:
                    continue
            reply = result["reply"]
            if kind == "greet":
                npc.say(reply, 5)
                continue
            npc.history.append({"role": "assistant", "content": reply})
            npc.say(reply, 7)
            if self.chat_npc is npc:
                self.chat_status = ""
            self.apply_action(npc, result.get("action"))

    def apply_action(self, npc, action):
        """Validate an AI-proposed action and apply it to the world (clamped, never trusted)."""
        if not action:
            return
        kind = action.get("type")
        try:
            if kind == "give_quest":
                item = action.get("item")
                if item not in CROPS or any(q["npc"] == npc.name for q in self.quests) or len(self.quests) >= 4:
                    return
                amount = max(1, min(5, int(action.get("amount", 1))))
                fair = CROPS[item]["sell"] * amount
                reward = max(fair, min(fair * 2, int(action.get("reward", fair))))
                self.quests.append({"npc": npc.name, "item": item, "amount": amount, "reward": reward})
                self.toast(f"New request from {npc.name}: bring {amount} {item} ({reward} coins)", 5)
            elif kind == "gift":
                item = action.get("item")
                if item not in ai.GIFTABLE or npc.gifts_today >= 2:
                    return
                amount = int(action.get("amount", 1))
                npc.gifts_today += 1
                if item == "coins":
                    amount = max(1, min(15, amount))
                    self.coins += amount
                else:
                    amount = max(1, min(5, amount))
                    self.inventory[item] += amount
                self.toast(f"{npc.name} gave you {amount} {item.replace('_', ' ')}!", 4)
            elif kind == "walk_to":
                place = action.get("place")
                if place in self.world.places:
                    npc.go_to(*self.world.random_walkable_near(*self.world.places[place], 50), duration=90)
                    self.toast(f"{npc.name} is heading to the {place}.")
            elif kind == "follow_player":
                npc.go_to(self.player.x, self.player.y, mode="follow", duration=75)
                self.toast(f"{npc.name} is walking with you.")
            elif kind == "challenge":
                place = action.get("place")
                if place not in self.world.places or self.challenge:
                    return
                seconds = max(15, min(90, int(action.get("seconds", 40))))
                reward = max(5, min(40, int(action.get("reward", 15))))
                self.challenge = {"npc": npc.name, "place": place, "time_left": float(seconds), "reward": reward}
                self.toast(f"Challenge! Reach the {place} in {seconds}s for {reward} coins!", 5)
        except (TypeError, ValueError):
            pass

    def check_quests(self, npc):
        for q in list(self.quests):
            if q["npc"] == npc.name and self.inventory.get(q["item"], 0) >= q["amount"]:
                self.inventory[q["item"]] -= q["amount"]
                self.coins += q["reward"]
                self.quests.remove(q)
                note = f"(The player just handed you {q['amount']} {q['item']} for your request and got {q['reward']} coins.)"
                npc.history.append({"role": "user", "content": note})
                npc.history.append({"role": "assistant", "content": "Oh, wonderful! Thank you so much!"})
                npc.say("Oh, wonderful! Thank you so much!", 5)
                self.toast(f"Delivered {q['amount']} {q['item']} to {npc.name}: +{q['reward']} coins", 5)

    # -- input ---------------------------------------------------------------------
    def keys(self):
        k = pygame.key.get_pressed()
        return {
            "up": k[pygame.K_w] or k[pygame.K_UP],
            "down": k[pygame.K_s] or k[pygame.K_DOWN],
            "left": k[pygame.K_a] or k[pygame.K_LEFT],
            "right": k[pygame.K_d] or k[pygame.K_RIGHT],
            "run": k[pygame.K_LSHIFT] or k[pygame.K_RSHIFT],
        }

    def handle_events(self):
        opened_text = False
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                self.running = False
            elif ev.type == pygame.TEXTINPUT:
                if opened_text:
                    continue
                if self.mode == "chat" and len(self.chat_input) < 200:
                    self.chat_input += ev.text
                elif self.mode == "key" and len(self.key_input) < 200:
                    self.key_input += ev.text.strip()
            elif ev.type == pygame.KEYDOWN:
                if ev.key == pygame.K_F11:
                    pygame.display.toggle_fullscreen()
                    continue
                handler = getattr(self, f"key_{self.mode}")
                opened_text |= bool(handler(ev))

    def _paste(self):
        try:
            return (pygame.scrap.get_text() or "").strip()
        except Exception:
            return ""

    def key_play(self, ev):
        k = ev.key
        if k == pygame.K_ESCAPE:
            self.mode, self.menu_idx = "menu", 0
        elif k == pygame.K_h:
            self.mode = "help"
        elif k == pygame.K_e:
            if self.player.in_car:
                if abs(self.car.speed) > 60:
                    self.toast("Slow down before getting out!")
                    return
                self.player.in_car = False
                ex = self.car.x - math.sin(self.car.angle) * 36
                ey = self.car.y + math.cos(self.car.angle) * 36
                if self.world.rect_blocked(pygame.Rect(int(ex) - 9, int(ey) - 10, 18, 10)):
                    ex, ey = self.world.random_walkable_near(self.car.x, self.car.y, 70)
                self.player.x, self.player.y = ex, ey
            elif self.near_car():
                self.player.in_car = True
                self.toast("Vroom! W/S to drive, A/D to steer, E to get out.")
            elif self.near_market():
                self.mode = "shop"
        elif k == pygame.K_f and not self.player.in_car:
            msg = self.farm.interact(self.player.target_tile(), self.inventory, SEEDS[self.seed_idx])
            self.toast(msg or "Stand next to the farm soil to farm (field is west of the village).")
        elif k in (pygame.K_1, pygame.K_2, pygame.K_3):
            self.seed_idx = k - pygame.K_1
            self.toast(f"Selected {SEEDS[self.seed_idx]} seeds.")
        elif k == pygame.K_t:
            npc = self.nearest_npc()
            if npc:
                self.mode, self.chat_npc, self.chat_input, self.chat_status = "chat", npc, "", ""
                self.check_quests(npc)
                return True
            self.toast("Walk up to a villager to talk.")
        return False

    def key_chat(self, ev):
        k = ev.key
        if k == pygame.K_ESCAPE:
            self.mode, self.chat_npc = "play", None
        elif k == pygame.K_BACKSPACE:
            self.chat_input = self.chat_input[:-1]
        elif k == pygame.K_v and ev.mod & (pygame.KMOD_META | pygame.KMOD_CTRL):
            self.chat_input = (self.chat_input + self._paste())[:200]
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            text = self.chat_input.strip()
            if text and not self.chat_npc.busy:
                self.chat_input = ""
                self.send_chat(self.chat_npc, text)

    def key_shop(self, ev):
        k = ev.key
        if k == pygame.K_ESCAPE:
            self.mode = "play"
        elif ev.unicode in ("1", "2", "3"):
            _, seed, amount = SHOP[int(ev.unicode) - 1]
            price = CROPS[seed]["seed"] * amount
            if self.coins >= price:
                self.coins -= price
                self.inventory[f"{seed}_seed"] += amount
                self.toast(f"Bought {amount} {seed} seeds for {price} coins.")
            else:
                self.toast("Not enough coins.")
        elif k == pygame.K_s:
            total = 0
            for crop, info in CROPS.items():
                total += self.inventory[crop] * info["sell"]
                self.inventory[crop] = 0
            self.coins += total
            self.toast(f"Sold everything for {total} coins." if total else "Nothing to sell yet.")

    MENU = ["Resume", "DeepSeek API key", "AI greetings when passing by", "Toggle fullscreen", "Save & Quit"]

    def key_menu(self, ev):
        k = ev.key
        if k == pygame.K_ESCAPE:
            self.mode = "play"
        elif k in (pygame.K_UP, pygame.K_w):
            self.menu_idx = (self.menu_idx - 1) % len(self.MENU)
        elif k in (pygame.K_DOWN, pygame.K_s):
            self.menu_idx = (self.menu_idx + 1) % len(self.MENU)
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            choice = self.MENU[self.menu_idx]
            if choice == "Resume":
                self.mode = "play"
            elif choice == "DeepSeek API key":
                self.mode, self.key_input, self.key_status = "key", "", ""
                return True
            elif choice.startswith("AI greetings"):
                self.settings["ambient_ai_greetings"] = not self.settings.get("ambient_ai_greetings", True)
                cfg.save_settings(self.settings)
            elif choice == "Toggle fullscreen":
                pygame.display.toggle_fullscreen()
            elif choice == "Save & Quit":
                self.running = False

    def key_key(self, ev):
        k = ev.key
        if k == pygame.K_ESCAPE:
            self.mode = "menu"
        elif k == pygame.K_BACKSPACE:
            self.key_input = self.key_input[:-1]
        elif k == pygame.K_v and ev.mod & (pygame.KMOD_META | pygame.KMOD_CTRL):
            self.key_input = self._paste()[:200]
        elif k in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.settings["deepseek_api_key"] = self.key_input.strip()
            cfg.save_settings(self.settings)
            self.ai = self._make_ai()
            if self.ai.online:
                self.key_status = "Testing connection..."
                self.ai.request(("test",), "Reply with JSON {\"reply\": \"ok\", \"action\": null}.", [], "ping",
                                max_tokens=20)
            else:
                self.key_status = "Key cleared. Villagers use offline lines."

    def key_help(self, ev):
        self.mode = "play"

    # -- update ------------------------------------------------------------------------
    def update(self, dt):
        self.real_time += dt
        self.handle_ai_results()
        self.toasts = [[t, s - dt] for t, s in self.toasts if s - dt > 0]
        if self.mode in ("menu", "key", "help"):
            return  # paused
        keys = self.keys() if self.mode == "play" else {k: False for k in ("up", "down", "left", "right", "run")}

        # clock, days and weather
        prev_hour = int(self.minutes // 60)
        self.minutes += MINUTES_PER_SECOND * dt
        if self.minutes >= 24 * 60:
            self.minutes -= 24 * 60
            self.day += 1
            for n in self.npcs:
                n.gifts_today = 0
            self.toast(f"Day {self.day} begins. Good morning!")
            self.save()
        if int(self.minutes // 60) != prev_hour:
            if self.raining:
                self.rain_left -= 1
                if self.rain_left <= 0:
                    self.raining = False
                    self.toast("The rain stopped. Everything smells fresh.")
            elif random.random() < 0.08:
                self.raining, self.rain_left = True, random.randint(1, 3)
                self.toast("It's starting to rain - your crops get watered for free.")

        self.player.update(dt, keys, self.world)
        self.car.update(dt, keys, self.world, driving=self.player.in_car)
        if self.player.in_car:
            self.player.x, self.player.y = self.car.x, self.car.y
        self.farm.update(dt, self.raining)
        for npc in self.npcs:
            npc.update(dt, self.world, (self.player.x, self.player.y), talking=npc is self.chat_npc)
            if (self.mode == "play" and not npc.busy and self.real_time - npc.last_greet > 150
                    and not self.player.in_car and math.dist((npc.x, npc.y), self.focus) < 85):
                self.ambient_greet(npc)

        if self.challenge:
            self.challenge["time_left"] -= dt
            target = self.world.places[self.challenge["place"]]
            if math.dist(target, self.focus) < 100:
                self.coins += self.challenge["reward"]
                self.toast(f"You made it! +{self.challenge['reward']} coins from {self.challenge['npc']}.", 5)
                self.challenge = None
            elif self.challenge["time_left"] <= 0:
                self.toast(f"Time's up! {self.challenge['npc']} wins this one.", 4)
                self.challenge = None

        self.save_timer -= dt
        if self.save_timer <= 0:
            self.save_timer = 60
            self.save()

    # -- drawing -------------------------------------------------------------------------
    def draw(self):
        scr = self.screen
        w, h = scr.get_size()
        cam = self.camera()
        view = pygame.Rect(0, 0, w, h)
        scr.blit(self.world.ground, (0, 0), pygame.Rect(cam[0], cam[1], w, h))
        self.farm.draw(scr, cam, view)

        drawables = []
        for tx, ty, var in self.world.trees:
            if -60 < tx - cam[0] < w + 60 and -20 < ty - cam[1] < h + 80:
                drawables.append((ty, lambda tx=tx, ty=ty, var=var: scr.blit(
                    self.world.tree_sprite(var), (tx - 28 - cam[0], ty - 66 - cam[1]))))
        for house in self.world.houses:
            if house[0].move(-cam[0], -cam[1]).colliderect(view.inflate(200, 200)):
                drawables.append((house[0].bottom, lambda hs=house: self.draw_house(scr, cam, hs)))
        drawables.append((self.world.market_rect.bottom, lambda: self.draw_market(scr, cam)))
        for npc in self.npcs:
            drawables.append((npc.y, lambda n=npc: n.draw(scr, cam)))
        drawables.append((self.player.y, lambda: self.player.draw(scr, cam, self.real_time)))
        drawables.append((self.car.sort_y(), lambda: self.car.draw(scr, cam)))
        for _, fn in sorted(drawables, key=lambda d: d[0]):
            fn()

        if self.challenge:
            self.draw_target(scr, cam)
        if self.mode == "play" and not self.player.in_car:
            tx, ty = self.player.target_tile()
            if (tx, ty) in self.farm.plots:
                pygame.draw.rect(scr, (255, 255, 255), (tx * TILE - cam[0], ty * TILE - cam[1], TILE, TILE), 2, 4)

        if self.raining:
            self.draw_rain(scr)
        self.draw_night(scr)
        for npc in self.npcs:
            self.draw_name_and_bubble(scr, cam, npc)
        self.draw_hud(scr)
        if self.mode == "chat":
            self.draw_chat(scr)
        elif self.mode == "shop":
            self.draw_shop(scr)
        elif self.mode in ("menu", "key"):
            self.draw_menu(scr)
        elif self.mode == "help":
            self.draw_help(scr)
        pygame.display.flip()

    def draw_house(self, scr, cam, house):
        rect, wall, roof, label = house
        r = rect.move(-cam[0], -cam[1])
        wall_rect = pygame.Rect(r.x + 6, r.y + r.h * 0.4, r.w - 12, r.h * 0.6)
        pygame.draw.rect(scr, wall, wall_rect)
        pygame.draw.polygon(scr, roof, [(r.x - 4, wall_rect.y + 4), (r.x + 18, r.y), (r.right - 18, r.y),
                                        (r.right + 4, wall_rect.y + 4)])
        dark = tuple(max(0, c - 40) for c in roof)
        pygame.draw.line(scr, dark, (r.x + 18, r.y + 2), (r.right - 18, r.y + 2), 3)
        door = pygame.Rect(0, 0, 26, 40)
        door.midbottom = (wall_rect.centerx, wall_rect.bottom)
        pygame.draw.rect(scr, (120, 80, 50), door, border_radius=4)
        night = self.time_of_day() in ("evening", "night")
        for wx in (wall_rect.x + 18, wall_rect.right - 46):
            pygame.draw.rect(scr, (255, 220, 120) if night else (160, 210, 240), (wx, wall_rect.y + 14, 28, 22),
                             border_radius=3)
            pygame.draw.rect(scr, (90, 70, 50), (wx, wall_rect.y + 14, 28, 22), 2, border_radius=3)
        txt = self.small.render(label, True, (60, 50, 40))
        scr.blit(txt, txt.get_rect(midtop=(wall_rect.centerx, r.y + 12)))

    def draw_market(self, scr, cam):
        r = self.world.market_rect.move(-cam[0], -cam[1])
        pygame.draw.rect(scr, (150, 105, 70), (r.x + 6, r.y + 40, r.w - 12, r.h - 40), border_radius=4)
        for i in range(0, r.w, 20):
            colour = (230, 80, 80) if (i // 20) % 2 == 0 else (250, 245, 235)
            pygame.draw.rect(scr, colour, (r.x + i, r.y + 16, 20, 26))
        for i, crop in enumerate(CROPS.values()):
            pygame.draw.circle(scr, crop["color"], (r.x + 30 + i * 45, r.y + 62), 9)
        txt = self.font.render("MARKET", True, (60, 40, 30))
        scr.blit(txt, txt.get_rect(midbottom=(r.centerx, r.y + 14)))

    def draw_target(self, scr, cam):
        x, y = self.world.places[self.challenge["place"]]
        pulse = 90 + math.sin(self.real_time * 6) * 10
        pygame.draw.circle(scr, (255, 220, 80), (int(x - cam[0]), int(y - cam[1])), int(pulse), 4)
        # arrow at screen edge pointing to target
        fx, fy = self.focus
        ang = math.atan2(y - fy, x - fx)
        cx, cy = self.screen.get_width() / 2, self.screen.get_height() / 2
        ax, ay = cx + math.cos(ang) * 120, cy + math.sin(ang) * 120
        pts = [(ax + math.cos(ang) * 16, ay + math.sin(ang) * 16),
               (ax + math.cos(ang + 2.5) * 12, ay + math.sin(ang + 2.5) * 12),
               (ax + math.cos(ang - 2.5) * 12, ay + math.sin(ang - 2.5) * 12)]
        pygame.draw.polygon(scr, (255, 220, 80), pts)

    def draw_rain(self, scr):
        w, h = scr.get_size()
        for i, (x, y) in enumerate(self.rain_drops):
            y = (y + self.real_time * 700 + i * 37) % h
            x = (x - self.real_time * 120) % w
            pygame.draw.line(scr, (180, 200, 240), (x, y), (x - 3, y + 10), 1)
        shade = pygame.Surface(scr.get_size(), pygame.SRCALPHA)
        shade.fill((40, 50, 80, 50))
        scr.blit(shade, (0, 0))

    def draw_night(self, scr):
        h = self.minutes / 60
        if 7 <= h < 18:
            return
        if 18 <= h < 21:
            a = (h - 18) / 3
        elif 5 <= h < 7:
            a = 1 - (h - 5) / 2
        else:
            a = 1
        shade = pygame.Surface(scr.get_size(), pygame.SRCALPHA)
        shade.fill((20, 24, 70, int(140 * a)))
        if a > 0.3:  # a soft glow around the player / headlights
            fx, fy = self.focus
            cam = self.camera()
            centre = (int(fx - cam[0]), int(fy - cam[1]))
            for i in range(12):
                r = 170 - i * 12
                pygame.draw.circle(shade, (20, 24, 70, int(140 * a * (0.95 - i * 0.06))), centre, r)
        scr.blit(shade, (0, 0))

    def draw_name_and_bubble(self, scr, cam, npc):
        sx, sy = int(npc.x - cam[0]), int(npc.y - cam[1])
        name = self.small.render(npc.name + (" ..." if npc.busy else ""), True, (255, 255, 255))
        scr.blit(name, name.get_rect(midbottom=(sx, sy - 50)))
        if npc.bubble_timer > 0 and npc.bubble and self.mode != "chat":
            lines = wrap(self.small, npc.bubble, 240)[:5]
            bw = max(self.small.size(l)[0] for l in lines) + 20
            bh = len(lines) * 18 + 14
            rect = pygame.Rect(0, 0, bw, bh)
            rect.midbottom = (sx, sy - 68)
            pygame.draw.rect(scr, (255, 255, 250), rect, border_radius=10)
            pygame.draw.polygon(scr, (255, 255, 250), [(sx - 8, rect.bottom - 1), (sx + 8, rect.bottom - 1),
                                                       (sx, rect.bottom + 10)])
            for i, line in enumerate(lines):
                scr.blit(self.small.render(line, True, (40, 40, 50)), (rect.x + 10, rect.y + 8 + i * 18))

    def draw_hud(self, scr):
        w, h = scr.get_size()
        panel(scr, pygame.Rect(12, 12, 300, 112))
        icon = "Rain" if self.raining else "Sunny"
        scr.blit(self.font.render(f"Day {self.day}   {self.time_str()}   {icon}", True, UI_FG), (24, 22))
        scr.blit(self.font.render(f"Coins: {self.coins}", True, UI_ACCENT), (24, 48))
        seeds = "  ".join(f"{i + 1}:{s[:3]} x{self.inventory[s + '_seed']}" for i, s in enumerate(SEEDS))
        scr.blit(self.small.render("Seeds  " + seeds, True, UI_DIM), (24, 74))
        sel = self.small.render(f"Planting: {SEEDS[self.seed_idx]}", True, UI_ACCENT)
        scr.blit(sel, (24, 96))
        crops = "  ".join(f"{c} x{self.inventory[c]}" for c in CROPS)
        scr.blit(self.small.render(crops, True, UI_FG), (150, 96))

        # minimap
        mm = self.world.minimap
        mr = pygame.Rect(w - mm.get_width() - 14, 12, mm.get_width(), mm.get_height())
        pygame.draw.rect(scr, (30, 34, 46), mr.inflate(6, 6), border_radius=6)
        scr.blit(mm, mr)
        scale = mm.get_width() / self.world.pixel_size[0]
        for npc in self.npcs:
            pygame.draw.circle(scr, npc.body, (mr.x + npc.x * scale, mr.y + npc.y * scale), 3)
        pygame.draw.circle(scr, (220, 70, 70), (mr.x + self.car.x * scale, mr.y + self.car.y * scale), 3)
        fx, fy = self.focus
        pygame.draw.circle(scr, (255, 255, 255), (mr.x + fx * scale, mr.y + fy * scale), 4)
        if self.challenge:
            tx, ty = self.world.places[self.challenge["place"]]
            pygame.draw.circle(scr, UI_ACCENT, (mr.x + tx * scale, mr.y + ty * scale), 5, 2)

        # quests and challenge
        y = mr.bottom + 12
        rows = [f"{q['npc']}: bring {q['amount']} {q['item']} ({q['reward']}c)" for q in self.quests]
        if self.challenge:
            rows.insert(0, f"Reach {self.challenge['place']}! {self.challenge['time_left']:.0f}s")
        if rows:
            panel(scr, pygame.Rect(mr.x - 3, y, mr.w + 6, 26 + 20 * len(rows)))
            scr.blit(self.small.render("Requests", True, UI_ACCENT), (mr.x + 6, y + 6))
            for i, row in enumerate(rows):
                scr.blit(self.small.render(row, True, UI_FG), (mr.x + 6, y + 26 + i * 20))

        # AI status
        status = "AI: DeepSeek" if self.ai.online else "AI: offline (Esc to add key)"
        colour = (140, 230, 150) if self.ai.online else UI_DIM
        scr.blit(self.small.render(status, True, colour), (24, 132))

        # context hint
        hint = self.context_hint()
        if hint and self.mode == "play":
            surf = self.font.render(hint, True, UI_FG)
            r = surf.get_rect(midbottom=(w / 2, h - 18)).inflate(24, 12)
            panel(scr, r)
            scr.blit(surf, surf.get_rect(center=r.center))
        # toasts (hidden behind open panels)
        for i, (text, _) in enumerate(reversed(self.toasts if self.mode == "play" else [])):
            surf = self.font.render(text, True, UI_FG)
            r = surf.get_rect(midbottom=(w / 2, h - 64 - i * 34)).inflate(20, 10)
            panel(scr, r, (20, 24, 34, 190), 8)
            scr.blit(surf, surf.get_rect(center=r.center))
        if self.player.in_car:
            spd = self.font.render(f"{abs(self.car.speed) / 4:.0f} km/h", True, UI_FG)
            r = spd.get_rect(bottomleft=(24, h - 20)).inflate(20, 10)
            panel(scr, r)
            scr.blit(spd, spd.get_rect(center=r.center))

    def context_hint(self):
        if self.player.in_car:
            return "E: get out    W/S: gas/brake    A/D: steer"
        npc = self.nearest_npc()
        if npc:
            return f"T: talk to {npc.name}"
        if self.near_car():
            return "E: drive the car"
        if self.near_market():
            return "E: open market"
        plot = self.farm.plots.get(self.player.target_tile())
        if plot is not None:
            if not plot["tilled"]:
                return "F: till soil"
            if not plot["crop"]:
                return f"F: plant {SEEDS[self.seed_idx]}  (1/2/3 to switch)"
            if self.farm.ripe(plot):
                return "F: harvest"
            return "F: water" if not plot["watered"] else "Growing..."
        return ""

    def draw_chat(self, scr):
        w, h = scr.get_size()
        npc = self.chat_npc
        rect = pygame.Rect(0, 0, min(760, w - 40), 330)
        rect.midbottom = (w / 2, h - 16)
        panel(scr, rect)
        scr.blit(self.font.render(f"Talking with {npc.name}", True, UI_ACCENT), (rect.x + 18, rect.y + 12))
        hint = self.small.render("Enter: send   Esc: close   Cmd+V: paste", True, UI_DIM)
        scr.blit(hint, hint.get_rect(topright=(rect.right - 18, rect.y + 16)))
        lines = []
        for msg in npc.history:
            if msg["content"].startswith("(") and msg["role"] == "user":
                continue  # hidden game notes
            who = "You" if msg["role"] == "user" else npc.name
            colour = (170, 210, 255) if msg["role"] == "user" else UI_FG
            for i, line in enumerate(wrap(self.font, msg["content"], rect.w - 120)):
                lines.append(((who + ":") if i == 0 else "", line, colour))
        lines = lines[-9:]
        y = rect.y + 44
        for who, line, colour in lines:
            scr.blit(self.font.render(who, True, UI_DIM), (rect.x + 18, y))
            scr.blit(self.font.render(line, True, colour), (rect.x + 90, y))
            y += 24
        if self.chat_status and npc.busy:
            dots = "." * (int(self.real_time * 3) % 4)
            scr.blit(self.font.render(f"{npc.name} is thinking{dots}", True, UI_DIM), (rect.x + 18, y))
        box = pygame.Rect(rect.x + 14, rect.bottom - 48, rect.w - 28, 36)
        pygame.draw.rect(scr, (250, 250, 245), box, border_radius=8)
        text = self.chat_input + ("|" if int(self.real_time * 2) % 2 == 0 else "")
        if not self.chat_input:
            text = "Say something... (try: 'need any help?', 'race me!', 'walk with me')"
            colour = (150, 150, 150)
        else:
            colour = (30, 30, 40)
        surf = self.font.render(text, True, colour)
        scr.blit(surf, (box.x + 10, box.y + 9), pygame.Rect(max(0, surf.get_width() - box.w + 20), 0, box.w - 20, 30))

    def draw_shop(self, scr):
        w, h = scr.get_size()
        rect = pygame.Rect(0, 0, 440, 280)
        rect.center = (w / 2, h / 2)
        panel(scr, rect)
        scr.blit(self.big.render("Market", True, UI_ACCENT), (rect.x + 20, rect.y + 16))
        y = rect.y + 70
        for key, seed, amount in SHOP:
            price = CROPS[seed]["seed"] * amount
            scr.blit(self.font.render(f"[{key}]  Buy {amount} {seed} seeds - {price} coins", True, UI_FG),
                     (rect.x + 24, y))
            y += 30
        value = sum(self.inventory[c] * i["sell"] for c, i in CROPS.items())
        scr.blit(self.font.render(f"[S]  Sell all crops - {value} coins", True, UI_FG), (rect.x + 24, y + 8))
        prices = "  ".join(f"{c} {i['sell']}c" for c, i in CROPS.items())
        scr.blit(self.small.render(f"Buying: {prices}", True, UI_DIM), (rect.x + 24, y + 44))
        scr.blit(self.small.render(f"You have {self.coins} coins.  Esc: close", True, UI_DIM), (rect.x + 24, y + 66))

    def draw_menu(self, scr):
        w, h = scr.get_size()
        shade = pygame.Surface((w, h), pygame.SRCALPHA)
        shade.fill((10, 12, 20, 140))
        scr.blit(shade, (0, 0))
        rect = pygame.Rect(0, 0, 560, 360)
        rect.center = (w / 2, h / 2)
        panel(scr, rect)
        if self.mode == "menu":
            scr.blit(self.big.render("Paused", True, UI_ACCENT), (rect.x + 24, rect.y + 18))
            for i, item in enumerate(self.MENU):
                label = item
                if item.startswith("AI greetings"):
                    label += ": " + ("on" if self.settings.get("ambient_ai_greetings", True) else "off")
                if item == "DeepSeek API key":
                    label += ": " + ("set" if self.ai.online else "not set")
                colour = UI_ACCENT if i == self.menu_idx else UI_FG
                scr.blit(self.font.render(("> " if i == self.menu_idx else "  ") + label, True, colour),
                         (rect.x + 30, rect.y + 80 + i * 36))
            scr.blit(self.small.render("Up/Down + Enter.  Esc: resume.", True, UI_DIM),
                     (rect.x + 30, rect.bottom - 34))
        else:
            scr.blit(self.big.render("DeepSeek API key", True, UI_ACCENT), (rect.x + 24, rect.y + 18))
            info = ("Paste your key (Cmd+V) and press Enter. It is stored only on this Mac in "
                    f"{cfg.SETTINGS_PATH}. Leave empty + Enter to remove it. You can also set "
                    "the DEEPSEEK_API_KEY environment variable.")
            for i, line in enumerate(wrap(self.small, info, rect.w - 48)):
                scr.blit(self.small.render(line, True, UI_DIM), (rect.x + 24, rect.y + 70 + i * 20))
            box = pygame.Rect(rect.x + 24, rect.y + 180, rect.w - 48, 40)
            pygame.draw.rect(scr, (250, 250, 245), box, border_radius=8)
            k = self.key_input
            masked = (k[:5] + "*" * max(0, len(k) - 9) + k[-4:]) if len(k) > 12 else "*" * len(k)
            scr.blit(self.font.render(masked + "|", True, (30, 30, 40)), (box.x + 10, box.y + 11))
            if self.key_status:
                colour = (140, 230, 150) if "Connected" in self.key_status else UI_FG
                for i, line in enumerate(wrap(self.font, self.key_status, rect.w - 48)):
                    scr.blit(self.font.render(line, True, colour), (rect.x + 24, rect.y + 240 + i * 24))
            scr.blit(self.small.render("Enter: save & test   Esc: back", True, UI_DIM), (rect.x + 24, rect.bottom - 34))

    def draw_help(self, scr):
        w, h = scr.get_size()
        rect = pygame.Rect(0, 0, 620, 470)
        rect.center = (w / 2, h / 2)
        panel(scr, rect)
        scr.blit(self.big.render("How to chill", True, UI_ACCENT), (rect.x + 24, rect.y + 18))
        rows = [
            ("WASD / Arrows", "walk"),
            ("Shift", "run"),
            ("E", "get in / out of the car, open the market"),
            ("F", "farm: till -> plant -> water -> harvest"),
            ("1 / 2 / 3", "choose carrot / tomato / pumpkin seeds"),
            ("T", "talk to a villager (AI chat)"),
            ("Esc", "pause, settings, DeepSeek key"),
            ("F11", "fullscreen"),
            ("", ""),
            ("Tips", "Crops need water once per growth stage."),
            ("", "Rain waters everything for you."),
            ("", "Villagers can give you requests, gifts,"),
            ("", "race challenges, or walk with you."),
        ]
        for i, (k, v) in enumerate(rows):
            scr.blit(self.font.render(k, True, UI_ACCENT), (rect.x + 30, rect.y + 76 + i * 28))
            scr.blit(self.font.render(v, True, UI_FG), (rect.x + 190, rect.y + 76 + i * 28))

    # -- main loop -----------------------------------------------------------------------
    def run(self):
        while self.running:
            dt = min(self.clock.tick(60) / 1000.0, 0.05)
            self.handle_events()
            self.update(dt)
            self.draw()
        self.save()
        pygame.quit()


def main():
    Game().run()
