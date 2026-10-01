import pygame
import random
import json
import os
import sys
from collections import Counter

pygame.init()
pygame.font.init()

WIDTH, HEIGHT = 600, 850
SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
pygame.display.set_caption("Wordle Hazard")

# Colors
COLORS = {
    "WHITE": (255, 255, 255), "BLACK": (0, 0, 0),
    "GREEN": (106, 170, 100), "YELLOW": (201, 180, 88),
    "GRAY": (120, 124, 126),
    "LIGHT_GRAY": (211, 211, 211),
    "KEY_DEFAULT": (129, 131, 132),
    "KEY_USED": (58, 58, 60),
    "RED": (200, 70, 70)
}

# --- Dynamic Font System ---
FONTS = {}
def update_fonts(width, height):
    """Calculates new font sizes based on window dimensions."""
    base_size = min(width, height)
    font_name = "Arial"
    try:
        # CHANGED: Reduced font sizes by another ~20%
        FONTS["letter"] = pygame.font.SysFont(font_name, int(base_size * 0.055), bold=True)
        FONTS["menu"] = pygame.font.SysFont(font_name, int(base_size * 0.05), bold=True)
        FONTS["stats"] = pygame.font.SysFont(font_name, int(base_size * 0.036))
        FONTS["message"] = pygame.font.SysFont(font_name, int(base_size * 0.03))
        FONTS["key"] = pygame.font.SysFont(font_name, int(base_size * 0.023), bold=True)
        # Added a larger font for the final win/loss message
        FONTS["end_game"] = pygame.font.SysFont(font_name, int(base_size * 0.06), bold=True)
    except Exception: # Fallback
        FONTS["letter"] = pygame.font.Font(None, int(base_size * 0.07))
        FONTS["menu"] = pygame.font.Font(None, int(base_size * 0.06))
        FONTS["stats"] = pygame.font.Font(None, int(base_size * 0.04))
        FONTS["message"] = pygame.font.Font(None, int(base_size * 0.035))
        FONTS["key"] = pygame.font.Font(None, int(base_size * 0.03))
        FONTS["end_game"] = pygame.font.Font(None, int(base_size * 0.07))


update_fonts(WIDTH, HEIGHT)

