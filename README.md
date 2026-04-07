# Ear Training

一个基于本地钢琴 WAV 样本的命令行绝对音感训练项目。

当前目标很聚焦：

- 按音名播放单音
- 运行 `absolute_train1`：先播放一段干扰音，再播放目标音，用户在控制台输入答案
- 判定时只比较十二半音，不比较八度

项目里的默认参数统一定义在 `ear_training/config.py`。  
README 主要说明“怎么使用”和“这些参数是什么意思”，不在这里重复抄默认值。

## 1. 环境安装

推荐使用虚拟环境：

```bash
python -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## 2. 目录结构

```text
Ear-Training/
├─ sound/                    # 本地钢琴样本，形如 4-cs.wav
├─ main.py                   # 命令行入口
├─ README.md
├─ docs/
│  └─ design.md             # 面向维护者的设计文档
├─ ear_training/
│  ├─ __init__.py
│  ├─ config.py             # 默认参数的唯一来源
│  ├─ notes.py              # 音名解析与归一化
│  ├─ sample_bank.py        # 扫描并索引本地样本
│  ├─ player.py             # 单音播放与干扰音短句渲染
│  └─ trainer.py            # absolute_train1 训练流程
├─ export_git_snapshot.py   # 工程辅助脚本
└─ .aiignore                # 给导出脚本使用的额外忽略规则
```

## 3. 样本命名规则

项目默认读取 `sound/*.wav`，并假设文件名类似：

- `4-c.wav`
- `4-cs.wav`
- `4-d.wav`

其中：

- 前半部分是八度
- 后半部分是音名 token
- `cs / ds / fs / gs / as` 分别表示升号音

## 4. 快速开始

播放一个单音：

```bash
python main.py play C4
python main.py play F#4 --duration 1.5
python main.py play cs --default-octave 5
```

开始训练：

```bash
python main.py absolute_train1 --set C D# F# A
python main.py absolute_train1 --set C D# F# A --rounds 10
python main.py absolute_train1 --set C D# F# A --distract-count 0
```

## 5. 支持的输入格式

音名支持这些写法：

- `C4`
- `C#4`
- `Db4`
- `C`
- `cs`
- `4-cs`

训练判定时只比较 pitch class，所以：

- `C3`
- `C4`
- `C5`

都视为同一个答案 `C`。

## 6. 关键参数的含义

所有默认值都在 `ear_training/config.py`。  
这里重点说明语义，而不是重复写默认值。

### `distract_count`

每轮干扰音的数量。允许为 `0`。

- 当 `distract_count > 0` 时，会先播放一段干扰音短句，再播放目标音
- 当 `distract_count = 0` 时，会跳过干扰音短句，直接进入：

```text
pre_target_gap -> target note -> user input
```

### `distract_duration`

每个干扰音的**标称时长**。

这里的“标称时长”指的是：相邻干扰音在时间轴上排布时，每个音占据的基本时间槽长度。  
它不是“纯粹独占、绝不重叠”的时长，因为相邻音之间可以有 `distract_overlap`。

### `distract_overlap`

相邻两个干扰音的重合时长。

它**包含在** `distract_duration` 内，而不是在 `distract_duration` 之后额外再加一段。  
因此，相邻两个干扰音的起点间隔是：

```text
distract_duration - distract_overlap
```

### `distract_fade_out`

每个干扰音尾部的淡出时长。

它只改变音尾包络，不改变任何音的起点，也不额外增加总时长。

### `distract_final_tail`

只加在**最后一个**干扰音上的额外尾音时长。

因此，一个有 `N >= 1` 个干扰音的短句，总理论时长为：

```text
N * distract_duration - (N - 1) * distract_overlap + distract_final_tail
```

忽略采样帧取整的话，这个公式可以直接用来检查实现是否正确。

### `pre_target_gap`

干扰音短句结束后，到目标音开始前的静默时长。

这段静默**不属于**干扰音短句内部，而是短句结束后的额外等待。

### `target_duration`

目标音的播放时长。  
它和干扰音参数分开设置，因为目标音通常需要更长的聆听时间。

## 7. 代码方式使用

项目不再提供“一键包装层”式 helper。  
如果你在 Python 里使用它，推荐显式构造对象：

```python
from ear_training import SampleBank, NotePlayer, absolute_train1

sample_bank = SampleBank("sound")
player = NotePlayer(sample_bank)

player.play_note("C4", 1.0)

absolute_train1(
    ["C", "D#", "F#", "A"],
    sound_dir="sound",
)
```

## 8. 常见问题

### 为什么干扰音不是一个个单独播放？

因为单独重复启动播放设备会让音头/音尾非常生硬。  
现在的实现会先把整段干扰音渲染成一条连续音频，再一次播放，听感更自然。

### 为什么项目假设样本采样率和声道数一致？

因为你当前这批本地钢琴样本本来就是统一来源。  
项目选择“假设一致并在不一致时报错”，而不是为了极少见情况保留更重的重采样/变声道兼容逻辑。

### 默认参数在哪里改？

统一改 `ear_training/config.py`。

CLI 不传参时，会使用 `config.py` 中的默认值。  
你也可以在命令行里临时覆盖：

```bash
python main.py absolute_train1 --set C D E --distract-count 0 --target-duration 2.5
```

## 9. 调试

默认情况下，命令行只显示简洁的用户错误。  
需要完整 traceback 时，加 `--debug`：

```bash
python main.py --debug play C5s
```
