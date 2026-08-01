"""
手动天气输入界面 —— 用户自行填写城市、温度和天气状况。
数据存入 st.session_state，供穿搭推荐规则引擎使用。

════════════════════ 天气规则引擎 ════════════════════════
以下规则供后续"根据天气推荐穿搭"功能调用，通过读取
st.session_state 中的 temperature 和 weather_condition 来决策：

规则 1：雨天 + 温度 < 10°C
  → 排除拖地裤（category='下装' 且 length='长'）
  → 优先推荐防水外套（material IN ('化纤','混纺')）
  → 推荐鞋子类型为防滑/防水

规则 2：温度 > 30°C
  → 过滤羊毛材质（material='羊毛'）
  → 过滤冬季单品（season='冬'）
  → 优先推荐 season IN ('夏','四季') 的单品

规则 3：温度 10-25°C（舒适区间）
  → 推荐匹配当前季节的已保存搭配方案
  → 查找 outfits 表中 season 匹配的搭配

规则 4：温度 < 5°C
  → 优先推荐 season='冬' 的单品
  → 推荐 layer=1（内搭）+ layer=2（外套）的组合

数据存储格式（st.session_state）：
  city:              str   - 城市名称（可选，默认空）
  temperature:       int   - 温度值（℃）
  weather_condition: str   - 天气状况（☀️晴天/☁️多云/🌧️雨天/❄️下雪）
  weather_confirmed: bool  - 是否已确认天气
"""
import streamlit as st

st.set_page_config(page_title="今日天气", page_icon="🌤")

# ═══════════════════════════════════════════
#  常量
# ═══════════════════════════════════════════

WEATHER_OPTIONS = ["☀️ 晴天", "☁️ 多云", "🌧️ 雨天", "❄️ 下雪"]

# ═══════════════════════════════════════════
#  初始化 session_state
# ═══════════════════════════════════════════

if "city" not in st.session_state:
    st.session_state.city = ""
if "temperature" not in st.session_state:
    st.session_state.temperature = 25
if "weather_condition" not in st.session_state:
    st.session_state.weather_condition = "☀️ 晴天"
if "weather_confirmed" not in st.session_state:
    st.session_state.weather_confirmed = False

# ═══════════════════════════════════════════
#  页面
# ═══════════════════════════════════════════

st.title("☀️ 今日天气（手动输入）")

# ── 未确认 → 显示输入表单 ──
if not st.session_state.weather_confirmed:
    st.info("👆 请填写今日天气，用于穿搭推荐")

    with st.container():
        city = st.text_input(
            "城市",
            value=st.session_state.city,
            placeholder="例如：上海（可选）",
            help="可选填写，仅用于显示",
        )

        col1, col2 = st.columns(2)
        with col1:
            temperature = st.number_input(
                "温度",
                min_value=-30,
                max_value=50,
                value=st.session_state.temperature,
                step=1,
                format="%d",
                help="输入当前室外温度（℃）",
            )
            st.caption(f"{temperature} ℃")
        with col2:
            weather_condition = st.selectbox(
                "天气",
                options=WEATHER_OPTIONS,
                index=WEATHER_OPTIONS.index(st.session_state.weather_condition),
                help="选择当前天气状况",
            )

    if st.button("✓ 确认天气", use_container_width=True, type="primary"):
        st.session_state.city = city.strip()
        st.session_state.temperature = temperature
        st.session_state.weather_condition = weather_condition
        st.session_state.weather_confirmed = True
        st.rerun()

# ── 已确认 → 显示天气 + 重新输入按钮 ──
else:
    icon = st.session_state.weather_condition[0]  # 取 emoji
    city_part = f"{st.session_state.city} " if st.session_state.city else ""

    st.success(
        f"当前天气：{city_part}{icon} "
        f"{st.session_state.temperature}°C "
        f"{st.session_state.weather_condition[2:]}"  # 去掉 "☀️ " 前缀
    )

    if st.button("🔄 重新输入", use_container_width=True):
        st.session_state.weather_confirmed = False
        st.rerun()

# ═══════════════════════════════════════════
#  天气规则引擎说明（折叠）
# ═══════════════════════════════════════════

with st.expander("📋 天气推荐规则（开发参考）"):
    st.markdown("""
    | 条件 | 动作 |
    |------|------|
    | 🌧️ 雨天 + < 10°C | 排除拖地裤，推荐防水外套（化纤/混纺） |
    | 🔥 > 30°C | 过滤羊毛材质 + 冬季单品，优先夏/四季 |
    | 🌤 10-25°C | 匹配当前季节的已保存搭配 |
    | ❄️ < 5°C | 优先冬季单品，推荐内搭+外套组合 |
    """)

    if st.session_state.weather_confirmed:
        t = st.session_state.temperature
        w = st.session_state.weather_condition
        st.caption(f"当前触发规则：")
        if "雨" in w and t < 10:
            st.warning("🌧️❄️ 触发规则 1：雨天+低温 → 排除拖地裤，推荐防水外套")
        elif t > 30:
            st.warning("🔥 触发规则 2：高温 → 过滤羊毛+冬季单品，优先夏装")
        elif 10 <= t <= 25:
            st.success("🌤 触发规则 3：舒适温度 → 推荐匹配季节搭配")
        elif t < 5:
            st.info("❄️ 触发规则 4：低温 → 优先冬季单品+内搭外套组合")
