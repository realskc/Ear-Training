# Ear Training

基于本地钢琴 WAV 样本的绝对音感训练小项目。

当前版本提供两项核心能力：

- 按音名播放单音
- 运行一个命令行绝对音感训练流程 `absolute_train1`

## 当前功能

- 从 `sound/` 目录扫描并索引本地钢琴样本
- 解析多种音名写法，例如 `C4`、`C#4`、`Db4`、`fs`、`4-cs`
- 使用 `soundfile + sounddevice` 播放单音
- 使用“连奏式干扰音短句 + 目标音 + 控制台输入”的训练流程
- 支持 0 个干扰音；此时本轮直接进入“静默停顿 -> 目标音”结构

## 环境安装

建议使用虚拟环境：

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 项目结构

```text
Ear-Training/
├─ sound/                     # 你自己的钢琴样本
├─ docs/
│  └─ design.md               # 面向维护者的设计说明
├─ ear_training/
│  ├─ __init__.py
│  ├─ config.py               # 默认参数的单一来源
│  ├─ notes.py                # 音名解析与归一化
│  ├─ sample_bank.py          # 样本扫描与索引
│  ├─ player.py               # 单音播放与连奏序列渲染/播放
│  └─ trainer.py              # absolute_train1
├─ main.py                    # 命令行入口
├─ export_git_snapshot.py     # 导出当前工作区快照
└─ requirements.txt
```

## 样本文件命名约定

当前项目假定你的样本大致遵循下面的命名风格：

- `4-c.wav`
- `4-cs.wav`
- `4-d.wav`
- `5-a.wav`

其中：

- 前半部分是八度
- 后半部分是音名
- `cs / ds / fs / gs / as` 分别表示 `C# / D# / F# / G# / A#`

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
python main.py play C#4 --duration 1.2
python main.py play fs
```

### 开始训练

```bash
python main.py absolute_train1 --set C D# F# A --rounds 5
```

在 PowerShell 里不想输入 `#` 时，可以写成：

```bash
python main.py absolute_train1 --set C Ds Fs A --rounds 5
```

## 命令行说明

### `play`

```bash
python main.py play NOTE [--duration SECONDS] [--default-octave N]
```

常用参数：

- `NOTE`：音名，例如 `C4`、`Db4`、`fs`、`4-cs`
- `--duration`：播放时长
- `--default-octave`：当音名不带八度时使用的默认八度

### `absolute_train1`

```bash
python main.py absolute_train1 --set C D# F# A [options]
```

常用参数：

- `--set`：目标音集合 `S`
- `--rounds`：训练轮数
- `--distract-count`：每轮固定干扰音数量，可设为 `0`
- `--distract-duration`：每个干扰音的标称时长
- `--distract-overlap`：相邻干扰音的重合时长
- `--distract-fade-out`：每个干扰音结尾的淡出时长
- `--distract-final-tail`：最后一个干扰音额外保留的尾音时长
- `--pre-target-gap`：干扰音序列结束到目标音开始前的静默
- `--target-duration`：目标音播放时长
- `--default-octave`：解析不带八度音名时的默认八度
- `--seed`：固定随机种子，便于复现实验
- `--debug`：显示完整 traceback，便于调试

兼容性说明：旧版本的 `--gap` 仍然可用，但现在它等价于 `--pre-target-gap`。

## 参数默认值在哪里看

本项目不在文档里重复抄写默认值。所有默认参数都集中在：

```text
ear_training/config.py
```

如果你想：

- 查看当前默认值
- 批量调整训练体验
- 统一修改 CLI 与库层的默认行为

优先去看和修改 `ear_training/config.py`。

## 关键播放参数的含义

### `DEFAULT_DISTRACT_DURATION` / `--distract-duration`

它表示每个干扰音的**标称时长**。这里的“标称”意思是：如果把连奏序列想成一个时间轴，每个干扰音先占有一个自己的基础槽位，这个槽位的长度就是 `distract_duration`。

