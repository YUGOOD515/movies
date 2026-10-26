# 🎬 CineVault — 基于 AList + DeepSeek AI + TMDB + MDBList 的智能影视媒体库

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-3.4-38bdf8.svg)](https://tailwindcss.com/)
[![uv](https://img.shields.io/badge/Managed_by-uv-purple.svg)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**CineVault** 是一个基于 **Python + Flask + Jinja2 + HTML + Tailwind CSS + JavaScript** 构建的全栈开源影视数据库管理系统，采用 **MVC (Model-View-Controller) + Connector** 架构设计，使用 `uv` 和 `git` 进行项目管理。

系统专为挂载在 **AList (`C:\alist`)** 中的**夸克网盘 / 百度网盘**影视资源打造，结合 **DeepSeek AI (`deepseek-flash`)** 自动处理网盘常见的防和谐字形变化（如**偏旁拆字**、**同形/形近字**、**同音谐音**、**穿插字母/假名/符号**），自动匹配 **TMDB** 与 **MDBList** 获取电影/剧集海报、每一季的海报、每一集的剧照、分集标题评分与透明艺术字 **LOGO**，并直接调用本地 **MPC-HC (`C:\Program Files\MPC-HC\mpc-hc64.exe`)** 播放器实现 4K HDR/杜比视界原盘秒播。

---

## ✨ 核心特性

1. **🔑 引导式密钥配置与一键添加影视**
   - 内置可视化 **密钥配置向导**（弹窗 + `/settings` 独立向导页），一步步引导用户配置并在线测试 **TMDB**、**MDBList**、**DeepSeek AI**、**AList** 与本地 **MPC-HC** 播放器。
   - 支持直接浏览 AList 网盘目录添加单部电影/剧集，或点击 **「一键智能扫描 AList 网盘」** 全自动入库。

2. **🧠 DeepSeek AI 网盘防和谐名称还原 (`LLMConnector`)**
   - 针对夸克网盘/百度网盘分享资源常见的防和谐改名，通过 AI 推理结合内层文件特征精准猜测原始片名：
     - **偏旁部首拆字还原**：`虫知-虫朱-亻夹` ➔ **《蜘蛛侠：崭新之日》** (*Spider-Man: Brand New Day*)
     - **同形字 / 形近异体字还原**：`R 人苼苆剨朮（2025）` ➔ **《人生切割术》** (*Severance*)
     - **同音谐音还原**：`【合.力.变.神.计.划】` ➔ **《河狸变身计划》** (*Hoppers*)
     - **穿插防和谐字符清理**：`长z安z的z荔z枝` ➔ **《长安的荔枝》**、`挽z救z计z划` ➔ **《挽救计划》**、`破か地か獄` ➔ **《破·地狱》**、`B 百丨年孤丨独` ➔ **《百年孤独》**、`鱿.鱼.游.戏` ➔ **《鱿鱼游戏》**

3. **🖼️ 全维度海报、分季海报、分集剧照与多平台评分 (`TMDBConnector` + `MDBListConnector`)**
   - 自动获取单部剧集/电影的**高清竖版主海报**、**横版巨幅背景海报 (Backdrop)** 以及**官方透明 PNG 艺术 LOGO**。
   - 针对剧集自动拉取**每一季的独立海报 (Season Poster)**、**每一集的高清剧照 (Episode Still)**、**每集标题**、**单集评分**与剧情简介。
   - 集成 **MDBList** 聚合 **IMDb**、**Rotten Tomatoes (烂番茄新鲜度/爆米花指数)**、**Metacritic**、**Letterboxd**、**Trakt** 与 **TMDB** 评分。

4. **🖥️ 主页横版巨幅海报轮播 & 本地 MPC-HC 直连播放 (`PlayerConnector`)**
   - 主页上方展示横版大型海报轮播图，叠加透明电影/剧集 LOGO 与多维评分，点击 **「立即调用 MPC-HC 播放」** 即可通过 AList 签名直链 (`/d/...?sign=...`) 唤起 `C:\Program Files\MPC-HC\mpc-hc64.exe` 直接播放。

5. **📺 剧集选季、选集、剧照小卡片与追剧进度跟踪**
   - 点开任意剧集可自由切换**每一季**（同步切换展示该季专属海报）与**每一集**。
   - 下方展示当前选中集剧照大卡与本季全集 **剧照小卡片 (Episode Still Cards)**。
   - 支持在主页与详情页实时进行 **追剧进度跟踪**（自动记录当前观看季/集、百分比进度条、`+1 集已看` 快捷打卡）。

6. **🎨 电影/剧集专属 LOGO 与后台切换管理 (`/admin`)**
   - 电影与剧集均拥有各自独立的透明 LOGO 与标题展示。
   - 提供完整的 **后台切换管理中心 (`/admin`)**：支持一键切换主页横版轮播、切换剧集/电影的透明 LOGO 与海报、切换默认展示季数、切换多网盘版本片源，以及重新搜索绑定 TMDB 条目。

---

## 🏗️ MVC + Connector 架构设计

```text
movies/
├── pyproject.toml                  # uv 项目与依赖配置
├── .env.example                    # 环境变量与密钥模板
├── run.py                          # 快速启动入口
├── src/movies/
│   ├── __init__.py                 # Flask 应用工厂 create_app()
│   ├── config.py                   # 配置管理
│   ├── extensions.py               # SQLAlchemy 实例
│   ├── models/                     # [Model 层] 数据模型
│   │   └── media.py                # Setting, MediaItem, Season, Episode
│   ├── connectors/                 # [Connector 层] 外部数据源与播放器连接器
│   │   ├── alist_connector.py      # AList API 认证、目录扫描、签名播放直链生成
│   │   ├── llm_connector.py        # DeepSeek AI (/responses & /chat/completions) 字形/谐音还原
│   │   ├── tmdb_connector.py       # TMDB API 海报、透明 LOGO、每季海报、每集剧照与评分
│   │   ├── mdblist_connector.py    # MDBList 多平台评分聚合 (IMDb / 烂番茄 / MC)
│   │   └── player_connector.py     # 本地 MPC-HC (C:\Program Files\MPC-HC\mpc-hc64.exe) 唤起器
│   ├── services/                   # [Service 层] 业务编排
│   │   └── library_service.py      # 智能网盘扫描、AI+TMDB+MDBList 刮削同步、播放与进度更新
│   ├── controllers/                # [Controller 层] 路由控制器
│   │   ├── page_controller.py      # 页面路由 (/, /media/<id>, /admin, /settings)
│   │   └── api_controller.py       # REST API (/api/play, /api/scan, /api/ai/guess, /api/progress 等)
│   ├── views/                      # [View 层] Jinja2 + Tailwind CSS 模板
│   │   ├── base.html               # 全局导航、密钥引导向导弹窗、添加影视弹窗
│   │   ├── index.html              # 主页横版海报轮播、追剧进度跟踪、剧集/电影专区、AI 识片看板
│   │   ├── detail.html             # 影视详情页、选季海报、选集与剧照小卡片
│   │   ├── admin.html              # 后台切换管理中心 (LOGO/标题/轮播/片源/TMDB 重匹配)
│   │   └── settings.html           # 独立 API 密钥引导设置页
│   └── static/                     # 静态资源 (Tailwind 扩展样式与前端交互逻辑)
└── tests/
    └── test_app.py                 # Pytest 自动化测试套件
```

---

## 🚀 快速开始

### 1. 环境要求
- **Python**: `>= 3.12` + [`uv`](https://docs.astral.sh/uv/)
- **AList**: 默认安装于 `C:\alist`，运行于 `http://localhost:5244`
- **播放器**: `C:\Program Files\MPC-HC\mpc-hc64.exe`

### 2. 安装依赖与配置环境变量
```powershell
# 克隆仓库后使用 uv 同步虚拟环境与依赖
uv sync

# 复制环境变量模板并填入您的密钥（或启动后在网页向导中填写）
Copy-Item .env.example .env
```

### 3. 启动服务
```powershell
uv run python run.py
# 或者使用 uv 脚本入口：
uv run movies
```
浏览器访问 **[http://127.0.0.1:5000](http://127.0.0.1:5000)** 即可体验！

### 4. 运行测试
```powershell
uv run pytest -v
```

---

## 📄 开源协议

本项目基于 [MIT License](LICENSE) 开源。
