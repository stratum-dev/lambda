## 方法论

该框架集成了 CPG、基于 LLM 的污点分析和 RAG，以实现结构化的漏洞推理。

### 静态分析

给定一个漏洞数据集
$\mathcal{D}=\{d_1,d_2,...,d_m\}$，
每个漏洞样本定义为
$d_i=\langle s_i,c_i\rangle$，
其中 $s_i$ 表示源代码，$c_i$ 表示漏洞先验上下文，如 CWE 描述和提交信息。我们复用了先前工作 CodeViews~\cite{das2023comex} 的编译器前端，并将其进一步扩展为一个分析工具，将源代码转换为 CPG。

我们选择 Sentence-BERT 编码器 $\mathrm{ST}(\cdot)$，它遵循广泛采用的检索实践，将文本程序元素映射为稠密表示~\cite{reimers-2019-sentence-bert}。向量数据库 $\mathbf{B}$ 存储漏洞表示，并通过 $R(\cdot,\mathbf{B})$ 支持相似性检索。

### 离线漏洞知识库构建

离线阶段从 $\mathcal{D}$ 构建一个检索数据库。
对于每个漏洞样本
$d=\langle s,c\rangle$，
源代码 $s$ 首先被转换为 CPG：

```math
\mathcal{G}=\mathrm{CPG}(s)
=({V},{E})
```

然后，执行基于 LLM 的污点分析。
针对污点子图 $\mathcal{G}$ 和漏洞上下文 $c$ 的污点分析提示被构造为 $P_\text{TA}(\mathcal{G},c)$，
其中注入了漏洞上下文 $c$。

污点推理过程公式化如下。

```math
\big(
\mathcal{T},
\mathcal{C}
\big)
=
\mathrm{LLM}
(
P_\text{TA}(\mathcal{G},c)
)
```

从生成的污点子图中提取汇点，并将其编码为检索键：

```math
\mathcal{T} \rightarrow v^\text{sink},
\quad
\boldsymbol{k}=
\mathrm{ST}
(v^\text{sink})
```

知识库存储结构化的漏洞模式及其推理链：

```math
\mathbf{B}
\leftarrow
\mathbf{B}
\cup
\{
(
\boldsymbol{k},
\mathcal{C}
)
\}
```

端到端过程的形式化定义为：

```math
\mathbf{B}
=
\bigcup_{i=1}^{m}
\Bigg\{
\Bigg(
\underbrace{
\mathrm{ST}
\big(
v^\text{sink}_{i}
\big)
}_{\boldsymbol{k}_i},
\mathcal{C}_i
\Bigg)
\Bigg|
\begin{aligned}
\mathcal{G}_i = \mathrm{CPG}(s_i), \quad \mathcal{T}_i \rightarrow v^\text{sink}_i \\
(\mathcal{T}_i,
\mathcal{C}_i)
=
\mathrm{LLM}
\big(
{P}_{\text{TA}}
(\mathcal{G}_i,c_i)
\big)
\end{aligned}
\Bigg\}
```

### 在线漏洞检测

给定一个未见过的源程序 $s$，目标是预测
$r\in\{\mathrm{Safe},\mathrm{Vulnerable}\}$。

首先，将查询程序转换为 CPG：

```math
\mathcal{G}=
\mathrm{CPG}(s)
=
({V},{E})
```

提取所有可能的污点链的提示被构造为
$P_\text{ETC}(\mathcal{G})$。
LLM 生成污点传播的所有可能子图：

```math
\mathcal{T}_{\{1,...,n\}}
=
\mathrm{LLM}
(
P_\text{ETC}(\mathcal{G})
)
```

对于每条污点路径，提取汇点。
查询表示计算如下：

```math
\mathcal{T}_{\{1,...,n\}} \rightarrow v^{\mathrm{sink}}_{\{1,...,n\}},\quad
\boldsymbol{q}_{\{1,...,n\}}
=
\mathrm{ST}
(
v^{\mathrm{sink}}_{\{1,...,n\}}
)
```

检索到的漏洞示例如下：

```math
\boldsymbol{v}_\text{\{1...n\}}
=
R
(
\boldsymbol{q}_\text{\{1...n\}}, \mathbf{B}
)
=
\{
(
\boldsymbol{k}_\text{\{1...n\}},
\mathcal{C}_{\{1...n\}}
)
\}
```

最后，检测提示集成了源代码和检索到的 CoT 示例：

```math
P_\text{detect}
(
\mathcal{C}_{1,..,n},
s
)
```

最终的漏洞预测通过以下方式获得：

```math
{r}
=
\mathrm{LLM}
P_\text{detect}
(
\mathcal{C}_{1,..,n},
s
)
\in
\{
\mathrm{Safe},
\mathrm{Vulnerable}
\}
```

端到端过程的形式化定义为：

```math
r
=
\mathrm{LLM}
\Bigg(
P_{\mathrm{detect}}
\Big(
\bigcup_{i=1}^{n}
R
\Big(
\mathrm{ST}
(
v^{\mathrm{sink}}_{\{1,...,n\}}
),
\mathbf{B},s
\Big)
\Big)
\Bigg),
\\
\text{s.t.}\quad
\mathcal{T}_{\{1,...,n\}}
=
\mathrm{LLM}
\Big(
P_{\mathrm{ETC}}
(
\mathcal{G}
)
\Big),
\\
\mathcal{T}_{\{1,...,n\}}
\rightarrow
v^{\mathrm{sink}}_{\{1,...,n\}}
```