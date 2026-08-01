"""
颜色提取工具 —— 使用 colorthief 从图片中提取主色调。

════════════════════════ 算法说明 ════════════════════════

1. 核心依赖：colorthief 库（基于 JavaScript 的 Color Thief 项目）
   - Color Thief 使用 Modified Median Cut Quantization（改进的中值切割量化算法）
   - 首先将图片缩小到 ~100px 以提高处理速度（quality 参数控制采样精度）
   - 将所有像素映射到 RGB 色彩空间，通过中值切割将颜色聚类
   - get_palette(color_count=N) 返回 N 个最具代表性的 (R, G, B) 元组
   - 我们取第 1 个（占比最大的主色），转为 6 位 HEX 格式如 #C23B22

2. 降级策略：
   - 如果 colorthief 未安装（ImportError），设置 COLORTHIEF_AVAILABLE = False
   - app.py 中检测到此标志后，自动切换为 st.color_picker 手动选色
   - 用户仍可手动输入任意 HEX 色值

3. 可扩展方向：
   - 可提取多色（如 color_count=5）来获取辅色配色建议
   - 可将 RGB 映射到中文颜色名（如"酒红""藏青"）供穿搭匹配
   - 可分析颜色季节属性（暖色→春秋，冷色→夏冬）自动推荐季节标签
"""

import os

# ═══════════════════════════════════════════
#  安全导入 colorthief（第三方库可能未安装）
# ═══════════════════════════════════════════

try:
    from colorthief import ColorThief
    COLORTHIEF_AVAILABLE = True
except ImportError as e:
    # 如果 colorthief 未安装，标记为不可用
    # app.py 读取此标志，自动降级为手动颜色选择器
    COLORTHIEF_AVAILABLE = False
    ColorThief = None  # 设为 None 防止后续调用报 NameError


def extract_dominant_color(image_path: str) -> str:
    """
    【核心函数】从图片中提取主色调。

    ── 算法流程 ──
    1. 用 ColorThief 加载图片文件
    2. 调用 get_palette(color_count=2, quality=10) 获取前 2 个主色
       - color_count=2：只取前 2 个颜色（够用了，避免多余计算）
       - quality=10：采样质量，值越大越精确但越慢（1 为最高质量）
    3. 取调色板第 1 个颜色作为"主色"
    4. 格式化为 6 位 HEX（如 RGB(194,59,34) → "#C23B22"）

    ── 参数 ──
    image_path: str  - 图片文件的绝对路径

    ── 返回值 ──
    str  - 6 位 HEX 色值（含 # 前缀），失败时返回 "#CCCCCC"（浅灰）

    ── 异常处理 ──
    所有异常被捕获并打印中文日志，不会中断程序。
    常见失败原因：文件不存在、图片格式损坏、不是图片文件。
    """
    # 如果 colorthief 根本没装上，直接返回默认值
    if not COLORTHIEF_AVAILABLE:
        print("[颜色提取] colorthief 库未安装，返回默认颜色 #CCCCCC")
        return "#CCCCCC"

    try:
        # 步骤 1: 用 colorthief 打开图片文件
        color_thief = ColorThief(image_path)

        # 步骤 2: 获取调色板
        # get_palette 内部流程：
        #   a) 用 Pillow 打开图片，缩小到 ~100px 宽
        #   b) 遍历所有像素，构建颜色直方图
        #   c) 用中值切割算法将颜色空间划分为 N 个桶
        #   d) 每个桶取平均颜色，按像素占比排序
        #   e) 返回 [(R,G,B), ...] 列表
        palette = color_thief.get_palette(color_count=2, quality=10)

        # 步骤 3: 取第一个颜色（占比最大的主色）
        if palette and len(palette) > 0:
            r, g, b = palette[0]
            # 步骤 4: RGB → HEX
            # f"#{r:02X}{g:02X}{b:02X}" 中：
            #   :02X 表示"用大写十六进制，至少 2 位，不足左侧补零"
            #   例如 R=194 → "C2", G=59 → "3B", B=34 → "22" → "#C23B22"
            return f"#{r:02X}{g:02X}{b:02X}"

    except FileNotFoundError:
        print(f"[颜色提取失败] 找不到图片文件：{image_path}")
    except OSError as e:
        print(f"[颜色提取失败] 文件读取错误（可能不是图片格式）：{e}")
    except ValueError as e:
        print(f"[颜色提取失败] colorthief 无法解析该图片：{e}")
    except Exception as e:
        # 兜底：捕获所有其他未知异常，保证程序不崩溃
        print(f"[颜色提取失败] 未知错误：{type(e).__name__} - {e}")

    # 所有异常路径最终返回默认灰色
    return "#CCCCCC"


# ═══════════════════════════════════════════
#  颜色匹配 / 色差计算 / 调色板提取
# ═══════════════════════════════════════════


