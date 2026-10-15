"""The village map: terrain, trees, houses, farm plots and named places."""
import math
import random

import pygame

TILE = 32
MAP_W, MAP_H = 100, 75

GRASS, ROAD, WATER, SOIL, SAND, STONE, FLOWER = range(7)

COLORS = {
    GRASS: (118, 178, 94),
    ROAD: (92, 92, 104),
    WATER: (72, 140, 210),
    SOIL: (140, 104, 70),
    SAND: (226, 206, 150),
    STONE: (190, 184, 172),
    FLOWER: (118, 178, 94),
}

# Buildings in tile units: (x, y, w, h, wall colour, roof colour, label)
HOUSES = [
    (38, 25, 6, 5, (236, 222, 196), (186, 84, 72), "Mira's house"),
    (56, 25, 6, 5, (226, 232, 240), (82, 120, 180), "Juno's house"),
    (56, 44, 6, 5, (244, 226, 180), (120, 150, 90), "Cottage"),
    (66, 40, 8, 5, (200, 200, 205), (90, 90, 96), "Ben's garage"),
    (20, 12, 5, 3, (196, 150, 104), (150, 60, 50), "Barn"),
]
MARKET = (39, 44, 5, 3)
FARM = (14, 17, 18, 12)  # soil field (x, y, w, h)

PLACES_TILES = {
    "farm": (23, 23),
    "market": (41, 48),
    "plaza": (49, 37),
    "pond": (74, 14),
    "lake": (24, 45),
    "garage": (70, 47),
    "north road": (49, 9),
    "south road": (49, 65),
    "east road": (90, 37),
    "west road": (9, 37),
    "flower meadow": (78, 56),
}


