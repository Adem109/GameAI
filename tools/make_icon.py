"""Render the app icon (1024x1024 PNG) with pygame - no external art needed."""
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
pygame.init()
S = 1024
surf = pygame.Surface((S, S), pygame.SRCALPHA)
pygame.draw.rect(surf, (118, 178, 94), (40, 40, S - 80, S - 80), border_radius=200)
pygame.draw.rect(surf, (250, 200, 120), (40, 40, S - 80, 330), border_top_left_radius=200, border_top_right_radius=200)
pygame.draw.circle(surf, (255, 235, 140), (760, 250), 110)
# road curving through
pygame.draw.polygon(surf, (92, 92, 104), [(330, 984), (690, 984), (560, 370), (470, 370)])
for y in range(420, 960, 110):
    w = 8 + (y - 370) // 40
    pygame.draw.rect(surf, (240, 220, 120), (512 - w // 2, y, w, 50))
# farm rows
for i in range(4):
    pygame.draw.rect(surf, (140, 104, 70), (110, 460 + i * 120, 260, 70), border_radius=20)
    pygame.draw.circle(surf, (240, 140, 50), (180, 480 + i * 120), 22)
    pygame.draw.circle(surf, (240, 140, 50), (290, 480 + i * 120), 22)
# tree
pygame.draw.rect(surf, (110, 76, 50), (790, 620, 40, 160))
pygame.draw.circle(surf, (54, 120, 62), (810, 590), 120)
# little red car
pygame.draw.rect(surf, (220, 70, 70), (450, 700, 120, 190), border_radius=40)
pygame.draw.rect(surf, (170, 220, 250), (470, 740, 80, 50), border_radius=14)
pygame.image.save(surf, out)
print("wrote", out)
