# 设计说明

本文档面向维护者，说明 Ear Training 项目的模块职责、关键数据流、错误处理策略和后续扩展方向。

## 1. 目标与范围

当前版本聚焦两个核心目标：

1. 基于本地钢琴样本，按音名播放单音
2. 提供一个最小可用的绝对音感训练流程 `absolute_train1`

当前版本**不处理**这些更复杂的场景：

- GUI
- MIDI 输入
- 节奏训练
- 持久化训练记录
- 自动评分的录音输入
- 完整的和弦/音程训练流程
- 复杂的事件时间轴抽象（例如 `NoteEvent`）

代码结构因此刻意保持轻量，并把“样本解析”“播放”“训练流程”分开。

## 2. 总体结构

```text
main.py                    命令行入口
ear_training/__init__.py   包级别导出与便捷 helper
ear_training/notes.py      音名解析与归一化
ear_training/sample_bank.py 样本索引与检索
ear_training/player.py     样本读取、单音播放、连奏序列渲染/播放
ear_training/trainer.py    训练流程
export_git_snapshot.py     导出当前工作区快照
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

当前 CLI 中和干扰音听感最相关的参数包括：

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
- 训练判定以 pitch class 为准，不在该模块处理中加入训练语义
- 无法解析时抛 `NoteFormatError`

这是样本层和训练层共用的基础模块。

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

为什么要单独建这一层：

- 避免播放器直接扫描目录
- 让训练逻辑只处理“音”和“样本”，不直接处理文件系统细节

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

#### 新增的连奏接口

当前版本的关键新增接口包括：

- `NotePlayer.render_legato_sequence(...)`
- `NotePlayer.play_legato_sequence(...)`
- `NotePlayer.render_sample_sequence(...)`
- `NotePlayer.play_sample_sequence(...)`
- `ear_training.play_legato_sequence(...)`

其中训练流程当前主要使用 `play_sample_sequence(...)`，因为训练层已经先选好了要播放的 `SampleInfo`。

#### 为什么要“先渲染再播放”

旧实现中，干扰音是一个一个独立 `play` 的。这会带来两个问题：

1. 每个音尾都很容易被机械截断
2. 每次单独启动播放都可能带来设备层面的空隙

现在改为：

1. 先读取若干个样本片段
2. 在内存中把它们放到同一时间轴上
3. 允许相邻音有少量重合
4. 对每个片段结尾做 fade-out
5. 把整个短句一次性播放

这样能明显改善干扰音的听感。

#### 当前边界

- 连奏接口目前只支持“同一时间轴上的短序列”
- 还没有正式的和弦接口
- 还没有引入更通用的事件对象（例如 `NoteEvent`）

### 3.6 `ear_training/trainer.py`

职责：

- 实现 `absolute_train1`
- 控制训练轮次、干扰音、目标音和用户输入
- 负责把训练结果整理成 `TrainRoundResult`

训练流程：

1. 校验集合 `S` 和参数
2. 随机选择若干干扰音样本
3. 通过 `play_sample_sequence(...)` 一次性播放整个干扰音短句
4. 等待 `pre_target_gap`
5. 从目标集合中选择一个 pitch class
6. 从该 pitch class 的样本中随机选取一个 concrete sample
7. 播放目标音
8. 读取用户输入并归一化
9. 仅按 pitch class 比较对错

关键点：

- “忽略八度”这一训练规则只在训练层生效
- 干扰音短句和目标音都通过 `SampleBank` 与 `NotePlayer` 获取/播放
- `gap_seconds` 作为旧接口兼容别名保留，但语义已退化为 `pre_target_gap`

### 3.7 `export_git_snapshot.py`

职责：

- 导出当前 Git 工作区快照
- 默认排除 `.git/` 和 Git ignored 文件
- 额外应用 `.aiignore` 与 `--exclude`

这个脚本与听音训练本身无关，但它是这个项目的工程工具，目的是让“发当前版本给 AI”这件事更方便、更可重复。

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

### 5.4 `export_git_snapshot.py`

```text
git ls-files
  -> 生成基础文件集合
  -> 应用 .aiignore 与 --exclude
  -> 排除输出归档自身
  -> 写入 zip/tar
