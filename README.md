# Ear Training

Ear Training 是一个基于本地钢琴样本的命令行听音训练项目。当前版本聚焦两件事：

- 按音名播放 `sound/` 目录中的单音样本
- 进行绝对音感训练 `absolute_train1`

训练流程中的干扰音不是一个一个单独播放，而是**先在内存中渲染成一整段连奏式序列，再一次播放**。这样做的目的，是让相邻干扰音之间保留少量自然重合，减少“硬切音头/音尾”和设备反复启停带来的生硬感。

## 当前功能

- `play`：按音名播放一个单音，并支持指定播放时长
- `absolute_train1`：先播放一串干扰音，再播放目标音，用户在 console 中输入答案
- `ear_training.play_legato_sequence(...)`：以连奏方式播放一串音，用于干扰音序列或其他短句
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

### 播放单音

```bash
python main.py play C4
python main.py play C#4 --duration 0.8
python main.py play fs --duration 1.2
python main.py play 4-cs --duration 1.0
```

### 开始绝对音感训练

```bash
python main.py absolute_train1 --set C D# F# A --rounds 5
```

在 PowerShell 里不想输入 `#` 时，可以写成：

```bash
python main.py absolute_train1 --set C Ds Fs A --rounds 5
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

常用参数：

- `--set`：目标音集合 `S`
- `--rounds`：训练轮数
- `--distract-min` / `--distract-max`：每轮干扰音数量范围
- `--distract-duration`：每个干扰音的标称时长
- `--distract-overlap`：相邻干扰音的重合时长
- `--distract-fade-out`：每个干扰音结尾的淡出时长
- `--distract-final-tail`：最后一个干扰音额外保留的尾音时长
- `--pre-target-gap`：干扰音序列和目标音之间的停顿
- `--target-duration`：目标音的播放时长
- `--default-octave`：解析不带八度音名时的默认八度
- `--seed`：固定随机种子，便于复现实验
- `--debug`：显示完整 traceback，便于调试

示例：

```bash
python main.py absolute_train1 --set C D E G ^
  --distract-duration 0.42 ^
  --distract-overlap 0.05 ^
  --distract-fade-out 0.03 ^
  --distract-final-tail 0.10 ^
  --pre-target-gap 0.50 ^
  --target-duration 1.20
```

> 兼容性说明：旧版本的 `--gap` 仍然可用，但现在它等价于 `--pre-target-gap`。新代码和新文档都建议优先使用 `--pre-target-gap`。

## 关键播放参数的实际含义

这一节只解释最容易混淆的几个参数。更正式、更接近实现的版本见 `docs/design.md`。

### `DEFAULT_DISTRACT_DURATION` / `--distract-duration`

它表示**每个干扰音的标称时长**，也就是每个音在“时间轴槽位”中的基础长度。当前默认值来自 `ear_training/trainer.py`：

```python
DEFAULT_DISTRACT_DURATION = 0.42
```

如果把干扰音序列看成一个时间轴，那么相邻两个干扰音并不是间隔 `distract_duration` 秒开始，而是间隔：

```text
distract_duration - distract_overlap
```

秒开始。

因此，`distract_overlap` 是**包含在标称时长里的**，不是额外再往后加的一段。  
也就是说：

- `distract_duration` 决定每个音“从哪里开始，到哪里算这个音自己的槽位”
- `distract_overlap` 决定下一个音会提前多少进入这个槽位的尾部

### `--distract-overlap`

它表示**相邻两个干扰音在时间轴上的重合时长**。  
例如：

- `distract_duration = 0.42`
- `distract_overlap = 0.05`

那么相邻两个干扰音的起点间隔其实是：

```text
0.42 - 0.05 = 0.37 秒
```

这意味着：

- 第一个音不会在 0.37 秒时消失
- 第二个音会在第一个音开始后 0.37 秒进入
- 两个音会有大约 0.05 秒的重合区

### `--distract-fade-out`

它表示**每个干扰音片段尾部的线性淡出时长**。  
它的作用是让音尾更自然，避免硬切。这个淡出是对已经读出来的片段尾部做包络处理，因此：

- 它**不会额外增加片段长度**
- 它**包含在当前片段的读取长度里**

对非最后一个干扰音来说，读取长度是：

```text
distract_duration
```

对最后一个干扰音来说，读取长度是：

```text
distract_duration + distract_final_tail
```

淡出始终发生在“这个片段自己的末尾那一小段”里。

### `--distract-final-tail`

它表示**只对最后一个干扰音额外保留的尾音时长**。  
它的作用是让整段干扰音不要在最后一个音的标称时长处突然结束，而是让最后一个音多留一点自然余韵。

因此，只有最后一个干扰音的读取长度会变成：

```text
distract_duration + distract_final_tail
```

其余干扰音仍然只读取 `distract_duration`。

### `--pre-target-gap`

它表示**整段干扰音序列播放结束后，到目标音开始前的静默时长**。  
它不属于干扰音序列内部，也不属于目标音本身，而是两者之间的明确停顿。

所以训练轮次的听感结构是：

```text
[一整段连奏式干扰音] -> [安静 pre_target_gap 秒] -> [目标音]
```

## 连奏序列的一个可直接使用的结论

为了方便理解和检验代码，可以把当前实现记成下面这个结论。

设：

- 干扰音个数为 `N`
- 标称时长为 `d`
- 重合时长为 `o`
- 最后额外尾音为 `t`

那么当前实现满足：

1. 第 `i` 个干扰音（从 0 开始计）在时间轴上的开始时刻是：

```text
i * (d - o)
```

2. 非最后一个干扰音的片段长度是：

```text
d
```

3. 最后一个干扰音的片段长度是：

```text
d + t
```

4. 整段干扰音序列的理论总时长是：

```text
N * d - (N - 1) * o + t
```

这里忽略了采样率换算时的单帧四舍五入误差。`fade_out` 不改变这段总时长，只改变每个片段尾部的振幅包络。

这个结论很有用，因为：

- 你可以据此检查参数是否符合预期
- 也可以据此推断“听起来为什么更连贯”
- 其他模块只要接受这套结论，就不必重新理解底层拼接实现

## Python 接口示例

除了命令行接口，也可以在 Python 代码里直接调用：

```python
from ear_training import play_note, play_legato_sequence, absolute_train1

