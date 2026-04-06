"""
prompt_builders_script.py - Kịch bảnTrình tạo Prompt

1. XML Phân tách bối cảnh nhãn
2. Mô tả đoạn văn rõ ràng và giới hạn khoảng cách
3. Danh sách giá trị tùy chọn đầu ra
"""


def _format_character_names(characters: dict) -> str:
    """định dạngDanh sách nhân vật hóa"""
    lines = []
    for name in characters.keys():
        lines.append(f"- {name}")
    return "\n".join(lines)


def _format_clue_names(clues: dict) -> str:
    """định dạngDanh sách manh mối hóa"""
    lines = []
    for name in clues.keys():
        lines.append(f"- {name}")
    return "\n".join(lines)


def build_narration_prompt(
    project_overview: dict,
    style: str,
    style_description: str,
    characters: dict,
    clues: dict,
    segments_md: str,
) -> str:
    """
    Xây dựng Prompt theo chế độ kể chuyện

    Args:
        project_overview: Mô tả dự án（synopsis, genre, theme, world_setting）
        style: Visual Phong cách标签
        style_description: Mô tả phong cách
        characters: Nhân vậttừĐiển hình (chỉ dùng để lấy tên danh sách)
        clues: Manh mốitừĐiển hình (chỉ dùng để lấy tên danh sách)
        segments_md: Step 1 Nội dung Markdown

    Returns:
        Prompt đã xây dựng
    """
    character_names = list(characters.keys())
    clue_names = list(clues.keys())

    prompt = f"""BạnNhiệm vụ là tạo các cảnh kịch bản cho video ngắn. Vui lòng làm theo các hướng dẫn sau một cách cẩn thận:

**Quan trọng：Tất cả nội dung đầu ra phải sử dụng ngôn ngữ đang dùng. Chỉ các tên khóa JSON và giá trị liệt kê sử dụng tiếng Anh.**

1. BạnSẽ nhận được tổng quan câu chuyện, phong cách hình ảnh, danh sách nhân vật, danh sách manh mối, cũng như các đoạn văn thuộc tiểu thuyết đã được tách.

2. Để tạo cho mỗi đoạn:
   - image_prompt：Không.Prompt tạo hình ảnh cho một khung hình (Mô tả bằng tiếng Trung)
   - video_prompt：Prompt tạo video hành động và âm thanh (Mô tả bằng tiếng Trung)

<overview>
{project_overview.get("synopsis", "")}

Thể loạiLoại：{project_overview.get("genre", "")}
Chủ đề chính:{project_overview.get("theme", "")}
Thế giới quanCài đặt:{project_overview.get("world_setting", "")}
</overview>

<style>
Phong cách：{style}
Mô tả：{style_description}
</style>

<characters>
{_format_character_names(characters)}
</characters>

<clues>
{_format_clue_names(clues)}
</clues>

<segments>
{segments_md}
</segments>

segments Bảng phân tách đoạn, mỗi dòng là một đoạn, bao gồm:
- Đoạn ID：định dạngCho E{{集数}}S{{Số thứ tự}}
- Văn bản gốc tiểu thuyết: phải giữ nguyên như novel_text từ đoạn
- Thời lượng: 4, 6 hoặc 8 giây
- Có đối thoại hay không: dùng để xác định có cần điền video_prompt.dialogue hay không
- Có phải là segment_break không: Điểm chuyển cảnh, cần cài đặt segment_break là true

3. Khi tạo cho mỗi đoạn, tuân theo các quy tắc sau:

a. **novel_text**：Sao chép nguyên văn văn bản gốc tiểu thuyết, không chỉnh sửa bất kỳ điều gì.

b. **characters_in_segment**：Liệt kê tên các nhân vật xuất hiện trong đoạn này.
   - Giá trị tùy chọn: [{", ".join(character_names)}]
   - Chỉ bao gồm các Nhân vật được đề cập rõ ràng hoặc ám chỉ rõ ràng

c. **clues_in_segment**：Liệt kê tên manh mối có liên quan trong Đoạn này.
   - Giá trị tùy chọn: [{", ".join(clue_names)}]
   - Chỉ bao gồm Manh mối được đề cập rõ ràng hoặc ám chỉ rõ ràng

d. **image_prompt**：Tạo đối tượng bao gồm các đoạn từ sau:
   - scene：Dùng tiếng Trung mô tả cụ thể cảnh trong khoảnh khắc này — vị trí Nhân vật, tư thế, biểu cảm, chi tiết trang phục, và các yếu tố Môi trường cũng như vật phẩm có thể thấy.
     Tập trung vào hình ảnh có thể thấy ngay tại khoảnh khắc hiện tại. Chỉ mô tả các yếu tố thị giác cụ thể mà máy quay có thể ghi lại.
     Đảm bảo mô tả tránh các yếu tố nằm ngoài cảnh này. Loại bỏ ẩn dụ, ẩn ý, từ ngữ cảm xúc trừu tượng, đánh giá chủ quan, nhiều cảnh chuyển đổi mà không thể hiển thị trực tiếp.
     Hình ảnh nên tự chứa, không ám chỉ sự kiện trong quá khứ hoặc phát triển tương lai.
   - composition：
     - shot_type：Góc máyLoại（Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Long Shot, Long Shot, Extreme Long Shot, Over-the-shoulder, Point-of-view）
     - lighting：Dùng tiếng Trung mô tả loại nguồn sáng, hướng và nhiệt màu cụ thể (ví dụ"Ánh sáng vàng ấm buổi sáng chiếu qua cửa sổ bên trái"）
     - ambiance：Dùng tiếng Trung mô tả hiệu ứng môi trường có thể thấy (ví dụ"Sương mỏng bao phủ"、"Bụi bay lơ lửng"），Tránh từ ngữ cảm xúc trừu tượng

e. **video_prompt**：Tạo đối tượng bao gồm các đoạn từ sau:
   - action：Dùng tiếng Trung mô tả chính xác các hành động cụ thể của chủ thể trong khoảng thời gian này — di chuyển cơ thể, thay đổi cử chỉ, chuyển đổi biểu cảm.
     Tập trung vào một hành động liền mạch duy nhất, đảm bảo có thể hoàn thành trong thời gian quy định (4/6/8 giây).
     Loại trừ việc chuyển cảnh nhiều, cắt cảnh nhanh, hiệu ứng montaje và các hiệu ứng không thể thực hiện trong một lần sinh tạo.
     Loại trừ mô tả hành động ẩn dụ (ví dụ"như đang bay lượn như bướm"）。
   - camera_motion：Chuyển động máy quay（Static, Pan Left, Pan Right, Tilt Up, Tilt Down, Zoom In, Zoom Out, Tracking Shot）
     Mỗi đoạn chỉ chọn một kiểu chuyển động của máy quay.
   - ambiance_audio：Dùng tiếng Trung mô tả âm thanh trong cảnh (diegetic sound) — âm thanh môi trường, tiếng bước chân, âm thanh vật thể.
     Chỉ mô tả âm thanh thực sự tồn tại trong cảnh. Loại trừ nhạc nền, BGM, lồng tiếng, âm thanh ngoài cảnh.
   - dialogue：{{speaker, line}} Dạng mảng. Chỉ điền khi văn bản gốc có dấu ngoặc kép đối thoại. speaker phải đến từ characters_in_segment.

f. **segment_break**：Nếu trong bảng đoạn được đánh dấu là"是"，thì đặt là true.

g. **duration_seconds**：Sử dụng thời lượng trong bảng đoạn (4, 6 hoặc 8).

h. **transition_to_next**：默认为 "cut"。

Mục tiêu: Tạo phân cảnh Prompt sinh động, nhất quán về mặt hình ảnh, dùng để hướng dẫn AI tạo hình ảnh và video. Giữ sáng tạo, cụ thể, và trung thành với văn bản gốc.
"""
    return prompt


