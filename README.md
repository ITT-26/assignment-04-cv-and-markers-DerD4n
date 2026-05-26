[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/5NorvP5a)

# CV and Markers Assignment

This assignment has two parts:

1. A perspective transformation tool for extracting a region from an image.
2. An augmented reality game that uses ArUco markers, webcam tracking, and a Pyglet window.

## Requirements

Install the required packages:

```bash
pip install -r requirements.txt
```

If your OpenCV build does not include ArUco support, install the contrib package instead:

```bash
pip install opencv-contrib-python numpy pyglet pillow
```

## Part 1: Perspective Transformation

File: `perspective_transformation/image_extractor.py`

This script lets you pick 4 points on an image and warps the selected area into a rectangle with the size you choose.

### Usage

```bash
python3 perspective_transformation/image_extractor.py -i <input_image> -o <output_image> -W <width> -H <height>
```

Example:

```bash
python3 perspective_transformation/image_extractor.py -i perspective_transformation/sample_image_2.jpg -o perspective_transformation/output.png -W 200 -H 200
```

### Controls

- Left click: select 4 corner points
- `a`: try automatic corner detection
- `Esc`: clear the selected points and start over
- `s`: save the warped result
- `q`: quit

### Notes

- Automatic corner detection will not work on 'sample_image.jpg' because it is too damaged.

## Part 2: AR Game

File: `ar_game/AR_game.py`

This program reads the webcam feed, detects 4 ArUco markers on a board, warps the board into a rectangular play area, and runs a small whac-a-mole style game in a Pyglet window.

### Gameplay

- Show the board with 4 ArUco markers to the camera.
- After the markers are detected, a 5 second countdown starts.
- The game then runs for 60 seconds.
- Diglett-style targets pop up, special Dugtrio targets give 3 points, and some targets subtract points.
- Move your hand over a target to hit it.
- At the end of the round, the final score is shown.

### Run

```bash
python3 ar_game/AR_game.py
```

You can also pass a different webcam index if needed:

```bash
python3 ar_game/AR_game.py 1
```

### Notes

- The game works best when the camera is looking down at the board.
- If tracking is unstable, make sure all 4 markers are visible again so the board can recalibrate.
- The replay button appears on the game-over screen and lets you start a new round.
