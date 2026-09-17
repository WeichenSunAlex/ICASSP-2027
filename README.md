# 独立版 AG2 Many-Agent 医疗诊断系统

这是从原项目提交 01826c0 中剥离出的、未加入节点污染功能的层级式 many-agent 基线。它不依赖原仓库中的 mac_core、mac_ag2、mac_legacy、旧版 pyautogen、评估脚本或历史输出目录。

项目只声明一个顶层运行依赖：ag2[openai]==0.12.1。Python 标准库负责命令行、数据加载和结果保存；科室 YAML 的解析器是 AG2 自身的传递依赖。

## 目录结构

~~~text
standalone_ag2_many_agent/
├── ag2_system/                 # agents、AG2 编排、schemas、CLI
│   └── configs/departments.yaml
├── configs/experiment.json    # 唯一实验配置入口
├── data/sample_cases.json     # 可直接运行的示例数据
├── tests/test_smoke.py        # 无第三方测试框架的 mock 冒烟测试
├── FLOW.md                    # 流程、输入输出和配置说明
└── requirements.txt           # 仅 AG2
~~~

## 1. 安装

建议使用 Python 3.10–3.13。在本目录中执行：

### Windows PowerShell

~~~powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -U pip
python -m pip install -r requirements.txt
~~~

### Linux/macOS

~~~bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
~~~

## 2. 先做本地冒烟运行

Mock 模式不会请求模型 API，用于验证配置、路由、委员会激活、Board 汇总、Final Judge 输出和结果落盘：

~~~powershell
python -m ag2_system --config configs/experiment.json --mock --limit 1 --force
~~~

结果写入：

~~~text
output/initial/gpt-4o-mini/sample-001.json
~~~

运行内置测试：

~~~powershell
python -m unittest discover -s tests -v
~~~

## 3. 真实 AG2 运行

默认配置使用 OpenAI provider。先设置凭据，再运行：

~~~powershell
$env:OPENAI_API_KEY = "你的密钥"
python -m ag2_system --config configs/experiment.json --live --limit 1 --force
~~~

使用 OpenAI 兼容接口时，可以使用统一的独立版环境变量：

~~~powershell
$env:AG2_API_KEY = "你的密钥"
$env:AG2_BASE_URL = "https://your-provider.example/v1"
~~~

然后把 configs/experiment.json 中的 model_name 改为接口实际支持的模型名，model_provider 保持 openai，再执行 live 命令。不要把真实密钥写入配置文件或提交到 Git。

Live 模式会让所有启用科室的主任各调用一次模型，再运行被激活委员会。首次联调可在 enabled_departments 中只保留 3–5 个科室，以控制耗时与调用成本；正式实验再恢复空数组，表示使用全部科室。

## 4. 使用自己的数据

命令行可直接覆盖数据路径：

~~~powershell
python -m ag2_system --config configs/experiment.json --dataset C:\path\cases.json --mock --limit 2 --force
~~~

支持两种 JSON 顶层格式：对象中的 Cases 数组，或直接使用数组。单条病例既兼容原项目字段，也支持精简字段：

~~~json
{
  "case_type": "rare_disease",
  "case_name": "可选的真实标签或病例名",
  "case_id": "case-001",
  "initial_presentation": "初诊信息",
  "follow_up_presentation": "随访信息"
}
~~~

原项目的 Type、Final Name、Case URL、Initial Presentation、Follow-up Presentation 字段也可直接读取。完整原始数据集不复制进子项目，以避免把 302 条历史实验数据一并打包；需要时通过 --dataset 指向它即可。

## 5. 常用命令

只跑第 0 条病例：

~~~powershell
python -m ag2_system --config configs/experiment.json --mock --case-index 0 --force
~~~

不加 --force 时，已存在的结果会自动跳过。--mock 和 --live 互斥；两者都不写时使用配置文件中的 mock 值。

## 6. 边界说明

- 没有异常节点选择器、污染 prompt、污染 trace、冻结路由或异常实验配置。
- 为保持最小运行边界，默认未使用的独立反方节点也已移除；冲突仍由普通委员会、Board 和 Final Judge 处理。
- Mock 模式只验证控制流，输出不是有效医疗诊断。
- Live 模式的输出仅适用于科研实验，不应直接用于临床决策。
- 当前 total_cost 保留为兼容字段，尚未接入 provider 的真实计费统计。

更完整的阶段说明和关键配置见 [FLOW.md](FLOW.md)。
