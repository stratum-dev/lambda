## Focus on Taint: LLM-Augmented Multi-Graphs for Vulnerability Detection and Analysis

The repository of implementation for paper: *Focus on Taint: LLM-Augmented Multi-Graphs for Vulnerability Detection and Analysis*.

![](./assets/overview.svg)

## Abstract

Large language models (LLMs) show promise in vulnerability reasoning through knowledge retrieval. However, direct application to source code is unreliable, as unconstrained token-level reasoning lacks structural understanding and often induces hallucinations—-issues especially acute for language-agnostic vulnerability knowledge. Existing approaches mainly rely on task-specific fine-tuning or text-based retrieval. While the former incurs prohibitive computational costs, the latter struggles to preserve semantic knowledge consistency across divergent programming languages.
To address these limitations, we propose $\textbf{Lambda}$, an augmented and multi-graph-constrained LLM reasoning framework that frames vulnerability analysis as inference within a program-structure-induced semantic space. $\textbf{Lambda}$ abstracts programs into Code Property Graphs (CPGs) and derives taint subgraphs as highly abstract, language-agnostic knowledge that capture vulnerability-relevant information propagation chains. By filtering structurally irrelevant information, these taint subgraphs significantly reduce the reasoning space of LLMs and constrain inference toward valid program behaviors, thereby preserving vulnerability-critical patterns and mitigating hallucinations. Also, $\textbf{Lambda}$ retrieves analogous vulnerability patterns directly in the highly abstract taint subgraph semantic space, enabling language-independent knowledge transfer without parameter updates.
Extensive experiments on multi-language benchmarks demonstrate that $\textbf{Lambda}$ outperforms state-of-the-art baselines while improving inference consistency and providing explicit interpretability without retraining overhead. Our findings show that constraining LLM reasoning within program-induced semantic spaces provides a principled paradigm for reliable LLM-driven program analysis.

## Getting Start

Create the Conda environment first,

```bash
conda env create -f environment.yml
conda activate lambda
```

Then copy the example environment file `.example.env` and rename it to `.env`, and edit it to provide your LLM settings, e.g., API Key, base URL.

## License

The source code and programming implementation in this repository are licensed under the **CC BY 4.0** License, align with the requests from AAAI official.

The datasets referenced or used by this project are **NOT** included under this license. All such datasets remain the intellectual property of their respective owners and are distributed under their own licenses, terms of use, and access conditions. Users are responsible for complying with the applicable licensing requirements of the original dataset providers when downloading, using, or redistributing these datasets.