class WordleGamePygame:
    def __init__(self, stats_file='wordle_stats_en.json'):
        self.WORD_LENGTH = 5
        self.MAX_GUESSES = 6
        self.stats_file = stats_file
        self.stats = self._load_stats()
        
        self.word_bank, self.target_word = [], ""
        self.guesses, self.results, self.current_guess = [], [], ""
        self.game_over, self.win = False, False
        self.current_mode = 'classic'
        self.message, self.message_timer = "", 0
        self.keyboard_colors = {chr(c): "KEY_DEFAULT" for c in range(ord('a'), ord('z') + 1)}

    def reset_game_state(self):
        self.guesses, self.results, self.current_guess = [], [], ""
        self.game_over, self.win = False, False
        self.message = ""
        self.keyboard_colors = {chr(c): "KEY_DEFAULT" for c in range(ord('a'), ord('z') + 1)}
    
    # --- Core game logic (No changes) ---
    def _load_words_from_file(self, filename):
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                words = [line.strip().lower() for line in f if len(line.strip()) == self.WORD_LENGTH and line.strip().isalpha()]
            if not words: self.word_bank = ['apple', 'train', 'audio', 'house', 'world']
            else: self.word_bank = words
        except FileNotFoundError:
            self.word_bank = ['apple', 'train', 'audio', 'house', 'world']
            with open(filename, 'w', encoding='utf-8') as f: pass

    def _load_stats(self):
        if not os.path.exists(self.stats_file): return {"played": 0, "wins": 0, "current_streak": 0, "max_streak": 0, "guess_dist": {}}
        try:
            with open(self.stats_file, 'r', encoding='utf-8') as f: return json.load(f)
        except json.JSONDecodeError: return {"played": 0, "wins": 0, "current_streak": 0, "max_streak": 0, "guess_dist": {}}

    def _save_stats(self):
        with open(self.stats_file, 'w', encoding='utf-8') as f: json.dump(self.stats, f, ensure_ascii=False, indent=4)

    def update_stats(self):
        self.stats["played"] += 1
        if self.win:
            self.stats["wins"] += 1; self.stats["current_streak"] += 1
            self.stats["max_streak"] = max(self.stats["max_streak"], self.stats["current_streak"])
            guess_count = str(len(self.guesses))
            self.stats["guess_dist"][guess_count] = self.stats["guess_dist"].get(guess_count, 0) + 1
        else: self.stats["current_streak"] = 0
        self._save_stats()

    def check_guess(self, guess):
        result = ["GRAY"] * self.WORD_LENGTH
        target_counts = Counter(self.target_word)
        for i, letter in enumerate(guess):
            if letter == self.target_word[i]:
                result[i] = "GREEN"; target_counts[letter] -= 1
        for i, letter in enumerate(guess):
            if result[i] != "GREEN" and letter in target_counts and target_counts[letter] > 0:
                result[i] = "YELLOW"; target_counts[letter] -= 1
        for i, letter in enumerate(guess):
            if 'a' <= letter <= 'z':
                if result[i] == "GREEN": self.keyboard_colors[letter] = "GREEN"
                elif result[i] == "YELLOW" and self.keyboard_colors[letter] != "GREEN": self.keyboard_colors[letter] = "YELLOW"
                elif self.keyboard_colors[letter] == "KEY_DEFAULT": self.keyboard_colors[letter] = "KEY_USED"
        return result

    def is_valid_guess(self, guess):
        if len(guess) != self.WORD_LENGTH:
            self.set_message(f"Guess must be {self.WORD_LENGTH} letters", "RED"); return False
        return True

    def handle_enter(self):
        if self.game_over: return
        if self.is_valid_guess(self.current_guess):
            self.guesses.append(self.current_guess)
            self.results.append(self.check_guess(self.current_guess))
            self.current_guess = ""
            if self.guesses[-1] == self.target_word:
                self.win = self.game_over = True
                # Set a simple win message; the drawing loop will handle the main display
                self.set_message("YOU WIN", "GREEN")
                if self.current_mode != 'unlimited': self.update_stats()
            elif len(self.guesses) == self.MAX_GUESSES:
                self.game_over = True
                # Set a simple loss message
                self.set_message("LOSE", "RED")
                if self.current_mode != 'unlimited': self.update_stats()

    def set_message(self, text, color_key="BLACK"):
        self.message = (text, COLORS[color_key]); self.message_timer = pygame.time.get_ticks()

    # --- Pygame Drawing ---
    def draw_board(self, surface):
        width, height = surface.get_size()
        #  CHANGED: Reduced board size and position
        board_area_h = height * 0.5
        box_size = min((width * 0.65) / self.WORD_LENGTH, board_area_h / self.MAX_GUESSES)
        padding = box_size * 0.1
        grid_width = (box_size * self.WORD_LENGTH) + (padding * (self.WORD_LENGTH - 1))
        start_x, start_y = (width - grid_width) / 2, height * 0.08
        
        rows_to_display = len(self.guesses) + 1
        if self.game_over: rows_to_display = len(self.guesses)
        rows_to_display = min(rows_to_display, self.MAX_GUESSES)

        for i in range(rows_to_display):
            for j in range(self.WORD_LENGTH):
                box = pygame.Rect(start_x + j * (box_size + padding), start_y + i * (box_size + padding), box_size, box_size)
                letter, color_key, l_color = "", "WHITE", COLORS["BLACK"]
                if i < len(self.guesses):
                    letter, color_key, l_color = self.guesses[i][j], self.results[i][j], COLORS["WHITE"]
                elif i == len(self.guesses) and j < len(self.current_guess):
                    letter = self.current_guess[j]
                pygame.draw.rect(surface, COLORS[color_key], box, border_radius=5)
                if color_key == "WHITE": pygame.draw.rect(surface, COLORS["GRAY"], box, 2, border_radius=5)
                if letter:
                    text_surf = FONTS["letter"].render(letter.upper(), True, l_color)
                    surface.blit(text_surf, text_surf.get_rect(center=box.center))

    def draw_keyboard(self, surface):
        width, height = surface.get_size()
        keys = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]
        #  CHANGED: Reduced key sizes
        key_h = height * 0.045
        key_w = min(width * 0.06, key_h * 1.3)
        padding = key_w * 0.15
        start_y = height * 0.65
        for i, row in enumerate(keys):
            row_width = len(row) * (key_w + padding) - padding
            start_x = (width - row_width) / 2
            for j, char in enumerate(row):
                key_rect = pygame.Rect(start_x + j * (key_w + padding), start_y + i * (key_h + padding * 0.8), key_w, key_h)
                color_name = self.keyboard_colors[char]
                pygame.draw.rect(surface, COLORS[color_name], key_rect, border_radius=5)
                key_text = FONTS["key"].render(char.upper(), True, COLORS["WHITE"])
                surface.blit(key_text, key_text.get_rect(center=key_rect.center))

    def draw_header(self, surface):
        width, height = surface.get_size()
        mode_text = f"Mode: {self.current_mode.capitalize()}"
        title_text = FONTS["menu"].render(mode_text, True, COLORS["BLACK"])
        surface.blit(title_text, title_text.get_rect(center=(width / 2, height * 0.04)))
        
    def draw_message(self, surface):
        width, height = surface.get_size()
        if self.message and pygame.time.get_ticks() - self.message_timer < 2000 and not self.game_over:
            text, color = self.message
            msg_surface = FONTS["message"].render(text, True, color)
            surface.blit(msg_surface, msg_surface.get_rect(center=(width / 2, height * 0.95)))
            
    # --- Game Loop and Menu ---
    def start_new_game(self, mode):
        file_map = {'classic': 'words_medium.txt', 'unlimited': 'words_easy.txt', 'hard': 'words_hard.txt'}
        filename = file_map.get(mode, 'words_medium.txt')
        self._load_words_from_file(filename)
        self.reset_game_state()
        self.current_mode = mode
        self.target_word = random.choice(self.word_bank)
        print(f"Starting {mode} mode. Hint: {self.target_word}")
        return True
    
    def run_game(self):
        global SCREEN, WIDTH, HEIGHT
        running = True
        clock = pygame.time.Clock()
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT: pygame.quit(); sys.exit()
                if event.type == pygame.VIDEORESIZE:
                    WIDTH, HEIGHT = max(event.w, 500), max(event.h, 750)
                    SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                    update_fonts(WIDTH, HEIGHT)
                if event.type == pygame.KEYDOWN:
                    if self.game_over:
                        if event.key in [pygame.K_RETURN, pygame.K_ESCAPE]: running = False
                        continue
                    if event.key == pygame.K_ESCAPE: running = False
                    elif event.key == pygame.K_BACKSPACE: self.current_guess = self.current_guess[:-1]
                    elif event.key == pygame.K_RETURN and len(self.current_guess) == self.WORD_LENGTH: self.handle_enter()
                    elif 'a' <= event.unicode.lower() <= 'z' and len(self.current_guess) < self.WORD_LENGTH:
                        self.current_guess += event.unicode.lower()
            SCREEN.fill(COLORS["LIGHT_GRAY"])
            self.draw_header(SCREEN)
            self.draw_board(SCREEN)
            self.draw_keyboard(SCREEN)
            self.draw_message(SCREEN)

            #  CHANGED: New block to draw a persistent win/loss message
            if self.game_over:
                # Create a semi-transparent overlay
                overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                overlay.fill((211, 211, 211, 180)) # Light gray with transparency
                SCREEN.blit(overlay, (0, 0))

                # Display the primary message (YOU WIN! or SO CLOSE!)
                end_text_str, color = self.message
                end_text_surf = FONTS["end_game"].render(end_text_str, True, color)
                SCREEN.blit(end_text_surf, end_text_surf.get_rect(center=(WIDTH / 2, HEIGHT / 2 - 30)))
                
                # If the player lost, also show the correct word
                if not self.win:
                    answer_surf = FONTS["message"].render(f"The word was: {self.target_word.upper()}", True, COLORS["BLACK"])
                    SCREEN.blit(answer_surf, answer_surf.get_rect(center=(WIDTH / 2, HEIGHT / 2 + 15)))

                # Prompt to return to menu
                prompt_surf = FONTS["message"].render("Press Enter to return to menu", True, COLORS["BLACK"])
                SCREEN.blit(prompt_surf, prompt_surf.get_rect(center=(WIDTH / 2, HEIGHT - 50)))

            pygame.display.flip()
            clock.tick(60)

