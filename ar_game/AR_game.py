import cv2
import cv2.aruco as aruco
import numpy as np
import pyglet
from PIL import Image
import sys
import time
import random

# converts OpenCV image to PIL image and then to pyglet texture
def cv2glet(img, fmt):
    if fmt == 'GRAY':
        rows, cols = img.shape
        channels = 1
    else:
        rows, cols, channels = img.shape

    raw_img = Image.fromarray(img).tobytes()

    top_to_bottom_flag = -1
    bytes_per_row = channels * cols
    pyimg = pyglet.image.ImageData(width=cols, 
                                   height=rows, 
                                   fmt=fmt, 
                                   data=raw_img, 
                                   pitch=top_to_bottom_flag * bytes_per_row)
    return pyimg

def order_points(pts):
    # Order points: Top-Left, Top-Right, Bottom-Right, Bottom-Left
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

video_id = 0
if len(sys.argv) > 1:
    video_id = int(sys.argv[1])

cap = cv2.VideoCapture(video_id)
# Ensure sensible resolution based on webcam (ai feature)
W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
if W == 0 or H == 0:
    W, H = 640, 480

window = pyglet.window.Window(W, H, caption="AR Whac-A-Diglett")

# ArUco parameters
aruco_dict = aruco.getPredefinedDictionary(aruco.DICT_6X6_250)
aruco_params = aruco.DetectorParameters()
detector = aruco.ArucoDetector(aruco_dict, aruco_params)

# Game State
score = 0
grid_size = 3
moles = [] # list of {"row": r, "col": c, "spawn_time": t}
hit_effects = [] # list of {"text": text, "x": x, "y": y, "color": color, "expire_time": t, "rect": (x1, y1, x2, y2)}
cooldowns = {} # dict mapping (r, c) -> time when cooldown expires
max_moles = 2
mole_duration = 3.0 # survive duration

game_state = "WAITING" # WAITING, COUNTDOWN, PLAYING, GAME_OVER
game_start_time = 0
countdown_start_time = 0
game_over_start_time = 0
GAME_DURATION = 60.0
COUNTDOWN_DURATION = 5.0

# Motion/Hand detection
bg_sub = cv2.createBackgroundSubtractorMOG2(history=30, varThreshold=50, detectShadows=False)

last_M = None
target_marker_corners = {}

