---
base_model:
- Qwen/Qwen2.5-VL-3B-Instruct
language:
- en
library_name: colpali
license: apache-2.0
---
# ColQwen2.5: Visual Retriever based on Qwen2.5-VL-3B-Instruct with ColBERT strategy

ColQwen is a model based on a novel model architecture and training strategy based on Vision Language Models (VLMs) to efficiently index documents from their visual features. It is a Qwen2.5-VL-3B extension that generates ColBERT- style multi-vector representations of text and images.  It was introduced in the paper ColPali: Efficient Document Retrieval with Vision Language Models and first released in this repository

This version is the untrained base version to guarantee deterministic projection layer initialization.

## Usage

> [!WARNING] This version should not be used: it is solely the base version useful for deterministic LoRA initialization.

## Contact

- Manuel Faysse: manuel.faysse@illuin.tech
- Hugues Sibille: hugues.sibille@illuin.tech
- Tony Wu: tony.wu@illuin.tech

## Citation

If you use any datasets or models from this organization in your research, please cite the original dataset as follows:

```bibtex
@misc{faysse2024colpaliefficientdocumentretrieval,
  title={ColPali: Efficient Document Retrieval with Vision Language Models},
  author={Manuel Faysse and Hugues Sibille and Tony Wu and Bilel Omrani and Gautier Viaud and Céline Hudelot and Pierre Colombo},
  year={2024},
  eprint={2407.01449},
  archivePrefix={arXiv},
  primaryClass={cs.IR},

}
```
