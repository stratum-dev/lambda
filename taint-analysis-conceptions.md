# CWE Graph 

定义：$V_c = \{s, t, m, x\}$

可以理解为一个**标准漏洞传播链条（attack flow template）**

## $s$: Source pattern（漏洞源）

**含义：** 数据进入程序的不可信入口点

常见例子：
* HTTP request 参数
* 用户输入（form / API / CLI）
* socket 输入
* 文件读取内容
* 环境变量

它是：“污点数据的起点（taint origin）”

直观理解：

```text
user input → program starts trusting data
```

## $t$: Tainted propagation（污点传播）

**含义：** 数据在程序内部传播，但仍然是“污染状态”


这里不是“攻击行为”，而是：数据在变量、函数、表达式之间流动

典型形式：
* 变量赋值传播
* 函数参数传递
* 字符串拼接传播
* return value 传播

示例：

```c
a = input;
b = a;
c = b;
```

**本质：** “污点在程序中的扩散路径”

## $m$: Manipulation（恶意构造 / 关键危险操作）

**含义：** 对数据进行“危险使用/加工”的步骤

这是漏洞真正“形成攻击语义”的地方。

常见例子：

1. SQL 注入：
```sql
query = "SELECT * FROM user WHERE id=" + input;
```

2. XSS：

```javascript
html = "<div>" + user_input + "</div>"
```

3. 命令执行：

```c
system("ls " + input);
```

本质：“不安全数据被拼接进危险上下文”。这一点很关键：$t$ 只是传播，$m$ 才是“变成漏洞语义”

## $x$: Sink（漏洞汇点）

**含义：** 危险操作的最终执行点（真正触发漏洞的位置）

常见 sink：
* `eval()`
* `exec()`
* SQL query execution
* system shell execution
* HTML rendering engine

示例：

```c
system(cmd);   ← sink
```

```sql
execute(query); ← sink
```


本质：“攻击最终发生的位置”


## 整体链条的意义（非常重要）

这个 CWE Graph：

$$
s \rightarrow t \rightarrow m \rightarrow x
$$

其实是在定义：一个“理想漏洞语义路径模板”

各个元素的作用，可以这样理解：

| 阶段 | 含义   | 安全语义  |
| -- | ---- | ----- |
| s  | 数据进入 | 不可信输入 |
| t  | 传播   | 污点扩散  |
| m  | 操作   | 危险构造  |
| x  | 执行   | 漏洞触发  |


CWE 链条定义了一条从“不可信输入”到“危险执行点”的标准漏洞语义路径，中间经过污点传播与不安全操作。

但是实际上，一段代码可能有多个 CWE 链条，不同的链条之间的节点可能有交叉、共享、重叠，从而组成 Vulnerability Graphs.
