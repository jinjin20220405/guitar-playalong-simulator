# WorkBuddy 版说明

本分支把 `main` 上的 Claude 版技能改造成 WorkBuddy 环境可用的版本。技能的核心（识谱规则、数据格式、播放器）一字未改，只换了平台相关的部分。

## 与 main 的差异（6 处）

| 文件 | 改了什么 |
|---|---|
| `template/player.html` | 删掉 `window.claude.use('db'/'user'/'downloads')` 云端能力代码和「保存到账号」按钮；歌词译文改为纯 localStorage + 导出/载入 JSON 文件 |
| `scripts/gsh.py` | 图像处理后端从只认 macOS `sips` 改为自动挑选 sips → ImageMagick → Pillow；新增 `env` 子命令做开工自检 |
| `SKILL.md` | 加 `agent_created: true`；描述改第三人称；新增「在 WorkBuddy 里怎么用」一节；交付改用 `present_files` |
| `README.md` | 补 env 命令、后端说明、WorkBuddy 安装路径 |
| `tests/test_gsh.py` | 新增 3 项测试（后端选择、env 命令、缩放只缩不放） |
| `guitar-playalong-simulator-skill-v2.0.0-workbuddy.zip` | 新增：可直接上传安装的技能包 |

未改动：`references/format.md`、`references/transcription.md`、`template/i18n.json`、`examples/selftest.score.json`。

## 在新机器上安装

### 方式一：客户端上传（推荐）

1. WorkBuddy 左侧「专家 · 技能 · 连接器」→「技能」
2. 「添加技能」→「上传技能」
3. 选 `guitar-playalong-simulator-skill-v2.0.0-workbuddy.zip`
4. 安全检测通过后提示安装成功，即可在所有项目中使用

### 方式二：手动解压

把 `guitar-playalong-simulator/` 整个目录复制到用户技能目录：

| 系统 | 路径 |
|---|---|
| macOS / Linux | `~/.workbuddy/skills/` |
| Windows | `%USERPROFILE%\.workbuddy\skills\` |

最终路径应为 `skills/guitar-playalong-simulator/`。客户端技能列表没刷出来时重启一次客户端。

## 跨设备同步

技能文件本身不随 WorkBuddy 账号同步，只同步「启用/关闭」开关状态。跨设备使用的办法：

- 本机改完后提交推送到本分支，异地 `git pull` 再重新上传 zip
- 异地若是 Web 端或云上任务，客户端个人技能库与之相互独立；此时把技能放进项目目录的 `.workbuddy/skills/`（项目 Skill 云端统一管理，双端可用），或在任务里临时导入 zip

## 使用

给出吉他谱，说「跟弹」「做成能播放的网页」「扒谱」等即可触发。开工前先跑环境自检：

```bash
python3 <技能目录>/scripts/gsh.py env
```

改了脚本记得跑测试：

```bash
python3 <技能目录>/tests/test_gsh.py
```

## Windows 注意

Windows 上没有 macOS 的 sips，裁图缩图会自动改用 ImageMagick（`magick`）或 Pillow；两者都没装时 `crop`/`shrink` 会报错并给出提示，此时用看图软件手工裁图，或自行提供已缩小的图片。
