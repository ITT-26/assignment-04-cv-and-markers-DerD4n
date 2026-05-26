import os
# Suppress Qt and OpenCV warnings (ai feature)
os.environ['QT_LOGGING_RULES'] = '*=false'
os.environ['OPENCV_LOG_LEVEL'] = 'ERROR'

import cv2
import numpy as np
import argparse
import sys

# Global variables
points = []
original_img = None
display_img = None

def mouse_callback(event, x, y, flags, param):
    global points, display_img
    if event == cv2.EVENT_LBUTTONDOWN:
        if len(points) < 4:
            points.append((x, y))
            # Draw a circle on the clicked point
            cv2.circle(display_img, (x, y), 5, (0, 255, 0), -1)
            cv2.imshow("Image", display_img)

def order_points(pts): # ai feature to ensure correct ordering of points for perspective transformation
    """Order points to avoid crossing lines and find the correct orientation."""
    # Find the center of mass (centroid) of the 4 points
    cx, cy = np.mean(pts, axis=0)
    
    # Sort points by their angle around the center to ensure a clockwise order
    # (This naturally prevents crossing lines)
    angles = np.arctan2(pts[:, 1] - cy, pts[:, 0] - cx)
    pts_sorted = pts[np.argsort(angles)]
    
    # Now we have a clockwise polygon. We just need to figure out which point is "Top-Left".
    # We can detect the "top-left-most" point by finding the one with the smallest sum of x and y.
    # By giving a slight multiplier to 'y', we prioritize finding the actual "top" point 
    scores = pts_sorted[:, 0] + (pts_sorted[:, 1] * 1.5)
    tl_index = np.argmin(scores)
    
    # Shift the points so the "Top-Left" is at the start (index 0)
    rect = np.roll(pts_sorted, -tl_index, axis=0)
    
    return np.array(rect, dtype="float32")
      


def auto_detect_corners(image):
    """Finds document corners using Canny edge detection on a scaled-down image."""
    # Scale down for consistent thresholding regardless of original image size
    resize_height = 500.0
    ratio = image.shape[0] / resize_height
    
    width = int(image.shape[1] * (resize_height / image.shape[0]))
    resized = cv2.resize(image, (width, int(resize_height)))
    
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(blurred, 75, 200)
    
    # Find contours
    contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Sort contours by size and keep the 5 largest to save processing time
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:5]
    
    image_area = resized.shape[0] * resized.shape[1]
    
    for c in contours:
        area = cv2.contourArea(c)
        
        # Ignore tiny contours
        if area < image_area * 0.05:
            continue
            
        peri = cv2.arcLength(c, True)
        
        # 0.02 is the optimal constant for document corner approximation
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        
        # Require exactly 4 corners and a convex shape
        if len(approx) == 4 and cv2.isContourConvex(approx):
            # Document found! Reshape and map the points back to original image scale
            pts = approx.reshape(4, 2) * ratio
            return order_points(pts)
            
    return None

def main():
    global points, original_img, display_img
    
    parser = argparse.ArgumentParser(description="Extract an area from an image and warp it to a rectangle.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input image file")
    parser.add_argument("-o", "--output", required=True, help="Path to the output image file")
    parser.add_argument("-W", "--width", type=int, required=True, help="Resolution width of the result")
    parser.add_argument("-H", "--height", type=int, required=True, help="Resolution height of the result")
    
    args = parser.parse_args()

    original_img = cv2.imread(args.input)
    if original_img is None:
        print(f"Error: Could not load image from {args.input}")
        sys.exit(1)

    display_img = original_img.copy()
    
    # Create a resizable window
    cv2.namedWindow("Image", cv2.WINDOW_NORMAL)
    
    # Scale down the window if the image is too large for a typical screen
    h, w = original_img.shape[:2]
    max_h, max_w = 800, 1200
    if h > max_h or w > max_w:
        scale = min(max_w / w, max_h / h)
        cv2.resizeWindow("Image", int(w * scale), int(h * scale))

    cv2.setMouseCallback("Image", mouse_callback)
    cv2.imshow("Image", display_img)

    warped_img = None
    show_result = False

    print("Click 4 points on the image.")
    print("Press 'a' to automatically detect points (corners of the largest shape).")
    print("Press ESC to discard changes and start over.")
    print("Press 's' or 'S' in the result window to save the extracted image.")
    print("Press 'q' to quit the application.")

    while True:
        # Check if 4 points are selected and we haven't shown the result yet
        if len(points) == 4 and not show_result:
            # Apply perspective transformation
            # Order the points: tl, tr, br, bl (ai feature to ensure correct ordering)
            pts = np.array(points, dtype="float32")
            pts1 = order_points(pts)
            
            # Destination points based on resolution
            pts2 = np.float32([
                [0, 0], 
                [args.width - 1, 0], 
                [args.width - 1, args.height - 1], 
                [0, args.height - 1]
            ])
            
            matrix = cv2.getPerspectiveTransform(pts1, pts2)
            warped_img = cv2.warpPerspective(original_img, matrix, (args.width, args.height))
            
            cv2.imshow("Result", warped_img)
            show_result = True

        key = cv2.waitKey(10) & 0xFF
        
        # ESC key
        if key == 27:
            points = []
            display_img = original_img.copy()
            show_result = False
            cv2.imshow("Image", display_img)
            try:
                cv2.destroyWindow("Result")
            except cv2.error:
                pass
            print("Points cleared. Start over.")
            
        # 'a' or 'A' key for automatic corner detection (partialy ai generated feature)
        elif key == ord('a') or key == ord('A'):
        
            print("Trying to automatically detect corners...")

            detected_corners = auto_detect_corners(original_img)

            if detected_corners is not None:
                # Update global list with integer tuples for drawing
                points = [tuple(pt.astype(int)) for pt in detected_corners]

                # Draw result
                display_img = original_img.copy()

                for pt in points:
                    cv2.circle(display_img, pt, 7, (0, 0, 255), -1)

                cv2.polylines(
                    display_img,
                    [np.array(points)],
                    True,
                    (0, 255, 0),
                    3
                )

                cv2.imshow("Image", display_img)
                print("Successfully detected 4 corners!")

            else:
                print("Could not automatically detect 4 corners.")
                print("Please select them manually.")          

        # 's' or 'S' key
        elif key == ord('s') or key == ord('S'):
            if show_result and warped_img is not None:
                try:
                    success = cv2.imwrite(args.output, warped_img)
                    if success:
                        print(f"Image successfully saved to {args.output}")
                        break
                    else:
                        print(f"Failed to save image. Make sure the output path is a file with a valid extension (e.g., .jpg, .png).")
                except cv2.error as e:
                    print(f"OpenCV Error: {e}")
                    print("Make sure your output path includes a valid file extension (e.g. '.jpg' or '.png') and not just a directory.")
            else:
                print("Please select 4 points first before saving.")
                
        # 'q' key to quit
        elif key == ord('q'):
            break

    cv2.destroyAllWindows()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt: # Ai feature to handle Ctrl+C gracefully
        print("\nApplication interrupted by user. Exiting...")
        sys.exit(0)
        