# The main_menu and display_stats functions remain unchanged
def main_menu():
    global SCREEN, WIDTH, HEIGHT
    game = WordleGamePygame()
    button_actions = {"Classic Mode": 'classic', "Unlimited Mode": 'unlimited', "Hard Mode": 'hard', "Statistics": 'stats', "Exit Game": 'exit'}
    button_keys = list(button_actions.keys())
    while True:
        SCREEN.fill(COLORS["LIGHT_GRAY"])
        title_text = FONTS["menu"].render("Wordle Game", True, COLORS["BLACK"])
        SCREEN.blit(title_text, title_text.get_rect(center=(WIDTH / 2, HEIGHT * 0.15)))
        buttons = {}
        button_h, button_w = HEIGHT * 0.08, WIDTH * 0.7
        for i, text in enumerate(button_keys):
            rect = pygame.Rect((WIDTH - button_w) / 2, HEIGHT * 0.3 + i * (button_h * 1.2), button_w, button_h)
            buttons[text] = rect
            pygame.draw.rect(SCREEN, COLORS["WHITE"], rect, border_radius=10)
            pygame.draw.rect(SCREEN, COLORS["BLACK"], rect, 2, border_radius=10)
            btn_text = FONTS["stats"].render(text, True, COLORS["BLACK"])
            SCREEN.blit(btn_text, btn_text.get_rect(center=rect.center))
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = max(event.w, 500), max(event.h, 750)
                SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                update_fonts(WIDTH, HEIGHT)
            if event.type == pygame.MOUSEBUTTONDOWN:
                for text, rect in buttons.items():
                    if rect.collidepoint(event.pos):
                        action = button_actions[text]
                        if action in ['classic', 'unlimited', 'hard']:
                            if game.start_new_game(action): game.run_game()
                        elif action == 'stats': display_stats(game.stats)
                        elif action == 'exit': pygame.quit(); sys.exit()
        pygame.display.flip()

