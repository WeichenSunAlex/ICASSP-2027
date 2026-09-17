# 运行流程与配置说明

## 一、端到端流程

~~~mermaid
flowchart TD
    A[读取一条病例] --> B[所有普通科室主任各发言一次]
    B --> C[Triage Router 综合病例与主任 brief]
    C --> D[只激活 top-k 个委员会]
    D --> E[激活委员会成员按轮次讨论]
    E --> F[委员会主任输出结构化 summary]
    F --> G[Board 多对一汇总]
    G --> H{仍有冲突且未超上限?}
    H -- 是 --> I[Board 发起有限轮次复核]
    I --> G
    H -- 否 --> J[Final Judge 裁决]
    J --> K[保存病例结果与完整事件/路由日志]
~~~

这对应基线的 Scheme A：

1. 所有普通科室主任在初筛阶段必须发言一次。
2. Router 只激活与病例最相关的少量委员会。
3. 只有被激活委员会的成员进入深度讨论。
4. 激活委员会首轮保证每名成员至少发言一次。
5. 委员会只把结构化 summary 向上提交，避免所有 agent 共用一个扁平上下文。
6. Board 处理跨委员会冲突，Final Judge 只根据病例、Board 与委员会 summary 作最终裁决。

## 二、AG2 在哪里使用

Live 模式下，AG2 的 ConversableAgent、RoundRobinPattern、DefaultPattern、AutoPattern、handoff 和 initiate_group_chat 负责真实 agent 对话。Mock 模式复用相同的层级控制流，但用确定性内容代替模型调用，便于离线检查拓扑与日志。

ag2 安装包的 Python 导入命名空间仍叫 autogen，因此源码中的 from autogen import ... 是 AG2 包的正常用法，不代表依赖旧版 pyautogen。

## 三、关键配置

configs/experiment.json 中最常用的字段如下：

| 字段 | 作用 |
| --- | --- |
| model_provider | AG2 provider 类型；OpenAI 兼容接口使用 openai |
| model_name | 默认模型名，所有角色未单独配置时共用 |
| stage | initial 或 follow_up |
| dataset_path | 病例 JSON 路径，按项目根目录解析 |
| top_k_committees | Router 最多保留的委员会数 |
| min_k_committees / max_k_committees | 动态激活数量上下界 |
| internal_discussion_rounds_per_member | 激活委员会中每名成员的讨论轮数 |
| board_followup_max_rounds | Board 冲突复核最大轮数 |
| use_native_ag2 | Live 模式是否使用 AG2 原生群聊编排 |
| strict_native_ag2 | AG2 API 不可用时是否立即失败 |
| heterogeneous_models | 可选：按角色覆盖模型；空对象表示全角色同模型 |

异构模型覆盖示例：

~~~json
"heterogeneous_models": {
  "triage_router": {"model_provider": "openai", "model_name": "router-model"},
  "committee_member": {"model_provider": "openai", "model_name": "member-model"},
  "final_judge": {"model_provider": "openai", "model_name": "judge-model"}
}
~~~

可覆盖的角色名是 triage_router、department_chair、committee_member、board 和 final_judge。

## 四、输出结构

每条病例生成一个 JSON，顶层包含：

- 病例标识、阶段和输入 presentation；
- most_likely_diagnosis；
- differential_diagnoses；
- recommended_tests；
- areas_of_disagreement；
- metadata.canonical_result：完整 many-agent 结果；
- metadata.canonical_result.metadata.event_log：逐条消息事件；
- metadata.canonical_result.metadata.routing_log：路由记录；
- metadata.canonical_result.metadata.activated_committees：被激活委员会；
- canonical 结果顶层的 committee_summaries：完整委员会 summary。

输出同时记录 baseline_source_commit: 01826c0 和 node_pollution_enabled: false，用于区分污染实验分支。

## 五、从原项目剥离掉的内容

独立版没有带入以下内容：

- main.py、main_ws.py、main_wo_supr.py 等 legacy flat MAC；
- mac_ag2 中的 flat/legacy many-agent 兼容入口；
- mac_core 的历史兼容层；
- 默认未启用的独立反方节点及其角色注入参数；
- 节点异常/污染模块、异常实验脚本和异常测试；
- evaluate.py、训练 shell 脚本、旧输出和重算目录；
- pandas、tqdm、pytest 等与独立推理无关的顶层依赖。