需要特别强调的是：相邻干扰音的重合不是在这个槽位之外额外再加一段，而是发生在槽位内部。换句话说，下一个干扰音会比“整整隔一个 `distract_duration` 再开始”更早进入，因此两段音频在前一个槽位的尾部产生重合。

### `DEFAULT_DISTRACT_OVERLAP` / `--distract-overlap`

它表示相邻两个干扰音在时间轴上的**重合时长**。这不是一个额外附加到序列末尾的尾巴，而是决定“下一个音提前多少进入前一个音的尾部”。因此，两个相邻干扰音的开始时刻并不是相差 `distract_duration`，而是相差：

```text
distract_duration - distract_overlap
```

这也是“为什么它听起来更连一些”的核心原因之一。

### `DEFAULT_DISTRACT_FADE_OUT` / `--distract-fade-out`

它表示每个干扰音片段尾部施加的线性淡出时长。它只改变片段尾部的振幅包络，不改变任何片段的开始时刻，也不会额外延长片段总时长。

因此，`fade_out` 的作用不是“把音拖长”，而是“把片段最后那一小段收得更自然”。

### `DEFAULT_DISTRACT_FINAL_TAIL` / `--distract-final-tail`

它只作用于最后一个干扰音。它的作用是给整段干扰音短句的最后一个音额外保留一点余韵，避免整段短句在最后一个音的标称时长处突然结束。

也就是说，前面的干扰音都只取自己的标称长度；只有最后一个干扰音会再额外保留一小段尾音。

### `DEFAULT_PRE_TARGET_GAP` / `--pre-target-gap`

它表示整段干扰音短句结束后，到目标音开始前的静默时间。它不属于干扰音短句内部，也不属于目标音自身，而是两者之间的明确停顿。

因此，一轮训练的听感结构是：

```text
[干扰音短句] -> [静默 pre_target_gap] -> [目标音]
```

如果这一轮的干扰音数量恰好为 0，那么结构会退化为：

```text
[无干扰音] -> [静默 pre_target_gap] -> [目标音]
```

## 连奏序列的一个可直接使用的结论

下面这段话可以把当前实现当成一个“中间定理”来记：

设：

- 干扰音个数为 `N`
- 标称时长为 `d`
- 重合时长为 `o`
- 最后额外尾音为 `t`

那么：

- 当 `N = 0` 时，本轮不播放干扰音短句，序列长度按 `0` 处理。
- 当 `N >= 1` 时，第 `i` 个干扰音（从 `0` 开始）的开始时刻是：

```text
i * (d - o)
```

- 非最后一个干扰音的片段长度是 `d`
- 最后一个干扰音的片段长度是 `d + t`
- 整段干扰音短句的理论总时长是：

```text
N * d - (N - 1) * o + t
```

这里忽略采样率取整带来的单帧误差。`fade_out` 不改变总时长，只改变每个片段尾部的振幅包络。

这条结论的价值在于：

- 你可以用它核对代码实现是否正确
- 你可以据此推断一组参数最终听起来会是什么结构
- 其他模块只要接受这条结论，就不必再次阅读底层拼接代码

## Python 接口示例

```python
from ear_training import absolute_train1, play_legato_sequence, play_note

play_note("C4", 1.0)
play_legato_sequence(["C4", "E4", "G4"], 0.32, overlap=0.05, fade_out=0.03)

absolute_train1(
    ["C", "D#", "F#", "A"],
    rounds=3,
    distract_count=10,
)
```

## 常见问题

### 输入非法音名时为什么会报错

库层会抛明确异常，CLI 层会把这类异常转换成用户可读的错误提示。这不是程序崩坏，而是输入不符合约定。

### 为什么 `sound/` 不在 `.gitignore` 里，但导出给 AI 时又能排除

因为 Git 忽略规则和“发给 AI 的打包视图”是两件不同的事。当前项目通过：

- `.gitignore`
- `.aiignore`
- `export_git_snapshot.py --exclude ...`

把这两层需求分开管理。

## 开发者入口

- 使用说明优先看 `README.md`
- 模块职责、数据流和正式语义优先看 `docs/design.md`
- 默认值统一看 `ear_training/config.py`