def hex_to_rgb(hex_color: str) -> tuple:
    """
    HEX 色值 → RGB 元组。

    ── 用途 ──
    色差计算需要 RGB 三个通道的数值，HEX 字符串不能直接做数学运算。
    此函数是颜色匹配管线的第一步。

    ── 示例 ──
    "#C23B22" → (194, 59, 34)
    "#FFFFFF" → (255, 255, 255)

    ── 异常处理 ──
    格式不合法时返回 (128, 128, 128)（中性灰），保证程序不崩溃。
    """
    try:
        hex_color = hex_color.lstrip("#")
        if len(hex_color) != 6:
            return (128, 128, 128)
        # 每 2 位一组，从十六进制转为十进制整数
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, AttributeError):
        return (128, 128, 128)


def delta_e_rgb(rgb1: tuple, rgb2: tuple) -> float:
    """
    【核心算法】计算两个 RGB 颜色之间的欧几里得距离（ΔE）。

    ── 公式 ──
    ΔE = sqrt( (R₁-R₂)² + (G₁-G₂)² + (B₁-B₂)² )

    ── 为什么用 RGB 欧几里得距离而非 CIELAB ΔE？ ──
    1. CIELAB 需要先做 RGB → XYZ → LAB 转换，计算量大
    2. 本应用场景是"找色调相似的衣服"，RGB 距离对日常穿搭已足够
    3. RGB 距离 = 0 表示完全相同，> 441（最大差值）表示完全相反

    ── 可扩展方向 ──
    如需更符合人眼感知的色差，可升级为 CIE76/CIE94/CIEDE2000：
      - 先转到 LAB：需要 RGB→XYZ→LAB（约 20 行代码）
      - 再计算 ΔE*₀₀（CIEDE2000，约 30 行代码）
    修改位置：替换此函数的实现即可，接口不变。

    ── 参数 ──
    rgb1: (R, G, B) 元组，各通道 0-255
    rgb2: (R, G, B) 元组，各通道 0-255

    ── 返回值 ──
    float - 色差值，越小越接近。0 = 完全相同。
    """
    r1, g1, b1 = rgb1
    r2, g2, b2 = rgb2
    return ((r1 - r2) ** 2 + (g1 - g2) ** 2 + (b1 - b2) ** 2) ** 0.5


def extract_palette(image_path: str, count: int = 5) -> list:
    """
    从图片中提取多色调色板（3-5 个主色）。

    ── 用途 ──
    - 灵感图入库时自动提取 extracted_colors 字段
    - 搭配画布保存时自动计算 color_palette
    - 支持后续"色调灵感匹配"功能

    ── 算法 ──
    使用 colorthief.get_palette(color_count=N)，内部流程同 extract_dominant_color()
    但返回 N 个颜色而非 1 个。

    ── 降级策略 ──
    colorthief 不可用时返回空列表，前端自动隐藏相关功能。

    ── 参数 ──
    image_path: str - 图片文件绝对路径
    count: int      - 提取颜色数量（默认 5）

    ── 返回值 ──
    list[str] - HEX 色值列表，如 ["#C23B22", "#FFFFFF", ...]
                失败时返回空列表 []
    """
    if not COLORTHIEF_AVAILABLE:
        return []

    try:
        color_thief = ColorThief(image_path)
        palette = color_thief.get_palette(color_count=count, quality=10)
        if palette:
            return [f"#{r:02X}{g:02X}{b:02X}" for r, g, b in palette]
    except Exception as e:
        print(f"[调色板提取失败] {type(e).__name__}: {e}")

    return []


def average_color(hex_list: list) -> str:
    """
    计算多个 HEX 颜色的平均值。

    ── 用途 ──
    保存搭配方案时，自动计算整套搭配（多件衣服）的综合色调，
    存入 outfits.color_palette 字段。

    ── 算法 ──
    1. 将每个 HEX 转为 RGB
    2. 对 R/G/B 三个通道分别取算术平均
    3. 将平均 RGB 转回 HEX
    这是最简单的"混合光"模型；如需"混合颜料"模型，
    可用 CMYK 色彩空间做减法混合（更复杂但更准确）。

    ── 参数 ──
    hex_list: list[str] - HEX 色值列表

    ── 返回值 ──
    str - 平均色的 HEX 值，空列表返回 "#CCCCCC"
    """
    if not hex_list:
        return "#CCCCCC"

    try:
        rgbs = [hex_to_rgb(h) for h in hex_list if h and h.startswith("#")]
        if not rgbs:
            return "#CCCCCC"

        n = len(rgbs)
        avg_r = sum(r[0] for r in rgbs) // n
        avg_g = sum(r[1] for r in rgbs) // n
        avg_b = sum(r[2] for r in rgbs) // n
        return f"#{avg_r:02X}{avg_g:02X}{avg_b:02X}"
    except Exception as e:
        print(f"[平均色计算失败] {e}")
        return "#CCCCCC"


