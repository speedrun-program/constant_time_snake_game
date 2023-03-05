
import pygame

from bitpacking import BitPackingArray
from clickablebox import ClickableBox, TextEntryBox

from random import randrange

from collections.abc import Iterable
from typing import Dict, Tuple, Union

# memory efficient snake game with O(1) algorithm for snake movement and bug placement.
# three grids are used:
# - a grid representing the game grid
# - a grid partitioned into empty coords, future bug coords, current bug coords, and snake spaces
# - a grid which maps game grid coords to partitioned grid coords/indexes

# the partitioned grid is needed to randomly select bug spaces in O(1) time.
# it's also used to find existing bug locations in O(1) time.


# controls:
# - wasd or arrow keys control the snake
# - z and x change bug hints
# - p pauses the game


# values of grid spaces
EMPTY = 0
SNAKE_UP = 1
SNAKE_RIGHT = 2
SNAKE_DOWN = 3
SNAKE_LEFT = 4
BUG = 5

GRID_Y_OFFSET = 20
GRID_X_OFFSET = 20
GRID_GUI_WIDTH = 15
GRID_GUI_HEIGHT = 15
GRID_SPACE_SIZE = 35
GUI_WIDTH = 1200
GUI_HEIGHT = 700

# a class which makes it easier to access data from the memory used by the Game class
# 0 is a special value which means it's the same as the index being used to access it
# this is done because bytearray objects initialize their values to 0 very quickly
class GridHelper:
    def __init__(
            self,
            grid: BitPackingArray,
            width: int,
            height: int,
            bits_per_index: int,
            start_bit: int,
            bits_to_read: int,
            is_game_grid: bool = False) -> None:
        self.grid = grid
        self.width = width
        self.height = height
        self.bits_per_index = bits_per_index
        self.start_bit = start_bit
        self.bits_to_read = bits_to_read
        self.is_game_grid = is_game_grid
    
    
    def __getitem__(self, pos: Union[Iterable[int, int], int]) -> int:
        if not isinstance(pos, int):
            pos = (pos[0] * self.width) + pos[1]
        
        value = (self.grid[pos] >> self.start_bit) & ((1 << self.bits_to_read) - 1)
        if not self.is_game_grid:
            if value == 0:
                return pos
            return value - 1
        return value
    
    
    def __setitem__(self, pos: Union[Iterable[int, int], int], new_value: int) -> None:
        if not isinstance(pos, int):
            pos = (pos[0] * self.width) + pos[1]
        if not isinstance(new_value, int):
            new_value = (new_value[0] * self.width) + new_value[1]
        
        new_value += not self.is_game_grid
        if not 0 <= new_value <= ((1 << self.bits_to_read) - 1):
            raise ValueError(f"value must be in range(0, {((1 << self.bits_to_read) - 1)}), value was {new_value}")
        
        number_of_end_bits = self.bits_per_index - self.start_bit - self.bits_to_read
        bits_at_end = self.grid[pos] & (((1 << number_of_end_bits) - 1) << (self.start_bit + self.bits_to_read))
        bits_at_start = self.grid[pos] & ((1 << self.start_bit) - 1)
        self.grid[pos] = bits_at_end + (new_value << self.start_bit) + bits_at_start


