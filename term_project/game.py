"""Wordle Hazard - polished pygame edition.

Features: dark theme, tile flip / shake / pop / bounce animations, clickable
on-screen keyboard, toast messages, confetti, animated menu, nicer stats screen,
fully resizable layout.
"""
import json
import math
import os
import random
import sys
from collections import Counter

import pygame

pygame.init()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATS_FILE = os.path.join(BASE_DIR, "wordle_stats_en.json")

WORD_LENGTH, MAX_GUESSES = 5, 6
MIN_W, MIN_H = 480, 720
VALIDATE_WORDS = False      # True = only accept words found in the word files
DEBUG_SHOW_ANSWER = False   # True = print the answer to the console

FLIP, STAGGER = 450, 260    # ms: flip duration per tile / delay between tiles

C = {
    "text": (245, 245, 247), "muted": (150, 152, 160),
    "border": (62, 62, 68), "panel": (30, 30, 36),
    "tile_empty": (58, 58, 64), "tile_active": (135, 135, 142),
    "GREEN": (83, 141, 78), "YELLOW": (181, 159, 59), "GRAY": (62, 62, 66),
    "KEY": (129, 131, 136),
    "button": (44, 44, 52), "accent": (83, 141, 78), "red": (214, 90, 90),
}

FALLBACK_WORDS = (
    "apple train audio house world crane slate stone light water earth plant river cloud "
    "bread chair table music dance movie phone smile happy green brain heart sleep dream "
    "tiger zebra mouse horse sheep snake whale shark eagle beach ocean storm flame sugar "
    "honey lemon grape peach melon pizza pasta salad candy novel story paper brush paint "
    "color shirt dress shoes"
).split()

MODE_INFO = {
    "classic":   ("Classic Mode",   "6 guesses - medium words", "words_medium.txt"),
    "unlimited": ("Unlimited Mode", "Practice - no stats",      "words_easy.txt"),
    "hard":      ("Hard Mode",      "6 guesses - hard words",   "words_hard.txt"),
}
PRAISE = ["Genius!", "Magnificent!", "Impressive!", "Splendid!", "Great!", "Phew!"]


# ----------------------------------------------------------------- helpers
_font_cache = {}


def font(size, bold=True):
    size = max(8, int(size))
    key = (size, bold)
    if key not in _font_cache:
        _font_cache[key] = pygame.font.SysFont(
            "segoeui,helveticaneue,arial,dejavusans", size, bold=bold)
    return _font_cache[key]


def text(surf, s, size, color, bold=True, **anchor):
    img = font(size, bold).render(s, True, color)
    surf.blit(img, img.get_rect(**anchor))
    return img


def lighten(color, amt=18):
    return tuple(min(255, c + amt) for c in color)


_bg_cache = {}


def background(w, h):
    if (w, h) not in _bg_cache:
        _bg_cache.clear()
        s = pygame.Surface((w, h))
        top, bot = (30, 30, 40), (12, 12, 16)
        for y in range(h):
            t = y / max(1, h - 1)
            pygame.draw.line(s, tuple(int(top[k] + (bot[k] - top[k]) * t) for k in range(3)),
                             (0, y), (w, y))
        _bg_cache[(w, h)] = s
    return _bg_cache[(w, h)]


