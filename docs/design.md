# 设计说明

本文档面向维护者，说明项目的内部组织、核心数据流，以及若干关键“中间结论”。

默认参数的唯一来源是 `ear_training/config.py`。  
本文档重点解释语义与分工，不在这里重复抄写默认值。

## 1. 目标与范围

当前项目目标非常收敛：

1. 从本地钢琴样本中按音名播放单音
2. 实现 `absolute_train1`
   - 播放干扰音短句
   - 等待一小段静默
   - 播放目标音
   - 读取用户输入
   - 只按十二半音判定正确性，忽略八度

项目中仍然保留了一些工程辅助文件，例如：

- `export_git_snapshot.py`
- `.aiignore`

它们对训练功能不是核心，但当前不删，因为还有其他用途。

## 2. 当前模块划分

```text
main.py
  ├─ 负责 CLI 参数解析、友好报错
  └─ 调用 ear_training 中的核心模块

ear_training/
  ├─ config.py       默认参数的唯一来源
  ├─ notes.py        音名解析与归一化
  ├─ sample_bank.py  sound/ 扫描与样本索引
  ├─ player.py       单音播放与干扰音短句渲染
  └─ trainer.py      absolute_train1 的训练流程
```

## 3. 模块职责

### 3.1 `notes.py`

职责：

- 解析用户输入的音名
- 归一化 pitch class
- 统一 sharp / flat / 本地文件名 token 的映射

不负责：

- 样本查找
- 音频播放
- 训练流程

### 3.2 `sample_bank.py`

职责：

- 扫描 `sound/*.wav`
- 建立 `(octave, pitch_class) -> SampleInfo` 索引
- 提供随机抽样与 pitch-class 子集校验

本模块只保留当前项目真正用到的接口：

- `resolve_sample(...)`
- `choose_random_sample(...)`
- `choose_random_from_pitch_class(...)`
- `validate_pitch_class_subset(...)`

未被当前主流程使用、也不太可能很快用到的展示型包装接口已经去掉。

### 3.3 `player.py`

职责：

- 播放单个样本
- 将多个干扰音样本渲染成一个连续短句，再一次性播放

这里做了一个明确设计取舍：

- **保留**：单音播放、短句渲染、峰值限制、淡出
- **删除**：按音名的额外短句包装层、临时播放器包装层、旧兼容接口
- **删除**：重采样和变声道兼容逻辑

原因是当前项目只服务于一套统一来源的钢琴样本。  
与其保留更泛化但并不需要的逻辑，不如直接假设：

- 样本采样率一致
- 样本声道数一致

如果这个假设被破坏，程序直接报错。

### 3.4 `trainer.py`

职责：

- 组织 `absolute_train1` 的完整交互流程
- 负责随机选择干扰音与目标音
- 负责判题和结果统计

已经删除的内容：

- 干扰音数量区间随机逻辑
- `gap_seconds` 这类旧兼容参数

现在训练函数只接收一个明确的 `distract_count`。

### 3.5 `main.py`

职责：

- 参数解析
- 运行前的用户输入校验
- 友好错误处理
- 显式构造 `SampleBank` / `NotePlayer` 或调用 `absolute_train1`

当前入口层不再依赖包级“一键 helper”。  
这是一次有意的瘦身：入口层稍微多写两行，但包内部少一层不必要包装。

## 4. 关键数据流

### 4.1 `play` 命令

```text
CLI note string
  -> SampleBank
  -> NotePlayer.play_note()
  -> resolve_sample()
  -> read WAV
  -> play audio
```

### 4.2 `absolute_train1`

```text
target set S
  -> normalize / validate pitch classes
  -> choose distractor samples
  -> render distractor phrase
  -> play distractor phrase
  -> wait pre_target_gap
  -> choose target sample
  -> play target sample
  -> read guess
  -> normalize guess
  -> compare pitch class only
```

## 5. 干扰音短句的正式语义

这部分是最重要的“中间定理式说明”，用于：

- 检验代码实现是否正确
- 给其他模块提供清晰语义边界

设：

- `N` = 干扰音个数，且 `N >= 1`
- `d` = `distract_duration`
- `o` = `distract_overlap`
- `f` = `distract_fade_out`
- `t` = `distract_final_tail`

则短句渲染逻辑满足：

### 5.1 片段长度

- 前 `N - 1` 个干扰音片段长度均为 `d`
- 最后一个干扰音片段长度为 `d + t`

### 5.2 起点间隔

第 `k + 1` 个干扰音的起点，与第 `k` 个干扰音的起点之间，相差：

```text
d - o
```

因此：

- `o` 表示相邻片段之间的重叠量
- `o` **包含在** `d` 中
- `o` 不是额外附加在 `d` 之后的时间

### 5.3 淡出

`f` 只作用于每个片段的末尾包络。  
它不会：

- 改变任何片段的起点
- 增加任何片段的理论长度
- 改变短句总理论时长公式

### 5.4 总理论时长

忽略采样帧取整后，短句总理论时长为：

```text
T = N * d - (N - 1) * o + t
```

这是一个可以直接拿来验证实现的结论。

### 5.5 `N = 0` 的边界情况

当 `distract_count = 0` 时：

- 不调用短句渲染器
- 不播放干扰音
- 训练流程直接退化为：

```text
pre_target_gap -> target note -> user input
```

也就是说，`N = 0` 不是“长度为 0 的短句”，而是“短句阶段整体不存在”。

## 6. 参数定义位置

项目中的默认参数统一定义在：

- `ear_training/config.py`

代码和文档都应该引用 `config.py` 的常量名，而不是复制数值。

CLI 只是把这些默认值暴露给用户；  
训练模块和播放器模块也从同一个配置源读取默认值。

## 7. 错误处理策略

### 7.1 库层

库层抛出明确异常，例如：

- `NoteFormatError`
- `ValueError`
- `InvalidWavFileError`
- `FileNotFoundError`

库层负责“准确失败”，不负责“怎么向用户显示”。

### 7.2 CLI 层

`main.py` 负责把常见用户错误转成简洁提示：

- 参数错误
- 音名输入错误
- 文件路径错误

只有在 `--debug` 时才暴露完整 traceback。

## 8. 当前刻意不做的事

为保持项目紧凑，当前不做这些更泛化的能力：

- 自动重采样
- 自动变更声道数
- 包级一键播放 helper
- 多余的样本列表展示接口
- 兼容旧版本参数名

如果以后目标真的扩大，再重新加这些能力会更清晰。