class World:
    def __init__(self, seed=7):
        self.rng = random.Random(seed)
        self.tiles = [[GRASS] * MAP_W for _ in range(MAP_H)]
        self.blocked = set()
        self.trees = []  # (px, py, variant)
        self.flowers = []  # (px, py, colour)
        self.houses = []
        self.places = {
            name: (tx * TILE + TILE // 2, ty * TILE + TILE // 2) for name, (tx, ty) in PLACES_TILES.items()
        }
        self._generate()
        self.ground = self._render_ground()
        self.minimap = pygame.transform.smoothscale(self.ground, (MAP_W * 2, MAP_H * 2))
        self._tree_sprites = [self._make_tree(v) for v in range(3)]

    # -- generation ---------------------------------------------------------
    def _fill(self, x, y, w, h, kind):
        for ty in range(max(0, y), min(MAP_H, y + h)):
            for tx in range(max(0, x), min(MAP_W, x + w)):
                self.tiles[ty][tx] = kind

    def _ellipse(self, cx, cy, rx, ry, kind, only=None):
        for ty in range(MAP_H):
            for tx in range(MAP_W):
                if ((tx - cx) / rx) ** 2 + ((ty - cy) / ry) ** 2 <= 1.0:
                    if only is None or self.tiles[ty][tx] in only:
                        self.tiles[ty][tx] = kind

    def _generate(self):
        rng = self.rng
        # Ponds with sandy shores
        self._ellipse(74, 22, 10, 7, SAND)
        self._ellipse(74, 22, 8.5, 5.5, WATER)
        self._ellipse(24, 54, 11, 8, SAND)
        self._ellipse(24, 54, 9.5, 6.5, WATER)
        # Roads: outer ring plus a cross through the village
        self._fill(8, 8, 84, 3, ROAD)
        self._fill(8, 64, 84, 3, ROAD)
        self._fill(8, 8, 3, 59, ROAD)
        self._fill(89, 8, 3, 59, ROAD)
        self._fill(8, 36, 84, 3, ROAD)
        self._fill(48, 8, 3, 59, ROAD)
        # Plaza
        self._fill(43, 31, 13, 13, STONE)
        self._fill(48, 31, 3, 13, ROAD)
        self._fill(43, 36, 13, 3, ROAD)
        # Farm
        fx, fy, fw, fh = FARM
        self._fill(fx - 1, fy - 1, fw + 2, fh + 2, GRASS)
        self._fill(fx, fy, fw, fh, SOIL)
        # Buildings
        for x, y, w, h, wall, roof, label in HOUSES:
            self.houses.append((pygame.Rect(x * TILE, y * TILE, w * TILE, h * TILE), wall, roof, label))
            for ty in range(y, y + h):
                for tx in range(x, x + w):
                    self.blocked.add((tx, ty))
        mx, my, mw, mh = MARKET
        self.market_rect = pygame.Rect(mx * TILE, my * TILE, mw * TILE, mh * TILE)
        for ty in range(my, my + mh):
            for tx in range(mx, mx + mw):
                self.blocked.add((tx, ty))
        # Water blocks walking
        for ty in range(MAP_H):
            for tx in range(MAP_W):
                if self.tiles[ty][tx] == WATER:
                    self.blocked.add((tx, ty))
        # Trees: dense border forest, sparse elsewhere
        reserved = [pygame.Rect(fx - 2, fy - 2, fw + 4, fh + 4), pygame.Rect(36, 23, 40, 30)]
        reserved += [pygame.Rect(tx - 3, ty - 3, 7, 7) for tx, ty in PLACES_TILES.values()]
        for ty in range(MAP_H):
            for tx in range(MAP_W):
                if self.tiles[ty][tx] != GRASS or (tx, ty) in self.blocked:
                    continue
                if self._near(tx, ty, ROAD, 1) or any(r.collidepoint(tx, ty) for r in reserved):
                    continue
                border = tx < 6 or ty < 6 or tx > MAP_W - 7 or ty > MAP_H - 7
                chance = 0.55 if border else 0.06
                if rng.random() < chance:
                    self.trees.append((tx * TILE + TILE // 2, ty * TILE + TILE - 4, rng.randrange(3)))
                    self.blocked.add((tx, ty))
                elif rng.random() < 0.05:
                    self.tiles[ty][tx] = FLOWER
                    colour = rng.choice([(250, 240, 120), (250, 150, 180), (255, 255, 255), (190, 150, 250)])
                    self.flowers.append((tx * TILE + rng.randrange(6, 26), ty * TILE + rng.randrange(6, 26), colour))
        # The map edge is solid
        for tx in range(MAP_W):
            self.blocked.update({(tx, 0), (tx, MAP_H - 1)})
        for ty in range(MAP_H):
            self.blocked.update({(0, ty), (MAP_W - 1, ty)})

    def _near(self, tx, ty, kind, dist):
        for dy in range(-dist, dist + 1):
            for dx in range(-dist, dist + 1):
                x, y = tx + dx, ty + dy
                if 0 <= x < MAP_W and 0 <= y < MAP_H and self.tiles[y][x] == kind:
                    return True
        return False

    # -- rendering ------------------------------------------------------------
    def _render_ground(self):
        rng = random.Random(3)
        surf = pygame.Surface((MAP_W * TILE, MAP_H * TILE))
        for ty in range(MAP_H):
            for tx in range(MAP_W):
                kind = self.tiles[ty][tx]
                rect = pygame.Rect(tx * TILE, ty * TILE, TILE, TILE)
                base = COLORS[kind]
                jitter = rng.randint(-6, 6)
                surf.fill(tuple(max(0, min(255, c + jitter)) for c in base), rect)
                if kind in (GRASS, FLOWER):
                    for _ in range(4):
                        x, y = rect.x + rng.randrange(TILE), rect.y + rng.randrange(TILE)
                        pygame.draw.line(surf, (96, 156, 78), (x, y), (x + 1, y - 4))
                elif kind == WATER:
                    if rng.random() < 0.3:
                        x, y = rect.x + rng.randrange(4, 20), rect.y + rng.randrange(6, 26)
                        pygame.draw.line(surf, (150, 200, 240), (x, y), (x + 8, y), 2)
                elif kind == STONE:
                    pygame.draw.rect(surf, (170, 164, 152), rect, 1)
                elif kind == ROAD:
                    if rng.random() < 0.2:
                        surf.set_at((rect.x + rng.randrange(TILE), rect.y + rng.randrange(TILE)), (110, 110, 120))
        # Dashed centre lines on the roads
        for y in (9, 37, 65):
            for x in range(10 * TILE, 89 * TILE, 48):
                pygame.draw.rect(surf, (240, 220, 120), (x, y * TILE + 14, 24, 4))
        for x in (9, 49, 90):
            for y in range(10 * TILE, 64 * TILE, 48):
                pygame.draw.rect(surf, (240, 220, 120), (x * TILE + 14, y, 4, 24))
        for x, y, colour in self.flowers:
            pygame.draw.circle(surf, colour, (x, y), 3)
            pygame.draw.circle(surf, (250, 210, 80), (x, y), 1)
        return surf

    def _make_tree(self, variant):
        greens = [(54, 120, 62), (70, 140, 70), (88, 128, 54)][variant]
        surf = pygame.Surface((56, 72), pygame.SRCALPHA)
        pygame.draw.ellipse(surf, (0, 0, 0, 50), (10, 60, 36, 12))
        pygame.draw.rect(surf, (110, 76, 50), (24, 40, 8, 26))
        pygame.draw.circle(surf, greens, (28, 28), 24)
        light = tuple(min(255, c + 30) for c in greens)
        pygame.draw.circle(surf, light, (22, 22), 12)
        return surf

    def tree_sprite(self, variant):
        return self._tree_sprites[variant]

    # -- queries ---------------------------------------------------------------
    def tile_at(self, px, py):
        tx, ty = int(px // TILE), int(py // TILE)
        if 0 <= tx < MAP_W and 0 <= ty < MAP_H:
            return self.tiles[ty][tx]
        return None

    def rect_blocked(self, rect: pygame.Rect) -> bool:
        for ty in range(rect.top // TILE, (rect.bottom - 1) // TILE + 1):
            for tx in range(rect.left // TILE, (rect.right - 1) // TILE + 1):
                if (tx, ty) in self.blocked or not (0 <= tx < MAP_W and 0 <= ty < MAP_H):
                    return True
        return False

    def random_walkable_near(self, px, py, radius, rng=random):
        for _ in range(30):
            ang = rng.random() * math.tau
            r = rng.random() * radius
            x, y = px + math.cos(ang) * r, py + math.sin(ang) * r
            if not self.rect_blocked(pygame.Rect(int(x) - 8, int(y) - 6, 16, 12)):
                return x, y
        return px, py

    def nearest_place(self, px, py):
        return min(self.places, key=lambda n: math.dist((px, py), self.places[n]))

    @property
    def pixel_size(self):
        return MAP_W * TILE, MAP_H * TILE