def draw_diglett(warped, center_x, center_y, radius): # Draws a cute Diglett-like character using simple shapes (ai generated design)
    digda_color = (60, 90, 150) # Brown in BGR
    nose_color = (180, 130, 255) # Pinkish
    
    # Body: top half ellipse + solid rectangle for the bottom
    cv2.ellipse(warped, (center_x, center_y), (radius//2 + radius//4, radius), 0, 180, 360, digda_color, -1) 
    cv2.rectangle(warped, (center_x - (radius//2 + radius//4), center_y), 
                          (center_x + (radius//2 + radius//4), center_y + radius), digda_color, -1)
    
    # Big Pink Nose
    cv2.ellipse(warped, (center_x, center_y + radius//6), (max(1, radius//3), max(1, radius//4)), 0, 0, 360, nose_color, -1)
    
    # Small black oval eyes
    cv2.ellipse(warped, (center_x - radius//4, center_y - radius//4), (max(1, radius//12), max(1, radius//6)), 0, 0, 360, (0, 0, 0), -1)
    cv2.ellipse(warped, (center_x + radius//4, center_y - radius//4), (max(1, radius//12), max(1, radius//6)), 0, 0, 360, (0, 0, 0), -1)
    
    # White eye glints
    cv2.circle(warped, (center_x - radius//4, center_y - radius//4 - radius//12), max(1, radius//25), (255, 255, 255), -1)
    cv2.circle(warped, (center_x + radius//4, center_y - radius//4 - radius//12), max(1, radius//25), (255, 255, 255), -1)

def update_game(warped):
    global score, moles, hit_effects, game_state, game_start_time, countdown_start_time, game_over_start_time, cooldowns, last_M, target_marker_corners

    current_time = time.time()
    
    if game_state == "WAITING":
        cv2.putText(warped, "Waiting...", (W//2 - 100, H//2), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 255), 5)
        bg_sub.apply(warped)
        return
        
    elif game_state == "COUNTDOWN": #coundown screen before game starts is ai aided feature
        time_left = COUNTDOWN_DURATION - (current_time - countdown_start_time)
        if time_left <= 0:
            game_state = "PLAYING"
            game_start_time = current_time
            score = 0
            moles = []
            hit_effects = []
            bg_sub.clear() # Reset background fully before playing
        else:
            text = f"Get Ready! {int(time_left) + 1}"
            cv2.putText(warped, text, (W//2 - 170, H//2), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 165, 255), 5)
            # Allow hands to leave the board before bg_sub tracks it for game start
            bg_sub.apply(warped)
            return

    elif game_state == "GAME_OVER": # (game over screen is ai aided feature)
        # Calculate mask BEFORE drawing over it, so the button itself isn't seen as motion
        clean_warped = warped.copy()
        
        cv2.rectangle(warped, (50, H//2 - 100), (W - 50, H//2 + 100), (0, 0, 0), -1)
        cv2.putText(warped, "GAME OVER!", (W//2 - 150, H//2 - 10), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (0, 0, 255), 5)
        cv2.putText(warped, f"Final Score: {score}", (W//2 - 160, H//2 + 60), cv2.FONT_HERSHEY_SIMPLEX, 1.5, (0, 255, 0), 5)
        
        # Play Again Button
        btn_y1, btn_y2 = min(H - 100, H//2 + 120), min(H - 20, H//2 + 200)
        btn_x1, btn_x2 = W//2 - 150, W//2 + 150
        cv2.rectangle(warped, (btn_x1, btn_y1), (btn_x2, btn_y2), (255, 255, 255), 3)
        cv2.putText(warped, "HIT TO REPLAY", (btn_x1 + 15, btn_y1 + 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255, 255, 255), 3)
        
        fg_mask = bg_sub.apply(clean_warped)
        
        # 2 second delay so people can read their score before restarting
        if current_time - game_over_start_time > 2.0:
            roi = fg_mask[btn_y1:btn_y2, btn_x1:btn_x2]
            if roi.size > 0 and cv2.countNonZero(roi) > (btn_x2 - btn_x1) * (btn_y2 - btn_y1) * 0.1:
                game_state = "WAITING"
                last_M = None
                target_marker_corners = {}
                bg_sub.clear()
        
        return

    # Else game_state == "PLAYING"
    time_left = GAME_DURATION - (current_time - game_start_time)
    if time_left <= 0:
        game_state = "GAME_OVER"
        game_over_start_time = current_time
        bg_sub.clear()
        return
        
    # Remove expired moles
    moles = [m for m in moles if current_time - m['spawn_time'] < mole_duration]

    # Spawn new moles dynamically
    if len(moles) < max_moles and random.random() < 0.05:
        r = random.randint(0, grid_size - 1)
        c = random.randint(0, grid_size - 1)
        # Check if cell is occupied or in cooldown
        on_cooldown = (r, c) in cooldowns and current_time < cooldowns[(r, c)]
        if not on_cooldown and not any(m['row'] == r and m['col'] == c for m in moles):
            rand_val = random.random()
            if rand_val < 0.25: # 25% chance
                m_type = 'shit'
            elif rand_val < 0.30: # 5% chance
                m_type = 'dugtrio'
            else: # 60% chance
                m_type = 'diglett'
            moles.append({'row': r, 'col': c, 'spawn_time': current_time, 'type': m_type})

    # Apply background subtraction
    fg_mask = bg_sub.apply(warped)
    
    hit_moles = []
    cell_w = W // grid_size
    cell_h = H // grid_size

    for m in moles:
        r, c = m['row'], m['col']
        # Region of interest for this mole cell
        y1, y2 = r * cell_h, (r + 1) * cell_h
        x1, x2 = c * cell_w, (c + 1) * cell_w
        
        roi = fg_mask[y1:y2, x1:x2]
        
        white_pixels = cv2.countNonZero(roi)
        area = cell_w * cell_h
        
        # 10% threshold for "hit/smash"
        if white_pixels > area * 0.10: 
            hit_moles.append(m)
            # Add cell to cooldown
            cooldowns[(r, c)] = current_time + 1.0
            
            if m['type'] == 'diglett':
                score += 1
                hit_effects.append({
                    "text": "+1 BAM!", "x": x1+10, "y": y1+cell_h//2, 
                    "color": (0, 255, 0), "expire_time": current_time + 1.0, 
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2
                })
            elif m['type'] == 'dugtrio':
                score += 3
                hit_effects.append({
                    "text": "+3 TRIPLE!", "x": x1+10, "y": y1+cell_h//2, 
                    "color": (0, 215, 255), "expire_time": current_time + 1.0, 
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2
                })
            else:
                score -= 1
                hit_effects.append({
                    "text": "YUCK!", "x": x1+10, "y": y1+cell_h//2, 
                    "color": (0, 0, 255), "expire_time": current_time + 1.0, 
                    "x1": x1, "y1": y1, "x2": x2, "y2": y2
                })

    # Remove hit moles
    moles = [m for m in moles if m not in hit_moles]

    # Draw hit effects
    active_effects = []
    for effect in hit_effects:
        if current_time < effect['expire_time']:
            cv2.rectangle(warped, (effect['x1'], effect['y1']), (effect['x2'], effect['y2']), effect['color'], 5)
            cv2.putText(warped, effect['text'], (effect['x'], effect['y']), cv2.FONT_HERSHEY_SIMPLEX, 1.5, effect['color'], 5)
            active_effects.append(effect)
    hit_effects = active_effects

    # Draw grid
    for i in range(1, grid_size):
        cv2.line(warped, (i * cell_w, 0), (i * cell_w, H), (0, 255, 0), 2)
        cv2.line(warped, (0, i * cell_h), (W, i * cell_h), (0, 255, 0), 2)

    # Draw active moles (ai generated digletts and poop)
    for m in moles:
        r, c = m['row'], m['col']
        center_x = c * cell_w + cell_w // 2
        center_y = r * cell_h + cell_h // 2
        radius = min(cell_w, cell_h) // 3
        
        if m['type'] == 'diglett':
            draw_diglett(warped, center_x, center_y, radius)
        elif m['type'] == 'dugtrio':
            # Dugtrio = 3 smaller Digletts combined
            small_r = int(radius * 0.7)
            # back left
            draw_diglett(warped, center_x - radius//2, center_y - radius//4, small_r)
            # back right
            draw_diglett(warped, center_x + radius//2, center_y - radius//4, int(small_r * 0.9))
            # front center
            draw_diglett(warped, center_x, center_y + radius//4, int(radius * 0.8))
        else:
            # Poop look (brown triangle-ish or circles)
            cv2.circle(warped, (center_x, center_y + radius//3), radius, (19, 69, 139), -1) # Base
            cv2.circle(warped, (center_x, center_y - radius//4), int(radius * 0.7), (19, 69, 139), -1) # Middle
            cv2.circle(warped, (center_x, center_y - int(radius * 0.7)), int(radius * 0.4), (19, 69, 139), -1) # Top

    # Draw Score and Timer
    cv2.putText(warped, f"Score: {score}", (10, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (255, 0, 0), 3)
    cv2.putText(warped, f"Time: {int(time_left)}s", (W - 200, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.2, (0, 0, 255), 3)


@window.event
def on_draw():
    window.clear()
    ret, frame = cap.read()
    if not ret:
        return

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    corners, ids, rejected = detector.detectMarkers(gray)
    
    display_img = frame.copy()
    
    global last_M, target_marker_corners, game_state, countdown_start_time

    # 1) Initial Calibration - Requires 4 UNIQUE markers seen at the exact same moment
    if ids is not None and len(ids) >= 4 and len(target_marker_corners) < 4:
        # Filter largest 4 markers to avoid tiny false positives
        marker_areas = [cv2.contourArea(c[0]) for c in corners]
        best_4_idx = np.argsort(marker_areas)[-4:]
        
        # FIX 1: Ensure the 4 chosen markers actually have unique IDs
        calib_ids = [int(ids[i][0]) for i in best_4_idx]
        if len(set(calib_ids)) == 4:
            pts = []
            for i in best_4_idx:
                center = corners[i][0].mean(axis=0)
                pts.append(center)
                
            pts = np.array(pts, dtype="float32")
            
            # Verify distance between points to discard crammed false clusters
            dist_matrix = np.linalg.norm(pts[:, None, :] - pts[None, :, :], axis=-1)
            np.fill_diagonal(dist_matrix, np.inf)
            
            if np.min(dist_matrix) > 100.0:
                rect = order_points(pts)
                
                # Rotate 180 degrees mapping
                dst = np.array([
                    [W - 1, H - 1],
                    [0, H - 1],
                    [0, 0],
                    [W - 1, 0]], dtype="float32")
        
                M = cv2.getPerspectiveTransform(rect, dst)
                
                # FIX 2: Reset the dictionary completely to prevent multi-frame pollution
                target_marker_corners = {}
                
                for i in best_4_idx:
                    marker_id = int(ids[i][0])
                    c_reshaped = np.array([corners[i][0]], dtype="float32")
                    c_target = cv2.perspectiveTransform(c_reshaped, M)[0]
                    target_marker_corners[marker_id] = c_target
                    
                last_M = M / M[2, 2]
                
                if game_state == "WAITING":
                    game_state = "COUNTDOWN"
                    countdown_start_time = time.time()

    # 2) Live Tracking Update - Only update if we have a stable configuration
    elif ids is not None and len(target_marker_corners) == 4:
        src_pts = []
        dst_pts = []
        for i in range(len(ids)):
            marker_id = int(ids[i][0])
            if marker_id in target_marker_corners:
                for j in range(4):
                    src_pts.append(corners[i][0][j])
                    dst_pts.append(target_marker_corners[marker_id][j])
                    
        # FIX 3: Require at least 3 visible markers (12 points) to recalculate Homography.
        # This keeps the matrix incredibly stable even if hands block 1 marker.
        if len(src_pts) >= 12:
            src_pts = np.array(src_pts, dtype="float32")
            dst_pts = np.array(dst_pts, dtype="float32")
            M, _ = cv2.findHomography(src_pts, dst_pts)
            if M is not None:
                M = M / M[2, 2] 
                alpha = 0.15 
                if last_M is not None:
                    last_M = last_M / last_M[2, 2] 
                    last_M = (M * alpha) + (last_M * (1.0 - alpha))
                else:
                    last_M = M

    # 3) Render Frame
    if last_M is not None:
        warped = cv2.warpPerspective(frame, last_M, (W, H))
        update_game(warped)
        display_img = warped
    else:
        bg_sub.clear()
        cv2.putText(display_img, f"Show exactly 4 markers to start! Detected: {len(ids) if ids is not None else 0}", 
                    (20, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        if ids is not None:
             aruco.drawDetectedMarkers(display_img, corners)
             
    # Render via pyglet
    img = cv2glet(display_img, 'BGR')
    img.blit(0, 0, 0)

def update(dt):
    # Needed to keep drawing at 30 fps
    pass

if __name__ == "__main__":
    pyglet.clock.schedule_interval(update, 1/30.0)
    pyglet.app.run()
    cap.release()
