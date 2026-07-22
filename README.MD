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

Copy the example environment file `.example.env` and rename it to `.env`, and edit it to provide your LLM settings, e.g., API Key, base URL.

## Dataset

The datasets used in this work are hosted on Huggingface Repository, and it will automatically download when start the programs, so you need not download the datasets manually.

> **NOTICE:** If you are in China mainland, accessing to huggingface needs the network proxy, you should set the following environments manually before getting start:
> ```bash
> export HF_ENDPOINT=https://hf-mirror.com
> ```

## Usage

The dataset is loaded directly from HuggingFace. Use `--subset` to choose a dataset config; the pipeline automatically loads the correct split (`knowledge` for building, `inference` for detection).

### Build the knowledge base

```bash
python build.py --subset js-to-cpp   \
                [--language LANG]    \
                [--reset-db]         \
                [--start N]          \
                [--limit N]          \
                [--workers N]
```

Description of flags:

+ `--subset NAME` Dataset subset to load. Available: `cpp-only`, `java-to-cpp`, `js-to-cpp`, `debug` (default: `js-to-cpp`).
+ `--language LANG` Programming language for CPG generation (default: `javascript`). Supported: `javascript`, `cpp`, `java`, `python`. Should match the subset's language.
+ `--reset-db` Drop and re-create the ChromaDB collection before processing.
+ `--start N` Resume from row index N (0-based).
+ `--limit N` Stop after N samples.
+ `--workers N` Max parallel LLM requests (default: `LLM_MAX_WORKERS` env or 4).

Each knowledge entry is tagged with its `subset` in ChromaDB metadata, so different subsets' knowledge bases remain isolated. You can safely build multiple subsets into the same collection — queries filter by subset automatically.

### Run vulnerability detection

```bash
python detect.py --subset js-to-cpp   \
                 [--language LANG]    \
                 [--start N]          \
                 [--limit N]          \
                 [--workers N]
```

Description of flags:

+ `--subset NAME` Dataset subset to load (same options as above). Must match the subset used during `build.py` for correct retrieval.
+ `--language LANG` Programming language for CPG generation (default: `javascript`). Should match the subset's language.
+ `--start N` Resume from row index N (0-based).
+ `--limit N` Stop after N samples.
+ `--workers N` Max parallel LLM requests (default: `LLM_MAX_WORKERS` env or 4).

Retrieval automatically filters ChromaDB by `where={"subset": subset}`, so only knowledge from the matching subset is used for RAG.

## License

The source code and programming implementation in this repository are licensed under the **CC BY 4.0** License, align with the requests from AAAI official.

The datasets referenced or used by this project are **NOT** included under this license. All such datasets remain the intellectual property of their respective owners and are distributed under their own licenses, terms of use, and access conditions. Users are responsible for complying with the applicable licensing requirements of the original dataset providers when downloading, using, or redistributing these datasets.
