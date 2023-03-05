
import pygame

from collections.abc import Iterable
from typing import Optional

# button class
class ClickableBox:
    def __init__(
            self,
            win: pygame.Surface,
            font: pygame.font.Font,
            text: str,
            text_location: Iterable[int, int],
            box_location: Iterable[int, int],
            dimensions: Iterable[int, int],
            color: Iterable[int, int, int] = (150, 150, 150)) -> None:
        self.font = font
        self.text = text
        self.text_location = tuple(text_location)
        self.box_location = tuple(box_location)
        self.dimensions = tuple(dimensions)
        self.color = tuple(color)
        
        self.win = win
        self.box = None
    
    
    def draw(self) -> None:
        self.box = pygame.draw.rect(self.win, self.color, (*self.box_location, *self.dimensions))
        text_surface = self.font.render(self.text, True, (50, 50, 50))
        self.win.blit(text_surface, self.text_location)
    
    
    def undraw(self) -> None:
        pygame.draw.rect(self.win, (0, 0, 0), (*self.box_location, *self.dimensions))
        self.box = None
    
    
    def redraw(self) -> None:
        self.undraw()
        self.draw()
    
    
    def clicked(self, coords: Iterable[int, int]) -> bool:
        return self.box is not None and self.box.collidepoint(coords)


# text box class
class TextEntryBox(ClickableBox):
    def __init__(
            self,
            win: pygame.Surface,
            font: pygame.font.Font,
            text: str,
            text_location: Iterable[int, int],
            box_location: Iterable[int, int],
            dimensions: Iterable[int, int],
            typing_location: Iterable[int, int],
            max_text: int,
            color: Iterable[int, int, int] = (150, 150, 150)) -> None:
        super().__init__(win, font, text, text_location, box_location, dimensions, color)
        self.typing_location = tuple(typing_location)
        self.max_text = max_text
        self.box_text = ""
    
    
    def redraw(self, new_box_text: Optional[str] = None) -> None:
        self.undraw()
        self.draw(new_box_text)
    
    
    def draw(self, new_box_text: Optional[str] = None) -> None:
        super().draw()
        new_box_text = new_box_text[:self.max_text] if new_box_text is not None else self.box_text
        typing_surface = self.font.render(new_box_text, True, (70, 70, 70))
        self.win.blit(typing_surface, self.typing_location)
        self.box_text = new_box_text
    
    
    def undraw(self) -> None:
        upper_left_undraw_box = (self.box_location[0], self.text_location[1])
        undraw_box_dimensions = (self.dimensions[0], self.dimensions[1] + (self.box_location[1] - self.text_location[1]))
        pygame.draw.rect(self.win, (0, 0, 0), (*upper_left_undraw_box, *undraw_box_dimensions))
        self.box = None
