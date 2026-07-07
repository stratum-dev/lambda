# Lambda $\lambda$

**L**LM-**A**ugmented **M**ulti-Graphs for Vulnerability **D**etection and **A**nalysis

## 问题定义

给定：源代码：$S$，CWE 描述：$C$

目标：判断是否存在漏洞，并给出解释路径：$f(S, C) \rightarrow (y, \mathcal{P})$

其中：

* $y \in \{0,1\}$：是否存在漏洞
* $\mathcal{P}$：可解释路径（reasoning chain）

## Program Graph 形式化（CPG）

将代码转换为异构图：$G_p = (V_p, E_p, \tau_v, \tau_e)$

节点集合：$V_p = V_{ast} \cup V_{dfg} \cup V_{cfg}$

边集合：$E_p = E_{ast} \cup E_{dfg} \cup E_{cfg}$

类型函数：

* 节点类型：$\tau_v: V_p \rightarrow \{\text{stmt, var, call, literal, block}\}$
* 边类型：$\tau_e: E_p \rightarrow \{\text{AST, CFG, DFG}\}$

## CWE Graph 形式化

将 CWE 转换为攻击模式图：$G_c = (V_c, E_c)$

节点：$V_c = \{s, t, m, x\}$

分别表示：

* $s$: source pattern
* $t$: tainted propagation
* $m$: manipulation (e.g., SQL concat)
* $x$: sink

边：$E_c = \{(s \rightarrow t), (t \rightarrow m), (m \rightarrow x)\}$

## 图对齐（Graph Alignment）

定义一个映射函数：$\phi: V_p \rightarrow V_c \cup \{\varnothing\}$

用于将程序节点映射到 CWE 模式节点：

$$
\phi(v) =
\begin{cases}
s & \text{if } v \text{ is source} \\
t & \text{if tainted} \\
m & \text{if SQL construction} \\
x & \text{if sink} \\
\varnothing & \text{otherwise}
\end{cases}
$$

## Path Extraction（核心）

从程序图中抽取路径集合：$\mathcal{P}_p = \{p_1, p_2, ..., p_k\}$

每条路径：$p = (v_1 \rightarrow v_2 \rightarrow ... \rightarrow v_n)$

满足：$(v_i, v_{i+1}) \in E_p$

## CWE Path Pattern

定义 CWE 模式路径：

$$
\mathcal{P}_c = (s \rightarrow t \rightarrow m \rightarrow x)
$$

## Path Matching Function（关键）

定义相似度函数：

$$
\mathcal{M}(p, p_c) = \sum_{i=1}^{n} \mathbb{1}[\phi(v_i) = p_c^i]
$$

归一化：

$$
\text{score}(p) = \frac{\mathcal{M}(p, \mathcal{P}_c)}{|\mathcal{P}_c|}
$$

## Vulnerability Decision

最终预测：

$$
y =
\begin{cases}
1 & \max_{p \in \mathcal{P}_p} \text{score}(p) \ge \delta \\
0 & \text{otherwise}
\end{cases}
$$

其中：$\delta$ 表示阈值

## Graph RAG 形式化（重点）

本质是：

### Retrieval Function

从图数据库检索子图：$G_r = \mathcal{R}(G_p, C)$

其中：$\mathcal{R}: (G_p, q) \rightarrow G_r$

$q$ 可以是：CWE query embedding、node embedding、path embedding

### Retrieval Objective

$$
G_r = \arg\max_{G' \subset G_p} \text{sim}(G', G_c)
$$

## Path-based Reasoning Chain

定义解释函数：

$$
\mathcal{E}(p) = (v_1, v_2, ..., v_n)
\Rightarrow \text{natural language}
$$

生成：

$$
\mathcal{P}_{text} = \text{LLM}(\mathcal{E}(p), C)
$$

## LLM 推理函数

完整模型：

$$
f(S, C) =
\text{LLM}(
\mathcal{R}(G_p, C),
\arg\max_{p \in \mathcal{P}_p} \text{score}(p)
)
$$

## 总体结构

整个方法可以压缩成：

$$
\boxed{
S \xrightarrow{\text{CPG}} G_p
\xrightarrow{\text{Graph RAG}} G_r
\xrightarrow{\text{Path Matching}} \mathcal{P}
\xrightarrow{\text{LLM}} (y, \text{explanation})
}
$$

## AAAI增强点

Graph-constrained decoding. LLM only generates：$\text{valid paths in } G_p$