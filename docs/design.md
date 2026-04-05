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
- 和弦/音程训练

代码结构因此刻意保持轻量，并把“样本解析”“播放”“训练流程”分开。

## 2. 总体结构

```text
main.py                 命令行入口
ear_training/__init__.py  包级别导出
ear_training/notes.py     音名解析与归一化
ear_training/sample_bank.py 样本索引与检索
ear_training/player.py    样本读取与播放
ear_training/trainer.py   训练流程
export_git_snapshot.py    导出当前工作区快照
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

### 3.2 `ear_training/__init__.py`

职责：

- 提供包级别的公共导出
- 提供 `play_note()` 这种一行可用的 helper

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
- 提供播放层兼容 helper，例如 `build_trimmed_wav_bytes()`

当前实现选型：

- `soundfile`：读取 WAV 到 NumPy 数组
- `sounddevice`：播放 NumPy 数组

选择这条路线的原因：

- 兼容 IEEE float WAV
- 以后扩展和弦/混音/数组级处理更自然
- 避免继续维护手写 WAV 解析逻辑

当前边界：

- 只做播放，不做训练控制
- 暂未提供正式的和弦接口

### 3.6 `ear_training/trainer.py`

职责：

- 实现 `absolute_train1`
- 控制训练轮次、干扰音、目标音和用户输入
- 负责把训练结果整理成 `TrainRoundResult`

训练流程：

1. 校验集合 `S` 和参数
2. 随机播放若干干扰音
3. 从目标集合中选择一个 pitch class
4. 从该 pitch class 的样本中随机选取一个 concrete sample
5. 播放目标音
6. 读取用户输入并归一化
7. 仅按 pitch class 比较对错

关键点：

- “忽略八度”这一训练规则只在训练层生效
- 干扰音和目标音都通过 `SampleBank` 与 `NotePlayer` 获取/播放

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

### 5.2 `absolute_train1`

```text
CLI 输入集合 S
  -> normalize_pitch_class_set(S)
  -> SampleBank.validate_pitch_class_subset(...)
  -> 随机播放干扰音
  -> 随机选择目标 pitch class
  -> 随机选择目标 sample
  -> 播放目标音
  -> 用户输入答案
  -> normalize_pitch_class(guess)
  -> 按 pitch class 判断对错
```

### 5.3 `export_git_snapshot.py`

```text
git ls-files
  -> 生成基础文件集合
  -> 应用 .aiignore 与 --exclude
  -> 排除输出归档自身
  -> 写入 zip/tar
```

## 6. 错误处理策略

### 6.1 库层

库层函数与类方法遇到错误时，优先抛出明确异常：

- `NoteFormatError`：音名无法解析
- `FileNotFoundError` / `NotADirectoryError`：路径问题
- `InvalidWavFileError`：音频文件损坏或无法读取
- `ValueError`：参数值不合法

原则：

- 库层负责“准确失败”
- 库层不负责决定错误如何展示给最终用户

### 6.2 CLI 层

`main.py` 捕获用户可修正错误，输出简洁提示并返回非零退出码。

例如：

- 非法音名
- `sound` 目录不存在
- 参数范围错误

`--debug` 用于在需要时显示完整 traceback，便于排查未预期错误。

## 7. 依赖选择

### 运行时依赖

- `numpy`：音频数组处理
- `soundfile`：读取 WAV
- `sounddevice`：播放音频
- `pathspec`：解析 `.aiignore` / `--exclude` 的 gitignore 风格规则

### 为什么不是 `winsound`

早期版本曾使用 `winsound`。后续改为 `soundfile + sounddevice`，主要原因是：

- 需要兼容 IEEE float WAV
- 需要更自然的数组级音频处理能力
- 为将来的多音同时播放预留空间

## 8. 扩展方向

比较自然的下一步包括：

1. 增加和弦播放接口，例如 `play_notes_simultaneously()`
2. 加入限制音域的训练参数
3. 持久化保存训练结果
4. 提供 GUI
5. 增加音程训练、和弦训练、旋律训练

扩展时建议继续保持以下边界：

- `notes.py`：只做音名语义，不做训练规则
- `sample_bank.py`：只做样本组织，不做播放控制
- `player.py`：只做播放，不负责训练流程
- `trainer.py`：只做训练流程，不直接操纵文件系统

## 9. 文档约定

本项目采用这套文档职责分工：

- `README.md`：面向使用者，回答“怎么安装、怎么运行、怎么使用”
- `docs/design.md`：面向维护者，回答“模块怎么分工、为什么这样设计”
- docstring：面向写代码的人，说明类、函数和模块的具体职责与调用约束