def find_closest_clothes(
    target_hex_list: list,
    clothes_list: list,
    top_n: int = 5,
) -> list:
    """
    【核心算法】在衣橱中找到与目标色板最接近的衣服。

    ── 匹配算法（逐件评分制）──
    对于衣橱中的每一件衣服：
      1. 取该衣服的 color_hex → 转为 RGB → 记为 cloth_rgb
      2. 遍历目标色板中的每个目标颜色：
         - 计算 ΔE(cloth_rgb, target_rgb)
         - 记录最小的 ΔE 作为该衣服的"最佳色差值"
      3. 为什么取 min ΔE 而非 avg ΔE？
         - 用户心理："这件衬衫和灵感图中某个颜色很像"就够了
         - 不需要和所有目标色都接近
      4. 最后按 best_delta 升序排列 → 取前 top_n 件

    ── 可扩展方向 ──
    - 加权匹配：给主色更高权重（灵感图第 1 个颜色权重大于第 5 个）
    - 色相优先：先按色相分组（暖/冷），再算 ΔE
    - 季节偏好：结合 season 字段加权

    ── 参数 ──
    target_hex_list: list[str] - 目标色板（来自灵感图的 extracted_colors）
    clothes_list:    list[dict] - 衣橱列表，每件需含 color_hex 字段
    top_n:           int        - 返回前 N 件最匹配的衣服

    ── 返回值 ──
    list[dict] - 原 clothes_list 的子集，按色差升序排列，
                 每件额外附加 _delta_e 字段（最小色差值）
    """
    if not target_hex_list or not clothes_list:
        return []

    # 步骤 1: 将目标色板全部转为 RGB（只转一次，避免重复计算）
    # 过滤掉无效颜色（如 #CCCCCC 默认值）
    target_rgbs = []
    for h in target_hex_list:
        rgb = hex_to_rgb(h)
        if rgb != (204, 204, 204):  # 跳过默认灰色
            target_rgbs.append(rgb)
    if not target_rgbs:
        target_rgbs = [hex_to_rgb(h) for h in target_hex_list]

    # 步骤 2: 对每件衣服计算最小色差
    scored = []
    for item in clothes_list:
        cloth_hex = item.get("color_hex", "#CCCCCC")
        if not cloth_hex:
            cloth_hex = "#CCCCCC"

        try:
            cloth_rgb = hex_to_rgb(cloth_hex)
        except Exception:
            continue  # 跳过颜色格式异常的数据

        # 计算该衣服与目标色板中任意颜色的最小距离
        best_delta = float("inf")
        for t_rgb in target_rgbs:
            d = delta_e_rgb(cloth_rgb, t_rgb)
            if d < best_delta:
                best_delta = d

        # 只保留有实际色差的匹配结果
        if best_delta < float("inf"):
            item_copy = dict(item)
            item_copy["_delta_e"] = round(best_delta, 1)
            scored.append(item_copy)

    # 步骤 3: 按色差升序排列 → 取前 top_n
    scored.sort(key=lambda x: x["_delta_e"])
    return scored[:top_n]


def rgb_to_hsl(r: int, g: int, b: int) -> tuple:
    """
    RGB → HSL 色彩空间转换。

    ── 用途 ──
    HSL（色相 Hue / 饱和度 Saturation / 明度 Lightness）比 RGB 更直观：
    - 色相 H：什么颜色（0°红 → 120°绿 → 240°蓝）
    - 饱和度 S：颜色有多纯（0%=灰 → 100%=最鲜艳）
    - 明度 L：颜色有多亮（0%=黑 → 100%=白）

    ── 可用于 ──
    - 季节色板匹配：春季暖亮(H≈30°)、夏季冷柔(H≈210°)、秋季暖深(H≈30°高饱)、冬季冷艳(H≈270°)
    - 互补色推荐：H 相差 180°
    - 邻近色推荐：H 相差 ±30°

    ── 参考 ──
    标准 RGB→HSL 算法，来自 CSS Color Level 3 规范。
    """
    r_norm = r / 255.0
    g_norm = g / 255.0
    b_norm = b / 255.0

    max_c = max(r_norm, g_norm, b_norm)
    min_c = min(r_norm, g_norm, b_norm)
    delta = max_c - min_c

    # L: 明度
    l_val = (max_c + min_c) / 2.0

    # S: 饱和度
    if delta == 0:
        s_val = 0.0
    else:
        s_val = delta / (1 - abs(2 * l_val - 1))

    # H: 色相
    if delta == 0:
        h_val = 0.0
    elif max_c == r_norm:
        h_val = 60 * (((g_norm - b_norm) / delta) % 6)
    elif max_c == g_norm:
        h_val = 60 * ((b_norm - r_norm) / delta + 2)
    else:
        h_val = 60 * ((r_norm - g_norm) / delta + 4)

    return (round(h_val, 1), round(s_val * 100, 1), round(l_val * 100, 1))