```

## 6. 默认参数的定义位置

本项目中的默认参数分为两层：

### 6.1 CLI 默认值

CLI 默认值定义在 `main.py` 的 `build_parser()` 中。

这些值控制“用户在命令行中什么都不传时”的默认行为。  
和当前听感关系最大的值包括：

- `--distract-duration = 0.22`
- `--distract-overlap = 0.05`
- `--distract-fade-out = 0.03`
- `--distract-final-tail = 0.10`
- `--pre-target-gap = 0.50`
- `--target-duration = 1.2`

### 6.2 库层默认值

库层默认值定义在函数签名或模块常量中。

例如：

- `player.py`
  - `DEFAULT_LEGATO_OVERLAP`
  - `DEFAULT_LEGATO_FADE_OUT`
  - `DEFAULT_LEGATO_FINAL_TAIL`
- `trainer.py`
  - `DEFAULT_DISTRACT_DURATION`
  - `DEFAULT_TARGET_DURATION`
  - `DEFAULT_PRE_TARGET_GAP`

此外，函数签名本身也带有默认参数，例如：

- `play_legato_sequence(..., overlap=..., fade_out=..., final_tail=...)`
- `absolute_train1(..., distract_overlap=..., pre_target_gap=...)`

需要注意：CLI 默认值与库函数默认值可以不同。当前 `main.py` 中 `absolute_train1` 的默认轮数为 `5`，而 `trainer.py` 中库函数默认轮数为 `1`。这是有意区分“命令行默认体验”和“库接口最小默认行为”。

## 7. 错误处理策略

### 7.1 库层

库层函数与类方法遇到错误时，优先抛出明确异常：

- `NoteFormatError`：音名无法解析
- `FileNotFoundError` / `NotADirectoryError`：路径问题
- `InvalidWavFileError`：音频文件损坏、无法读取或音频结构不支持
- `ValueError`：参数值不合法

这让库在命令行、测试代码或未来 GUI 中都能被复用。

### 7.2 CLI 层

`main.py` 负责把“用户可修正”的问题转换成更友好的输出：

- 参数错误
- 音名输入错误
- 路径错误
- 普通值错误

默认模式下不打印 traceback；只有传 `--debug` 时才保留完整异常细节。

## 8. 当前限制与取舍

### 8.1 干扰音连奏仍然是简化模型

当前实现只是把若干个短片段在时间轴上做重合和淡出。它并不是物理意义上的真实钢琴连奏模拟，也没有踏板建模。

这是一种听感优化，而不是乐器建模。

### 8.2 采样率不一致时只做轻量 resample

`player.py` 中包含一个简单的线性插值重采样函数。它的目标是“避免因为偶发采样率不一致而直接失败”，而不是提供高保真离线重采样。

如果以后项目大量依赖重采样质量，再考虑更专业的方案。

### 8.3 还没有统一的时间轴事件抽象

当前为了控制复杂度，没有引入 `NoteEvent` 一类的通用事件模型。  
等项目开始需要：

- 和弦
- 更复杂的旋律片段
- 动态音量
- 更灵活的时序

再引入统一事件层会更合适。

## 9. 后续扩展方向

优先级较高的扩展方向包括：

1. 正式的 `play_chord()` 接口
2. 训练结果持久化
3. 更丰富的训练模式（音程、和弦、旋律）
4. GUI 或 TUI
5. 更通用的时间轴事件抽象

如果未来确实开始支持和弦和复杂片段，比较自然的下一步就是引入“一个音频事件 = 音名 + 开始时间 + 时长 + 增益”这样的统一表示。
