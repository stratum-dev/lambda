# Lambda $\lambda$：

**L**LM-**A**ugmented **M**ulti-Graphs for Vulnerability **D**etection and **A**nalysis

## 问题定义

给定：

* 源代码：$S$
* 漏洞类型描述（CWE）：$C$

目标是学习一个映射函数：

$$
f(S, C) \rightarrow (y, \mathcal{H})
$$

其中：

* $y \in \{0,1\}$：是否存在漏洞
* $\mathcal{H}$：用于解释漏洞的**结构化推理子图**

## 程序图构建（CPG）

将源代码表示为异构程序图：

$$
G_p = (V_p, E_p, \tau_v, \tau_e)
$$

### 节点集合：

$$
V_p = V_{ast} \cup V_{cfg} \cup V_{dfg}
$$

### 边集合：

$$
E_p = E_{ast} \cup E_{cfg} \cup E_{dfg}
$$

### 类型函数：

* 节点类型：
  $$
  \tau_v: V_p \rightarrow {\text{stmt, var, call, literal, block}}
  $$

* 边类型：
  $$
  \tau_e: E_p \rightarrow \{\text{AST, CFG, DFG}\}
  $$

## CWE 攻击模式图建模

将 CWE 语义抽象为攻击模式图：

$$
G_c = (V_c, E_c)
$$

### 节点定义：

$$
V_c = {s, t, m, x}
$$

分别表示：

* $s$：漏洞源（source）
* $t$：污点传播（taint propagation）
* $m$：恶意操作（如拼接、转换）
* $x$：漏洞汇点（sink）

### 边定义：

$$
E_c = \{(s \rightarrow t), (t \rightarrow m), (m \rightarrow x)\}
$$

## 概率化图对齐（核心改进一）

不同于传统的硬映射函数 $\phi$，我们引入**概率语义对齐模型**：

$$
P(v \rightarrow c_i) = \text{softmax}\left(\frac{\text{sim}(h_v, h_{c_i})}{\tau}\right)
$$

### 路径级对齐得分：

对于程序路径：

$$
p = (v_1, v_2, ..., v_n)
$$

定义其与 CWE 模式路径的匹配概率：

$$
\text{score}_{align}(p) =
\sum_{i=1}^{n} \log P(v_i \rightarrow c_i)
$$

## 因果感知路径建模

我们进一步引入**数据流因果约束**：

$$
\mathcal{C}(p) =
\prod_{i=1}^{n-1} P(v_{i+1} \mid v_i, \text{DFG})
$$

最终路径评分函数：

$$
\text{Score}(p) =
\text{score}_{align}(p) \cdot \mathcal{C}(p)
$$

## CWE 条件子图生成

不同于传统“检索子图”，我们定义**结构诱导式子图生成**：

$$
G_r = \arg\max_{G' \subset G_p}
\left[
\text{Coverage}(G', C)_\lambda \cdot \text{Complexity}(G')
  \right]
$$

其中：

* Coverage：子图与 CWE 的语义覆盖度
* Complexity：结构复杂度正则项

### CWE 潜变量表示：

$$
z_C = \text{Encoder}(C)
$$

因此：

$$
G_r = \text{Induce}(G_p, z_C)
$$

## 推理单位升级：从“路径”到“子图”

我们不再仅依赖单路径，而是建模：

$$
\mathcal{H} = (V_h, E_h) \subset G_r
$$

满足约束：

* 至少包含一个 source 节点
* 至少包含一个 sink 节点
* 保持图连通性

### 子图评分函数：

$$
\text{Score}(\mathcal{H}) =
\sum_{p \in \mathcal{P}(\mathcal{H})}
\text{Score}(p)
$$

## LLM 引导的验证–修复–约束推理

我们引入闭环推理机制：

### （1）路径验证

$$
V(p) \in {0,1}
$$

### （2）路径修复

当路径不合法时：

$$
p' = \text{LLM}_{repair}(p, G_p)
$$

### （3）受约束生成

LLM 仅允许在程序图约束内生成：

$$
y, \mathcal{H} \sim \text{LLM}(\text{valid paths in } G_p)
$$

## 最终决策函数

$$
y =
\begin{cases}
1 & \max_{\mathcal{H}} \text{Score}(\mathcal{H}) \ge \delta \\
0 & \text{otherwise}
\end{cases}
$$

## 整体流程

整个方法可以表示为：

$$
S
\xrightarrow{\text{CPG构建}}
G_p
\xrightarrow{\text{CWE条件子图生成}}
G_r
\xrightarrow{\text{概率 + 因果推理}}
\mathcal{H}
\xrightarrow{\text{LLM验证与修复}}
(y, \text{解释路径})
$$

## 方法要点总结

* **概率化 CWE 对齐机制** 我们将传统硬编码映射函数 $\phi$ 替换为不确定性感知的概率对齐模型，从而提升语义匹配鲁棒性。
* **因果感知漏洞路径建模** 通过引入数据流约束，我们显式建模程序执行中的因果依赖关系，从而减少虚假路径推理。
* **CWE 条件子图推理式 Graph RAG** 将传统“检索子图”升级为“结构诱导子图生成”，实现 CWE 条件下的程序结构自适应抽取。
* **LLM 验证–修复闭环推理机制** 提出 LLM 参与的结构约束推理循环，使模型能够修正非法路径并生成符合程序语义的推理子图。