play_note("C4", 1.0)
play_legato_sequence(["C4", "E4", "G4"], 0.42, overlap=0.05, fade_out=0.03)

absolute_train1(
    ["C", "D#", "F#", "A"],
    rounds=3,
    distract_duration=0.42,
    distract_overlap=0.05,
    pre_target_gap=0.50,
)
```

## 默认参数在哪里调节

通常优先通过命令行参数覆盖默认值，而不是直接修改源码。例如：

```bash
python main.py play C4 --duration 1.5
python main.py absolute_train1 --set C D E --pre-target-gap 0.6 --target-duration 1.5
```

本项目中的默认参数分为两层。

### 1. CLI 默认值

CLI 默认值定义在 `main.py` 的 `build_parser()` 中。  
这些值决定用户在命令行中未显式传参时的默认行为。

当前和播放/训练听感最相关的 CLI 默认值包括：

- `play --duration = 1.0`
- `play --default-octave = 4`
- `absolute_train1 --rounds = 5`
- `absolute_train1 --distract-min = 10`
- `absolute_train1 --distract-max = 20`
- `absolute_train1 --distract-duration = 0.42`
- `absolute_train1 --distract-overlap = 0.05`
- `absolute_train1 --distract-fade-out = 0.03`
- `absolute_train1 --distract-final-tail = 0.10`
- `absolute_train1 --pre-target-gap = 0.50`
- `absolute_train1 --target-duration = 1.20`

如果你希望永久修改命令行默认行为，请修改 `main.py` 中对应参数的 `default=...`。

### 2. 库层默认值

库层默认值定义在具体模块中的常量和函数签名里。

主要位置包括：

- `ear_training/player.py`
  - `DEFAULT_LEGATO_OVERLAP = 0.05`
  - `DEFAULT_LEGATO_FADE_OUT = 0.03`
  - `DEFAULT_LEGATO_FINAL_TAIL = 0.10`
- `ear_training/trainer.py`
  - `DEFAULT_DISTRACT_DURATION = 0.42`
  - `DEFAULT_TARGET_DURATION = 1.20`
  - `DEFAULT_PRE_TARGET_GAP = 0.50`

以及相关接口的参数默认值，例如：

- `ear_training.play_note(..., sound_dir="sound", default_octave=4)`
- `ear_training.play_legato_sequence(..., overlap=0.05, fade_out=0.03, final_tail=0.10)`
- `absolute_train1(..., rounds=1, distract_duration=0.42, distract_overlap=0.05, pre_target_gap=0.50, ...)`

需要注意：CLI 默认值和库函数默认值可以不同。当前 `main.py` 中 `absolute_train1` 的默认轮数是 `5`，而 `trainer.py` 中库函数默认轮数是 `1`。这是有意区分“命令行默认体验”和“库接口最小默认行为”。

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

## 常见问题

### 输入了不合法的音名，为什么程序会报错？

像 `C5s` 这种格式虽然人能猜到你想表达什么，但它不在当前解析规则里，所以库层会抛出明确的输入异常。CLI 会把这种异常转换成友好提示，而不是把它当成“程序崩坏”。

### 为什么干扰音听起来不像真正钢琴连奏？

当前实现追求的是“听感更自然、工程上足够稳定”，不是完整模拟真实钢琴的物理发声。现在的做法是：

- 为每个干扰音读出一个短片段
- 允许相邻片段轻微重合
- 对片段尾部做 fade-out
- 把整段短句一次性播放

这比逐个独立播放要自然得多，但仍然是“样本拼接的短句”，不是严格意义上的钢琴演奏建模。

### `--gap` 和 `--pre-target-gap` 有什么关系？

`--gap` 是旧接口留下来的兼容别名。当前版本中它等价于 `--pre-target-gap`。新的代码和文档都建议使用 `--pre-target-gap`，这样语义更清楚。
