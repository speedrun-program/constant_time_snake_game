Memory efficient snake game with O(1) algorithm for snake movement and bug placement.
Three grids are used:
- a grid representing the game grid
- a grid partitioned into empty coords, future bug coords, current bug coords, and snake spaces
- a grid which maps game grid coords to partitioned grid coords/indexes

The partitioned grid is needed to randomly select bug spaces in O(1) time.
It's also used to find existing bug locations in O(1) time.

controls:
wasd or arrow keys control the snake
z and x change bug hints
p pauses the game
