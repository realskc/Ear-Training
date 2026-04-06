# 设计说明

本文档面向维护者，说明 Ear Training 项目的模块职责、关键数据流、默认参数位置，以及“连奏式干扰音序列”这套子逻辑的正式语义。

## 1. 目标与范围

当前版本聚焦两个核心目标：

1. 基于本地钢琴样本，按音名播放单音
2. 提供一个最小可用的绝对音感训练流程 `absolute_train1`

当前版本**不处理**这些更复杂的场景：

- GUI
- MIDI 输入
- 节奏训练
- 录音输入与自动评分
- 完整的和弦/音程训练流程
- 通用的时间轴事件模型（例如 `NoteEvent`）

代码结构因此刻意保持轻量，并把“音名解析”“样本索引”“播放”“训练流程”分开。

## 2. 总体结构

```text
main.py                     命令行入口
ear_training/__init__.py    包级别导出与便捷 helper
ear_training/notes.py       音名解析与归一化
ear_training/sample_bank.py 样本索引与检索
ear_training/player.py      样本读取、单音播放、连奏序列渲染/播放
ear_training/trainer.py     训练流程
export_git_snapshot.py      导出当前工作区快照
```

总体依赖关系如下：

```text
main.py
  ├─ ear_training.play_note
  └─ ear_training.absolute_train1

absolute_train1
  ├─ SampleBank
  ├─ NotePlayer
  └─ normalize_pitch_class / normalize_pitch_class_set

NotePlayer
  └─ SampleBank.resolve_sample
```

## 3. 模块职责

### 3.1 `main.py`

职责：

- 解析命令行参数
- 做参数级别和路径级别的输入校验
- 调用库层函数
- 捕获“用户可修正”的错误，并输出友好提示

不负责：

- 解析音频文件
- 训练逻辑本身
- 具体的音名归一化规则

设计原则：

- 库层抛异常
- CLI 层决定如何向最终用户展示错误

和干扰音听感最相关的 CLI 参数包括：

- `--distract-duration`
- `--distract-overlap`
- `--distract-fade-out`
- `--distract-final-tail`
- `--pre-target-gap`

其中旧参数 `--gap` 只作为兼容旧版本的别名保留，内部映射到 `pre_target_gap`。

### 3.2 `ear_training/__init__.py`

职责：

- 提供包级别的公共导出
- 提供 `play_note()`、`play_legato_sequence()` 这种一行可用的 helper

这里不做重逻辑初始化，只整理对外 API。

### 3.3 `ear_training/notes.py`

职责：

- 统一处理音名输入
- 把多种别名归一到 canonical pitch class
- 解析是否带八度
- 把 canonical pitch class 转换为本地文件名 token

关键设计点：

- 内部 canonical 形式统一用升号，例如 `Db -> C#`
- 训练判定以 pitch class 为准，不在该模块中加入训练语义
- 无法解析时抛 `NoteFormatError`

### 3.4 `ear_training/sample_bank.py`

职责：

- 扫描 `sound/` 目录下的 `.wav`
- 从文件名推导 `(octave, pitch_class)`
- 建立两套索引：
  - `(octave, pitch_class) -> SampleInfo`
  - `pitch_class -> [SampleInfo, ...]`
- 提供样本解析、随机选样、集合校验等能力

关键数据结构：

- `SampleInfo`：单个样本的只读描述
- `SampleBank`：样本索引和查询入口

### 3.5 `ear_training/player.py`

职责：

- 按给定 `SampleInfo` 或音名播放样本
- 按指定时长裁剪读取音频
- 提供一个“连奏式序列”的渲染/播放接口，让多段样本拼成一条连续时间轴

当前实现选型：

- `soundfile`：读取 WAV 到 NumPy 数组
- `sounddevice`：播放 NumPy 数组

选择这条路线的原因：

- 兼容 IEEE float WAV
- 以后扩展和弦/混音/数组级处理更自然
- 避免继续维护手写 WAV 解析逻辑

关键公开接口：

- `NotePlayer.play_note(...)`
- `NotePlayer.play_sample(...)`
- `NotePlayer.render_legato_sequence(...)`
- `NotePlayer.play_legato_sequence(...)`
- `NotePlayer.render_sample_sequence(...)`
- `NotePlayer.play_sample_sequence(...)`
- `ear_training.play_legato_sequence(...)`

### 3.6 `ear_training/trainer.py`

职责：

- 实现 `absolute_train1`
- 控制训练轮次、干扰音、目标音和用户输入
- 把结果整理成 `TrainRoundResult`

训练层语义上只关心：

- 目标集合 `S`
- 干扰音短句的听感参数
- 目标音与用户答案
- “忽略八度，只比较 pitch class”这条评分规则

### 3.7 `export_git_snapshot.py`