def display_stats(stats):
    global SCREEN, WIDTH, HEIGHT
    stats_running = True
    while stats_running:
        SCREEN.fill(COLORS["LIGHT_GRAY"])
        title_text = FONTS["menu"].render("Statistics", True, COLORS["BLACK"])
        SCREEN.blit(title_text, title_text.get_rect(center=(WIDTH / 2, HEIGHT * 0.07)))
        win_rate = (stats['wins'] / stats['played'] * 100) if stats['played'] > 0 else 0
        stats_lines = [f"Played: {stats['played']}", f"Wins: {stats['wins']} ({win_rate:.1f}%)", f"Current Streak: {stats['current_streak']}", f"Max Streak: {stats['max_streak']}", "--- Guess Distribution ---"]
        for i, line in enumerate(stats_lines):
            line_surface = FONTS["stats"].render(line, True, COLORS["BLACK"])
            SCREEN.blit(line_surface, line_surface.get_rect(midleft=(WIDTH * 0.1, HEIGHT * 0.2 + i * HEIGHT * 0.06)))
        dist_y_start = HEIGHT * 0.2 + len(stats_lines) * HEIGHT * 0.06
        max_dist = max(stats['guess_dist'].values()) if stats['guess_dist'] else 0
        for i in range(1, 7):
            count = stats['guess_dist'].get(str(i), 0)
            y_pos = dist_y_start + (i - 1) * HEIGHT * 0.06
            dist_text = FONTS["stats"].render(f"Guess {i}: {count}", True, COLORS["BLACK"])
            SCREEN.blit(dist_text, dist_text.get_rect(midleft=(WIDTH * 0.1, y_pos)))
            if max_dist > 0:
                bar_width = (count / max_dist) * (WIDTH * 0.5) if count > 0 else 0
                bar = pygame.Rect(WIDTH * 0.4, y_pos - (HEIGHT * 0.02), bar_width, HEIGHT * 0.04)
                pygame.draw.rect(SCREEN, COLORS["KEY_DEFAULT"], bar, border_radius=5)
        back_button = pygame.Rect(WIDTH * 0.3, HEIGHT * 0.85, WIDTH * 0.4, HEIGHT * 0.08)
        pygame.draw.rect(SCREEN, COLORS["WHITE"], back_button, border_radius=10)
        pygame.draw.rect(SCREEN, COLORS["BLACK"], back_button, 2, border_radius=10)
        back_text = FONTS["menu"].render("Back", True, COLORS["BLACK"])
        SCREEN.blit(back_text, back_text.get_rect(center=back_button.center))
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            if event.type == pygame.VIDEORESIZE:
                WIDTH, HEIGHT = event.w, event.h
                SCREEN = pygame.display.set_mode((WIDTH, HEIGHT), pygame.RESIZABLE)
                update_fonts(WIDTH, HEIGHT)
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE: stats_running = False
            if event.type == pygame.MOUSEBUTTONDOWN and back_button.collidepoint(event.pos): stats_running = False
        pygame.display.flip()

if __name__ == "__main__":
    main_menu()