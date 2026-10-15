"""Player, car, villagers and the farm."""
import math
import random

import pygame

from .world import TILE, ROAD, FARM

WALK_SPEED = 140
RUN_SPEED = 260

CROPS = {
    # total grow time in seconds (split over 3 stages), sell price, seed price
    "carrot": {"grow": 45, "sell": 10, "seed": 3, "color": (240, 140, 50)},
    "tomato": {"grow": 75, "sell": 22, "seed": 7, "color": (220, 60, 50)},
    "pumpkin": {"grow": 120, "sell": 48, "seed": 16, "color": (240, 160, 40)},
}
STAGES = 3


def feet_rect(x, y, w=18, h=10):
    return pygame.Rect(int(x - w / 2), int(y - h), w, h)


def try_move(world, x, y, dx, dy, w=18, h=10):
    """Move with axis-separated collision so you slide along walls."""
    if dx and not world.rect_blocked(feet_rect(x + dx, y, w, h)):
        x += dx
    if dy and not world.rect_blocked(feet_rect(x, y + dy, w, h)):
        y += dy
    return x, y


def draw_person(surf, sx, sy, body, skin, t, moving, facing, hat=None):
    bob = math.sin(t * 14) * 2 if moving else 0
    pygame.draw.ellipse(surf, (0, 0, 0, 60) if surf.get_flags() & pygame.SRCALPHA else (60, 100, 50),
                        (sx - 10, sy - 5, 20, 8))
    leg = math.sin(t * 14) * 4 if moving else 0
    pygame.draw.line(surf, (60, 60, 80), (sx - 4, sy - 12), (sx - 4 + leg, sy - 2), 4)
    pygame.draw.line(surf, (60, 60, 80), (sx + 4, sy - 12), (sx + 4 - leg, sy - 2), 4)
    pygame.draw.rect(surf, body, (sx - 9, sy - 28 + bob, 18, 18), border_radius=6)
    pygame.draw.circle(surf, skin, (sx, int(sy - 34 + bob)), 9)
    ex = {"left": -3, "right": 3}.get(facing, 0)
    if facing != "up":
        pygame.draw.circle(surf, (40, 40, 40), (sx - 3 + ex, int(sy - 35 + bob)), 1)
        pygame.draw.circle(surf, (40, 40, 40), (sx + 3 + ex, int(sy - 35 + bob)), 1)
    if hat:
        pygame.draw.rect(surf, hat, (sx - 12, sy - 42 + bob, 24, 4), border_radius=2)
        pygame.draw.rect(surf, hat, (sx - 7, sy - 48 + bob, 14, 8), border_radius=3)


