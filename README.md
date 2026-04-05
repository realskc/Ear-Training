# Ear Training

Ear Training 是一个基于本地钢琴采样的命令行听音训练项目。当前版本聚焦两件事：

- 按音名播放 `sound/` 目录中的单音样本
- 进行绝对音感训练 `absolute_train1`

项目附带了按 `4-cs.wav` 这类形式命名的钢琴样本文件，位于 `sound/` 目录中。

## 当前功能

- `play`：按音名播放一个单音，并支持指定播放时长
- `absolute_train1`：先播放一串干扰音，再播放目标音，用户在 console 中输入答案
- `export_git_snapshot.py`：把当前工作区打包成适合发给 AI 的 `.zip` 或 `.tar`，并支持 `.aiignore`

## 目录结构

```text
Ear-Training/
├─ .aiignore
├─ .gitignore
├─ docs/
│  └─ design.md
├─ sound/
├─ ear_training/
│  ├─ __init__.py
│  ├─ notes.py
│  ├─ player.py
│  ├─ sample_bank.py
│  └─ trainer.py
├─ export_git_snapshot.py
├─ main.py
├─ README.md
└─ requirements.txt
```

## 环境准备

推荐用 `venv` 创建项目专用环境：

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果你使用 Conda，也可以先创建环境，再执行最后一条 `pip install -r requirements.txt`。

## 音频样本要求

程序默认从项目根目录下的 `sound/` 读取样本。当前约定的文件名格式是：

```text
<octave>-<pitch>.wav
```

例如：

- `4-c.wav`
- `4-cs.wav`
- `5-a.wav`
- `7-gs.wav`

其中：

- 八度使用整数，如 `4`、`5`
- 升号使用 `s`，例如 `cs`、`fs`、`as`
- 文件扩展名使用 `.wav`

## 支持的音名输入

命令行与训练答案都支持这些写法：

- 自然音：`C`, `D`, `E`, `F`, `G`, `A`, `B`
- 升号：`C#`, `D#`, `F#`, `G#`, `A#`
- 降号：`Db`, `Eb`, `Gb`, `Ab`, `Bb`
- 本地简写：`cs`, `ds`, `fs`, `gs`, `as`
- 带八度：`C4`, `Db5`
- 本地文件风格：`4-cs`, `5-a`

训练判定时只比较十二半音中的音高类别，忽略八度。例如你输入 `C`，实际播放 `C3`，仍然视为正确。

## 快速开始

### 1. 播放单音

```bash
python main.py play C4
python main.py play C#4 --duration 0.8
python main.py play fs --duration 1.2
python main.py play 4-cs --duration 1.0
```

### 2. 开始绝对音感训练

```bash
python main.py absolute_train1 --set C D# F# A --rounds 5
```

如果你在 PowerShell 中不想输入 `#`，可以写成：

```bash
python main.py absolute_train1 --set C Ds Fs A --rounds 5
```

### 3. 查看帮助

```bash
python main.py --help
python main.py play --help
python main.py absolute_train1 --help
```

## 命令行说明

### `play`

播放一个单音。

```bash
python main.py play NOTE [--duration SECONDS] [--default-octave N]
```

常用参数：

- `NOTE`：音名，例如 `C4`、`Db4`、`fs`、`4-cs`
- `--duration`：播放时长，单位秒
- `--default-octave`：当音名不带八度时使用的默认八度

### `absolute_train1`

开始绝对音感训练 v1。

```bash
python main.py absolute_train1 --set C D# F# A [options]
```

### 常用参数

- `--set`：目标音集合 `S`
- `--rounds`：训练轮数
- `--distract-min` / `--distract-max`：每轮干扰音数量范围
- `--distract-duration`：每个干扰音的播放时长
- `--target-duration`：目标音的播放时长
- `--gap`：相邻音之间的停顿时长
- `--default-octave`：解析不带八度音名时的默认八度
- `--seed`：固定随机种子，便于复现实验
- `--debug`：显示完整 traceback，便于调试

## 打包当前项目发给 AI

项目根目录下提供了 `export_git_snapshot.py`，用于导出“当前工作区快照”。

默认行为：

- 包含 tracked 文件
- 包含 untracked 但未被 `.gitignore` 忽略的文件
- 排除 `.git/`
- 排除 Git ignored 文件
- 额外应用 `.aiignore`
- 支持命令行 `--exclude` 追加额外排除规则

常用命令：

```bash
python export_git_snapshot.py
python export_git_snapshot.py --dry-run
python export_git_snapshot.py --exclude sound/
python export_git_snapshot.py --format tar
```

如果你希望默认不把样本目录发给 AI，可以在 `.aiignore` 中写：

```text
sound/
```

## 默认参数的定义位置

通常优先通过命令行参数覆盖默认值，而不是直接修改源码，参见 命令行说明->常用参数。例如：

```bash
python main.py play C4 --duration 1.5
python main.py absolute_train1 --set C D E --target-duration 1.5 --gap 0.12
```

本项目中的默认参数分为两层：

### 1. CLI 默认值
CLI 默认值定义在 `main.py` 的 `build_parser()` 中。
这些值决定用户在命令行中未显式传参时的默认行为。

例如：
- `play --duration = 1.0`
- `absolute_train1 --rounds = 5`
- `absolute_train1 --target-duration = 1.2`

### 2. 库层默认值
库层默认值定义在具体函数或类的签名中。

例如：
- `ear_training.play_note(..., sound_dir="sound", default_octave=4)`
- `NotePlayer(..., default_octave=4)`
- `LazyPlayer(..., sound_dir="sound", default_octave=4)`
- `absolute_train1(..., rounds=1, distract_duration=0.22, target_duration=1.2, gap_seconds=0.08, ...)`

需要注意：CLI 默认值与库函数默认值可以不同。当前 `main.py` 中 `absolute_train1` 的默认轮数为 `5`，而 `trainer.py` 中库函数默认轮数为 `1`。这是有意区分“命令行默认体验”和“库接口最小默认行为”。

## 常见问题

### 1. `sound` 目录不存在

请确认你在项目根目录执行命令，或者显式传入：

```bash
python main.py --sound-dir D:\Life\project\Ear-Training\sound play C4
```

### 2. 输入了非法音名

例如 `C5s` 这种写法当前不支持。程序会给出友好的输入错误提示。推荐输入：

- `C4`
- `C#5`
- `Db5`
- `cs`
- `4-cs`

### 3. 音频无法播放

请先确认依赖已安装：

```bash
python -m pip install -r requirements.txt
```

并确认系统音频设备正常可用。

## 设计文档

面向维护者的设计说明见：

- `docs/design.md`

如果你准备继续扩展这个项目，建议先阅读该文件，再开始改动模块边界或公共接口。
