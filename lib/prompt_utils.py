"""
Prompt Công cụHàm

Cung cấp chức năng chuyển đổi Prompt có cấu trúc sang định dạng YAML.
"""

import yaml

# Định nghĩa tùy chọn mặc định
STYLES = ["Photographic", "Anime", "3D Animation"]

SHOT_TYPES = [
    "Extreme Close-up",
    "Close-up",
    "Medium Close-up",
    "Medium Shot",
    "Medium Long Shot",
    "Long Shot",
    "Extreme Long Shot",
    "Over-the-shoulder",
    "Point-of-view",
]

CAMERA_MOTIONS = [
    "Static",
    "Pan Left",
    "Pan Right",
    "Tilt Up",
    "Tilt Down",
    "Zoom In",
    "Zoom Out",
    "Tracking Shot",
]


def image_prompt_to_yaml(image_prompt: dict, project_style: str) -> str:
    """
    Chuyển đổi cấu trúc imagePrompt sang chuỗi định dạng YAML

    Args:
        image_prompt: segment trong đối tượng image_prompt, cấu trúc như sau:
            {
                "scene": "CảnhMô tả",
                "composition": {
                    "shot_type": "Góc máyLoại",
                    "lighting": "Ánh sángMô tả",
                    "ambiance": "Không khíMô tả"
                }
            }
        project_style: Dự ánCấp Phong cách Cài đặt (đọc từ project.json)

    Returns:
        YAML định dạngchuỗi，Dùng để gọi API Gemini
    """
    ordered = {
        "Style": project_style,
        "Scene": image_prompt["scene"],
        "Composition": {
            "shot_type": image_prompt["composition"]["shot_type"],
            "lighting": image_prompt["composition"]["lighting"],
            "ambiance": image_prompt["composition"]["ambiance"],
        },
    }
    return yaml.dump(ordered, allow_unicode=True, default_flow_style=False, sort_keys=False)


def video_prompt_to_yaml(video_prompt: dict) -> str:
    """
    Chuyển đổi cấu trúc videoPrompt sang chuỗi định dạng YAML

    Args:
        video_prompt: segment trong đối tượng video_prompt, cấu trúc như sau:
            {
                "action": "Hành động Mô tả",
                "camera_motion": "Chuyển động máy quay",
                "ambiance_audio": "Âm thanh môi trườngMô tả",
                "dialogue": [{"speaker": "Tên nhân vật", "line": "Thoại"}]
            }

    Returns:
        YAML định dạngchuỗi，Dùng để gọi API Veo
    """
    dialogue = [{"Speaker": d["speaker"], "Line": d["line"]} for d in video_prompt.get("dialogue", [])]

    ordered = {
        "Action": video_prompt["action"],
        "Camera_Motion": video_prompt["camera_motion"],
        "Ambiance_Audio": video_prompt.get("ambiance_audio", ""),
    }

    # Chỉ thêm Dialogue từ đoạn khi có Đối thoại
    if dialogue:
        ordered["Dialogue"] = dialogue

    return yaml.dump(ordered, allow_unicode=True, default_flow_style=False, sort_keys=False)


def is_structured_image_prompt(image_prompt) -> bool:
    """
    Kiểm tra image_prompt có phải là định dạng cấu trúc hay không

    Args:
        image_prompt: image_prompt từGiá trị đoạn

    Returns:
        True Nếu là định dạng cấu trúc (dict), False nếu là định dạng chuỗi cũ
    """
    return isinstance(image_prompt, dict) and "scene" in image_prompt


def is_structured_video_prompt(video_prompt) -> bool:
    """
    Kiểm tra video_prompt có phải là định dạng cấu trúc không

    Args:
        video_prompt: video_prompt từGiá trị đoạn

    Returns:
        True Nếu là định dạng cấu trúc (dict), False nếu là định dạng chuỗi cũ
    """
    return isinstance(video_prompt, dict) and "action" in video_prompt


def validate_style(style: str) -> bool:
    """Xác thực Phong cách có phải là tùy chọn mặc định"""
    return style in STYLES


def validate_shot_type(shot_type: str) -> bool:
    """Xác thực Loại Góc máy có phải là tùy chọn mặc định"""
    return shot_type in SHOT_TYPES


def validate_camera_motion(camera_motion: str) -> bool:
    """Xác thực chuyển động máy quay có phải là tùy chọn mặc định"""
    return camera_motion in CAMERA_MOTIONS