def draw_tile(surf, rect, fill, border, letter, vscale=1.0):
    r = rect.copy()
    if vscale < 1:
        r.height = max(2, int(rect.h * vscale))
        r.centery = rect.centery
    radius = max(1, min(8, r.h // 2))
    if fill:
        pygame.draw.rect(surf, fill, r, border_radius=radius)
    if border and not fill:
        pygame.draw.rect(surf, border, r, 2, border_radius=radius)
    if letter:
        img = font(rect.w * 0.55).render(letter, True, C["text"])
        if vscale < 1:
            img = pygame.transform.smoothscale(img, (img.get_width(), max(1, int(img.get_height() * vscale))))
        surf.blit(img, img.get_rect(center=r.center))


def draw_button(surf, rect, label, hover, sub=None, primary=False, danger=False):
    base = (150, 55, 55) if danger else (C["accent"] if primary else C["button"])
    col = lighten(base, 20) if hover else base
    r = rect.move(0, -2) if hover else rect
    pygame.draw.rect(surf, (8, 8, 10), r.move(0, 4), border_radius=14)
    pygame.draw.rect(surf, col, r, border_radius=14)
    pygame.draw.rect(surf, lighten(col, 25), r, 2, border_radius=14)
    if sub:
        text(surf, label, r.h * 0.33, C["text"], center=(r.centerx, r.centery - r.h * 0.15))
        text(surf, sub, r.h * 0.2, C["muted"] if not primary else C["text"], bold=False,
             center=(r.centerx, r.centery + r.h * 0.23))
    else:
        text(surf, label, r.h * 0.36, C["text"], center=r.center)


# ------------------------------------------------------------- data / logic
def load_words(filename):
    for folder in (BASE_DIR, os.getcwd()):
        path = os.path.join(folder, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                words = sorted({w.strip().lower() for w in f
                                if len(w.strip()) == WORD_LENGTH and w.strip().isalpha() and w.strip().isascii()})
            if words:
                return words
    return list(FALLBACK_WORDS)


def default_stats():
    return {"played": 0, "wins": 0, "current_streak": 0, "max_streak": 0, "guess_dist": {}}


def load_stats():
    stats = default_stats()
    try:
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            stats.update(json.load(f))
    except (OSError, json.JSONDecodeError):
        pass
    return stats


def check_guess(target, guess):
    result = ["GRAY"] * WORD_LENGTH
    counts = Counter(target)
    for i, ch in enumerate(guess):
        if ch == target[i]:
            result[i] = "GREEN"
            counts[ch] -= 1
    for i, ch in enumerate(guess):
        if result[i] != "GREEN" and counts[ch] > 0:
            result[i] = "YELLOW"
            counts[ch] -= 1
    return result


class Game:
    def __init__(self):
        self.stats = load_stats()
        self.mode = "classic"
        self.confetti = []
        self.new_game("classic")

    # --- state
    def new_game(self, mode):
        self.mode = mode
        self.words = load_words(MODE_INFO[mode][2])
        self.target = random.choice(self.words)
        if DEBUG_SHOW_ANSWER:
            print("Answer:", self.target)
        self.guesses, self.results, self.current = [], [], ""
        self.game_over = self.win = self.celebrated = False
        self.reveal_start, self.reveal_end, self.end_time = None, 0, 0
        self.pop_times = [-10 ** 6] * WORD_LENGTH
        self.shake_start = -10 ** 6
        self.toast = None
        self.confetti = []
        self._valid = None

    def valid_words(self):
        if self._valid is None:
            self._valid = set()
            for _, _, fn in MODE_INFO.values():
                self._valid.update(load_words(fn))
        return self._valid

    def animating(self, now):
        return self.reveal_start is not None and now < self.reveal_end

    def overlay_visible(self, now):
        return self.game_over and now >= self.end_time

    def show_toast(self, msg, now):
        self.toast = (msg, now)

    def shake_offset(self, now, box):
        dt = now - self.shake_start
        if 0 <= dt < 500:
            return math.sin(dt / 500 * math.pi * 6) * box * 0.12 * (1 - dt / 500)
        return 0

    # --- input
    def type_letter(self, ch, now):
        if self.game_over or self.animating(now) or len(self.current) >= WORD_LENGTH:
            return
        self.pop_times[len(self.current)] = now
        self.current += ch

    def backspace(self, now):
        if not self.game_over and not self.animating(now):
            self.current = self.current[:-1]

    def submit(self, now):
        if self.game_over or self.animating(now):
            return
        if len(self.current) < WORD_LENGTH:
            self.shake_start = now
            self.show_toast("Not enough letters", now)
            return
        if VALIDATE_WORDS and self.current not in self.valid_words():
            self.shake_start = now
            self.show_toast("Not in word list", now)
            return
        guess = self.current
        self.guesses.append(guess)
        self.results.append(check_guess(self.target, guess))
        self.current = ""
        self.reveal_start = now
        self.reveal_end = now + STAGGER * (WORD_LENGTH - 1) + FLIP
        if guess == self.target:
            self.win = self.game_over = True
        elif len(self.guesses) == MAX_GUESSES:
            self.game_over = True
        if self.game_over:
            self.end_time = self.reveal_end + (1300 if self.win else 600)
            if self.mode != "unlimited":
                self.update_stats()

    def update_stats(self):
        s = self.stats
        s["played"] += 1
        if self.win:
            s["wins"] += 1
            s["current_streak"] += 1
            s["max_streak"] = max(s["max_streak"], s["current_streak"])
            k = str(len(self.guesses))
            s["guess_dist"][k] = s["guess_dist"].get(k, 0) + 1
        else:
            s["current_streak"] = 0
        self.save_stats()

    def save_stats(self):
        try:
            with open(STATS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.stats, f, ensure_ascii=False, indent=4)
        except OSError:
            pass

    def reset_stats(self):
        self.stats = default_stats()
        self.save_stats()

    def keyboard_state(self, now):
        rank = {"KEY": 0, "GRAY": 1, "YELLOW": 2, "GREEN": 3}
        rows = len(self.guesses) - (1 if self.animating(now) else 0)
        state = {}
        for g, res in zip(self.guesses[:rows], self.results[:rows]):
            for ch, r in zip(g, res):
                if rank[r] > rank[state.get(ch, "KEY")]:
                    state[ch] = r
        return state

    # --- per-frame update
    def update(self, now, w, h, dt):
        if self.win and not self.celebrated and now >= self.reveal_end:
            self.celebrated = True
            self.show_toast(PRAISE[len(self.guesses) - 1], now)
            colors = [C["GREEN"], C["YELLOW"], (225, 225, 235), (214, 90, 120), (90, 150, 220)]
            for _ in range(150):
                self.confetti.append([random.uniform(0, w), random.uniform(-h * 0.3, 0),
                                      random.uniform(-40, 40), random.uniform(120, 340),
                                      random.choice(colors), random.uniform(6, 11),
                                      random.uniform(0, 6.28), random.uniform(-6, 6)])
        for p in self.confetti:
            p[0] += p[2] * dt + math.sin(p[6]) * 0.6
            p[1] += p[3] * dt
            p[6] += p[7] * dt
        self.confetti = [p for p in self.confetti if p[1] < h + 20]


# ------------------------------------------------------------------- layout
def game_layout(w, h):
    header_h = max(60, h * 0.085)
    kbw = min(w * 0.96, 620)
    gap = max(4, kbw * 0.011)
    key_w = (kbw - 9 * gap) / 10
    key_h = min(key_w * 1.4, h * 0.075)
    kb_top = h - (3 * key_h + 2 * gap) - max(16, h * 0.03)

    rows = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
    keys = []
    for r, row in enumerate(rows):
        units = [(c, 1) for c in row]
        if r == 2:
            units = [("ENTER", 1.5)] + units + [("DEL", 1.5)]
        widths = [u * key_w + (u - 1) * gap for _, u in units]
        x = (w - (sum(widths) + (len(units) - 1) * gap)) / 2
        y = kb_top + r * (key_h + gap)
        for (label, _), wd in zip(units, widths):
            keys.append((label, pygame.Rect(x, y, wd, key_h)))
            x += wd + gap

    avail = kb_top - header_h - h * 0.05
    box = min(avail / 6.6, (w * 0.9) / 5.6)
    tgap = box * 0.12
    grid_w = WORD_LENGTH * box + (WORD_LENGTH - 1) * tgap
    grid_h = MAX_GUESSES * box + (MAX_GUESSES - 1) * tgap
    return {
        "header_h": header_h, "keys": keys, "box": box, "tgap": tgap,
        "bx": (w - grid_w) / 2, "by": header_h + h * 0.025 + (avail - grid_h) / 2,
        "menu_btn": pygame.Rect(12, header_h * 0.22, 78, header_h * 0.56),
    }


def overlay_layout(w, h):
    pw, ph = min(w * 0.88, 440), min(h * 0.44, 330)
    panel = pygame.Rect(0, 0, pw, ph)
    panel.center = (w / 2, h / 2)
    pad = pw * 0.05
    bw, bh = (pw - 3 * pad) / 2, ph * 0.2
    again = pygame.Rect(panel.x + pad, panel.bottom - pad - bh, bw, bh)
    menu = pygame.Rect(again.right + pad, again.y, bw, bh)
    return panel, again, menu


def confirm_layout(w, h):
    panel, yes, no = overlay_layout(w, h)
    panel.height = int(panel.h * 0.75)
    panel.center = (w / 2, h / 2)
    yes.bottom = no.bottom = panel.bottom - panel.w * 0.05
    return panel, yes, no


def menu_buttons(w, h):
    bw, bh = min(w * 0.8, 420), min(h * 0.085, 72)
    gap = h * 0.018
    entries = [(k, v[0], v[1]) for k, v in MODE_INFO.items()]
    entries += [("stats", "Statistics", "Your results"), ("exit", "Exit Game", None)]
    out = []
    for i, (key, label, sub) in enumerate(entries):
        out.append((key, label, sub, pygame.Rect((w - bw) / 2, h * 0.34 + i * (bh + gap), bw, bh)))
    return out


def stats_buttons(w, h):
    bw, bh, gap = min(w * 0.4, 210), min(h * 0.075, 60), w * 0.03
    back = pygame.Rect(0, 0, bw, bh)
    back.midright = (w / 2 - gap / 2, h * 0.9)
    reset = pygame.Rect(0, 0, bw, bh)
    reset.midleft = (w / 2 + gap / 2, h * 0.9)
    return back, reset


# --------------------------------------------------------------------- app
class App:
    def __init__(self):
        self.screen = pygame.display.set_mode((600, 850), pygame.RESIZABLE)
        pygame.display.set_caption("Wordle Hazard")
        self.clock = pygame.time.Clock()
        self.game = Game()
        self.scene = "menu"
        self.menu_sel = 0
        self.confirm_reset = False

    def menu_action(self, key):
        if key in MODE_INFO:
            self.game.new_game(key)
            self.scene = "game"
        elif key == "stats":
            self.confirm_reset = False
            self.scene = "stats"
        else:
            pygame.quit()
            sys.exit()

    # ---- events
    def handle_event(self, e, now):
        g = self.game
        if e.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if e.type == pygame.VIDEORESIZE:
            if e.w < MIN_W or e.h < MIN_H:
                self.screen = pygame.display.set_mode((max(e.w, MIN_W), max(e.h, MIN_H)), pygame.RESIZABLE)
            return
        w, h = pygame.display.get_surface().get_size()

        if self.scene == "menu":
            btns = menu_buttons(w, h)
            if e.type == pygame.MOUSEMOTION:
                for i, (_, _, _, rect) in enumerate(btns):
                    if rect.collidepoint(e.pos):
                        self.menu_sel = i
            elif e.type == pygame.KEYDOWN:
                if e.key in (pygame.K_DOWN, pygame.K_s, pygame.K_TAB):
                    self.menu_sel = (self.menu_sel + 1) % len(btns)
                elif e.key in (pygame.K_UP, pygame.K_w):
                    self.menu_sel = (self.menu_sel - 1) % len(btns)
                elif e.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    self.menu_action(btns[self.menu_sel][0])
                elif pygame.K_1 <= e.key <= pygame.K_5:
                    self.menu_sel = e.key - pygame.K_1
                    self.menu_action(btns[self.menu_sel][0])
                elif e.key == pygame.K_ESCAPE:
                    pygame.quit()
                    sys.exit()
            elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                for key, _, _, rect in btns:
                    if rect.collidepoint(e.pos):
                        self.menu_action(key)
                        break

        elif self.scene == "stats":
            back, reset = stats_buttons(w, h)
            _, yes, no = confirm_layout(w, h)
            if self.confirm_reset:
                if e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_y, pygame.K_RETURN):
                        g.reset_stats()
                        self.confirm_reset = False
                    elif e.key in (pygame.K_n, pygame.K_ESCAPE):
                        self.confirm_reset = False
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if yes.collidepoint(e.pos):
                        g.reset_stats()
                        self.confirm_reset = False
                    elif no.collidepoint(e.pos):
                        self.confirm_reset = False
            else:
                if e.type == pygame.KEYDOWN:
                    if e.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_BACKSPACE):
                        self.scene = "menu"
                    elif e.key == pygame.K_r:
                        self.confirm_reset = True
                elif e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                    if back.collidepoint(e.pos):
                        self.scene = "menu"
                    elif reset.collidepoint(e.pos):
                        self.confirm_reset = True

        elif self.scene == "game":
            if e.type == pygame.KEYDOWN:
                if g.overlay_visible(now):
                    if e.key == pygame.K_RETURN:
                        g.new_game(g.mode)
                    elif e.key == pygame.K_ESCAPE:
                        self.scene = "menu"
                elif e.key == pygame.K_ESCAPE:
                    self.scene = "menu"
                elif e.key == pygame.K_RETURN:
                    g.submit(now)
                elif e.key == pygame.K_BACKSPACE:
                    g.backspace(now)
                elif len(e.unicode) == 1 and e.unicode.isascii() and e.unicode.isalpha():
                    g.type_letter(e.unicode.lower(), now)
            if e.type == pygame.MOUSEBUTTONDOWN and e.button == 1:
                if g.overlay_visible(now):
                    _, again, menu = overlay_layout(w, h)
                    if again.collidepoint(e.pos):
                        g.new_game(g.mode)
                    elif menu.collidepoint(e.pos):
                        self.scene = "menu"
                    return
                L = game_layout(w, h)
                if L["menu_btn"].collidepoint(e.pos):
                    self.scene = "menu"
                    return
                for label, rect in L["keys"]:
                    if rect.collidepoint(e.pos):
                        if label == "ENTER":
                            g.submit(now)
                        elif label == "DEL":
                            g.backspace(now)
                        else:
                            g.type_letter(label, now)
                        break

    # ---- drawing
    def draw_menu(self, surf, now, mouse):
        w, h = surf.get_size()
        tsize = min(w * 0.12, 72)
        tg = tsize * 0.12
        x0 = (w - (6 * tsize + 5 * tg)) / 2
        y = h * 0.1
        cols = [C["GREEN"], C["YELLOW"], C["GRAY"]]
        for i, ch in enumerate("WORDLE"):
            phase = now / 1000 - i * 0.15
            cycle = math.floor(phase / 4.0)
            p = (phase - cycle * 4.0) / 0.5
            new, old = cols[(i + cycle) % 3], cols[(i + cycle - 1) % 3]
            if p < 1:
                s, col = abs(math.cos(p * math.pi)), (old if p < 0.5 else new)
            else:
                s, col = 1, new
            draw_tile(surf, pygame.Rect(x0 + i * (tsize + tg), y, tsize, tsize), col, col, ch, s)
        text(surf, " ".join("HAZARD"), tsize * 0.5, C["red"], center=(w / 2, y + tsize * 1.5))
        text(surf, "Click or use arrow keys / 1-5 + Enter", tsize * 0.27, C["muted"], bold=False,
             center=(w / 2, y + tsize * 2.15))
        for i, (key, label, sub, rect) in enumerate(menu_buttons(w, h)):
            draw_button(surf, rect, label, rect.collidepoint(mouse) or i == self.menu_sel, sub,
                        primary=(key == "classic"))

    def draw_stats(self, surf, mouse):
        w, h = surf.get_size()
        s = self.game.stats
        text(surf, "STATISTICS", h * 0.05, C["text"], center=(w / 2, h * 0.09))
        pw = min(w * 0.9, 520)
        x0 = (w - pw) / 2
        played, wins = s["played"], s["wins"]
        rate = int(round(wins / played * 100)) if played else 0
        for k, (label, val) in enumerate([("Played", played), ("Win %", rate),
                                          ("Streak", s["current_streak"]), ("Best", s["max_streak"])]):
            cx = x0 + pw * (k + 0.5) / 4
            text(surf, str(val), h * 0.055, C["text"], center=(cx, h * 0.19))
            text(surf, label, h * 0.022, C["muted"], bold=False, center=(cx, h * 0.235))
        text(surf, "GUESS DISTRIBUTION", h * 0.026, C["text"], center=(w / 2, h * 0.32))
        dist = s["guess_dist"]
        mx = max([dist.get(str(i), 0) for i in range(1, 7)] + [1])
        row_h = min(h * 0.065, 52)
        for i in range(1, 7):
            y = h * 0.37 + (i - 1) * row_h * 1.2
            cnt = dist.get(str(i), 0)
            text(surf, str(i), row_h * 0.5, C["text"], midleft=(x0, y + row_h / 2))
            bw = max(row_h * 1.2, (pw - row_h * 0.7) * cnt / mx)
            bar = pygame.Rect(x0 + row_h * 0.7, y, bw, row_h)
            col = C["GREEN"] if (cnt == mx and cnt > 0) else C["GRAY"]
            pygame.draw.rect(surf, col, bar, border_radius=6)
            text(surf, str(cnt), row_h * 0.45, C["text"], midright=(bar.right - 10, bar.centery))
        back, reset = stats_buttons(w, h)
        text(surf, "Esc = back   R = reset", h * 0.02, C["muted"], bold=False, center=(w / 2, h * 0.96))
        draw_button(surf, back, "Back", back.collidepoint(mouse) and not self.confirm_reset)
        draw_button(surf, reset, "Reset Stats", reset.collidepoint(mouse) and not self.confirm_reset, danger=True)
        if self.confirm_reset:
            dim = pygame.Surface((w, h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, 170))
            surf.blit(dim, (0, 0))
            panel, yes, no = confirm_layout(w, h)
            pygame.draw.rect(surf, C["panel"], panel, border_radius=18)
            pygame.draw.rect(surf, C["border"], panel, 2, border_radius=18)
            text(surf, "Reset all statistics?", panel.h * 0.15, C["text"], center=(panel.centerx, panel.y + panel.h * 0.22))
            text(surf, "This cannot be undone.  (Y / N)", panel.h * 0.09, C["muted"], bold=False,
                 center=(panel.centerx, panel.y + panel.h * 0.42))
            draw_button(surf, yes, "Reset", yes.collidepoint(mouse), danger=True)
            draw_button(surf, no, "Cancel", no.collidepoint(mouse))

    def draw_game(self, surf, now, mouse):
        g = self.game
        w, h = surf.get_size()
        L = game_layout(w, h)
        hh = L["header_h"]

        # header
        text(surf, "WORDLE HAZARD", hh * 0.36, C["text"], center=(w / 2, hh * 0.42))
        text(surf, MODE_INFO[g.mode][0].upper(), hh * 0.18, C["muted"], center=(w / 2, hh * 0.78))
        draw_button(surf, L["menu_btn"], "Menu", L["menu_btn"].collidepoint(mouse))
        pygame.draw.line(surf, C["border"], (0, hh), (w, hh), 1)

        # board
        box, tgap = L["box"], L["tgap"]
        last = len(g.guesses) - 1
        for i in range(MAX_GUESSES):
            shake = g.shake_offset(now, box) if (i == len(g.guesses) and not g.game_over) else 0
            for j in range(WORD_LENGTH):
                rect = pygame.Rect(L["bx"] + j * (box + tgap) + shake, L["by"] + i * (box + tgap), box, box)
                if i < len(g.guesses):
                    ch, res = g.guesses[i][j].upper(), g.results[i][j]
                    t = (now - g.reveal_start - j * STAGGER) / FLIP if (i == last and g.reveal_start is not None) else 1
                    if t <= 0:
                        draw_tile(surf, rect, None, C["tile_active"], ch)
                    elif t < 1:
                        s = abs(math.cos(t * math.pi))
                        if t < 0.5:
                            draw_tile(surf, rect, None, C["tile_active"], ch, s)
                        else:
                            draw_tile(surf, rect, C[res], C[res], ch, s)
                    else:
                        if g.win and i == last and now >= g.reveal_end:
                            bt = (now - g.reveal_end - j * 90) / 450
                            if 0 <= bt <= 1:
                                rect.y -= int(math.sin(bt * math.pi) * box * 0.35)
                        draw_tile(surf, rect, C[res], C[res], ch)
                elif i == len(g.guesses) and not g.game_over and j < len(g.current):
                    p = now - g.pop_times[j]
                    if 0 <= p < 120:
                        k = box * 0.12 * math.sin(p / 120 * math.pi)
                        rect = rect.inflate(k, k)
                    draw_tile(surf, rect, None, C["tile_active"], g.current[j].upper())
                else:
                    draw_tile(surf, rect, None, C["tile_empty"], "")

        # keyboard
        kstate = g.keyboard_state(now)
        for label, rect in L["keys"]:
            col = C[kstate.get(label, "KEY")] if len(label) == 1 else C["KEY"]
            if rect.collidepoint(mouse) and not g.overlay_visible(now):
                col = lighten(col, 22)
            pygame.draw.rect(surf, col, rect, border_radius=7)
            text(surf, label.upper(), rect.h * (0.3 if len(label) > 1 else 0.4), C["text"], center=rect.center)

        # toast
        if g.toast and now - g.toast[1] < 1800:
            img = font(h * 0.024).render(g.toast[0], True, (20, 20, 24))
            pill = img.get_rect(center=(w / 2, hh + h * 0.035)).inflate(36, 22)
            pygame.draw.rect(surf, (240, 240, 245), pill, border_radius=pill.h // 2)
            surf.blit(img, img.get_rect(center=pill.center))

        # end-of-game overlay
        if g.overlay_visible(now):
            a = min(1.0, (now - g.end_time) / 250)
            dim = pygame.Surface((w, h), pygame.SRCALPHA)
            dim.fill((0, 0, 0, int(165 * a)))
            surf.blit(dim, (0, 0))
            panel, again, menu = overlay_layout(w, h)
            pygame.draw.rect(surf, C["panel"], panel, border_radius=18)
            pygame.draw.rect(surf, C["border"], panel, 2, border_radius=18)
            ph = panel.h
            if g.win:
                text(surf, "YOU WIN!", ph * 0.13, C["GREEN"], center=(panel.centerx, panel.y + ph * 0.15))
                n = len(g.guesses)
                text(surf, f"Solved in {n} guess{'es' if n != 1 else ''}", ph * 0.07, C["muted"], bold=False,
                     center=(panel.centerx, panel.y + ph * 0.28))
            else:
                text(surf, "GAME OVER", ph * 0.13, C["red"], center=(panel.centerx, panel.y + ph * 0.15))
                text(surf, "The word was", ph * 0.07, C["muted"], bold=False,
                     center=(panel.centerx, panel.y + ph * 0.28))
            ts = min(panel.w * 0.13, ph * 0.17)
            tg = ts * 0.12
            ax = panel.centerx - (WORD_LENGTH * ts + (WORD_LENGTH - 1) * tg) / 2
            for k, ch in enumerate(g.target.upper()):
                draw_tile(surf, pygame.Rect(ax + k * (ts + tg), panel.y + ph * 0.4, ts, ts), C["GREEN"], None, ch)
            draw_button(surf, again, "Play Again", again.collidepoint(mouse), primary=True)
            draw_button(surf, menu, "Menu", menu.collidepoint(mouse))

        # confetti (on top of everything)
        for x, y, _, _, col, size, rot, _ in g.confetti:
            pygame.draw.rect(surf, col, (x, y, max(2, size * abs(math.cos(rot))), size * 0.6))

    # ---- main loop
    def frame(self):
        now = pygame.time.get_ticks()
        for e in pygame.event.get():
            self.handle_event(e, now)
        surf = pygame.display.get_surface()
        w, h = surf.get_size()
        dt = self.clock.tick(60) / 1000
        now = pygame.time.get_ticks()
        mouse = pygame.mouse.get_pos()
        surf.blit(background(w, h), (0, 0))
        if self.scene == "menu":
            self.draw_menu(surf, now, mouse)
        elif self.scene == "stats":
            self.draw_stats(surf, mouse)
        else:
            self.game.update(now, w, h, dt)
            self.draw_game(surf, now, mouse)
        pygame.display.flip()

    def run(self):
        while True:
            self.frame()


if __name__ == "__main__":
    App().run()