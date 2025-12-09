# import cv2
# import numpy as np

# ==============================
# ORIGINAL — Whisper (with OpenCV)
# ==============================
#
# def detect_face_position(video_path: str, sample_frames=10):
#     """
#     Detect face position in video to determine best caption placement.
#     
#     Returns SSA alignment value:
#     - 2: Bottom center (face in top/middle)
#     - 8: Top center (face in bottom)
#     - 5: Middle center (no face detected or centered face)
#     """
#     cap = cv2.VideoCapture(video_path)
#     
#     if not cap.isOpened():
#         print(f"Warning: Could not open video {video_path}, defaulting to bottom")
#         return 2  # Default to bottom
#     
#     total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
#     frame_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
#     
#     if total_frames == 0 or frame_height == 0:
#         cap.release()
#         return 2
#     
#     # Load face detection cascade
#     face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
#     
#     face_positions = []
#     
#     frame_indices = np.linspace(0, total_frames - 1, min(sample_frames, total_frames), dtype=int)
#     
#     for frame_idx in frame_indices:
#         cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
#         ret, frame = cap.read()
#         
#         if not ret:
#             continue
#         
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         
#         faces = face_cascade.detectMultiScale(
#             gray,
#             scaleFactor=1.1,
#             minNeighbors=5,
#             minSize=(30, 30)
#         )
#         
#         for (x, y, w, h) in faces:
#             face_center_y = y + h / 2
#             normalized_position = face_center_y / frame_height
#             face_positions.append(normalized_position)
#     
#     cap.release()
#     
#     if not face_positions:
#         return 2
#     
#     avg_position = np.mean(face_positions)
#     
#     if avg_position < 0.33:
#         return 2  # Face top third → captions bottom
#     elif avg_position > 0.67:
#         return 8  # Face bottom third → captions top
#     else:
#         return 2  # Face middle → bottom preferred


# ==============================
# OPENAI DEPLOYMENT — Lightweight fallback
# ==============================

def detect_face_position(video_path: str, sample_frames=10):
    """
    Lightweight version (OpenAI deployment).
    Skips face detection entirely — always bottom-center captions.
    """
    print(f"[INFO] Skipping face detection for {video_path} (OpenAI mode)")
    return 2  # bottom center


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
