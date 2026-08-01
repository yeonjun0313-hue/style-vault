"""
Style Vault —— 个人穿搭素材库
=================================
使用 Streamlit + SQLite 构建的个人衣橱管理 Web 应用。

════════════════════════ 页面布局 ════════════════════════

┌─ 侧边栏（Sidebar）────────────────────┐
│  📦 录入新物品                        │
│  ○ 衣服  ○ 饰品  ○ 灵感图            │
│  ────────────────────────────         │
│  [上传图片] → 自动取色 → 填信息 → 保存 │
└───────────────────────────────────────┘

┌─ 主区域 ─────────────────────────────┐
│  👗 Style Vault                   │
│  ┌─👕衣柜──┬─💍饰品库──┬─✨灵感墙──┐ │
│  │ 筛选栏  │ 按部位分组 │ 类型筛选  │ │
│  │ 四列网格│ 四列网格  │ 四列网格  │ │
│  └─────────┴───────────┴───────────┘ │
└───────────────────────────────────────┘

════════════════════════ 扩展预留说明 ════════════════════════

1. 【天气匹配规则】（待实现）
   可在 season 字段基础上扩展为温度区间匹配：
   - 建立 weather_rules 表，字段：min_temp, max_temp, weather_type, suggest_category
   - 示例规则：
     · 温度 > 25°C → 推荐 season IN ('夏','四季') 且 category IN ('连衣裙','短袖')
     · 温度 10-20°C → 推荐 season IN ('春','秋','四季') 且 category IN ('外套','长袖')
     · 温度 < 10°C → 推荐 season IN ('冬','四季') 且 category IN ('外套','羽绒服')
     · 雨天 → 推荐 material NOT IN ('丝绸','羊毛')（不耐水材质）
   - 接入天气 API（如和风天气）获取实时气温和天气类型
   - 匹配算法：遍历 clothes 表，对每件衣服计算"适配分数"
     · season 匹配权重 40%
     · material 天气适宜度权重 30%
     · 最近穿着间隔权重 20%（越久没穿越推荐）
     · 穿着频率权重 10%（高频单品优先）
   - 修改位置：在 衣柜 Tab 添加"今日推荐"按钮，调用匹配函数

2. 【颜色匹配算法】（待实现）
   可基于 color_hex 实现色系分析和搭配建议：
   - HEX → HSL 转换：分析明度、饱和度
   - 互补色推荐：色相环对面颜色（HSL 色相 ±180°）
   - 邻近色推荐：色相环相邻颜色（HSL 色相 ±30°）
   - 季节色板匹配：春季(暖亮)、夏季(冷柔)、秋季(暖深)、冬季(冷艳)
   - 修改位置：新增"搭配建议"Tab 或弹窗模块

3. 【胶囊衣橱统计】（待实现）
   利用 wear_count 和 last_wear_date 做数据分析：
   - 30天未穿预警
   - 月度穿着排行
   - 品类占比饼图
   - 投入产出比（价格/wear_count）
"""

import streamlit as st
import os
import json
import time
import random
import requests
from datetime import date, timedelta
from PIL import Image, UnidentifiedImageError

# ── 安全导入自定义模块 ──
# 每个导入都加 try-except，第三方库缺失时给出中文提示而非英文 traceback
try:
    import database as db
except ImportError as e:
    st.error(f"❌ 导入 database.py 失败：{e}")
    st.stop()

try:
    from color_utils import (
        extract_dominant_color, extract_palette, average_color,
        find_closest_clothes, delta_e_rgb, hex_to_rgb, COLORTHIEF_AVAILABLE,
    )
except ImportError as e:
    st.error(f"❌ 导入 color_utils.py 失败：{e}")
    st.stop()

# ═══════════════════════════════════════════
#  页面配置
# ═══════════════════════════════════════════

try:
    st.set_page_config(
        page_title="Style Vault · 我的穿搭素材库",
        page_icon="👗",
        layout="wide",
        initial_sidebar_state="expanded",
    )
except Exception as e:
    # st.set_page_config 必须是第一个 st 调用，重复调用会报错
    # 此处捕获以防某些 Streamlit 版本兼容问题
    print(f"[页面配置] {e}")


# ═══════════════════════════════════════════
#  PWA 支持
# ═══════════════════════════════════════════

