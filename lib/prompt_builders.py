"""
Hàm xây dựng Prompt tạo hình ảnh thống nhất

Tất cả mẫu Prompt tập trung ở đây để quản lý tập tin, đảm bảo WebUI và Skill sử dụng cùng một logic.

Trách nhiệm của mô-đun:
- Ảnh thiết kế nhân vật Prompt Xây dựng
- Ảnh thiết kế manh mối Prompt Xây dựng (Loại Đạo cụ/Loại Môi trường)
- Ảnh phân cảnh Prompt Hậu tố

Người sử dụng:
- webui/server/routers/generate.py
- .claude/skills/generate-characters/scripts/generate_character.py
- .claude/skills/generate-clues/scripts/generate_clue.py
"""


def build_character_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    Xây dựng Prompt Ảnh thiết kế nhân vật

    Tuân theo thực tiễn tốt nhất của nano-banana: sử dụng đoạn văn tường thuật Mô tả, thay vì danh sách từ khóa.

    Args:
        name: Tên nhân vật
        description: Nhân vậtMô tả ngoại hình (nên là đoạn văn tường thuật)
        style: Phong cách dự án
        style_description: AI Phân tích Mô tả phong cách

    Returns:
        Chuỗi Prompt đầy đủ
    """
    style_part = f"，{style}" if style else ""

    # Xây dựng Tiền tố phong cách
    style_prefix = ""
    if style_description:
        style_prefix = f"Visual style: {style_description}\n\n"

    return f"""{style_prefix}Nhân vậtThiết kế Ảnh tham chiếu{style_part}。

「{name}」Bản vẽ toàn thân.

{description}

Yêu cầu bố cục: Hình toàn thân của một Nhân vật duy nhất, tư thế tự nhiên, hướng về Góc máy.
Nền: Xám nhạt tinh khiết, không có bất kỳ yếu tố trang trí nào.
Ánh sáng：Ánh sáng trong phòng chụp nhẹ nhàng và đều, không có bóng đổ mạnh.
Chất lượng hình ảnh: Độ nét cao, chi tiết rõ ràng, màu sắc chính xác."""


def build_clue_prompt(
    name: str, description: str, clue_type: str = "prop", style: str = "", style_description: str = ""
) -> str:
    """
    Xây dựng Prompt manh mối thiết kế Ảnh

    Chọn mẫu tương ứng theo Loại Manh mối.

    Args:
        name: Tên manh mối
        description: Manh mốiMô tả
        clue_type: Manh mốiLoại ("prop" Đạo cụ hoặc "location" Môi trường)
        style: Phong cách dự án
        style_description: AI Phân tích Mô tả phong cách

    Returns:
        Chuỗi Prompt đầy đủ
    """
    if clue_type == "location":
        return build_location_prompt(name, description, style, style_description)
    else:
        return build_prop_prompt(name, description, style, style_description)


def build_prop_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    Xây dựng Prompt manh mối loại Đạo cụ

    Sử dụng bố cục ba góc nhìn: Toàn cảnh chính diện, góc nghiêng 45 độ, cận cảnh chi tiết.

    Args:
        name: Đạo cụTên
        description: Đạo cụMô tả
        style: Phong cách dự án
        style_description: AI Phân tích Mô tả phong cách

    Returns:
        Chuỗi Prompt đầy đủ
    """
    style_suffix = f"，{style}" if style else ""

    # Xây dựng Tiền tố phong cách
    style_prefix = ""
    if style_description:
        style_prefix = f"Visual style: {style_description}\n\n"

    return f"""{style_prefix}Một Ảnh tham chiếu thiết kế Đạo cụ chuyên nghiệp{style_suffix}。

Đạo cụ「{name}」Trình diễn đa góc độ.{description}

Ba góc nhìn được sắp xếp theo chiều ngang trên nền xám nhạt tinh khiết: bên trái là toàn cảnh chính diện, giữa là góc nghiêng 45 độ thể hiện cảm giác ba chiều, bên phải là cận cảnh chi tiết quan trọng. Ánh sáng studio mềm mại và đều, chất lượng hình ảnh HD, màu sắc chính xác."""


def build_location_prompt(name: str, description: str, style: str = "", style_description: str = "") -> str:
    """
    Xây dựng Prompt loại Môi trường gợi ý

    Sử dụng bố cục 3/4 cho hình chính + cận cảnh chi tiết ở góc dưới bên phải.

    Args:
        name: CảnhTên
        description: CảnhMô tả
        style: Phong cách dự án
        style_description: AI Phân tích Mô tả phong cách

    Returns:
        Chuỗi Prompt đầy đủ
    """
    style_suffix = f"，{style}" if style else ""

    # Xây dựng Tiền tố phong cách
    style_prefix = ""
    if style_description:
        style_prefix = f"Visual style: {style_description}\n\n"

    return f"""{style_prefix}Một thiết kế Cảnh chuyên nghiệp làm hình tham chiếu{style_suffix}。

Cảnh biểu tượng{name}」làm tham chiếu hình ảnh.{description}

Hình chính chiếm ba phần tư khu vực hiển thị toàn bộ Môi trường và Không khí, hình nhỏ góc dưới bên phải là cận cảnh chi tiết. Ánh sáng mềm mại và tự nhiên."""


def build_storyboard_suffix(content_mode: str = "narration") -> str:
    """
    Lấy hậu tố Prompt hình phân cảnh

    Trả về hậu tố bố cục tương ứng theo chế độ nội dung.

    Args:
        content_mode: chế độ nội dung ("narration" Chế độ kể chuyện hoặc "drama" Tập phimchế độ)

    Returns:
        Chuỗi hậu tố bố cục
    """
    if content_mode == "narration":
        return "Bố cục dọc."
    else:
        return ""


def build_style_prompt(project_data: dict) -> str:
    """
    Xây dựng Đoạn Prompt mô tả phong cách

    Kết hợp style (do người dùng điền thủ công) và style_description (do AI phân tích tạo ra).

    Args:
        project_data: project.json Dữ liệu

    Returns:
        Mô tả phong cáchchuỗi，Dùng để ghép vào Prompt tạo ra
    """
    parts = []

    # Nhãn phong cách cơ bản
    style = project_data.get("style", "")
    if style:
        parts.append(f"Style: {style}")

    # AI Phân tích Mô tả phong cách
    style_description = project_data.get("style_description", "")
    if style_description:
        parts.append(f"Visual style: {style_description}")

    return "\n".join(parts)