def build_drama_prompt(
    project_overview: dict,
    style: str,
    style_description: str,
    characters: dict,
    clues: dict,
    scenes_md: str,
) -> str:
    """
    Xây dựng Prompt chế độ hoạt hình phim.

    Args:
        project_overview: Mô tả dự án
        style: Visual Phong cách标签
        style_description: Mô tả phong cách
        characters: Nhân vậttừĐiển
        clues: Manh mốitừĐiển
        scenes_md: Step 1 Nội dung Markdown

    Returns:
        Prompt đã xây dựng
    """
    character_names = list(characters.keys())
    clue_names = list(clues.keys())

    prompt = f"""BạnNhiệm vụ là tạo phân cảnh kịch bản cho tập phim hoạt hình. Vui lòng làm theo chỉ dẫn sau một cách cẩn thận.

**Quan trọng：Tất cả nội dung đầu ra phải sử dụng ngôn ngữ đang dùng. Chỉ các tên khóa JSON và giá trị liệt kê sử dụng tiếng Anh.**

1. BạnSẽ nhận được tổng quan câu chuyện, phong cách hình ảnh, danh sách nhân vật, danh sách manh mối, cũng như danh sách cảnh đã được phân tách.。

2. Tạo cho mỗi cảnh:
   - image_prompt：Không.Prompt tạo hình ảnh cho một khung hình (Mô tả bằng tiếng Trung)
   - video_prompt：Prompt tạo video hành động và âm thanh (Mô tả bằng tiếng Trung)

<overview>
{project_overview.get("synopsis", "")}

Thể loạiLoại：{project_overview.get("genre", "")}
Chủ đề chính:{project_overview.get("theme", "")}
Thế giới quanCài đặt:{project_overview.get("world_setting", "")}
</overview>

<style>
Phong cách：{style}
Mô tả：{style_description}
</style>

<characters>
{_format_character_names(characters)}
</characters>

<clues>
{_format_clue_names(clues)}
</clues>

<scenes>
{scenes_md}
</scenes>

scenes Bảng phân tách cảnh, mỗi dòng là một cảnh, bao gồm:
- Cảnh ID：định dạngCho E{{集数}}S{{Số thứ tự}}
- CảnhMô tả：Kịch bảnNội dung cảnh đã được chuyển thể
- Thời lượng: 4, 6 hoặc 8 giây (mặc định 8 giây)
- CảnhLoại：Cốt truyện, hành động, đối thoại, v.v.
- Có phải là segment_break không: Điểm chuyển cảnh, cần cài đặt segment_break là true

3. Khi tạo cho mỗi cảnh, tuân theo các quy tắc sau:

a. **characters_in_scene**：Liệt kê tên nhân vật xuất hiện trong cảnh.
   - Giá trị tùy chọn: [{", ".join(character_names)}]
   - Chỉ bao gồm các Nhân vật được đề cập rõ ràng hoặc ám chỉ rõ ràng

b. **clues_in_scene**：Liệt kê tên manh mối liên quan trong cảnh.
   - Giá trị tùy chọn: [{", ".join(clue_names)}]
   - Chỉ bao gồm Manh mối được đề cập rõ ràng hoặc ám chỉ rõ ràng

c. **image_prompt**：Tạo đối tượng bao gồm các đoạn từ sau:
   - scene：Dùng tiếng Trung mô tả cụ thể cảnh này — vị trí nhân vật, tư thế, biểu cảm, chi tiết trang phục, cùng các yếu tố môi trường và vật phẩm có thể thấy. Bố cục ngang 16:9.
     Tập trung vào hình ảnh có thể thấy ngay tại khoảnh khắc hiện tại. Chỉ mô tả các yếu tố thị giác cụ thể mà máy quay có thể ghi lại.
     Đảm bảo mô tả tránh các yếu tố nằm ngoài cảnh này. Loại bỏ ẩn dụ, ẩn ý, từ ngữ cảm xúc trừu tượng, đánh giá chủ quan, nhiều cảnh chuyển đổi mà không thể hiển thị trực tiếp.
     Hình ảnh nên tự chứa, không ám chỉ sự kiện trong quá khứ hoặc phát triển tương lai.
   - composition：
     - shot_type：Góc máyLoại（Extreme Close-up, Close-up, Medium Close-up, Medium Shot, Medium Long Shot, Long Shot, Extreme Long Shot, Over-the-shoulder, Point-of-view）
     - lighting：Dùng tiếng Trung mô tả loại nguồn sáng, hướng và nhiệt màu cụ thể (ví dụ"Ánh sáng vàng ấm buổi sáng chiếu qua cửa sổ bên trái"）
     - ambiance：Dùng tiếng Trung mô tả hiệu ứng môi trường có thể thấy (ví dụ"Sương mỏng bao phủ"、"Bụi bay lơ lửng"），Tránh từ ngữ cảm xúc trừu tượng

d. **video_prompt**：Tạo đối tượng bao gồm các đoạn từ sau:
   - action：Dùng tiếng Trung mô tả chính xác các hành động cụ thể của chủ thể trong khoảng thời gian này — di chuyển cơ thể, thay đổi cử chỉ, chuyển đổi biểu cảm.
     Tập trung vào một hành động liền mạch duy nhất, đảm bảo có thể hoàn thành trong thời gian quy định (4/6/8 giây).
     Loại trừ việc chuyển cảnh nhiều, cắt cảnh nhanh, hiệu ứng montaje và các hiệu ứng không thể thực hiện trong một lần sinh tạo.
     Loại trừ mô tả hành động ẩn dụ (ví dụ"như đang bay lượn như bướm"）。
   - camera_motion：Chuyển động máy quay（Static, Pan Left, Pan Right, Tilt Up, Tilt Down, Zoom In, Zoom Out, Tracking Shot）
     Mỗi đoạn chỉ chọn một kiểu chuyển động của máy quay.
   - ambiance_audio：Dùng tiếng Trung mô tả âm thanh trong cảnh (diegetic sound) — âm thanh môi trường, tiếng bước chân, âm thanh vật thể.
     Chỉ mô tả âm thanh thực sự tồn tại trong cảnh. Loại trừ nhạc nền, BGM, lồng tiếng, âm thanh ngoài cảnh.
   - dialogue：{{speaker, line}} Mảng, bao gồm đối thoại của nhân vật. Người nói phải là một trong những nhân vật trong cảnh.

e. **segment_break**：Nếu trong bảng cảnh được đánh dấu là"是"，thì đặt là true.

f. **duration_seconds**：Sử dụng thời lượng từ bảng cảnh (4, 6 hoặc 8 giây), mặc định là 8.

g. **scene_type**：Sử dụng loại cảnh từ bảng cảnh, mặc định là"Cốt truyện"。

h. **transition_to_next**：默认为 "cut"。

Mục tiêu: Tạo các prompt phân cảnh sống động và thống nhất về mặt thị giác, dùng để hướng dẫn AI tạo hình ảnh và video. Giữ tính sáng tạo, cụ thể, phù hợp với trình bày hoạt hình theo bố cục ngang 16:9.
"""
    return prompt
