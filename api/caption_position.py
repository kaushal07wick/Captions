import cv2
import numpy as np

# detect face position via opencv
def detect_face_position(video_path: str, sample_frames=10):
    """
    Detect face position in video to determine best caption placement.
    
    Returns SSA alignment value:
    - 2: Bottom center (face in top/middle)
    - 8: Top center (face in bottom)
    - 5: Middle center (no face detected or centered face)
    
    Args:
        video_path: Path to video file
        sample_frames: Number of frames to sample for detection
    """
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"Warning: Could not open video {video_path}, defaulting to bottom")
        return 2  # Default to bottom
    
    # Get video properties
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    
    if total_frames == 0 or frame_height == 0:
        cap.release()
        return 2
    
    # Load face detection cascade
    face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
    
    face_positions = []
    
    # Sample frames evenly throughout video
    frame_indices = np.linspace(0, total_frames - 1, min(sample_frames, total_frames), dtype=int)
    
    for frame_idx in frame_indices:
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        
        if not ret:
            continue
        
        # Convert to grayscale for face detection
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Detect faces
        faces = face_cascade.detectMultiScale(
            gray,
            scaleFactor=1.1,
            minNeighbors=5,
            minSize=(30, 30)
        )
        
        # Record vertical center of each face
        for (x, y, w, h) in faces:
            face_center_y = y + h / 2
            normalized_position = face_center_y / frame_height
            face_positions.append(normalized_position)
    
    cap.release()
    
    # Determine alignment based on average face position
    if not face_positions:
        # No faces detected - default to bottom captions
        return 2
    
    avg_position = np.mean(face_positions)
    
    # Position logic:
    # 0.0 = top of frame
    # 1.0 = bottom of frame
    
    if avg_position < 0.33:
        # Face in top third -> captions at bottom
        return 2  # Bottom center
    elif avg_position > 0.67:
        # Face in bottom third -> captions at top
        return 8  # Top center
    else:
        # Face in middle -> try bottom with larger margin
        # (bottom is generally safer than middle)
        return 2  # Bottom center
    
    
def get_alignment_name(alignment: int) -> str:
    """Get human-readable alignment name."""
    alignment_map = {
        1: "Bottom Left",
        2: "Bottom Center",
        3: "Bottom Right",
        4: "Middle Left",
        5: "Middle Center",
        6: "Middle Right",
        7: "Top Left",
        8: "Top Center",
        9: "Top Right"
    }
    return alignment_map.get(alignment, "Bottom Center")