class Game:
    extra_memory = BitPackingArray(0, 0)
    
    def __init__(
            self,
            width: int,
            height: int,
            min_bugs: int,
            max_bugs: int,
            snake_speed: int) -> None:
        total_grid_spaces = width * height
        
        self.snake_spaces = 5
        self.available_bug_spaces = total_grid_spaces - self.snake_spaces
        self.min_bugs = min(self.available_bug_spaces, min_bugs)
        self.max_bugs = min(self.available_bug_spaces, max_bugs)
        self.bug_spaces = self.max_bugs
        self.future_bug_spaces = 0
        self.bug_spawn_cycle = 1
        self.bug_hint_idx = total_grid_spaces - self.snake_spaces - self.max_bugs # used to look up bug location from self.partitioned_grid
        
        self.tail = (height // 2, (width // 2) - 3)
        self.head = (height // 2, (width // 2) + 1)
        
        self.width = width
        self.height = height
        self.snake_speed = snake_speed
        
        # if the maximum number of bugs is always on the grid, the spawn cycle trick isn't needed
        if self.max_bugs != self.min_bugs:
            possible_bug_spawn_cycles = (total_grid_spaces - self.snake_spaces - self.max_bugs) // (self.max_bugs - self.min_bugs)
            possible_bug_spawn_cycles += (total_grid_spaces - self.snake_spaces - self.max_bugs) % (self.max_bugs - self.min_bugs) != 0 # for last cycle
        else:
            possible_bug_spawn_cycles = 1
        
        game_grid_bits = (possible_bug_spawn_cycles + 5).bit_length()
        other_grid_bits = total_grid_spaces.bit_length()
        bits_per_grid_space = (other_grid_bits * 2) + game_grid_bits
        
        Game.extra_memory.reshape(total_grid_spaces, bits_per_grid_space)
        
        self.game_grid = GridHelper(Game.extra_memory, width, height, bits_per_grid_space, 0, game_grid_bits, True)
        self.key_grid = GridHelper(Game.extra_memory, width, height, bits_per_grid_space, game_grid_bits, other_grid_bits)
        self.partitioned_grid = GridHelper(Game.extra_memory, width, height, bits_per_grid_space, game_grid_bits + other_grid_bits, other_grid_bits)
        
        # setting initial snake spaces
        for n in range(5):
            snake_segment = (height // 2, (width // 2 - 3) + n)
            end_position = (self.height - 1, self.width - 1 - n)
            self.game_grid[snake_segment] = SNAKE_RIGHT
            self.key_grid[snake_segment] = end_position
            self.key_grid[end_position] = snake_segment
            self.partitioned_grid[snake_segment] = end_position
            self.partitioned_grid[end_position] = snake_segment
        
        # setting initial bug spaces
        for n in range(1, self.max_bugs + 1):
            partitioned_grid_replace_idx = total_grid_spaces - self.snake_spaces - n
            partitioned_grid_random_idx = randrange(self.available_bug_spaces)
            key_grid_random_idx = self.swap(partitioned_grid_replace_idx, partitioned_grid_random_idx)[1]
            self.game_grid[key_grid_random_idx] = BUG
            self.available_bug_spaces -= 1
    
    
    def free_memory(self) -> None:
        Game.extra_memory.reshape(0, 0)
    
    
    def get_next_coord(self, coord: Iterable[int, int], direction: int) -> Tuple[int, int]:
        vertical_change, horizontal_change = ((-1, 0), (0, 1), (1, 0), (0, -1))[direction - SNAKE_UP]
        return (coord[0] + vertical_change, coord[1] + horizontal_change)
    
    
    def change_bug_hint(self, backwards: bool = False) -> None:
        direction = -1 if backwards else 1
        self.bug_hint_idx += direction
        if self.bug_hint_idx < self.available_bug_spaces + self.future_bug_spaces:
            self.bug_hint_idx = self.available_bug_spaces + self.future_bug_spaces + self.bug_spaces - 1
        elif self.bug_hint_idx >= self.available_bug_spaces + self.future_bug_spaces + self.bug_spaces:
            self.bug_hint_idx = self.available_bug_spaces + self.future_bug_spaces
    
    
    def swap(self, idx_1: Union[Iterable[int, int], int], idx_2: Union[Iterable[int, int], int]) -> Tuple[int, int]:
        swap_value_1 = self.partitioned_grid[idx_1]
        swap_value_2 = self.partitioned_grid[idx_2]
        
        self.partitioned_grid[idx_1] = swap_value_2
        self.partitioned_grid[idx_2] = swap_value_1
        
        self.key_grid[swap_value_2] = idx_1
        self.key_grid[swap_value_1] = idx_2
        
        return (swap_value_1, swap_value_2)
    
    
    # - look up where new_head and old_tail are positioned in partitioned grid using key grid
    # - partitioned grid new_head and old_tail positions swap places, so old_tail is in unoccupied section
    #   and new_head is in snake space section
    # - key grid new_head and old_tail positions update so they say where they're positioned in partitioned grid
    def move_into_empty(self, next_head_coord: Union[Iterable[int, int], int], direction: int) -> None:
        partitioned_tail_idx = self.key_grid[self.tail]
        partitioned_head_idx = self.key_grid[next_head_coord]
        
        self.swap(partitioned_tail_idx, partitioned_head_idx)
        
        old_tail_coord = self.tail
        self.tail = self.get_next_coord(self.tail, self.game_grid[self.tail])
        self.game_grid[old_tail_coord] = EMPTY
        self.game_grid[self.head] = direction
        self.head = next_head_coord
        self.game_grid[next_head_coord] = direction
    
    
    # - look up where new_head/future_bug_space and old_tail are positioned in partitioned grid using key grid
    # - partitioned grid new_head and old_tail positions swap places, so old_tail is in future bug space section
    #   and new_head/future_bug_space is in snake space section
    # - key grid new_head/future_bug_space and old_tail positions update so they say where they're positioned in partitioned grid
    # - randomly choose new future_bug_space
    # - if new future_bug_space ends up where the tail was, stop here
    # - partitioned grid new future_bug_space and old_tail positions swap places, so old_tail is in unoccupied section
    #   and new future_bug_space is in future bug space section
    # - key grid new future_bug_space and old_tail positions update so they say where they're positioned in partitioned grid
    def move_into_future_bug(self, next_head_coord: Union[Iterable[int, int], int], direction: int) -> None:
        partitioned_tail_idx = self.key_grid[self.tail]
        partitioned_head_idx = self.key_grid[next_head_coord]
        
        self.swap(partitioned_tail_idx, partitioned_head_idx)
        
        random_partitioned_grid_idx = randrange(self.available_bug_spaces + 1)
        if random_partitioned_grid_idx == self.available_bug_spaces: # old tail coord was chosen as new future bug space
            old_tail_coord = self.tail
            self.tail = self.get_next_coord(self.tail, self.game_grid[self.tail])
            self.game_grid[old_tail_coord] = BUG + self.bug_spawn_cycle
            self.game_grid[self.head] = direction
            self.head = next_head_coord
            self.game_grid[next_head_coord] = direction
            return
        
        bug_location = self.swap(random_partitioned_grid_idx, partitioned_head_idx)[0]
        
        old_tail_coord = self.tail
        self.tail = self.get_next_coord(self.tail, self.game_grid[self.tail])
        self.game_grid[old_tail_coord] = EMPTY
        self.game_grid[self.head] = direction
        self.head = next_head_coord
        self.game_grid[next_head_coord] = direction
        
        self.game_grid[bug_location] = BUG + self.bug_spawn_cycle
    
    
    # - randomly choose new future_bug_space
    # - look up where new_head/bug_space is positioned in partitioned grid using key grid
    # - partitioned grid new_head/bug_space and the bug position touching the snake space section swap places, so
    #   new_head/bug_space becomes part of the snake space section
    # - key grid new_head/bug_space and position touching snake space section update so they say where
    #   they're positioned in partitioned grid
    # - partitioned grid future_bug_space and the unoccupied position touching the future bug space section swap places, so
    #   future_bug_space becomes part of the future bug space section
    # - key grid future_bug_space and position touching future bug space section update so they say where
    #   they're positioned in partitioned grid
    def move_into_bug(self, next_head_coord: Union[Iterable[int, int], int], direction: int) -> None:
        touching_snake_idx = self.available_bug_spaces + self.bug_spaces + self.future_bug_spaces - 1
        
        partitioned_head_idx = self.key_grid[next_head_coord]
        
        self.swap(partitioned_head_idx, touching_snake_idx)
        
        if self.available_bug_spaces > 0:
            random_partitioned_grid_idx = randrange(self.available_bug_spaces)
            touching_bug_idx = self.available_bug_spaces - 1
            
            bug_location = self.swap(random_partitioned_grid_idx, touching_bug_idx)[0]
            
            self.future_bug_spaces += 1
            
            self.game_grid[bug_location] = BUG + self.bug_spawn_cycle if self.max_bugs != self.min_bugs else BUG
        
        self.available_bug_spaces -= self.available_bug_spaces > 0
        self.game_grid[self.head] = direction
        self.head = next_head_coord
        self.game_grid[next_head_coord] = direction
        
        self.snake_spaces += 1
        self.bug_spaces -= 1
        if self.bug_spaces == self.min_bugs - 1: # future bug spaces become current bug spaces
            self.bug_spaces += self.future_bug_spaces
            self.future_bug_spaces = 0
            self.bug_spawn_cycle += 1
        
        if self.bug_hint_idx == partitioned_head_idx:
            self.bug_hint_idx = self.available_bug_spaces + self.future_bug_spaces
        elif self.bug_hint_idx == touching_snake_idx:
            self.bug_hint_idx = partitioned_head_idx
    
    
    def error_check(self) -> None:
        # testing function
        for i in range(self.available_bug_spaces):
            idx = self.partitioned_grid[i]
            if self.game_grid[idx] > 0:
                print(
                    "non-empty space referenced in empty area of self.partitioned_grid.",
                    f"game grid value: {self.game_grid[idx]}",
                    f"self.partitioned_grid index: {i}",
                    sep="\n"
                )
                raise ValueError
        for i in range(self.available_bug_spaces, self.available_bug_spaces + self.future_bug_spaces):
            idx = self.partitioned_grid[i]
            if self.game_grid[idx] != BUG + self.bug_spawn_cycle:
                print(
                    "non-future_bug_space referenced in bug area of self.partitioned_grid.",
                    f"game grid value: {self.game_grid[idx]}",
                    f"self.partitioned_grid index: {i}",
                    sep="\n"
                )
                raise ValueError
        for i in range(self.available_bug_spaces + self.future_bug_spaces, self.available_bug_spaces + self.future_bug_spaces + self.bug_spaces):
            idx = self.partitioned_grid[i]
            if not BUG <= self.game_grid[idx] < BUG + self.bug_spawn_cycle:
                print(
                    "non-bug space referenced in empty area of self.partitioned_grid.",
                    f"game grid value: {self.game_grid[idx]}",
                    f"self.partitioned_grid index: {i}",
                    sep="\n"
                )
                raise ValueError
        for i in range(self.available_bug_spaces + self.future_bug_spaces + self.bug_spaces, self.height * self.width):
            idx = self.partitioned_grid[i]
            if not SNAKE_UP <= self.game_grid[idx] <= SNAKE_LEFT:
                print(
                    "non-snake space referenced in empty area of self.partitioned_grid.",
                    f"game grid value: {self.game_grid[idx]}",
                    f"self.partitioned_grid index: {i}",
                    sep="\n"
                )
                raise ValueError
        
        s1 = set()
        s2 = set()
        for i in range(self.height * self.width):
            value = self.key_grid[i]
            if value in s1:
                print(f"duplicate value {value} found at index {i} in self.key_grid")
                raise ValueError
            s1.add(value)
        for i in range(self.height * self.width):
            value = self.partitioned_grid[i]
            if value in s2:
                print(f"duplicate value {value} found at index {i} in self.partitioned_grid")
                raise ValueError
            s2.add(value)


class GUI:
    def __init__(self) -> None:
        self.win = pygame.display.set_mode((GUI_WIDTH, GUI_HEIGHT))
        self.font = pygame.font.Font(pygame.font.get_default_font(), 24)
        self.textbox_text = ("MINIMUM_BUGS", "MAXIMUM_BUGS", "SNAKE_SPEED", "GRID_WIDTH", "GRID_HEIGHT")
        self.textboxes = (
            TextEntryBox(self.win, self.font, "", (20, 20), (10, 45), (1000, 30), (15, 50), 20),
            TextEntryBox(self.win, self.font, "", (20, 120), (10, 145), (1000, 30), (15, 150), 20),
            TextEntryBox(self.win, self.font, "", (20, 220), (10, 245), (1000, 30), (15, 250), 20),
            TextEntryBox(self.win, self.font, "", (20, 320), (10, 345), (1000, 30), (15, 350), 20),
            TextEntryBox(self.win, self.font, "", (20, 420), (10, 445), (1000, 30), (15, 450), 20)
        )
        self.buttons = (
            ClickableBox(self.win, self.font, "START", (GUI_WIDTH - 100, GUI_HEIGHT - 290), (GUI_WIDTH - 110, GUI_HEIGHT - 330), (100, 100)),
            ClickableBox(self.win, self.font, "CONFIG", (GUI_WIDTH - 108, GUI_HEIGHT - 180), (GUI_WIDTH - 110, GUI_HEIGHT - 220), (100, 100)),
            (quit_button := ClickableBox(self.win, self.font, "QUIT", (GUI_WIDTH - 90, GUI_HEIGHT - 70), (GUI_WIDTH - 110, GUI_HEIGHT - 110), (100, 100))),
            ClickableBox(self.win, self.font, "<", (572, GUI_HEIGHT - 40), (565, GUI_HEIGHT - 40), (30, 30)), # NOT CURRENTLY USED
            ClickableBox(self.win, self.font, ">", (615, GUI_HEIGHT - 40), (605, GUI_HEIGHT - 40), (30, 30)) # NOT CURRENTLY USED
        )
        self.quit_button = quit_button # this specific button is checked in several areas in the code
        
        self.settings = read_cfg()
        if int(self.settings["MINIMUM_BUGS"]) > int(self.settings["MAXIMUM_BUGS"]):
            self.settings["MINIMUM_BUGS"] = self.settings["MAXIMUM_BUGS"]
        
        for button in self.buttons[:3]:
            button.draw()
        
        self.game_drawn = False
        self.config_drawn = False
        self.cfg_page_number = 0 # NOT CURRENTLY USED
        self.cfg_pages = 1 # NOT CURRENTLY USED
    
    
    def toggle_top_two_buttons(self) -> None:
        if self.buttons[0].box is None: # this means self.buttons[0].box isn't drawn
            self.buttons[0].draw()
            self.buttons[1].draw()
            self.buttons[2].text = "QUIT"
            self.buttons[2].text_location = (GUI_WIDTH - 90, GUI_HEIGHT - 70)
            self.buttons[2].draw()
        else:
            self.buttons[0].undraw()
            self.buttons[1].undraw()
            self.buttons[2].text = "BACK"
            self.buttons[2].text_location = (GUI_WIDTH - 95, GUI_HEIGHT - 70)
            self.buttons[2].draw()
    
    
    def toggle_cfg_screen(self) -> None:
        self.set_messages("")
        self.toggle_top_two_buttons()
        self.cfg_page_number = 0
        if not self.config_drawn:
            # self.buttons[3].draw()
            # self.buttons[4].draw()
            for i in range(len(self.textboxes)):
                self.textboxes[i].text = self.textbox_text[i]
                self.textboxes[i].box_text = self.settings[self.textbox_text[i]]
                self.textboxes[i].draw(self.textboxes[i].box_text)
            self.config_drawn = True
        else:
            # self.buttons[3].undraw()
            # self.buttons[4].undraw()
            for t in self.textboxes:
                t.undraw()
            self.config_drawn = False
    
    
    def toggle_game_screen(self) -> None:
        self.toggle_top_two_buttons()
        if not self.game_drawn:
            self.game_drawn = True
        else:
            pygame.draw.rect(self.win, (0, 0, 0), (GRID_X_OFFSET, GRID_Y_OFFSET, GRID_SPACE_SIZE * GRID_GUI_WIDTH, GRID_SPACE_SIZE * GRID_GUI_HEIGHT)) # undrawing grid
            self.game_drawn = False
    
    
    def set_messages(self, *messages: Iterable[str]) -> None:
        # undrawing previous message
        pygame.draw.rect(self.win, (0, 0, 0), (50, GRID_Y_OFFSET + (GRID_SPACE_SIZE * GRID_GUI_HEIGHT), GUI_WIDTH - 160, GUI_HEIGHT - GRID_Y_OFFSET + (GRID_SPACE_SIZE * GRID_GUI_HEIGHT)))
        
        for n, message in enumerate(messages):
            text_surface = self.font.render(message, True, (50, 50, 50))
            self.win.blit(text_surface, (50, 570 + (50 * n)))
    
    
    def get_grid_color(
            self,
            grid: GridHelper,
            grid_width: int,
            grid_height: int,
            grid_y: int,
            grid_x: int,
            bug_spawn_cycle: int) -> tuple[int, int, int]:
        if (not 0 <= grid_y < grid_height) or (not 0 <= grid_x < grid_width):
            return (100, 100, 100)
        else:
            try:
                grid_value = grid[grid_y, grid_x]
            except TypeError:
                grid_value = grid[grid_y][grid_x] # this function should be able to work with normal lists too
            if grid_value == 0:
                return (200, 200, 200)
            elif SNAKE_UP <= grid_value <= SNAKE_LEFT:
                return (255, 243, 128)
            elif BUG <= grid_value < BUG + bug_spawn_cycle:
                return (65, 163, 23)
            elif grid_value == BUG + bug_spawn_cycle: # this can be used for testing
                return (200, 200, 200) # (255, 165, 0)
            else:
                return (106, 13, 173) # error color
    
    
    def draw_grid_not_centered_on_head(
            self,
            grid: GridHelper,
            grid_width: int,
            grid_height: int,
            bug_spawn_cycle: int) -> None:
        for grid_y in range(grid_height):
            for grid_x in range(grid_width):
                color = self.get_grid_color(grid, grid_width, grid_height, grid_y, grid_x, bug_spawn_cycle)
                pygame.draw.rect(self.win, color, (GRID_X_OFFSET + (grid_x * GRID_SPACE_SIZE), GRID_Y_OFFSET + (grid_y * GRID_SPACE_SIZE), GRID_SPACE_SIZE, GRID_SPACE_SIZE))
    
    
    def draw_grid(
            self,
            grid: GridHelper,
            grid_width: int,
            grid_height: int,
            snake_coord: Iterable[int, int],
            bug_spawn_cycle: int) -> None:
        if grid_width <= 15 and grid_height <= 15:
            self.draw_grid_not_centered_on_head(grid, grid_width, grid_height, bug_spawn_cycle)
            return
        
        for gui_y, grid_y in enumerate(range(snake_coord[0] - 7, snake_coord[0] + 8)):
            for gui_x, grid_x in enumerate(range(snake_coord[1] - 7, snake_coord[1] + 8)):
                color = self.get_grid_color(grid, grid_width, grid_height, grid_y, grid_x, bug_spawn_cycle)
                pygame.draw.rect(self.win, color, (GRID_X_OFFSET + (gui_x * GRID_SPACE_SIZE), GRID_Y_OFFSET + (gui_y * GRID_SPACE_SIZE), GRID_SPACE_SIZE, GRID_SPACE_SIZE))


def read_cfg() -> Dict[str, str]:
    try:
        with open("config.txt") as f:
            settings = dict(map(str.split, f))
            
            # checking if the file is valid
            for k in ("MINIMUM_BUGS", "MAXIMUM_BUGS", "SNAKE_SPEED", "GRID_WIDTH", "GRID_HEIGHT"):
                if (v := settings.get(k)) is None or (int_v := int(v)) < 0 or (int_v == 0 and k != "SNAKE_SPEED"):
                    raise ValueError
            
            if int(settings["GRID_WIDTH"]) < 10:
                settings["GRID_WIDTH"] = "10"
            if int(settings["GRID_HEIGHT"]) < 10:
                settings["GRID_HEIGHT"] = "10"
            if int(settings["MINIMUM_BUGS"]) > int(settings["MAXIMUM_BUGS"]):
                settings["MINIMUM_BUGS"] = settings["MAXIMUM_BUGS"]
            return settings
    except (FileNotFoundError, ValueError, KeyError):
        settings = {
            "MINIMUM_BUGS": "1",
            "MAXIMUM_BUGS": "1",
            "SNAKE_SPEED": "30",
            "GRID_WIDTH": "10",
            "GRID_HEIGHT": "10"
        }
        write_cfg(settings)
        return settings


def write_cfg(settings: Dict[str, str]) -> None:
    with open("config.txt", "w") as f:
        f.write("\n".join(map(" ".join, settings.items())))


def config(gui: GUI) -> bool:
    new_settings = gui.settings.copy() # used to check if settings were changed
    active_box = None
    
    while True:
        pygame.time.wait(16)
        pygame.display.update()
        
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                mouse_position = pygame.mouse.get_pos()
                if any((tb := textbox).clicked(mouse_position) for textbox in gui.textboxes):
                    if active_box is not None:
                        active_box.color = (150, 150, 150)
                        active_box.redraw()
                    active_box = tb
                    active_box.color = (200, 200, 200)
                    active_box.redraw()
                elif gui.quit_button.clicked(mouse_position):
                    if active_box is not None:
                        active_box.color = (150, 150, 150)
                        active_box.redraw()
                    if int(new_settings["GRID_WIDTH"]) < 10:
                        new_settings["GRID_WIDTH"] = "10"
                    if int(new_settings["GRID_HEIGHT"]) < 10:
                        new_settings["GRID_HEIGHT"] = "10"
                    if int(new_settings["MINIMUM_BUGS"]) > int(new_settings["MAXIMUM_BUGS"]):
                        new_settings["MINIMUM_BUGS"] = new_settings["MAXIMUM_BUGS"]
                    if new_settings != gui.settings: # don't write to file if settings weren't changed
                        for k in gui.textbox_text:
                            gui.settings[k] = new_settings[k]
                        write_cfg(gui.settings)
                    return True
            elif event.type == pygame.KEYDOWN and active_box is not None:
                if event.key == pygame.K_BACKSPACE:
                    active_box.redraw(active_box.box_text[:-1])
                    new_settings[active_box.text] = active_box.box_text
                elif (ch := (pygame.key.name(event.key))).isdecimal():
                    active_box.redraw(active_box.box_text + ch)
                    new_settings[active_box.text] = active_box.box_text


def wait_for_input(gui: GUI, waiting_for_unpause: bool = False) -> Tuple[int, int]:
    while True:
        pygame.time.wait(16)
        pygame.display.update()
        
        events = pygame.event.get()
        for event in events:
            if (
                (event.type == pygame.MOUSEBUTTONUP and event.button == 1 and gui.quit_button.clicked(pygame.mouse.get_pos()))
                or event.type == pygame.QUIT
                or (event.type == pygame.KEYDOWN and (event.key == pygame.K_p or not waiting_for_unpause))
                ):
                return event.type != pygame.MOUSEBUTTONUP, event.type != pygame.QUIT


def play_game(game: Game, gui: GUI) -> Tuple[int, int]:
    gui.set_messages("")
    ticks_since_last_movement = 0
    direction = None
    current_head_direction = game.game_grid[game.head]
    next_head_y, next_head_x = game.head
    bug_hint_coord = game.partitioned_grid[game.bug_hint_idx]
    bug_hint_x, bug_hint_y = (bug_hint_coord % game.width, bug_hint_coord // game.width)
    gui.set_messages(f"snake: ({next_head_x}, {next_head_y})", f"bug: ({bug_hint_x}, {bug_hint_y})")
    
    while True:
        pygame.time.wait(16)
        pygame.display.update()
        ticks_since_last_movement += game.snake_speed != 0
        
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                return False, False
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and gui.quit_button.clicked(pygame.mouse.get_pos()):
                return False, True
            elif event.type == pygame.KEYDOWN:
                if (event.key == pygame.K_UP or event.key == pygame.K_w) and current_head_direction != SNAKE_DOWN:
                    direction = SNAKE_UP
                elif (event.key == pygame.K_RIGHT or event.key == pygame.K_d) and current_head_direction != SNAKE_LEFT:
                    direction = SNAKE_RIGHT
                elif (event.key == pygame.K_DOWN or event.key == pygame.K_s) and current_head_direction != SNAKE_UP:
                    direction = SNAKE_DOWN
                elif (event.key == pygame.K_LEFT or event.key == pygame.K_a) and current_head_direction != SNAKE_RIGHT:
                    direction = SNAKE_LEFT
                elif event.key == pygame.K_p:
                    ticks_since_last_movement = 0
                    gui.set_messages("paused")
                    keep_playing, keep_running = wait_for_input(gui, True)
                    if not keep_playing or not keep_running:
                        return keep_playing, keep_running
                    gui.set_messages(f"snake: ({next_head_x}, {next_head_y})", f"bug: ({bug_hint_x}, {bug_hint_y})")
                elif event.key == pygame.K_z or event.key == pygame.K_x:
                    game.change_bug_hint(event.key == pygame.K_x)
                    bug_hint_coord = game.partitioned_grid[game.bug_hint_idx]
                    bug_hint_x, bug_hint_y = (bug_hint_coord % game.width, bug_hint_coord // game.width)
                    gui.set_messages(f"snake: ({next_head_x}, {next_head_y})", f"bug: ({bug_hint_x}, {bug_hint_y})")
        if direction is not None or (game.snake_speed != 0 and ticks_since_last_movement == game.snake_speed):
            if direction is None:
                direction = game.game_grid[game.head]
            ticks_since_last_movement = 0
            next_head_y, next_head_x = game.get_next_coord(game.head, direction)
            if not 0 <= next_head_y < game.height or not 0 <= next_head_x < game.width or SNAKE_UP <= game.game_grid[next_head_y, next_head_x] <= SNAKE_LEFT:
                game.free_memory() # free memory immediately since it will need to be freed later anyways
                gui.set_messages("you lose, press any key to reset")
                return wait_for_input(gui)
            if game.game_grid[next_head_y, next_head_x] == EMPTY:
                game.move_into_empty((next_head_y, next_head_x), direction)
            elif game.game_grid[next_head_y, next_head_x] == 5 + game.bug_spawn_cycle:
                game.move_into_future_bug((next_head_y, next_head_x), direction)
            else:
                game.move_into_bug((next_head_y, next_head_x), direction)
                if game.snake_spaces == game.width * game.height:
                    gui.draw_grid(game.game_grid, game.width, game.height, game.head, game.bug_spawn_cycle)
                    game.free_memory() # free memory immediately since it will need to be freed later anyways
                    gui.set_messages("you win, press any key to reset")
                    return wait_for_input(gui)
            gui.draw_grid(game.game_grid, game.width, game.height, game.head, game.bug_spawn_cycle)
            bug_hint_coord = game.partitioned_grid[game.bug_hint_idx]
            bug_hint_x, bug_hint_y = (bug_hint_coord % game.width, bug_hint_coord // game.width)
            gui.set_messages(f"snake: ({next_head_x}, {next_head_y})", f"bug: ({bug_hint_x}, {bug_hint_y})")
            current_head_direction = game.game_grid[game.head]
            direction = None


def main() -> None:
    pygame.init()
    pygame.display.set_caption("snake game")
    gui = GUI()
    
    keep_running = True
    while keep_running:
        pygame.time.wait(16)
        pygame.display.update()
        
        events = pygame.event.get()
        for event in events:
            if event.type == pygame.QUIT:
                keep_running = False
            elif (
                    event.type == pygame.MOUSEBUTTONUP
                    and event.button == 1
                    and any((b := button).clicked(pygame.mouse.get_pos()) for button in gui.buttons)
                ):
                if b.text == "QUIT":
                    keep_running = False
                elif b.text == "CONFIG":
                    gui.toggle_cfg_screen()
                    keep_running = config(gui)
                    gui.toggle_cfg_screen()
                elif b.text == "START":
                    error_happened = False
                    keep_playing = True
                    gui.toggle_game_screen()
                    while keep_playing and keep_running:
                        try:
                            game = Game(
                                int(gui.settings["GRID_WIDTH"]),
                                int(gui.settings["GRID_HEIGHT"]),
                                int(gui.settings["MINIMUM_BUGS"]),
                                int(gui.settings["MAXIMUM_BUGS"]),
                                int(gui.settings["SNAKE_SPEED"])
                            )
                        except (MemoryError, OverflowError) as e:
                            gui.set_messages(e.__class__.__name__)
                            error_happened = True
                            break
                        gui.set_messages("press any key to start")
                        gui.draw_grid(game.game_grid, game.width, game.height, game.head, game.bug_spawn_cycle)
                        pygame.display.update()
                        keep_playing, keep_running = wait_for_input(gui)
                        if keep_playing and keep_running:
                            keep_playing, keep_running = play_game(game, gui)
                        game.free_memory()
                    gui.toggle_game_screen()
                    if not error_happened:
                        gui.set_messages("")
    
    pygame.quit()


if __name__ == "__main__":
    main()