职责：

- 导出当前 Git 工作区快照
- 默认排除 `.git/` 和 Git ignored 文件
- 额外应用 `.aiignore` 与 `--exclude`

这个脚本与听音训练本身无关，但它是项目的工程工具，用来让“发当前版本给 AI”这件事更方便、更可重复。

## 4. 关键数据模型

### `pitch class`

表示十二半音中的类别，不带八度，例如：

- `C`
- `C#`
- `D`
- `A#`

内部统一使用 canonical sharp-based 形式。

### `concrete note`

表示带八度的具体音，例如：

- `C4`
- `F#5`

### `SampleInfo`

保存单个样本的三项核心信息：

- `path`
- `octave`
- `pitch_class`

并提供：

- `concrete_name`
- `local_filename_style`

## 5. 关键数据流

### 5.1 `play` 命令

```text
CLI 输入 note
  -> parse args
  -> play_note(...)
  -> LazyPlayer
  -> SampleBank.resolve_sample(note)
  -> NotePlayer.play_sample(sample)
  -> soundfile 读取音频
  -> sounddevice 播放
```

### 5.2 连奏式干扰音短句

```text
训练层选出 distractor SampleInfo 列表
  -> NotePlayer.play_sample_sequence(...)
  -> 逐个读取样本片段
  -> 转成 NumPy 数组
  -> 在统一时间轴上按 step = note_duration - overlap 排列
  -> 对每个片段结尾做 fade-out
  -> 对最终短句做峰值限制
  -> sounddevice 一次性播放
```

### 5.3 `absolute_train1`

```text
CLI 输入集合 S
  -> normalize_pitch_class_set(S)
  -> SampleBank.validate_pitch_class_subset(...)
  -> 选出 distractor samples
  -> 播放连奏式干扰音短句
  -> 等待 pre_target_gap
  -> 随机选择目标 pitch class
  -> 随机选择目标 sample
  -> 播放目标音
  -> 用户输入答案
  -> normalize_pitch_class(guess)
  -> 按 pitch class 判断对错
```

## 6. 默认参数与其定义位置

本项目中的默认参数分为两层。

### 6.1 CLI 默认值

CLI 默认值定义在 `main.py` 的 `build_parser()` 中。它们控制“用户在命令行中什么都不传时”的默认行为。

当前默认值：

- `play --duration = 1.0`
- `play --default-octave = 4`

`absolute_train1` 的 CLI 默认值：

- `--rounds = 5`
- `--distract-min = 10`
- `--distract-max = 20`
- `--distract-duration = DEFAULT_DISTRACT_DURATION = 0.42`
- `--distract-overlap = DEFAULT_LEGATO_OVERLAP = 0.05`
- `--distract-fade-out = DEFAULT_LEGATO_FADE_OUT = 0.03`
- `--distract-final-tail = DEFAULT_LEGATO_FINAL_TAIL = 0.10`
- `--pre-target-gap = DEFAULT_PRE_TARGET_GAP = 0.50`
- `--target-duration = DEFAULT_TARGET_DURATION = 1.20`
- `--default-octave = 4`

### 6.2 库层默认值

库层默认值定义在具体模块的常量和函数签名里。

`ear_training/player.py`：

```python
DEFAULT_LEGATO_OVERLAP = 0.05
DEFAULT_LEGATO_FADE_OUT = 0.03
DEFAULT_LEGATO_FINAL_TAIL = 0.10
DEFAULT_SEQUENCE_PEAK_LIMIT = 0.98
```

`ear_training/trainer.py`：

```python
DEFAULT_DISTRACT_DURATION = 0.42
DEFAULT_TARGET_DURATION = 1.2
DEFAULT_PRE_TARGET_GAP = 0.50
```

接口签名中的关键默认值：

- `absolute_train1(..., rounds=1, distract_count_range=(6, 10), ...)`
- `play_legato_sequence(..., overlap=0.05, fade_out=0.03, final_tail=0.10)`

需要注意：CLI 默认值和库函数默认值可以不同。当前 `main.py` 中 `absolute_train1` 的默认轮数是 `5`，而 `trainer.py` 中库函数默认轮数是 `1`。这是刻意区分“命令行默认体验”和“库接口最小默认行为”。

## 7. 连奏序列的正式语义

这一节是本文档最重要的“中间定理式说明”。它的目的不是描述用户体验，而是给维护者一条**可检验代码正确性**、也可供其他模块直接引用的结论。

### 7.1 参数定义

对 `render_sample_sequence(samples, note_duration=d, overlap=o, fade_out=f, final_tail=t)`，记：

- `N = len(samples)`，且 `N >= 1`
- `d = note_duration`
- `o = overlap`
- `f = fade_out`
- `t = final_tail`

约束条件：