st.markdown("""
<link rel="manifest" href="/app/static/manifest.json">
<!-- iOS PWA -->
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Style Vault">
<link rel="apple-touch-icon" href="/app/static/icon-192.png">
<link rel="apple-touch-startup-image" href="/app/static/splash-iphone.png"
      media="(device-width: 375px) and (device-height: 812px) and (-webkit-device-pixel-ratio: 3)">
<!-- General -->
<meta name="theme-color" content="#C8957B">
<script>
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('/app/static/sw.js').catch(function(){});
  }
</script>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════
#  CSS 美化 —— 暖色时尚杂志风格
# ═══════════════════════════════════════════

st.markdown("""
<style>
    /* ══════════════════════════════════════════
       Style Vault — 暖杏色高级时尚风格
       主色：#C8957B  辅色：#2C3E50  背景：#FDF8F5
       强调：#E8A87C  成功：#7BAE7F
       ══════════════════════════════════════════ */

    /* ── 全局 ── */
    * { box-sizing: border-box; }
    .main > div { max-width: 1200px; margin: 0 auto; }
    html, body, [class*="css"] {
        font-family: "Georgia", "PingFang SC", "Microsoft YaHei", "Noto Serif SC", serif;
        color: #5A4A42; font-size: 15px;
    }
    .stApp { background: #FDF8F5; }

    /* ── 标题层级 ── */
    h1 { font-family: "Georgia", "Noto Serif SC", serif !important;
         color: #2C1810 !important; font-weight: 700 !important; font-size: 1.8rem !important; }
    h2 { color: #2C1810 !important; font-weight: 600 !important; }
    h3 { color: #2C1810 !important; font-weight: 500 !important; }

    .main .block-container { background: #FDF8F5; padding: 1.2rem 1.8rem; }

    /* ── 卡片 ── */
    .item-card {
        border: 1px solid #EDE0D8; border-radius: 16px; padding: 12px;
        margin-bottom: 20px; background: #FFFFFF;
        transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94);
        box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    }
    .item-card:hover {
        box-shadow: 0 12px 32px rgba(0,0,0,0.08);
        transform: translateY(-4px); border-color: #C8957B;
    }

    /* ── 颜色圆点 ── */
    .color-dot {
        display: inline-block; width: 18px; height: 18px;
        border-radius: 50%; border: 1.5px solid #EDE0D8;
        vertical-align: middle; margin-right: 6px;
        box-shadow: inset 0 0 0 2px rgba(255,255,255,0.6);
    }

    /* ── 标签徽章 ── */
    .tag-badge {
        display: inline-block; padding: 3px 12px; border-radius: 20px;
        font-size: 0.76rem; margin: 3px 4px; font-weight: 500;
    }
    .tag-badge.c1 { background: #F5E6E0; color: #A0524A; }
    .tag-badge.c2 { background: #E0EDE8; color: #2C3E50; }
    .tag-badge.c3 { background: #FDF0E0; color: #B8860B; }
    .tag-badge.c4 { background: #F0E5F0; color: #7D5298; }
    .tag-badge.c5 { background: #E0EAF5; color: #3A6090; }

    .group-header {
        font-size: 1.15rem; font-weight: 600; margin: 24px 0 12px 0;
        padding: 6px 16px; color: #2C1810;
        background: linear-gradient(to right, #F5E6E0, transparent);
        border-left: 4px solid #C8957B; display: block;
    }

    .empty-state {
        text-align: center; padding: 80px 20px; color: #C4B5AB;
        font-size: 1.15rem; background: rgba(255,255,255,0.5);
        border-radius: 16px; border: 2px dashed #EDE0D8;
    }

    .color-status { font-size: 0.82rem; padding: 6px 10px; border-radius: 10px; margin: 6px 0; }
    .color-status.success { background: #E8F0EB; color: #7BAE7F; }
    .color-status.fallback { background: #FDF5EE; color: #B8860B; }

    .weather-card {
        background: #FFFFFF; border: 1px solid #EDE0D8;
        border-radius: 16px; padding: 16px 20px; margin: 8px 0 16px 0;
        box-shadow: 0 2px 12px rgba(0,0,0,0.04);
    }

    /* ── 按钮 ── */
    .stButton > button {
        border-radius: 12px !important; font-weight: 500 !important;
        transition: all 0.2s ease !important;
        border: 1.5px solid #EDE0D8 !important;
        background: #FFFFFF !important; color: #5A4A42 !important;
        min-height: 36px; min-width: 44px;
    }
    .stButton > button:hover {
        background: #FDF8F5 !important; border-color: #C8957B !important;
        transform: scale(0.97);
    }
    .stButton > button[kind="primary"] {
        background: #C8957B !important; color: #FFFFFF !important;
        border-color: #C8957B !important; font-weight: 600 !important;
    }
    .stButton > button[kind="primary"]:hover {
        background: #B8846A !important; border-color: #B8846A !important;
    }

    /* ── 输入框 ── */
    input, select, .stSelectbox, .stTextInput input, .stNumberInput input {
        border-radius: 12px !important; border: 1px solid #EDE0D8 !important;
    }
    input:focus, .stSelectbox:focus-within {
        border-color: #C8957B !important;
        box-shadow: 0 0 0 3px rgba(200,149,123,0.12) !important;
    }

    .filter-container {
        background: #FFFFFF; border: 1px solid #EDE0D8;
        border-radius: 16px; padding: 16px 20px; margin-bottom: 20px;
    }

    /* ── Tab 胶囊 ── */
    .stTabs [data-baseweb="tab-list"] { gap: 8px; background: transparent; }
    .stTabs [data-baseweb="tab"] {
        border-radius: 24px !important; padding: 8px 20px !important;
        background: #FFFFFF !important; border: 1.5px solid #EDE0D8 !important;
        color: #8B7E74 !important; font-weight: 500; transition: all 0.2s;
        min-height: 44px;
    }
    .stTabs [data-baseweb="tab"]:hover { border-color: #C8957B !important; color: #5A4A42 !important; }
    .stTabs [aria-selected="true"] {
        background: #C8957B !important; color: #FFFFFF !important;
        border-color: #C8957B !important;
    }

    .stExpander { border: 1px solid #EDE0D8 !important; border-radius: 16px !important; background: #FFFFFF !important; }

    /* ── 侧边栏 ── */
    [data-testid="stSidebar"] { background: #FFFFFF; border-right: 1px solid #EDE0D8; }

    /* ── 消息条 ── */
    .stSuccess { background: #E8F0EB !important; border-left: 4px solid #7BAE7F !important; border-radius: 8px !important; }
    .stWarning { background: #FDF5EE !important; border-left: 4px solid #E8A87C !important; border-radius: 8px !important; }
    .stError   { background: #FDF0F0 !important; border-left: 4px solid #C0392B !important; border-radius: 8px !important; }
    .stInfo    { background: #F0F4F8 !important; border-left: 4px solid #2C3E50 !important; border-radius: 8px !important; }

    hr { border-color: #EDE0D8 !important; }

    /* ── 推荐卡片横向滚动 ── */
    .outfit-scroll { display: flex; gap: 16px; overflow-x: auto; padding: 8px 0 16px; -webkit-overflow-scrolling: touch; }
    .outfit-scroll > div { flex: 0 0 220px; }

    /* ── 移动端适配 ── */
    @media (max-width: 768px) {
        .main .block-container { padding: 0.8rem; }
        h1 { font-size: 1.4rem !important; }
        .item-card { border-radius: 12px; padding: 8px; }
        .stTabs [data-baseweb="tab"] { padding: 6px 12px !important; font-size: 0.78rem !important; }
    }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════
#  初始化（DB + 常量 + 文件目录）
# ═══════════════════════════════════════════

try:
    db.init_db()
except RuntimeError as e:
    st.error(f"❌ 数据库初始化失败：{e}\n\n请检查项目目录是否有写入权限。")
    st.stop()

# ── 品类/材质/季节等枚举值 ──
# 这些是前端下拉框的固定选项，与 DB 中实际存储的值保持一致
CATEGORIES   = ["上衣", "下装", "外套", "连衣裙", "鞋履"]
# 材质预设选项 —— 用户可选择预设或手动输入自定义面料
# "其他" 选项触发动态文本框，支持任意新型面料（莱赛尔、三醋酸等）
MATERIALS    = [
    "棉", "羊毛", "牛仔", "丝绸", "化纤",
    "亚麻", "莱赛尔", "三醋酸", "涤纶", "锦纶",
    "氨纶", "混纺", "皮革", "其他",
]
SEASONS      = ["春", "夏", "秋", "冬", "四季"]
PARTS        = ["耳部", "头部", "颈部", "手部"]
INSP_TYPES   = ["穿搭灵感", "色调灵感", "INS元素", "发型妆容", "📸 拍照姿势"]

# 拍照姿势预设标签（灵感墙上传感知姿势时可选）
POSE_PRESETS = [
    "站姿", "坐姿", "蹲姿", "躺姿", "回眸", "侧脸", "背影",
    "抬手", "撩发", "叉腰", "拿包", "看镜头", "不看镜头",
    "室内", "室外", "街拍", "自然光", "逆光",
]

# 颜色名称映射（HEX → 中文名，未匹配的显示色值）
COLOR_NAME_MAP = {
    "#1A1A1A": "黑", "#000000": "黑",
    "#FFFFFF": "白", "#F5F5F5": "白",
    "#9E9E9E": "灰", "#808080": "灰", "#95A5A6": "灰",
    "#E74C3C": "红", "#C0392B": "红", "#FF0000": "红",
    "#F39C12": "橙", "#FF8C00": "橙",
    "#F1C40F": "黄", "#FFFF00": "黄",
    "#27AE60": "绿", "#2D4A3E": "绿", "#008000": "绿",
    "#2980B9": "蓝", "#0000FF": "蓝", "#87CEEB": "浅蓝",
    "#8E44AD": "紫", "#800080": "紫",
    "#E8A0BF": "粉", "#FFC0CB": "粉",
    "#F5E6D3": "米", "#F5DEB3": "米", "#FAF5F0": "米",
    "#C9A87C": "驼", "#C4A882": "驼", "#D4A89B": "棕",
    "#CCCCCC": "浅灰",
}

# ── 星座幸运色配置 ──
ZODIAC_SIGNS = [
    "白羊座", "金牛座", "双子座", "巨蟹座", "狮子座", "处女座",
    "天秤座", "天蝎座", "射手座", "摩羯座", "水瓶座", "双鱼座",
]

ZODIAC_LUCKY_COLORS = {
    "白羊座": [("#E74C3C", "红色"), ("#FFFFFF", "白色")],
    "金牛座": [("#27AE60", "绿色"), ("#F1C40F", "黄色")],
    "双子座": [("#F1C40F", "黄色"), ("#8E44AD", "紫色")],
    "巨蟹座": [("#FFFFFF", "白色"), ("#2980B9", "蓝色")],
    "狮子座": [("#F39C12", "橙色"), ("#E74C3C", "红色")],
    "处女座": [("#C9A87C", "驼色"), ("#1A1A1A", "黑色")],
    "天秤座": [("#8E44AD", "紫色"), ("#87CEEB", "浅蓝")],
    "天蝎座": [("#1A1A1A", "黑色"), ("#E74C3C", "红色")],
    "射手座": [("#2980B9", "蓝色"), ("#8E44AD", "紫色")],
    "摩羯座": [("#C9A87C", "驼色"), ("#1A1A1A", "黑色")],
    "水瓶座": [("#2980B9", "蓝色"), ("#87CEEB", "浅蓝")],
    "双鱼座": [("#8E44AD", "紫色"), ("#27AE60", "绿色")],
}

def get_today_lucky_color(zodiac_sign):
    """基于当日日期从星座幸运色列表中轮换选择今日幸运色。"""
    colors = ZODIAC_LUCKY_COLORS.get(zodiac_sign)
    if not colors:
        return ("#CCCCCC", "默认")
    day_of_year = date.today().timetuple().tm_yday
    idx = (day_of_year + ZODIAC_SIGNS.index(zodiac_sign)) % len(colors)
    return colors[idx]


# ── 目录常量 ──
# BASE_DIR:    项目根目录（即 my-style-vault/ 文件夹）
# UPLOAD_DIR:  图片存储根目录（本地文件夹，不提交到 git）
# DB 中只存相对路径，如 uploaded_images/clothes/1712345678_img.jpg
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploaded_images")

# 确保三个子目录存在（exist_ok=True 避免重复创建报错）
for sub in ["clothes", "accessories", "inspirations"]:
    try:
        os.makedirs(os.path.join(UPLOAD_DIR, sub), exist_ok=True)
    except OSError as e:
        st.error(f"❌ 无法创建图片存储目录 {UPLOAD_DIR}/{sub}：{e}")
        st.stop()


# ═══════════════════════════════════════════
#  辅助函数
# ═══════════════════════════════════════════

def save_uploaded_image(uploaded_file, subfolder: str) -> str:
    """
    将 Streamlit UploadedFile 保存到 uploaded_images/<subfolder>/ 下。

    ── 文件命名规则 ──
    使用"时间戳_原始文件名"避免重名冲突：
    - 时间戳取 time.time() × 1000，精度到毫秒
    - 例如：1712345678123_白衬衫.jpg

    ── 返回值 ──
    str - 【相对路径】，如 uploaded_images/clothes/1712345678123_白衬衫.jpg
           数据库只存相对路径，确保项目文件夹可整体移动而不失效
    """
    try:
        # 生成唯一文件名：毫秒时间戳 + 原始文件名
        timestamp = int(time.time() * 1000)
        safe_name = f"{timestamp}_{uploaded_file.name}"
        dest_dir  = os.path.join(UPLOAD_DIR, subfolder)
        dest_path = os.path.join(dest_dir, safe_name)

        # 写入文件
        with open(dest_path, "wb") as f:
            f.write(uploaded_file.getbuffer())

        # 返回相对于项目根目录的路径（而非绝对路径）
        # 例如：uploaded_images/clothes/1712345678123_白衬衫.jpg
        rel_path = os.path.join("uploaded_images", subfolder, safe_name)
        return rel_path

    except OSError as e:
        raise RuntimeError(f"❌ 图片保存失败（{uploaded_file.name}）：{e}") from e


def resolve_image_path(rel_path: str) -> str:
    """
    将 DB 中的相对路径转为绝对路径，供 st.image() 使用。

    ── 兼容性处理 ──
    - 如果已是绝对路径（旧数据兼容），直接返回
    - 如果是相对路径，拼接 BASE_DIR
    - 路径分隔符自动适配 Windows（\）和 macOS/Linux（/）
    """
    if os.path.isabs(rel_path):
        return rel_path
    return os.path.join(BASE_DIR, rel_path)


def tag_badge_html(tag: str, idx: int = 0) -> str:
    """
    生成一个彩色标签徽章的 HTML。

    ── 颜色分配算法 ──
    使用 idx % 5 循环分配 5 种预定义颜色类：
    - 不是随机，而是按标签顺序固定分配
    - 同一位置的标签每次渲染颜色一致

    ── CSS 类映射 ──
    idx % 5 → c1/c2/c3/c4/c5 → 5 种不同的背景/文字颜色组合
    """
    color_class = f"c{(idx % 5) + 1}"
    return f'<span class="tag-badge {color_class}">{tag}</span>'


def color_dot_html(hex_color: str) -> str:
    """
    生成一个颜色圆点的 HTML（内联 style 设置背景色）。
    用于在物品名称前显示主色调指示器。
    """
    return f'<span class="color-dot" style="background:{hex_color};"></span>'


def validate_hex_color(value: str) -> bool:
    """
    验证 HEX 颜色格式是否合法。

    ── 合法格式 ──
    - #RRGGBB（6 位十六进制 + # 前缀）
    - 例如：#C23B22, #FFFFFF, #000000

    ── 使用场景 ──
    在保存前校验用户输入（或 color_picker 输出）的颜色值
    """
    if not value or not value.startswith("#"):
        return False
    hex_part = value[1:]  # 去掉 # 前缀
    if len(hex_part) != 6:
        return False
    # 检查是否全部为十六进制字符（0-9, A-F, a-f）
    try:
        int(hex_part, 16)
        return True
    except ValueError:
        return False


def _parse_season(season_val):
    """Parse season field: handles old strings ('春'), new JSON arrays ('[\"春\",\"秋\"]'), and empty values."""
    if not season_val:
        return []
    if isinstance(season_val, list):
        return season_val
    if season_val.startswith("["):
        try:
            return json.loads(season_val)
        except (json.JSONDecodeError, TypeError):
            return []
    return [season_val]  # legacy: single string


def _format_season_tags(season_val):
    """Render season as colored emoji tags for card display."""
    seasons = _parse_season(season_val)
    if not seasons:
        return "—"
    icons = {"春": "🌸春", "夏": "☀️夏", "秋": "🍂秋", "冬": "❄️冬", "四季": "📅四季"}
    return " ".join(icons.get(s, s) for s in seasons)


def _get_distinct_pose_tags():
    """
    Get all unique pose tags across inspirations (inline version to avoid import issues).
    """
    try:
        conn = db.get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT pose_tags FROM inspirations WHERE pose_tags != '[]' AND pose_tags != ''"
        )
        all_tags = set()
        for row in cur.fetchall():
            try:
                tags = json.loads(row["pose_tags"])
                for t in tags:
                    if t.strip():
                        all_tags.add(t.strip())
            except (json.JSONDecodeError, TypeError):
                pass
        conn.close()
        return sorted(all_tags)
    except Exception:
        return POSE_PRESETS


# ═══════════════════════════════════════════
#  侧边栏 —— 录入表单
# ═══════════════════════════════════════════

st.sidebar.markdown("# 📦 录入新物品")
st.sidebar.caption("上传图片 → 自动取色 → 填写信息 → 保存")

# ── 录入类型切换（水平单选按钮） ──
upload_type = st.sidebar.radio(
    "选择录入类型",
    ["👕 衣服", "💍 饰品", "✨ 灵感图"],
    horizontal=True,
)

st.sidebar.divider()

# ╔══════════════════════════════════════════════════════════╗
# ║  衣服录入表单                                           ║
# ╚══════════════════════════════════════════════════════════╝
#
#  【设计决策】不使用 st.form，全部用原生 st.sidebar widget
#
#  原因：st.form 内的 widget 变化不会触发脚本重跑，导致：
#    1. 材质下拉框选"其他"后，条件文本框不出现（if 无法重新计算）
#    2. 需要把材质放到 form 外面 → form 外 widget 总是先于 form 渲染
#       → 侧边栏顺序错乱（品类/材质跑到图片上传前面）
#
#  改用全原生 widget 后：
#    - 每个 widget 变化都触发脚本重跑 → 材质联动实时响应
#    - 渲染顺序 = 代码书写顺序 → 字段排列完全可控
#    - st.file_uploader（带 key）在 Streamlit 1.28+ 会自动保持上传状态
#
#  手动管理提交后重置（替代 form 的 clear_on_submit）：
#    见下方 _reset_clothing_form() 辅助函数

if upload_type == "👕 衣服":

    # ── 初始化 session_state ──
    if "cloth_name" not in st.session_state:
        st.session_state.cloth_name = ""
    if "cloth_category" not in st.session_state:
        st.session_state.cloth_category = "上衣"
    if "cloth_material_preset" not in st.session_state:
        st.session_state.cloth_material_preset = ""
    if "cloth_material_custom" not in st.session_state:
        st.session_state.cloth_material_custom = ""
    if "cloth_color" not in st.session_state:
        st.session_state.cloth_color = "#CCCCCC"
    if "cloth_season" not in st.session_state:
        st.session_state.cloth_season = []

    # ── ① 上传衣服照片（最顶部）──
    uploaded_img = st.sidebar.file_uploader(
        "📷 上传衣服照片",
        type=["jpg", "jpeg", "png", "webp"],
        key="cloth_upload",
        help="支持 JPG / PNG / WebP 格式，建议裁剪为正方形",
    )

    # ── ② 自动取色 + 预览 ──
    auto_color = "#CCCCCC"
    color_auto_detected = False
    tmp_path = ""

    if uploaded_img is not None:
        # 显示图片预览
        try:
            st.sidebar.image(uploaded_img, use_container_width=True)
        except Exception as e:
            st.sidebar.warning(f"⚠️ 图片预览失败：{e}")

        # --- 颜色提取流程 ---
        tmp_dir = os.path.join(UPLOAD_DIR, "clothes")
        tmp_path = os.path.join(tmp_dir, f"_tmp_{uploaded_img.name}")
        os.makedirs(tmp_dir, exist_ok=True)

        # 仅在临时文件不存在时写入（避免每次 rerun 都写磁盘）
        if not os.path.exists(tmp_path):
            try:
                with open(tmp_path, "wb") as f:
                    f.write(uploaded_img.getbuffer())
            except OSError as e:
                st.sidebar.error(f"❌ 暂存图片失败：{e}")

        if os.path.exists(tmp_path) and COLORTHIEF_AVAILABLE:
            try:
                auto_color = extract_dominant_color(tmp_path)
                if auto_color != "#CCCCCC":
                    color_auto_detected = True
                    # 将提取到的颜色同步到 session_state（用户可后续修改）
                    if not st.session_state.cloth_color or st.session_state.cloth_color == "#CCCCCC":
                        st.session_state.cloth_color = auto_color
            except Exception as e:
                st.sidebar.warning(f"⚠️ 颜色提取失败：{e}")

        # 显示提取结果
        if color_auto_detected:
            st.sidebar.markdown(
                f'<div class="color-status success">'
                f'🎨 已自动提取主色：{auto_color}'
                f'<span class="color-dot" style="background:{auto_color};margin-left:8px;"></span>'
                f'</div>',
                unsafe_allow_html=True,
            )
        elif not COLORTHIEF_AVAILABLE:
            st.sidebar.markdown(
                '<div class="color-status fallback">'
                '⚠️ colorthief 库未安装，请使用下方颜色选择器手动选色</div>',
                unsafe_allow_html=True,
            )

    # ── ③ 名称 ──
    name = st.sidebar.text_input(
        "👕 名称",
        key="cloth_name",
        placeholder="例如：白色棉质衬衫",
        help="给这件衣服起个好记的名字",
    )

    # ── ④ 品类 ──
    category = st.sidebar.selectbox(
        "📂 品类",
        CATEGORIES,
        key="cloth_category",
        help="选择这件衣服的品类",
    )

    # ── ⑤ 材质（下拉 + "其他"→文本框实时联动）──
    # 因为不在 st.form 里，每次下拉切换都触发脚本重跑，
    # if material_preset == "其他" 会被重新计算 → 文本框立即出现/消失
    material_preset = st.sidebar.selectbox(
        "🧵 材质",
        [""] + MATERIALS,
        key="cloth_material_preset",
        help="选择预设面料，或选「其他」手动输入任意材质",
    )

    if material_preset == "其他":
        material_custom = st.sidebar.text_input(
            "✏️ 自定义材质",
            key="cloth_material_custom",
            placeholder="请输入自定义材质名称，如：天丝、铜氨丝等",
            help="自由输入任意面料名称，会直接存入数据库",
        )
        material = material_custom.strip() if material_custom else ""
    else:
        material = material_preset

    # ── ⑥ 颜色（10 种预设快速选色 + 自定义）──
    COLOR_PRESETS = [
        ("#1A1A1A", "⚫"), ("#FFFFFF", "⚪"), ("#F5E6D3", "🟤"),
        ("#C0392B", "🔴"), ("#2980B9", "🔵"), ("#27AE60", "🟢"),
        ("#F1C40F", "🟡"), ("#E8A0BF", "🩷"), ("#95A5A6", "🩶"),
        ("#C9A87C", "🟠"),
    ]
    st.sidebar.caption("🎨 快速选色")
    for row in range(2):
        pcols = st.sidebar.columns(5)
        for ci in range(5):
            pi = row * 5 + ci
            p_hex, p_icon = COLOR_PRESETS[pi]
            with pcols[ci]:
                if st.button(p_icon, key=f"cp_{pi}", use_container_width=True,
                             help=p_hex):
                    st.session_state.cloth_color = p_hex
                    st.rerun()

    color_hex = st.sidebar.color_picker(
        "自定义颜色",
        key="cloth_color",
        help="上方预设色或自定义任意颜色",
    )

    # ── ⑦ 季节（多选，支持跨季穿搭）──
    season_list = st.sidebar.multiselect(
        "🌤 季节（可多选）",
        SEASONS,
        key="cloth_season",
        help="可同时选择多个季节，如「春」「秋」适合过渡季穿着",
    )
    season = json.dumps(season_list, ensure_ascii=False) if season_list else ""

    # ── ⑧ 保存按钮（最底部）──
    st.sidebar.divider()
    submitted = st.sidebar.button(
        "✅ 保存到衣柜",
        use_container_width=True,
        key="cloth_submit",
    )

    if submitted:
        # 前端校验
        if uploaded_img is None:
            st.sidebar.error("❌ 请先上传一张照片！")
        elif not name.strip():
            st.sidebar.error("❌ 请填写衣服名称！")
        elif material_preset == "其他" and not material:
            st.sidebar.error("❌ 请填写自定义材质名称！")
        else:
            try:
                # 保存图片（返回相对路径）
                img_path = save_uploaded_image(uploaded_img, "clothes")

                # 清理临时文件
                if tmp_path and os.path.exists(tmp_path):
                    os.remove(tmp_path)

                # 写入数据库
                db.add_clothing(
                    img_path,
                    name.strip(),
                    category,
                    material,
                    color_hex,
                    season,
                )
                st.sidebar.success(f"✅「{name}」已加入衣柜！")

                # 提交成功后重置所有字段
                st.session_state.cloth_name = ""
                st.session_state.cloth_category = "上衣"
                st.session_state.cloth_material_preset = ""
                st.session_state.cloth_material_custom = ""
                st.session_state.cloth_color = "#CCCCCC"
                st.session_state.cloth_season = []
                # 清除上传的图片（需要删 key 让 file_uploader 重置）
                if "cloth_upload" in st.session_state:
                    del st.session_state["cloth_upload"]
                st.rerun()

            except RuntimeError as e:
                st.sidebar.error(str(e))
            except Exception as e:
                st.sidebar.error(f"❌ 保存失败，请重试：{e}")

            # 即使出错也尝试清理临时文件
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


# ╔══════════════════════════════════════════════════════════╗
# ║  饰品录入表单                                           ║
# ╚══════════════════════════════════════════════════════════╝

elif upload_type == "💍 饰品":
    with st.sidebar.form("accessory_form", clear_on_submit=True):
        uploaded_img = st.file_uploader(
            "📷 上传饰品照片",
            type=["jpg", "jpeg", "png", "webp"],
            key="acc_upload",
            help="建议在纯色背景上拍摄，便于取色",
        )

        auto_color = "#CCCCCC"
        color_auto_detected = False

        if uploaded_img is not None:
            try:
                st.image(uploaded_img, use_container_width=True)
            except Exception as e:
                st.warning(f"⚠️ 图片预览失败：{e}")

            tmp_dir = os.path.join(UPLOAD_DIR, "accessories")
            tmp_path = os.path.join(tmp_dir, f"_tmp_{uploaded_img.name}")
            os.makedirs(tmp_dir, exist_ok=True)

            try:
                with open(tmp_path, "wb") as f:
                    f.write(uploaded_img.getbuffer())

                if COLORTHIEF_AVAILABLE:
                    try:
                        auto_color = extract_dominant_color(tmp_path)
                        if auto_color != "#CCCCCC":
                            color_auto_detected = True
                    except Exception as e:
                        st.warning(f"⚠️ 颜色提取失败：{e}")

                if color_auto_detected:
                    st.markdown(
                        f'<div class="color-status success">'
                        f'🎨 已自动提取主色：{auto_color}'
                        f'<span class="color-dot" style="background:{auto_color};margin-left:8px;"></span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
                elif not COLORTHIEF_AVAILABLE:
                    st.markdown(
                        '<div class="color-status fallback">'
                        '⚠️ colorthief 库未安装，请使用下方颜色选择器手动选色</div>',
                        unsafe_allow_html=True,
                    )
            except OSError as e:
                st.error(f"❌ 暂存图片失败：{e}")

        name     = st.text_input("💍 名称", placeholder="例如：珍珠耳环")
        part     = st.selectbox("📍 佩戴部位", PARTS)
        material = st.text_input(
            "🧵 材质", placeholder="例如：银、珍珠",
            help="饰品材质多样，支持自由输入",
        )
        color_hex = st.color_picker(
            "🎨 颜色",
            value=auto_color if color_auto_detected else "#CCCCCC",
        )
        season_list = st.multiselect("🌤 季节（可多选）", SEASONS)
        season = json.dumps(season_list, ensure_ascii=False) if season_list else ""

        submitted = st.form_submit_button("✅ 保存饰品", use_container_width=True)

        if submitted:
            if uploaded_img is None:
                st.error("❌ 请先上传一张照片！")
            elif not name.strip():
                st.error("❌ 请填写饰品名称！")
            else:
                try:
                    img_path = save_uploaded_image(uploaded_img, "accessories")
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    db.add_accessory(img_path, name.strip(), part, material, color_hex, season)
                    st.success(f"✅「{name}」已加入饰品库！")
                    st.rerun()
                except RuntimeError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"❌ 保存失败，请重试：{e}")
                tmp_path_check = os.path.join(UPLOAD_DIR, "accessories", f"_tmp_{uploaded_img.name}")
                if os.path.exists(tmp_path_check):
                    try:
                        os.remove(tmp_path_check)
                    except OSError:
                        pass


# ╔══════════════════════════════════════════════════════════╗
# ║  灵感图录入表单                                         ║
# ╚══════════════════════════════════════════════════════════╝

else:  # "✨ 灵感图"
    with st.sidebar.form("inspiration_form", clear_on_submit=True):
        uploaded_img = st.file_uploader(
            "📷 上传灵感图片",
            type=["jpg", "jpeg", "png", "webp"],
            key="insp_upload",
            help="街拍、杂志翻拍、色板截图……任何给你穿搭灵感的图片",
        )

        if uploaded_img is not None:
            try:
                st.image(uploaded_img, use_container_width=True)
            except Exception as e:
                st.warning(f"⚠️ 图片预览失败：{e}")

        title     = st.text_input("✨ 标题", placeholder="例如：日系通勤风")
        insp_type = st.selectbox("📂 灵感类型", [""] + INSP_TYPES)

        # 姿势标签（用于"拍照姿势"类型，其他类型可忽略）
        pose_selected = st.multiselect(
            "📸 姿势标签",
            options=POSE_PRESETS,
            placeholder="选择拍照姿势标签（可多选）",
            help="选择这张图片展示的拍照姿势，仅对「📸 拍照姿势」类型生效",
        )
        tags_raw  = st.text_input(
            "🏷 标签",
            placeholder="多个标签用逗号分隔，例如：波点,条纹,通勤",
            help="逗号分隔的标签，保存后以彩色徽章显示在灵感墙",
        )

        submitted = st.form_submit_button("✅ 保存灵感", use_container_width=True)

        if submitted:
            if uploaded_img is None:
                st.error("❌ 请先上传一张图片！")
            elif not title.strip():
                st.error("❌ 请填写灵感标题！")
            else:
                try:
                    img_path = save_uploaded_image(uploaded_img, "inspirations")

                    # 解析标签
                    tag_list = (
                        [t.strip() for t in tags_raw.split(",") if t.strip()]
                        if tags_raw else []
                    )
                    tags_json = json.dumps(tag_list, ensure_ascii=False)

                    # 姿势标签（仅拍照姿势类型保存）
                    pose_tags_json = json.dumps(
                        pose_selected if insp_type == "📸 拍照姿势" else [],
                        ensure_ascii=False,
                    )

                    insp_id = db.add_inspiration(
                        img_path, title.strip(), insp_type,
                        tags=tags_json, pose_tags=pose_tags_json,
                    )

                    # Auto-extract color palette from inspiration image
                    abs_path = resolve_image_path(img_path)
                    if os.path.exists(abs_path) and COLORTHIEF_AVAILABLE:
                        try:
                            palette = extract_palette(abs_path, count=5)
                            if palette:
                                palette_json = json.dumps(palette, ensure_ascii=False)
                                db.update_inspiration_colors(insp_id, palette_json)
                        except Exception:
                            pass  # Color extraction is best-effort, not critical

                    st.success(f"✅「{title}」已加入灵感墙！")
                    st.rerun()

                except RuntimeError as e:
                    st.error(str(e))
                except Exception as e:
                    st.error(f"❌ 保存失败，请重试：{e}")


# ── 侧边栏底部：星座设置 ──
st.sidebar.divider()
st.sidebar.markdown("#### ♈ 星座幸运色")
if "zodiac_sign" not in st.session_state:
    st.session_state.zodiac_sign = ""
zodiac = st.sidebar.selectbox(
    "我的星座",
    [""] + ZODIAC_SIGNS,
    index=0 if not st.session_state.zodiac_sign
    else ZODIAC_SIGNS.index(st.session_state.zodiac_sign) + 1,
    key="zodiac_select",
    format_func=lambda x: x or "未设置",
)
if zodiac:
    st.session_state.zodiac_sign = zodiac

# ═══════════════════════════════════════════
#  主区域 —— 三个 Tab
# ═══════════════════════════════════════════

st.title("👗 Style Vault")
st.caption("我的个人穿搭素材库 —— 记录每一件心爱之物与灵感瞬间")

# ═══════════════════════════════════════════
#  天气模块（高德 API 自动获取 + 手动备选）
# ═══════════════════════════════════════════

WEATHER_OPTIONS = ["☀️ 晴天", "☁️ 多云", "🌧️ 雨天", "❄️ 下雪"]

# 高德天气文本 → emoji+中文映射
AMAP_WEATHER_MAP = {
    "晴": ("☀️", "晴天"), "少云": ("☀️", "晴天"),
    "多云": ("☁️", "多云"), "阴": ("☁️", "多云"),
    "小雨": ("🌧️", "雨天"), "中雨": ("🌧️", "雨天"), "大雨": ("🌧️", "雨天"),
    "暴雨": ("🌧️", "雨天"), "大暴雨": ("🌧️", "雨天"),
    "雷阵雨": ("🌧️", "雨天"), "阵雨": ("🌧️", "雨天"),
    "小雪": ("❄️", "下雪"), "中雪": ("❄️", "下雪"), "大雪": ("❄️", "下雪"),
    "暴雪": ("❄️", "下雪"), "雨夹雪": ("❄️", "下雪"),
    "雾": ("🌫️", "多云"), "霾": ("🌫️", "多云"),
    "浮尘": ("🌫️", "多云"), "扬沙": ("🌫️", "多云"),
}


def _fetch_amap_weather(city):
    """Fetch real-time weather from Amap API (with debug output)."""
    import json as _json

    # Step 1: Check API Key
    try:
        api_key = st.secrets["AMAP_API_KEY"]
        st.write(f"✅ 高德 Key 已读取: {api_key[:8]}...")
    except KeyError:
        st.error("❌ 未找到 AMAP_API_KEY，请在 .streamlit/secrets.toml 中配置")
        return None

    if not api_key or api_key == "你的高德Key":
        st.error("❌ API Key 未配置，请替换 .streamlit/secrets.toml 中的 '你的高德Key'")
        return None

    # Step 2: Build request
    url = "https://restapi.amap.com/v3/weather/weatherInfo"
    params = {"city": city, "key": api_key, "extensions": "base"}
    st.write(f"📍 请求: {url}?city={city}&key={api_key[:8]}...")

    # Step 3: Send request
    try:
        st.write("⏳ 正在请求天气数据...")
        resp = requests.get(url, params=params, timeout=5)
        st.write(f"📡 HTTP 状态码: {resp.status_code}")

        # Step 4: Parse response
        data = resp.json()
        st.write(f"📦 响应: {_json.dumps(data, ensure_ascii=False)[:300]}")

        # Step 5: Check result
        if data.get("status") == "1" and data.get("lives"):
            live = data["lives"][0]
            weather_text = live.get("weather", "晴")
            emoji, text = AMAP_WEATHER_MAP.get(weather_text, ("🌤", weather_text))
            result = {
                "temperature": int(live.get("temperature", "25")),
                "weather_icon": emoji,
                "weather_text": text,
                "weather_full": f"{emoji} {text}",
            }
            st.success(
                f"✅ 获取成功：{live.get('city', city)} "
                f"{result['weather_full']} {result['temperature']}°C "
                f"(湿度{live.get('humidity','--')}%)"
            )
            return result
        else:
            st.error(f"❌ 高德 API 错误: {data.get('info', data.get('message', '未知'))}")
            st.info("💡 请检查：1) API Key 是否正确 2) 城市名格式")
            return None

    except requests.exceptions.Timeout:
        st.error("❌ 请求超时（5秒），请检查网络")
        return None
    except requests.exceptions.ConnectionError:
        st.error("❌ 网络连接失败")
        return None
    except Exception as e:
        st.error(f"❌ 请求异常: {e}")
        return None


# 初始化 session_state
for key, default in [
    ("weather_city", ""),
    ("weather_temp", 25),
    ("weather_cond", "☀️ 晴天"),
    ("weather_confirmed", False),
    ("weather_auto_failed", False),
    ("weather_updated_at", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ── 天气卡片 ──
weather_container = st.container()
with weather_container:
    # Step 1: City input (first time or switch city)
    if not st.session_state.weather_city:
        with st.expander("☀️ 设置城市以获取天气", expanded=True):
            c1, c2 = st.columns([2, 1])
            with c1:
                city_input = st.text_input("城市名称", placeholder="例如：乐山、北京、上海",
                                           key="weather_city_input")
            with c2:
                st.write("")
                if st.button("✓ 确认城市", use_container_width=True) and city_input.strip():
                    st.session_state.weather_city = city_input.strip()
                    st.rerun()

    else:
        # Step 2: Try auto-fetch weather
        weather_data = None
        if not st.session_state.weather_confirmed or st.session_state.weather_auto_failed:
            weather_data = _fetch_amap_weather(st.session_state.weather_city)

        if weather_data:
            # Auto-fetch succeeded → store and confirm
            st.session_state.weather_temp = weather_data["temperature"]
            st.session_state.weather_cond = weather_data["weather_full"]
            st.session_state.weather_confirmed = True
            st.session_state.weather_auto_failed = False
            st.session_state.weather_updated_at = time.strftime("%H:%M")
            st.rerun()

        # Step 3: Display weather or fallback form
        if not st.session_state.weather_confirmed or st.session_state.weather_auto_failed:
            # Manual fallback
            with st.expander("☀️ 今日天气（手动输入）", expanded=True):
                if st.session_state.weather_auto_failed:
                    st.warning(f"⚠️ {st.session_state.weather_city} 自动获取失败，请手动输入")

                wcol1, wcol2, wcol3, wcol4 = st.columns([1, 1, 1, 1])
                with wcol1:
                    temp = st.number_input("温度 ℃", -30, 50,
                                           st.session_state.weather_temp, step=1,
                                           key="weather_temp_input")
                with wcol2:
                    cond = st.selectbox("天气", WEATHER_OPTIONS,
                                        index=WEATHER_OPTIONS.index(st.session_state.weather_cond)
                                        if st.session_state.weather_cond in WEATHER_OPTIONS else 0,
                                        key="weather_cond_input")
                with wcol3:
                    st.write("")
                    if st.button("✓ 确认天气", use_container_width=True):
                        st.session_state.weather_temp = temp
                        st.session_state.weather_cond = cond
                        st.session_state.weather_confirmed = True
                        st.session_state.weather_auto_failed = False
                        st.rerun()
                with wcol4:
                    st.write("")
                    if st.button("🔄 重试自动获取", use_container_width=True):
                        st.session_state.weather_auto_failed = False
                        st.rerun()
        else:
            # Confirmed → show weather display
            col_a, col_b, col_c = st.columns([3, 1, 1])
            with col_a:
                st.success(
                    f"☀️ {st.session_state.weather_city} · "
                    f"{st.session_state.weather_cond} · "
                    f"{st.session_state.weather_temp}°C"
                )
            with col_b:
                if st.button("🔄 刷新天气", use_container_width=True):
                    st.session_state.weather_auto_failed = False
                    st.session_state.weather_confirmed = False
                    st.rerun()
            with col_c:
                if st.button("📍 切换城市", use_container_width=True):
                    st.session_state.weather_city = ""
                    st.session_state.weather_confirmed = False
                    st.rerun()

            if st.session_state.weather_updated_at:
                st.caption(f"最后更新：今天 {st.session_state.weather_updated_at}")

# ── 星座幸运色行（天气下方）──
if st.session_state.zodiac_sign:
    lucky_hex, lucky_name = get_today_lucky_color(st.session_state.zodiac_sign)

    lc1, lc2 = st.columns([3, 1])
    with lc1:
        st.markdown(
            f"♈ {st.session_state.zodiac_sign} · "
            f"今日幸运色："
            f'<span class="color-dot" style="background:{lucky_hex};width:20px;height:20px;margin:0 6px;"></span>'
            f"<b>{lucky_name}</b>",
            unsafe_allow_html=True,
        )
    with lc2:
        if st.button("✨ 查看幸运色单品", key="lucky_search", use_container_width=True):
            st.session_state.active_filter_color = lucky_hex
            st.rerun()

# ── 穿搭推荐区（确认天气后自动显示）──
if st.session_state.weather_confirmed:
    st.divider()
    st.subheader("✨ 今日穿搭推荐")

    t = st.session_state.weather_temp
    w = st.session_state.weather_cond

    # ── 天气规则引擎 ──
    recommend_filter = None
    recommend_season = None
    recommend_msg = ""
    is_cold = t < 10
    is_hot = t > 30
    is_rain = "雨" in w

    if is_rain and is_cold:
        recommend_msg = "🌧️ 雨天低温，推荐防水外套 + 非拖地裤装"
        recommend_filter = {"material_exclude": ["丝绸", "羊毛"]}
        recommend_season = "冬"
    elif is_hot:
        recommend_msg = "🔥 高温天气，推荐轻薄夏装"
        recommend_filter = {"material_exclude": ["羊毛"]}
        recommend_season = "夏"
    elif 10 <= t <= 25:
        recommend_msg = "🌤 舒适气温，自动搭配成套方案"
        month = date.today().month
        if month in [3, 4, 5]: recommend_season = "春"
        elif month in [6, 7, 8]: recommend_season = "夏"
        elif month in [9, 10, 11]: recommend_season = "秋"
        else: recommend_season = "冬"
    elif t < 5:
        recommend_msg = "❄️ 寒冷天气，推荐叠穿搭配"
        recommend_season = "冬"

    st.caption(recommend_msg)

    # ── 自动生成 3 套穿搭方案 ──
    try:
        # Get available clothes by category
        all_active = db.get_all_clothes(active_only=True)

        # Filter by season (check JSON season array)
        def _match_season(item_season, target):
            if not target: return True
            try:
                sl = json.loads(item_season) if item_season and item_season.startswith("[") else [item_season]
                return target in sl or "四季" in sl
            except Exception:
                return True

        season_filtered = [c for c in all_active if _match_season(c.get("season",""), recommend_season)]

        # Filter by material exclusion
        if recommend_filter and recommend_filter.get("material_exclude"):
            season_filtered = [c for c in season_filtered
                               if c.get("material") not in recommend_filter["material_exclude"]]

        # Exclude recently worn (last 3 days)
        three_days_ago = (date.today() - timedelta(days=3)).isoformat()
        fresh = [c for c in season_filtered
                 if not c.get("last_wear_date") or c["last_wear_date"] < three_days_ago]
        if not fresh:
            fresh = season_filtered  # fallback if all were recently worn

        # ── Preference-based scoring ──
        # Load user preferences from wear history
        # Inline to avoid pycache import issues
        try:
            conn = db.get_connection(); cur = conn.cursor()
            cur.execute("SELECT COUNT(*) FROM wear_history"); history_count = cur.fetchone()[0]
            conn.close()
        except Exception:
            history_count = 0
        fav_colors, fav_materials = set(), set()
        if history_count >= 10:
            try:
                conn = db.get_connection(); cur = conn.cursor()
                cur.execute("SELECT c.color_hex, COUNT(*) AS cnt FROM wear_history wh JOIN clothes c ON wh.clothes_id=c.id WHERE c.color_hex IS NOT NULL AND c.color_hex!='' AND c.color_hex!='#CCCCCC' GROUP BY c.color_hex ORDER BY cnt DESC LIMIT 5")
                fav_colors = {r[0] for r in cur.fetchall()}
                cur.execute("SELECT c.material, COUNT(*) AS cnt FROM wear_history wh JOIN clothes c ON wh.clothes_id=c.id WHERE c.material IS NOT NULL AND c.material!='' GROUP BY c.material ORDER BY cnt DESC LIMIT 5")
                fav_materials = {r[0] for r in cur.fetchall()}
                conn.close()
            except Exception:
                pass

        def _score_item(item):
            """Score an item based on user preference. Higher = more likely to be picked."""
            s = item.get("wear_count", 0) * 2  # base: frequency
            if item.get("color_hex") in fav_colors: s += 10
            if item.get("material") in fav_materials: s += 8
            return max(s, 1)  # minimum weight 1

        def _weighted_pick(items):
            """Randomly pick from items, weighted by preference score."""
            if not items: return None
            if len(items) == 1: return items[0]
            weights = [_score_item(c) for c in items]
            total = sum(weights)
            r = random.uniform(0, total)
            cumulative = 0
            for item, w in zip(items, weights):
                cumulative += w
                if r <= cumulative:
                    return item
            return items[-1]

        # Categorize
        tops = [c for c in fresh if c["category"] == "上衣"]
        bottoms = [c for c in fresh if c["category"] in ("下装", "连衣裙")]
        outers = [c for c in fresh if c["category"] == "外套"]
        shoes = [c for c in fresh if c["category"] == "鞋履"]

        # Temperature-based category logic
        if is_hot:
            outers = []  # no outerwear in hot weather
        elif is_cold and outers:
            tops = tops  # keep tops for layering
        if is_rain and outers:
            tops = tops  # need both top and outer

        if tops or bottoms:
            st.markdown("##### 👗 今日穿搭方案（3套）")

            generated = []
            for i in range(3):
                top = _weighted_pick(tops) if tops else None
                bottom = _weighted_pick(bottoms) if bottoms else None
                # If dress, skip bottom (dress is both)
                if bottom and bottom["category"] == "连衣裙":
                    pass  # dress can be worn alone
                outer = _weighted_pick(outers) if outers and (is_cold or is_rain) else None
                shoe = _weighted_pick(shoes) if shoes else None

                # Skip duplicate combinations
                key = tuple(c["id"] for c in [top, bottom, outer, shoe] if c)
                if key in [g[0] for g in generated]:
                    continue

                # Build outfit items list for display
                items = [c for c in [top, bottom, outer, shoe] if c]
                generated.append((key, items))

                if len(generated) >= 3:
                    generated = generated[:3]
                    break

            for gi, (key, items) in enumerate(generated[:3]):
                st.markdown(f"**方案 {gi + 1}**")

                # Display items in a row
                ic_cols = st.columns(len(items) + 1)
                colors_for_palette = []
                for ii, item in enumerate(items):
                    with ic_cols[ii]:
                        img_abs = resolve_image_path(item["image_path"])
                        if os.path.exists(img_abs):
                            try:
                                st.image(img_abs, use_container_width=True)
                            except Exception:
                                st.caption("📷")
                        dot = color_dot_html(item.get("color_hex", "#CCC"))
                        st.markdown(
                            f"{dot} <small>{item['name']}<br>({item['category']})</small>",
                            unsafe_allow_html=True,
                        )
                        if item.get("color_hex") and item["color_hex"] != "#CCCCCC":
                            colors_for_palette.append(item["color_hex"])

                # Save button
                with ic_cols[-1]:
                    st.write("")
                    st.write("")
                    palette = average_color(colors_for_palette) if colors_for_palette else "#CCCCCC"
                    outfit_label = f"今日推荐{gi+1} · {t}°C"
                    if st.button(f"💾 保存这套", key=f"save_gen_outfit_{gi}_{t}",
                                 use_container_width=True):
                        try:
                            oid = db.create_outfit(
                                name=outfit_label,
                                season=recommend_season or "",
                                color_palette=palette,
                            )
                            for layer_idx, item in enumerate(items):
                                db.add_outfit_detail(
                                    oid, "clothes", item["id"], layer=layer_idx + 1,
                                )
                            st.success(f"✅「{outfit_label}」已保存！")
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))

                st.caption("---")

        else:
            st.info("衣柜中还没有足够的衣服来生成搭配，先在侧边栏录入几件吧 ✨")

    except RuntimeError as e:
        st.warning(f"推荐加载失败：{e}")

    # ── 穿搭报告（仅确认天气时显示）──
    try:
        # Inline trends queries to avoid pycache issues
        try:
            conn_t = db.get_connection(); cur_t = conn_t.cursor()
            cur_t.execute("SELECT COUNT(*) FROM wear_history"); h_count = cur_t.fetchone()[0]
            conn_t.close()
        except Exception:
            h_count = 0

        if h_count > 0:
            with st.expander("📊 穿搭趋势报告", expanded=False):
                if h_count < 10:
                    st.caption(f"已学习你的 {h_count} 条穿搭记录，数据越多推荐越精准 ✨")
                else:
                    st.caption(f"已学习你的 {h_count} 条穿搭记录，推荐越来越懂你了 ✨")

                col_a, col_b, col_c = st.columns(3)

                # Fetch all trend data in one connection
                try:
                    conn_t = db.get_connection(); cur_t = conn_t.cursor()
                    # Categories
                    cur_t.execute("SELECT c.category, COUNT(*) AS cnt FROM wear_history wh JOIN clothes c ON wh.clothes_id=c.id WHERE c.category IS NOT NULL AND c.category!='' GROUP BY c.category ORDER BY cnt DESC LIMIT 5")
                    fav_cats = [{"category": r[0], "cnt": r[1]} for r in cur_t.fetchall()]
                    # Materials
                    cur_t.execute("SELECT c.material, COUNT(*) AS cnt FROM wear_history wh JOIN clothes c ON wh.clothes_id=c.id WHERE c.material IS NOT NULL AND c.material!='' GROUP BY c.material ORDER BY cnt DESC LIMIT 5")
                    fav_mats = [{"material": r[0], "cnt": r[1]} for r in cur_t.fetchall()]
                    # Colors
                    cur_t.execute("SELECT c.color_hex, COUNT(*) AS cnt FROM wear_history wh JOIN clothes c ON wh.clothes_id=c.id WHERE c.color_hex IS NOT NULL AND c.color_hex!='' AND c.color_hex!='#CCCCCC' GROUP BY c.color_hex ORDER BY cnt DESC LIMIT 5")
                    fav_cols = [{"color_hex": r[0], "cnt": r[1]} for r in cur_t.fetchall()]
                    # Most worn
                    cur_t.execute("SELECT c.id, c.name, c.category, c.color_hex, c.image_path, COUNT(wh.id) AS wear_times FROM wear_history wh JOIN clothes c ON wh.clothes_id=c.id GROUP BY c.id ORDER BY wear_times DESC LIMIT 5")
                    top_items = [dict(r) for r in cur_t.fetchall()]
                    conn_t.close()
                except Exception:
                    fav_cats, fav_mats, fav_cols, top_items = [], [], [], []

                with col_a:
                    if fav_cats:
                        st.markdown("**👕 常穿品类**")
                        st.bar_chart({r["category"]: r["cnt"] for r in fav_cats}, use_container_width=True)

                with col_b:
                    if fav_mats:
                        st.markdown("**🧵 偏好材质**")
                        st.bar_chart({r["material"]: r["cnt"] for r in fav_mats}, use_container_width=True)

                with col_c:
                    if fav_cols:
                        st.markdown("**🎨 常用颜色**")
                        for r in fav_cols:
                            hex_c = r["color_hex"]
                            name = COLOR_NAME_MAP.get(hex_c, hex_c)
                            st.markdown(
                                f'<span class="color-dot" style="background:{hex_c};'
                                f'width:14px;height:14px;"></span> '
                                f'{name} · <b>{r["cnt"]}次</b>',
                                unsafe_allow_html=True,
                            )

                if top_items:
                    st.markdown("**🏆 最常穿单品 Top5**")
                    tcols = st.columns(5)
                    for ti, item in enumerate(top_items[:5]):
                        with tcols[ti]:
                            img_abs = resolve_image_path(item["image_path"])
                            if os.path.exists(img_abs):
                                try:
                                    st.image(img_abs, use_container_width=True)
                                except Exception:
                                    st.caption("📷")
                            st.caption(f"{item['name']} · {item['wear_times']}次")
    except RuntimeError:
        pass

st.divider()

tab_clothes, tab_accessories, tab_inspirations, tab_outfits = st.tabs(
    ["👕 衣柜", "💍 饰品库", "✨ 灵感墙", "🧵 搭配工坊"]
)


# ╔══════════════════════════════════════════════════════════╗
# ║  Tab 1: 衣柜 —— 筛选栏 + 四列网格 + 单件操作            ║
# ╚══════════════════════════════════════════════════════════╝

with tab_clothes:

    # ── 筛选栏 ──
    # 筛选逻辑采用"多条件 AND 叠加"模式：
    # - 选了品类 → 只看该品类
    # - 选了材质 → 同时满足品类 AND 材质
    # - 选了季节 → 同时满足品类 AND 材质 AND 季节（IN 匹配）
    # - 所有筛选条件为空 → 显示全部

    with st.container():
        st.markdown("### 🔍 筛选条件")

        # 用 4 列布局放置筛选控件
        f_col1, f_col2, f_col3, f_col4 = st.columns([1, 1, 1.5, 0.6])

        with f_col1:
            # 动态获取 DB 中实际存在的品类（而非硬编码列表）
            # 这样用户自定义的品类也能出现在筛选器中
            try:
                cat_options = [""] + db.get_distinct_values("clothes", "category")
            except RuntimeError:
                cat_options = [""] + CATEGORIES  # 降级为硬编码列表
            filter_category = st.selectbox(
                "品类", cat_options,
                format_func=lambda x: x or "全部品类",
            )

        with f_col2:
            try:
                mat_options = [""] + db.get_distinct_values("clothes", "material")
            except RuntimeError:
                # 降级时排除"其他"（它只是表单触发器，不是真实的材质值）
                mat_options = [""] + [m for m in MATERIALS if m != "其他"]
            filter_material = st.selectbox(
                "材质", mat_options,
                format_func=lambda x: x or "全部材质",
            )

        with f_col3:
            # 季节是多选（用户可以同时筛选"适合春天或秋天"的衣服）
            filter_seasons = st.multiselect(
                "季节（可多选）", SEASONS,
                placeholder="全部季节",
                help="可同时选择多个季节，例如选「春」「秋」看过渡季衣物",
            )

        with f_col4:
            st.write("")
            st.write("")
            show_inactive = st.checkbox(
                "显示已清理", value=False,
                help="勾选后会显示已经标记为「已清理」的衣服",
            )

        # ── 颜色搜索行（动态读取衣柜中已有的颜色）──
        if "active_filter_color" not in st.session_state:
            st.session_state.active_filter_color = None

        try:
            # Inline query to avoid pycache import issues
            conn = db.get_connection()
            cur = conn.cursor()
            cur.execute(
                "SELECT DISTINCT color_hex FROM clothes "
                "WHERE color_hex IS NOT NULL AND color_hex != '' "
                "AND is_active = 1 ORDER BY color_hex"
            )
            existing_colors = [r[0] for r in cur.fetchall()]
            conn.close()
        except Exception:
            existing_colors = []

        if existing_colors:
            st.caption(f"🎨 按颜色筛选（衣柜中共 {len(existing_colors)} 种颜色，精确匹配）")
            # Show color swatches in a wrapping row
            cc_cols = st.columns(min(len(existing_colors), 12))
            for ci, c_hex in enumerate(existing_colors):
                col_idx = ci % len(cc_cols)
                # If more colors than columns, wrap to new rows
                if ci >= len(cc_cols) and ci % len(cc_cols) == 0:
                    cc_cols = st.columns(min(len(existing_colors) - ci, 12))
                with cc_cols[ci % len(cc_cols)]:
                    c_name = COLOR_NAME_MAP.get(c_hex, c_hex)
                    is_selected = (st.session_state.active_filter_color == c_hex)
                    border = "3px solid #2D4A3E" if is_selected else "2px solid #E8DDD5"
                    st.markdown(
                        f'<div style="background:{c_hex};width:28px;height:28px;'
                        f'border-radius:50%;margin:0 auto 2px;border:{border};'
                        f'box-shadow:{"0 0 0 2px #D4A89B" if is_selected else "none"};'
                        f'cursor:pointer;" title="{c_name} ({c_hex})"></div>',
                        unsafe_allow_html=True,
                    )
                    if st.button(c_name, key=f"color_dyn_{ci}", use_container_width=True):
                        if st.session_state.active_filter_color == c_hex:
                            st.session_state.active_filter_color = None  # toggle off
                        else:
                            st.session_state.active_filter_color = c_hex
                        st.rerun()

            # Clear button
            if st.session_state.active_filter_color:
                sel_name = COLOR_NAME_MAP.get(st.session_state.active_filter_color,
                                              st.session_state.active_filter_color)
                c1, c2 = st.columns([1, 11])
                with c1:
                    st.markdown(
                        f'<span class="color-dot" style="background:{st.session_state.active_filter_color};'
                        f'width:28px;height:28px;"></span>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.markdown(f"📌 当前筛选：**{sel_name}** · "
                                f"[✕ 清除](?clear_color)", unsafe_allow_html=True)
                    if st.button("✕ 清除颜色筛选", key="clear_color_filter"):
                        st.session_state.active_filter_color = None
                        st.rerun()
        else:
            st.caption("📭 衣柜还是空的，添加衣服后颜色筛选才会出现 🎨")

        filter_color = st.session_state.active_filter_color

    st.divider()

    # ── 查询数据库 ──
    try:
        clothes = db.get_all_clothes(
            category=filter_category,
            material=filter_material,
            seasons=filter_seasons if filter_seasons else None,
            active_only=not show_inactive,
        )
    except RuntimeError as e:
        st.error(str(e))
        clothes = []

    # ── 颜色筛选（精确匹配 color_hex == filter_color）──
    if filter_color and clothes:
        clothes = [c for c in clothes if c.get("color_hex") == filter_color]
    elif filter_color and not clothes:
        pass

    # ── 空状态 ──
    if not clothes:
        if filter_color:
            st.markdown(
                '<div class="empty-state">🎨 还没有这个颜色的衣服哦<br>'
                '<small>考虑添置一件吧 💡</small></div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                '<div class="empty-state">👔 你的衣柜还空空的<br>'
                '<small>在左侧边栏上传第一件衣服吧 ✨</small></div>',
                unsafe_allow_html=True,
            )
    else:
        # ── 四列网格渲染 ──
        # 网格布局算法：
        # 1. 按 COLS_PER_ROW = 4 分组
        # 2. 外层循环：每 4 件一组，st.columns(4) 创建一行
        # 3. 内层循环：在每列中渲染单件衣服卡片
        # 4. 最后一行不足 4 件时，剩余列为空（用 break 跳过）

        COLS_PER_ROW = 4
        for i in range(0, len(clothes), COLS_PER_ROW):
            # 创建一行（4 个等宽列）
            cols = st.columns(COLS_PER_ROW)

            for j in range(COLS_PER_ROW):
                idx = i + j
                if idx >= len(clothes):
                    break  # 最后一行不足 4 列，提前退出

                item = clothes[idx]

                with cols[j]:
                    # ── 渲染卡片 ──

                    # ① 图片：从相对路径解析绝对路径后显示
                    img_abs = resolve_image_path(item["image_path"])

                    try:
                        if os.path.exists(img_abs):
                            # st.image 内部用 Pillow 加载图片
                            st.image(img_abs, use_container_width=True)
                        else:
                            st.markdown(
                                '<div style="height:200px;background:#f5f5f5;border-radius:8px;'
                                'display:flex;align-items:center;justify-content:center;color:#bbb;">'
                                '📷 图片文件丢失</div>',
                                unsafe_allow_html=True,
                            )
                    except Exception as e:
                        # Pillow 可能无法解析损坏的图片
                        st.markdown(
                            f'<div style="height:200px;background:#f5f5f5;border-radius:8px;'
                            f'display:flex;align-items:center;justify-content:center;color:#bbb;">'
                            f'⚠️ 图片无法加载</div>',
                            unsafe_allow_html=True,
                        )

                    # ② 信息区：卡片的文字内容
                    color_dot = color_dot_html(item["color_hex"] or "#CCC")
                    inactive_badge = ' <span style="color:#e74c3c;">🔒已清理</span>' if not item["is_active"] else ''

                    # 穿着次数统计行
                    wear_info = f'<small>👟 穿着 <b>{item["wear_count"]}</b> 次'
                    if item["last_wear_date"]:
                        wear_info += f'  ·  最近：{item["last_wear_date"]}'
                    wear_info += '</small>'

                    st.markdown(
                        f'<div class="item-card">'
                        f'<strong>{color_dot} {item["name"]}</strong>{inactive_badge}<br>'
                        f'<small>📂 {item["category"]}  ·  '
                        f'🧵 {item["material"] or "—"}  ·  '
                        f'🌤 {_format_season_tags(item["season"])}</small><br>'
                        f'{wear_info}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # ③ 操作按钮行（3 个按钮并排）
                    btn_col1, btn_col2, btn_col3 = st.columns(3)

                    with btn_col1:
                        # "穿过"按钮 —— 穿着次数 +1，更新最后穿着日期
                        if st.button("👟 穿过", key=f"wear_{item['id']}", use_container_width=True):
                            try:
                                db.increment_wear_count(item["id"])
                                # Log wear history with current weather context
                                today_str = date.today().isoformat()
                                temp = st.session_state.get("weather_temp") if st.session_state.get("weather_confirmed") else None
                                cond = st.session_state.get("weather_cond") if st.session_state.get("weather_confirmed") else None
                                # Log wear history (inline to avoid pycache)
                                try:
                                    conn_w = db.get_connection(); cur_w = conn_w.cursor()
                                    cur_w.execute("INSERT INTO wear_history (clothes_id, wear_date, temperature, weather) VALUES (?,?,?,?)", (item["id"], today_str, temp, cond))
                                    conn_w.commit(); conn_w.close()
                                except Exception:
                                    pass
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))

                    with btn_col2:
                        # 切换在柜/已清理状态（软删除）
                        toggle_label = "🔓 召回" if not item["is_active"] else "🔒 清理"
                        if st.button(toggle_label, key=f"toggle_{item['id']}", use_container_width=True):
                            try:
                                db.toggle_clothing_active(item["id"])
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))

                    with btn_col3:
                        # 硬删除按钮
                        if st.button("🗑", key=f"del_c_{item['id']}", use_container_width=True,
                                     help="永久删除这条记录和对应的图片文件"):
                            try:
                                db.delete_clothing(item["id"])
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))

                    # ── 一衣多穿：显示包含该单品的搭配方案 ──
                    with st.expander(f"🔗 一衣多穿", expanded=False):
                        try:
                            related_outfits = db.get_outfits_by_item("clothes", item["id"])
                            if related_outfits:
                                for ro in related_outfits:
                                    col_a, col_b = st.columns([1, 4])
                                    with col_a:
                                        if ro.get("color_palette"):
                                            st.markdown(
                                                f'<span class="color-dot" style="background:{ro["color_palette"]};'
                                                f'width:24px;height:24px;display:inline-block;"></span>',
                                                unsafe_allow_html=True,
                                            )
                                    with col_b:
                                        st.caption(
                                            f"🧵 {ro['name']}  ·  "
                                            f"{ro.get('scene','')}  ·  "
                                            f"{ro.get('season','')}"
                                        )
                            else:
                                st.caption("还没有搭配方案包含这件衣服")
                        except RuntimeError as e:
                            st.caption(f"加载失败：{e}")


# ╔══════════════════════════════════════════════════════════╗
# ║  Tab 2: 饰品库 —— 按佩戴部位分组展示                     ║
# ╚══════════════════════════════════════════════════════════╝

with tab_accessories:

    try:
        accessories = db.get_all_accessories()
    except RuntimeError as e:
        st.error(str(e))
        accessories = []

    if not accessories:
        st.markdown(
            '<div class="empty-state">💍 饰品库还是空的<br>'
            '<small>在左侧边栏上传你的第一件饰品吧！</small></div>',
            unsafe_allow_html=True,
        )
    else:
        # ── 按佩戴部位分组渲染 ──
        # 遍历 PARTS 固定顺序（耳部→头部→颈部→手部），保证 UI 一致性
        # 分组算法：
        # 1. 用列表推导式过滤出当前部位的饰品
        # 2. 如果该部位没有饰品，跳过（不显示空分组标题）
        # 3. 有饰品则渲染分组标题 + 网格
        for part in PARTS:
            # 过滤出当前部位的饰品
            items = [a for a in accessories if a["part"] == part]
            if not items:
                continue  # 无饰品则跳过该分组

            # 分组标题（带底部边框线）
            st.markdown(f'<div class="group-header">📍 {part}</div>', unsafe_allow_html=True)

            # 四列网格（与衣柜一致的网格布局）
            COLS_PER_ROW = 4
            for i in range(0, len(items), COLS_PER_ROW):
                cols = st.columns(COLS_PER_ROW)
                for j in range(COLS_PER_ROW):
                    idx = i + j
                    if idx >= len(items):
                        break
                    item = items[idx]
                    with cols[j]:
                        # 图片
                        img_abs = resolve_image_path(item["image_path"])
                        try:
                            if os.path.exists(img_abs):
                                st.image(img_abs, use_container_width=True)
                            else:
                                st.markdown(
                                    '<div style="height:180px;background:#f5f5f5;border-radius:8px;'
                                    'display:flex;align-items:center;justify-content:center;color:#bbb;">'
                                    '📷 图片丢失</div>',
                                    unsafe_allow_html=True,
                                )
                        except Exception:
                            st.markdown(
                                '<div style="height:180px;background:#f5f5f5;border-radius:8px;'
                                'display:flex;align-items:center;justify-content:center;color:#bbb;">'
                                '⚠️ 图片无法加载</div>',
                                unsafe_allow_html=True,
                            )

                        # 信息卡片
                        color_dot = color_dot_html(item["color_hex"] or "#CCC")
                        st.markdown(
                            f'<div class="item-card">'
                            f'<strong>{color_dot} {item["name"]}</strong><br>'
                            f'<small>🧵 {item["material"] or "—"}  ·  🌤 {item["season"] or "—"}</small>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                        # 删除按钮
                        if st.button("🗑 删除", key=f"del_a_{item['id']}", use_container_width=True):
                            try:
                                db.delete_accessory(item["id"])
                                st.rerun()
                            except RuntimeError as e:
                                st.error(str(e))

            st.divider()


# ╔══════════════════════════════════════════════════════════╗
# ║  Tab 3: 灵感墙 —— 类型筛选 + 标签彩色徽章               ║
# ╚══════════════════════════════════════════════════════════╝

with tab_inspirations:

    # ── 灵感类型筛选 ──
    f_i1, f_i2 = st.columns([1, 1])
    with f_i1:
        insp_filter = st.selectbox(
            "筛选灵感类型",
            [""] + INSP_TYPES,
            format_func=lambda x: x or "全部类型",
            key="insp_filter",
        )
    with f_i2:
        # 姿势标签筛选（动态获取 DB 中已有的标签）
        try:
            pose_tag_options = _get_distinct_pose_tags()
        except RuntimeError:
            pose_tag_options = POSE_PRESETS
        pose_tag_filter = st.selectbox(
            "筛选姿势标签",
            [""] + pose_tag_options,
            format_func=lambda x: x or "全部姿势",
            key="pose_tag_filter",
        )

    st.divider()

    try:
        if pose_tag_filter:
            inspirations = db.get_all_inspirations(
                insp_type=insp_filter, pose_tag=pose_tag_filter,
            )
        else:
            inspirations = db.get_all_inspirations(insp_type=insp_filter)
    except RuntimeError as e:
        st.error(str(e))
        inspirations = []

    if not inspirations:
        st.markdown(
            '<div class="empty-state">✨ 灵感墙还是空的<br>'
            '<small>在左侧边栏上传你的第一张灵感图吧！</small></div>',
            unsafe_allow_html=True,
        )
    else:
        COLS_PER_ROW = 4
        for i in range(0, len(inspirations), COLS_PER_ROW):
            cols = st.columns(COLS_PER_ROW)
            for j in range(COLS_PER_ROW):
                idx = i + j
                if idx >= len(inspirations):
                    break
                item = inspirations[idx]
                with cols[j]:
                    # 图片
                    img_abs = resolve_image_path(item["image_path"])
                    try:
                        if os.path.exists(img_abs):
                            st.image(img_abs, use_container_width=True)
                        else:
                            st.markdown(
                                '<div style="height:220px;background:#f5f5f5;border-radius:8px;'
                                'display:flex;align-items:center;justify-content:center;color:#bbb;">'
                                '📷 图片丢失</div>',
                                unsafe_allow_html=True,
                            )
                    except Exception:
                        st.markdown(
                            '<div style="height:220px;background:#f5f5f5;border-radius:8px;'
                            'display:flex;align-items:center;justify-content:center;color:#bbb;">'
                            '⚠️ 图片无法加载</div>',
                            unsafe_allow_html=True,
                        )

                    # ── 标签渲染 ──
                    tags_html = ""
                    try:
                        tag_list = json.loads(item["tags"]) if item["tags"] else []
                        for ti, t in enumerate(tag_list):
                            tags_html += tag_badge_html(t, ti)
                    except (json.JSONDecodeError, TypeError):
                        pass

                    # ── 姿势标签渲染（仅拍照姿势类型）──
                    pose_html = ""
                    pose_list = []
                    try:
                        pose_list = json.loads(item.get("pose_tags", "[]")) if item.get("pose_tags") else []
                    except (json.JSONDecodeError, TypeError):
                        pass
                    if pose_list:
                        pose_html = "<br>" + " ".join(
                            tag_badge_html(p, i + 10) for i, p in enumerate(pose_list)
                        )

                    st.markdown(
                        f'<div class="item-card">'
                        f'<strong>{item["title"]}</strong><br>'
                        f'<small>📂 {item["type"] or "未分类"}</small><br>'
                        f'{tags_html}'
                        f'{pose_html}'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                    # --- 灵感匹配按钮 ---
                    # 点击后提取灵感图的 extracted_colors，在衣橱中查找色差最小的衣服
                    match_key = f"match_{item['id']}"
                    if st.button("🎯 匹配我的衣柜", key=match_key, use_container_width=True,
                                 help="根据这张灵感图的色调，找到衣橱中最匹配的衣服"):
                        st.session_state[match_key] = True

                    if st.session_state.get(match_key):
                        with st.status("🔍 正在匹配衣橱中的衣服...", expanded=True) as status:
                            try:
                                # 1. 获取灵感图的色板
                                colors_json = item.get("extracted_colors", "[]")
                                target_colors = json.loads(colors_json) if colors_json else []

                                # 如果没有预提取的色板，实时提取
                                if not target_colors and COLORTHIEF_AVAILABLE:
                                    img_abs = resolve_image_path(item["image_path"])
                                    if os.path.exists(img_abs):
                                        target_colors = extract_palette(img_abs, count=5)

                                if target_colors:
                                    # 2. 获取所有在柜衣服
                                    all_clothes = db.get_all_clothes(active_only=True)
                                    # 3. 计算色差匹配
                                    matched = find_closest_clothes(target_colors, all_clothes, top_n=5)

                                    if matched:
                                        st.success(f"🎯 找到 {len(matched)} 件色调匹配的衣服：")
                                        for m in matched:
                                            delta = m["_delta_e"]
                                            # 色差评级
                                            if delta < 50:
                                                grade = "🟢 极相似"
                                            elif delta < 120:
                                                grade = "🟡 较接近"
                                            else:
                                                grade = "🟠 略有关联"

                                            st.markdown(
                                                f'<div style="display:flex;align-items:center;gap:10px;'
                                                f'padding:6px;border:1px solid #eee;border-radius:8px;margin:4px 0;">'
                                                f'<span class="color-dot" style="background:{m["color_hex"]};"></span>'
                                                f'<span><strong>{m["name"]}</strong> '
                                                f'<small>({m["category"]}, ΔE={delta})</small></span>'
                                                f'<span style="margin-left:auto;">{grade}</span>'
                                                f'</div>',
                                                unsafe_allow_html=True,
                                            )
                                    else:
                                        st.info("未找到匹配的衣服，试试上传更多单品吧！")
                                else:
                                    st.warning("⚠️ 该灵感图暂无色板数据。"
                                               + ("请确保已安装 colorthief 库以自动提取颜色。" if not COLORTHIEF_AVAILABLE else ""))
                                status.update(label="匹配完成", state="complete")
                            except Exception as e:
                                st.error(f"❌ 匹配失败：{e}")

                    # 删除按钮
                    if st.button("🗑 删除", key=f"del_i_{item['id']}", use_container_width=True):
                        try:
                            db.delete_inspiration(item["id"])
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))


# ╔══════════════════════════════════════════════════════════╗
# ║  Tab 4: 搭配工坊 —— 单品库 + 画布 + 保存                ║
# ╚══════════════════════════════════════════════════════════╝

with tab_outfits:

    st.markdown("### 🧵 搭配工坊")
    st.caption("左侧浏览单品 → 点击添加 → 右侧画布排序 → 保存搭配方案")

    # Initialize canvas in session state
    if "outfit_canvas" not in st.session_state:
        st.session_state.outfit_canvas = []  # list of (item_type, item_id, layer)

    # Two-column layout: left = wardrobe browser, right = canvas
    left_col, right_col = st.columns([3, 2])

    # ── LEFT: Wardrobe Browser ──
    with left_col:
        st.markdown("#### 📦 单品库")

        # Sub-tabs for clothes vs accessories
        item_tab1, item_tab2 = st.tabs(["👕 衣服", "💍 饰品"])

        with item_tab1:
            # Quick filter for clothes
            cf_col1, cf_col2 = st.columns(2)
            with cf_col1:
                ws_cat = st.selectbox("品类", [""] + CATEGORIES, key="ws_cat",
                                      format_func=lambda x: x or "全部")
            with cf_col2:
                ws_season = st.selectbox("季节", [""] + SEASONS, key="ws_season",
                                         format_func=lambda x: x or "全部")

            try:
                ws_clothes = db.get_all_clothes(
                    category=ws_cat,
                    seasons=[ws_season] if ws_season else None,
                    active_only=True,
                )
            except RuntimeError:
                ws_clothes = []

            if ws_clothes:
                # 3-column grid
                for i in range(0, len(ws_clothes), 3):
                    ccols = st.columns(3)
                    for j in range(3):
                        idx = i + j
                        if idx >= len(ws_clothes):
                            break
                        c = ws_clothes[idx]
                        with ccols[j]:
                            img_abs = resolve_image_path(c["image_path"])
                            if os.path.exists(img_abs):
                                try:
                                    st.image(img_abs, use_container_width=True)
                                except Exception:
                                    st.caption("📷 无法加载")
                            else:
                                st.caption("📷 图片丢失")

                            st.caption(f"{c['name']} ({c['category']})")

                            # Check if already in canvas
                            already = any(
                                d[0] == "clothes" and d[1] == c["id"]
                                for d in st.session_state.outfit_canvas
                            )
                            if already:
                                st.success("✅ 已添加")
                            else:
                                if st.button("➕ 加入搭配", key=f"ws_add_c_{c['id']}",
                                             use_container_width=True):
                                    # Determine layer: clothes default to 2 (outer)
                                    st.session_state.outfit_canvas.append(
                                        ("clothes", c["id"], 2)
                                    )
                                    st.rerun()
            else:
                st.caption("衣柜为空，请先在侧边栏录入衣服")

        with item_tab2:
            try:
                ws_accessories = db.get_all_accessories()
            except RuntimeError:
                ws_accessories = []

            if ws_accessories:
                for i in range(0, len(ws_accessories), 3):
                    ccols = st.columns(3)
                    for j in range(3):
                        idx = i + j
                        if idx >= len(ws_accessories):
                            break
                        a = ws_accessories[idx]
                        with ccols[j]:
                            img_abs = resolve_image_path(a["image_path"])
                            if os.path.exists(img_abs):
                                try:
                                    st.image(img_abs, use_container_width=True)
                                except Exception:
                                    st.caption("📷 无法加载")
                            else:
                                st.caption("📷 图片丢失")

                            st.caption(f"{a['name']} ({a['part']})")

                            already = any(
                                d[0] == "accessories" and d[1] == a["id"]
                                for d in st.session_state.outfit_canvas
                            )
                            if already:
                                st.success("✅ 已添加")
                            else:
                                if st.button("➕ 加入搭配", key=f"ws_add_a_{a['id']}",
                                             use_container_width=True):
                                    # Accessories default to layer 3
                                    st.session_state.outfit_canvas.append(
                                        ("accessories", a["id"], 3)
                                    )
                                    st.rerun()
            else:
                st.caption("饰品库为空")

    # ── RIGHT: Canvas ──
    with right_col:
        st.markdown("#### 🎨 搭配画布")

        if not st.session_state.outfit_canvas:
            st.markdown(
                '<div class="empty-state" style="padding:40px 10px;">'
                '你的搭配画布还空空的<br>'
                '<small>单品将出现在此处</small></div>',
                unsafe_allow_html=True,
            )
        else:
            # Sort by layer
            canvas_sorted = sorted(
                enumerate(st.session_state.outfit_canvas),
                key=lambda x: x[1][2],  # sort by layer
            )

            # Collect colors for palette
            canvas_colors = []

            for original_idx, (item_type, item_id, layer) in canvas_sorted:
                # Fetch item details
                item_info = None
                try:
                    if item_type == "clothes":
                        item_info = db.get_clothing_by_id(item_id)
                    else:
                        # Get accessory info - we need a get_accessory_by_id function
                        # Using get_all_accessories and filtering
                        all_acc = db.get_all_accessories()
                        for acc in all_acc:
                            if acc["id"] == item_id:
                                item_info = acc
                                break
                except RuntimeError:
                    pass

                if item_info is None:
                    continue

                item_name = item_info.get("name", "未知")
                item_color = item_info.get("color_hex", "#CCC")
                if item_color and item_color != "#CCCCCC":
                    canvas_colors.append(item_color)
                item_img = resolve_image_path(item_info.get("image_path", ""))

                # Layer label
                layer_labels = {1: "🔹 内搭", 2: "🔸 外套/主件", 3: "🔺 配饰"}
                layer_label = layer_labels.get(layer, f"层级{layer}")

                # Mini card
                with st.container():
                    st.markdown(f"**{layer_label}**")

                    c1, c2, c3, c4 = st.columns([2, 3, 1, 1])
                    with c1:
                        if os.path.exists(item_img):
                            try:
                                st.image(item_img, width=60)
                            except Exception:
                                st.caption("📷")
                        else:
                            st.caption("📷")
                    with c2:
                        st.caption(item_name)
                        if item_color:
                            st.markdown(
                                f'<span class="color-dot" style="background:{item_color};"></span>'
                                f'<small>{item_color}</small>',
                                unsafe_allow_html=True,
                            )
                    with c3:
                        # Move up button
                        if layer > 1:
                            if st.button("⬆️", key=f"ws_up_{original_idx}",
                                         help="上移一层"):
                                st.session_state.outfit_canvas[original_idx] = (
                                    item_type, item_id, layer - 1
                                )
                                st.rerun()
                    with c4:
                        if st.button("✕", key=f"ws_rm_{original_idx}",
                                     help="从画布移除"):
                            st.session_state.outfit_canvas.pop(original_idx)
                            st.rerun()

            # Canvas action buttons
            st.divider()

            if st.button("🧹 清空画布", use_container_width=True):
                st.session_state.outfit_canvas = []
                st.rerun()

            # Calculate canvas average color
            canvas_palette = average_color(canvas_colors) if canvas_colors else "#CCCCCC"
            st.markdown(
                f'<div style="text-align:center;padding:8px;">'
                f'<span class="color-dot" style="background:{canvas_palette};width:24px;height:24px;"></span>'
                f'<small> 整体色调：{canvas_palette}</small></div>',
                unsafe_allow_html=True,
            )

            # Save outfit form
            st.markdown("#### 💾 保存搭配方案")
            outfit_name = st.text_input("搭配名称", key="outfit_name",
                                        placeholder="例如：周五通勤风")
            outfit_scene = st.selectbox("场景", [""] + ["通勤", "约会", "运动", "带娃"],
                                        key="outfit_scene")
            outfit_season_list = st.multiselect("季节（可多选）", SEASONS, key="outfit_season")
            outfit_season = json.dumps(outfit_season_list, ensure_ascii=False) if outfit_season_list else ""

            if st.button("💾 保存搭配", use_container_width=True, type="primary"):
                if not outfit_name.strip():
                    st.error("❌ 请填写搭配名称！")
                elif not st.session_state.outfit_canvas:
                    st.error("❌ 画布为空，请先添加单品！")
                else:
                    try:
                        # Create outfit
                        outfit_id = db.create_outfit(
                            name=outfit_name.strip(),
                            scene=outfit_scene,
                            season=outfit_season,
                            color_palette=canvas_palette,
                        )
                        # Add each canvas item
                        for item_type, item_id, layer in st.session_state.outfit_canvas:
                            db.add_outfit_detail(outfit_id, item_type, item_id, layer)

                        st.success(f"✅「{outfit_name}」搭配方案已保存！")
                        # Clear canvas
                        st.session_state.outfit_canvas = []
                        st.rerun()
                    except RuntimeError as e:
                        st.error(str(e))

        # ── Saved outfits gallery ──
        st.divider()
        st.markdown("#### 📚 已保存的搭配方案")

        try:
            all_outfits = db.get_all_outfits()
        except RuntimeError:
            all_outfits = []

        if all_outfits:
            for outfit in all_outfits:
                with st.expander(
                    f"🧵 {outfit['name']}  ·  {outfit.get('scene','')}  ·  {outfit.get('season','')}"
                ):
                    # Show palette
                    if outfit.get("color_palette"):
                        st.markdown(
                            f'<span class="color-dot" style="background:{outfit["color_palette"]};'
                            f'width:20px;height:20px;"></span> '
                            f'<small>色调：{outfit["color_palette"]}  ·  '
                            f'日期：{outfit.get("outfit_date","")}</small>',
                            unsafe_allow_html=True,
                        )

                    # Show items
                    try:
                        details = db.get_outfit_details(outfit["id"])
                        if details:
                            dcols = st.columns(min(len(details), 4))
                            for di, d in enumerate(details):
                                with dcols[di % len(dcols)]:
                                    img_p = resolve_image_path(d["item_image"])
                                    if os.path.exists(img_p):
                                        try:
                                            st.image(img_p, use_container_width=True)
                                        except Exception:
                                            st.caption("📷")
                                    st.caption(
                                        f'{d["item_name"]} '
                                        f'({d.get("item_category","")})'
                                    )
                    except RuntimeError:
                        st.caption("加载明细失败")

                    # Delete outfit button
                    if st.button("🗑 删除此搭配", key=f"del_outfit_{outfit['id']}"):
                        try:
                            db.delete_outfit(outfit["id"])
                            st.rerun()
                        except RuntimeError as e:
                            st.error(str(e))
        else:
            st.caption("✨ 还没有保存搭配方案，在画布中创建第一个吧")


# ═══════════════════════════════════════════
#  底部信息
# ═══════════════════════════════════════════

st.divider()
st.caption(
    "🛠 Style Vault v1.1 · Streamlit + SQLite · 所有数据存储在本地 · "
    "colorthief 自动取色" if COLORTHIEF_AVAILABLE else
    "🛠 Style Vault v1.1 · Streamlit + SQLite · 所有数据存储在本地 · "
    "手动颜色选择器"
)
