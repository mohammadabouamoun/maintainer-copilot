# Colab Training Hand-Off & Instructions

This document is designed as a direct handoff to another AI assistant or a self-guided Google Colab session. It contains the exact context, dataset descriptions, training objectives, and required output schemas to complete the fine-tuning of the **Maintainer's Copilot** issue classifier on a GPU.

---

## 1. Project Context & Objectives

* **Project Name:** Maintainer's Copilot
* **Objective:** Fine-tune a pre-trained sequence encoder transformer to classify GitHub issues from the `fastapi/fastapi` repository into one of 4 mutually exclusive categories:
  * `bug` (label index `0`)
  * `feature` (label index `1`)
  * `docs` (label index `2`)
  * `question` (label index `3`)
* **Base Model:** `distilbert-base-uncased` (small, highly efficient sequence classification encoder).
* **Input Representation:** Formatted as `title + " [SEP] " + body[:512]` to capture both short summaries and error trace snippets.
* **Epochs:** 2
* **Batch Size:** 8
* **Learning Rate:** 2e-5

---

## 2. Dataset Specifications

The dataset consists of closed, categorized issues from `fastapi/fastapi` that have already been split chronologically (retaining temporal constraints where the test set is strictly newer than train/val).

* **Train Set (`train.jsonl`):** 781 samples
* **Val Set (`val.jsonl`):** 172 samples
* **Test Set (`test.jsonl`):** 169 samples (held-out for baseline scoring)

Each line is a JSON object with this shape:
```json
{
  "id": 12345678,
  "number": 4321,
  "title": "Bug report or feature request title",
  "body": "Detailed description containing error trace or usage...",
  "labels": ["bug", "enhancement"],
  "created_at": "2026-05-18T12:00:00Z",
  "closed_at": "2026-05-18T13:00:00Z",
  "mapped_label": "bug"
}
```

---

## 3. Google Colab Checklist & Step-by-Step Training Task

Your job when training in Google Colab is to:
1. **Set up Colab Hardware:** Enable the **T4 GPU** accelerator (Runtime -> Change runtime type -> Hardware accelerator: GPU -> T4).
2. **Mount / Upload splits:** Create a folder `data/splits/` and upload `train.jsonl` and `val.jsonl` directly.
3. **Execute Training:** Run the fine-tuning training loop using Hugging Face's `Trainer` API.
4. **Compute Hashes (Critical "Refuse-to-Boot" requirement):**
   * Compute the SHA-256 hash of the **training dataset** (`data/splits/train.jsonl`).
   * Compute the SHA-256 hash of the **saved weight binary** (typically `model.safetensors` or `pytorch_model.bin` depending on the transformers save engine).
5. **Generate Model Card (`model_card.json`):** Write a metadata JSON file inside `models/classifier/` with the exact schema below.
6. **Package and Download:** Compress the entire output `models/classifier/` directory and download it to place back into the local project structure.

### Required `model_card.json` Schema
```json
{
  "architecture": "distilbert-base-uncased",
  "num_labels": 4,
  "label_map": {
    "bug": 0,
    "feature": 1,
    "docs": 2,
    "question": 3
  },
  "hyperparameters": {
    "lr": 2e-05,
    "epochs": 2,
    "batch_size": 8,
    "weight_decay": 0.01
  },
  "training_data_hash": "<sha256 of train.jsonl>",
  "freeze_policy": "all encoder layers unfrozen after epoch 0",
  "weight_file_hash": "<sha256 of output weights file>",
  "final_metrics": {
    "accuracy": 0.852,
    "macro_f1": 0.835
  }
}
```

---

## 4. Verification & Validation Criteria

Upon completion, verify that the following files exist in the output zip:
* `config.json` (Model configuration parameters)
* `model.safetensors` or `pytorch_model.bin` (Saved weights)
* `tokenizer.json` / `vocab.txt` (Tokenizer files)
* `model_card.json` (Metadata containing hashes and accuracy/macro-F1 metrics)