- `d > 0`
- `0 <= o < d`
- `f >= 0`
- `t >= 0`

### 7.2 单个片段的读取长度

当前实现对每个样本的读取长度不是统一的：

- 对第 `0 .. N-2` 个样本，读取长度为 `d`
- 对最后一个样本，读取长度为 `d + t`

因此，`final_tail` 只影响最后一个片段，不影响前面任何片段。

### 7.3 相邻片段的起点间隔

相邻两个片段不是间隔 `d` 秒开始，而是间隔：

```text
step = d - o
```

秒开始。

这条语义可以直接回答最容易混淆的问题：

- `overlap` **包含在** `note_duration` 内部
- `overlap` 不是“额外加出来的尾巴”
- `overlap` 的作用是让下一个片段提前 `o` 秒进入前一个片段的尾部

因此，第 `i` 个片段（从 0 开始）的开始时刻是：

```text
start(i) = i * (d - o)
```

### 7.4 `fade_out` 的地位

`fade_out` 不改变任何片段的开始时刻，也不改变任何片段的读取长度。  
它只在片段尾部的最后一段时间内施加线性包络，使振幅从 1 逐渐减到 0。

所以：

- `fade_out` **包含在片段长度内**
- `fade_out` **不会额外增加总时长**
- `fade_out` 只改变尾部的振幅，不改变时间轴布局

### 7.5 整段序列的理论总时长

忽略采样率取整造成的单帧误差，整段连奏序列的理论总时长是：

```text
T = N * d - (N - 1) * o + t
```

推导方法很直接：

- 最后一个片段开始于 `(N - 1) * (d - o)`
- 最后一个片段自身长度为 `d + t`

因此：

```text
T = (N - 1) * (d - o) + (d + t)
  = N * d - (N - 1) * o + t
```

这条公式是本模块最重要的可检验结论之一。只要参数和 `samples` 已知，就可以根据它预估整段短句的大致总长度。

### 7.6 干扰音与目标音之间的整体时间结构

`absolute_train1` 当前不是把“干扰音 + 停顿 + 目标音”渲染成一条完整时间轴，而是分两段：

1. 先调用 `play_sample_sequence(...)` 播放整段干扰音短句
2. 再 `sleep(pre_target_gap)`
3. 再单独播放目标音

因此，对训练层来说，整体听感结构是：

```text
[长度约为 T 的干扰音短句]
-> [长度为 pre_target_gap 的静默]
-> [长度约为 target_duration 的目标音]
```

其中 `pre_target_gap` **不属于** 干扰音短句内部，也**不属于** 目标音自身。

### 7.7 一个具体例子

假设：

- `N = 4`
- `d = 0.42`
- `o = 0.05`
- `t = 0.10`

那么：

- `step = 0.42 - 0.05 = 0.37`
- 四个片段的起点大约在：
  - `0.00`
  - `0.37`
  - `0.74`
  - `1.11`
- 前三个片段长度都是 `0.42`
- 最后一个片段长度是 `0.52`

所以整段短句理论总时长为：

```text
T = 4 * 0.42 - 3 * 0.05 + 0.10 = 1.63 秒
```

如果再设：

- `pre_target_gap = 0.50`
- `target_duration = 1.20`

那么从第一个干扰音开始，到目标音播放结束，理论总时长大约是：

```text
1.63 + 0.50 + 1.20 = 3.33 秒
```

这里仍然忽略帧级取整和设备层极小开销。

## 8. 为什么采用“先渲染再播放”

旧实现中，干扰音是一个一个独立 `play` 的。这会带来两个问题：

1. 每个音尾都容易被机械截断
2. 每次单独启动播放都可能带来设备层面的空隙

当前实现改为：

1. 先读取若干个样本片段
2. 在内存中把它们放到同一时间轴上
3. 允许相邻片段有少量重合
4. 对每个片段尾部做 fade-out
5. 对整段短句做峰值限制
6. 再一次性播放整段短句

这样做的直接收益是：

- 听感更连续
- 设备只需要启动一次播放
- 以后扩展和弦或更一般的时间轴合成会更自然

## 9. 当前边界

当前连奏接口只支持“同一时间轴上的短序列”，还没有实现：

- 正式的和弦接口
- 通用事件时间轴
- 更复杂的包络模型
- 踏板或真实钢琴演奏建模

因此，当前实现应被理解为：

**一个针对短干扰音序列的、工程上足够稳定的样本拼接方案。**

## 10. 后续扩展方向

比较自然的扩展路径包括：

- 新增 `play_chord(...)`
- 引入更一般的时间轴事件模型
- 把“干扰音短句 + 目标音”一次性渲染成完整轮次音频
- 给训练加入统计记录、错误分布分析和配置文件
- 在保持 CLI 的同时增加 GUI