class Player:
    def __init__(self, x, y):
        self.x, self.y = x, y
        self.facing = "down"
        self.moving = False
        self.running = False
        self.in_car = False
        self.t = 0.0
        self.distance_walked = 0.0

    def update(self, dt, keys, world):
        self.t += dt
        if self.in_car:
            return
        dx = (keys["right"] - keys["left"])
        dy = (keys["down"] - keys["up"])
        self.moving = bool(dx or dy)
        self.running = self.moving and keys["run"]
        if self.moving:
            length = math.hypot(dx, dy)
            speed = RUN_SPEED if self.running else WALK_SPEED
            mx, my = dx / length * speed * dt, dy / length * speed * dt
            ox, oy = self.x, self.y
            self.x, self.y = try_move(world, self.x, self.y, mx, my)
            self.distance_walked += math.dist((ox, oy), (self.x, self.y))
            if abs(dx) > abs(dy):
                self.facing = "right" if dx > 0 else "left"
            else:
                self.facing = "down" if dy > 0 else "up"

    def target_tile(self):
        """The tile in front of the player (used for farming)."""
        ox, oy = {"up": (0, -20), "down": (0, 14), "left": (-22, -4), "right": (22, -4)}[self.facing]
        return int((self.x + ox) // TILE), int((self.y + oy) // TILE)

    def draw(self, surf, cam, t):
        if self.in_car:
            return
        sx, sy = int(self.x - cam[0]), int(self.y - cam[1])
        draw_person(surf, sx, sy, (70, 120, 220), (250, 210, 170), self.t, self.moving,
                    self.facing, hat=(230, 200, 90))


class Car:
    W, H = 54, 28

    def __init__(self, x, y, color=(220, 70, 70)):
        self.x, self.y = x, y
        self.angle = 0.0
        self.speed = 0.0
        self.color = color
        self.sprite = self._make_sprite()

    def _make_sprite(self):
        s = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        pygame.draw.rect(s, (30, 30, 30), (6, 0, 12, 4), border_radius=2)
        pygame.draw.rect(s, (30, 30, 30), (36, 0, 12, 4), border_radius=2)
        pygame.draw.rect(s, (30, 30, 30), (6, self.H - 4, 12, 4), border_radius=2)
        pygame.draw.rect(s, (30, 30, 30), (36, self.H - 4, 12, 4), border_radius=2)
        pygame.draw.rect(s, self.color, (0, 3, self.W, self.H - 6), border_radius=8)
        pygame.draw.rect(s, (170, 220, 250), (30, 6, 12, self.H - 12), border_radius=3)
        pygame.draw.rect(s, (150, 200, 230), (10, 7, 8, self.H - 14), border_radius=3)
        pygame.draw.rect(s, (255, 250, 200), (self.W - 4, 5, 4, 5))
        pygame.draw.rect(s, (255, 250, 200), (self.W - 4, self.H - 10, 4, 5))
        return s

    def update(self, dt, keys, world, driving):
        on_road = world.tile_at(self.x, self.y) == ROAD
        max_speed = 430 if on_road else 190
        if driving:
            accel = keys["up"] - keys["down"]
            if accel > 0:
                self.speed += 320 * dt
            elif accel < 0:
                self.speed -= (480 if self.speed > 0 else 200) * dt
            steer = keys["right"] - keys["left"]
            grip = min(1.0, abs(self.speed) / 120)
            self.angle += steer * 2.6 * grip * dt * (1 if self.speed >= 0 else -1)
        # rolling friction, stronger off-road
        friction = 160 if on_road else 320
        if abs(self.speed) > max_speed:
            self.speed -= math.copysign(500 * dt, self.speed)
        elif not driving or not (keys["up"] or keys["down"]):
            self.speed -= math.copysign(min(abs(self.speed), friction * dt), self.speed)
        self.speed = max(-150, self.speed)
        nx = self.x + math.cos(self.angle) * self.speed * dt
        ny = self.y + math.sin(self.angle) * self.speed * dt
        if world.rect_blocked(pygame.Rect(int(nx) - 16, int(ny) - 16, 32, 32)):
            self.speed *= -0.3  # soft bump
        else:
            self.x, self.y = nx, ny

    def draw(self, surf, cam):
        img = pygame.transform.rotate(self.sprite, -math.degrees(self.angle))
        r = img.get_rect(center=(int(self.x - cam[0]), int(self.y - cam[1])))
        shadow = pygame.Rect(r.x + 4, r.y + 6, r.w - 8, r.h - 6)
        pygame.draw.ellipse(surf, (60, 90, 50), shadow)
        surf.blit(img, r)

    def sort_y(self):
        return self.y + 10


class NPC:
    def __init__(self, name, personality, x, y, body, skin=(240, 200, 160), hat=None):
        self.name = name
        self.personality = personality
        self.home = (x, y)
        self.x, self.y = x, y
        self.body, self.skin, self.hat = body, skin, hat
        self.target = None
        self.wait = random.uniform(1, 4)
        self.mode = "wander"  # wander | goto | follow
        self.mode_timer = 0.0
        self.facing = "down"
        self.moving = False
        self.t = random.random() * 10
        self.bubble = ""
        self.bubble_timer = 0.0
        self.history = []  # chat history for the AI (role/content dicts)
        self.last_greet = -999.0
        self.gifts_today = 0
        self.busy = False  # waiting for an AI reply
        self.stuck = 0.0

    def say(self, text, seconds=6.0):
        self.bubble = text
        self.bubble_timer = seconds

    def go_to(self, x, y, mode="goto", duration=60.0):
        self.mode = mode
        self.target = (x, y)
        self.mode_timer = duration

    def update(self, dt, world, player_pos, talking):
        self.t += dt
        self.bubble_timer = max(0.0, self.bubble_timer - dt)
        self.moving = False
        if talking:
            self._face(player_pos)
            return
        if self.mode != "wander":
            self.mode_timer -= dt
            if self.mode_timer <= 0:
                self.mode = "wander"
                self.target = None
        if self.mode == "follow":
            if math.dist((self.x, self.y), player_pos) > 60:
                self.target = player_pos
            else:
                self.target = None
        if self.target is None:
            if self.mode == "wander":
                self.wait -= dt
                if self.wait <= 0:
                    self.target = world.random_walkable_near(*self.home, 220)
                    self.wait = random.uniform(2, 6)
            return
        tx, ty = self.target
        d = math.dist((self.x, self.y), (tx, ty))
        if d < 6:
            self.target = None
            return
        speed = 95 if self.mode == "follow" else 75
        step = min(d, speed * dt)
        ox, oy = self.x, self.y
        self.x, self.y = try_move(world, self.x, self.y, (tx - self.x) / d * step, (ty - self.y) / d * step)
        self.moving = True
        self._face((tx, ty))
        if math.dist((ox, oy), (self.x, self.y)) < step * 0.3:
            self.stuck += dt
            if self.stuck > 1.0:  # blocked: sidestep randomly
                self.stuck = 0
                self.target = world.random_walkable_near(self.x, self.y, 90) if self.mode != "goto" else self.target
                self.x, self.y = try_move(world, self.x, self.y, random.uniform(-20, 20), random.uniform(-20, 20))
        else:
            self.stuck = 0

    def _face(self, pos):
        dx, dy = pos[0] - self.x, pos[1] - self.y
        if abs(dx) > abs(dy):
            self.facing = "right" if dx > 0 else "left"
        else:
            self.facing = "down" if dy > 0 else "up"

    def draw(self, surf, cam):
        sx, sy = int(self.x - cam[0]), int(self.y - cam[1])
        draw_person(surf, sx, sy, self.body, self.skin, self.t, self.moving, self.facing, self.hat)


class Farm:
    def __init__(self):
        fx, fy, fw, fh = FARM
        self.plots = {
            (tx, ty): {"tilled": False, "crop": None, "growth": 0.0, "watered": False}
            for ty in range(fy, fy + fh) for tx in range(fx, fx + fw)
        }

    def stage(self, plot):
        if not plot["crop"]:
            return -1
        total = CROPS[plot["crop"]]["grow"]
        return min(STAGES, int(plot["growth"] / (total / STAGES)))

    def ripe(self, plot):
        return plot["crop"] and self.stage(plot) >= STAGES

    def update(self, dt, raining):
        for plot in self.plots.values():
            if not plot["crop"] or self.ripe(plot):
                continue
            if raining:
                plot["watered"] = True
            if plot["watered"]:
                before = self.stage(plot)
                plot["growth"] += dt
                if self.stage(plot) > before:
                    plot["watered"] = False  # needs water again each stage

    def interact(self, tile, inventory, seed):
        """Do the obvious next thing on a plot. Returns a message or None."""
        plot = self.plots.get(tile)
        if plot is None:
            return None
        if not plot["tilled"]:
            plot["tilled"] = True
            return "Tilled the soil."
        if not plot["crop"]:
            key = f"{seed}_seed"
            if inventory.get(key, 0) <= 0:
                return f"No {seed} seeds. Buy some at the market (or press 1/2/3 to switch)."
            inventory[key] -= 1
            plot.update(crop=seed, growth=0.0, watered=False)
            return f"Planted {seed}. Water it with F!"
        if self.ripe(plot):
            inventory[plot["crop"]] = inventory.get(plot["crop"], 0) + 1
            name = plot["crop"]
            plot.update(crop=None, growth=0.0, watered=False)
            return f"Harvested a {name}!"
        if not plot["watered"]:
            plot["watered"] = True
            return "Watered. Growing..."
        return "Already watered. Give it a little time."

    def draw(self, surf, cam, view):
        for (tx, ty), plot in self.plots.items():
            rect = pygame.Rect(tx * TILE - cam[0], ty * TILE - cam[1], TILE, TILE)
            if not rect.colliderect(view):
                continue
            if plot["tilled"]:
                colour = (96, 66, 44) if plot["watered"] else (120, 86, 58)
                pygame.draw.rect(surf, colour, rect.inflate(-2, -2), border_radius=4)
                for i in range(3):
                    y = rect.y + 8 + i * 8
                    pygame.draw.line(surf, (84, 58, 38), (rect.x + 5, y), (rect.right - 6, y))
            if plot["crop"]:
                self._draw_crop(surf, rect, plot)

    def _draw_crop(self, surf, rect, plot):
        st = self.stage(plot)
        cx, cy = rect.center
        info = CROPS[plot["crop"]]
        green = (70, 160, 70)
        if st == 0:
            pygame.draw.circle(surf, (90, 70, 50), (cx, cy + 4), 3)
            pygame.draw.line(surf, green, (cx, cy + 3), (cx, cy - 2), 2)
        elif st == 1:
            pygame.draw.line(surf, green, (cx, cy + 6), (cx, cy - 6), 2)
            pygame.draw.circle(surf, green, (cx - 4, cy - 4), 4)
            pygame.draw.circle(surf, green, (cx + 4, cy - 6), 4)
        elif st == 2:
            pygame.draw.circle(surf, (60, 150, 60), (cx, cy - 2), 10)
            pygame.draw.circle(surf, info["color"], (cx + 3, cy + 3), 3)
        else:
            if plot["crop"] == "carrot":
                pygame.draw.polygon(surf, info["color"], [(cx - 5, cy - 2), (cx + 5, cy - 2), (cx, cy + 12)])
                pygame.draw.line(surf, green, (cx, cy - 2), (cx - 4, cy - 12), 3)
                pygame.draw.line(surf, green, (cx, cy - 2), (cx + 4, cy - 12), 3)
            elif plot["crop"] == "tomato":
                pygame.draw.circle(surf, (60, 150, 60), (cx, cy - 4), 10)
                for ox, oy in ((-5, 0), (5, -3), (0, 5)):
                    pygame.draw.circle(surf, info["color"], (cx + ox, cy + oy), 4)
            else:
                pygame.draw.ellipse(surf, info["color"], (cx - 12, cy - 6, 24, 16))
                pygame.draw.line(surf, (110, 80, 40), (cx, cy - 6), (cx, cy - 10), 3)
            # sparkle to signal "ready"
            pygame.draw.circle(surf, (255, 255, 200), (rect.right - 6, rect.y + 6), 2)

    def to_json(self):
        return {f"{tx},{ty}": p for (tx, ty), p in self.plots.items() if p["tilled"] or p["crop"]}

    def load_json(self, data):
        for key, p in data.items():
            tx, ty = map(int, key.split(","))
            if (tx, ty) in self.plots and (p.get("crop") in (None, *CROPS)):
                self.plots[(tx, ty)].update(p)
