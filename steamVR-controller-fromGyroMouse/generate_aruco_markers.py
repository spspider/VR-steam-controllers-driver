#!/usr/bin/env python3
"""
Generate ArUco markers for left and right hand controllers
"""

import cv2
import numpy as np

def generate_aruco_marker(marker_id, size=200, filename=None):
    """Generate and save ArUco marker"""
    # Use 4x4 dictionary with 50 markers
    aruco_dict = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    
    # Generate marker image
    marker_img = cv2.aruco.generateImageMarker(aruco_dict, marker_id, size)
    
    # Save to file
    if filename is None:
        filename = f"aruco_marker_{marker_id}.png"
    
    cv2.imwrite(filename, marker_img)
    print(f"Generated ArUco marker ID {marker_id} -> {filename}")
    
    return marker_img

def main():
    print("Generating ArUco markers for VR controllers...")
    print()
    
    # Generate markers
    left_marker = generate_aruco_marker(0, 200, "aruco_left_hand.png")
    right_marker = generate_aruco_marker(1, 200, "aruco_right_hand.png")
    
    # Create combined image for printing
    combined = np.hstack([left_marker, right_marker])
    
    # Add labels
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(combined, "LEFT HAND (ID=0)", (10, 30), font, 0.7, (0, 0, 0), 2)
    cv2.putText(combined, "RIGHT HAND (ID=1)", (210, 30), font, 0.7, (0, 0, 0), 2)
    
    cv2.imwrite("aruco_both_hands.png", combined)
    print("Generated combined image -> aruco_both_hands.png")
    print()
    print("Instructions:")
    print("1. Print aruco_both_hands.png")
    print("2. Cut out the markers")
    print("3. Attach LEFT marker (ID=0) to your gyro mouse")
    print("4. Attach RIGHT marker (ID=1) to second controller (if needed)")
    print("5. Each marker should be about 5cm x 5cm for best tracking")
    
    # Show preview
    cv2.imshow("ArUco Markers", combined)
    cv2.waitKey(0)
    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()