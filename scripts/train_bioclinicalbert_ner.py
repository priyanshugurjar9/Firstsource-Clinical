"""Fine-tune BioClinicalBERT for the POC entity labels.

The default configuration freezes most encoder layers so the script remains
practical on a CPU. Use --unfreeze-layers 2 for a deeper fine-tune when compute
is available.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
from collections import defaultdict
from pathlib import Path

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import torch
from seqeval.metrics import f1_score, precision_score, recall_score
from torch.utils.data import DataLoader, Dataset
from transformers import AutoModelForTokenClassification, AutoTokenizer

ROOT = Path(__file__).resolve().parents[1]
DOCUMENT_CSV = ROOT / "data" / "clinical_poc_synthetic_dataset.csv"
ENTITY_CSV = ROOT / "data" / "clinical_poc_entity_annotations.csv"
OUTPUT_DIR = ROOT / "models" / "bioclinicalbert-ner"
BASE_MODEL = "emilyalsentzer/Bio_ClinicalBERT"

ENTITY_TYPES = ["ALLERGY", "DIAGNOSIS", "LAB_RESULT", "MEDICATION", "RED_FLAG", "SYMPTOM"]
LABELS = ["O"] + [f"{prefix}-{entity}" for entity in ENTITY_TYPES for prefix in ("B", "I")]
LABEL2ID = {label: index for index, label in enumerate(LABELS)}
ID2LABEL = {index: label for label, index in LABEL2ID.items()}


def read_records():
    documents = {}
    with DOCUMENT_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            documents[row["doc_id"]] = row

    annotations = defaultdict(list)
    with ENTITY_CSV.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            annotations[row["doc_id"]].append(
                {
                    "label": row["entity_label"],
                    "start": int(row["start_char"]),
                    "end": int(row["end_char"]),
                }
            )
    return documents, annotations


class ClinicalNerDataset(Dataset):
    def __init__(self, records, annotations, tokenizer, max_length=256):
        self.items = []
        for row in records:
            encoded = tokenizer(
                row["clinical_note"],
                truncation=True,
                padding="max_length",
                max_length=max_length,
                return_offsets_mapping=True,
            )
            labels = self._align_labels(encoded["offset_mapping"], annotations[row["doc_id"]])
            encoded.pop("offset_mapping")
            encoded["labels"] = labels
            self.items.append({key: torch.tensor(value) for key, value in encoded.items()})

    @staticmethod
    def _align_labels(offsets, spans):
        labels = []
        for token_start, token_end in offsets:
            if token_start == token_end:
                labels.append(-100)
                continue
            assigned = "O"
            for span in spans:
                if token_start >= span["start"] and token_end <= span["end"]:
                    prefix = "B" if token_start == span["start"] else "I"
                    assigned = f"{prefix}-{span['label']}"
                    break
            labels.append(LABEL2ID[assigned])
        return labels

    def __len__(self):
        return len(self.items)

    def __getitem__(self, index):
        return self.items[index]


def prepare_model(unfreeze_layers: int):
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, use_fast=True, local_files_only=True)
    model = AutoModelForTokenClassification.from_pretrained(
        BASE_MODEL,
        num_labels=len(LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
        local_files_only=True,
        ignore_mismatched_sizes=True,
    )

    for parameter in model.base_model.parameters():
        parameter.requires_grad = False

    encoder_layers = model.base_model.encoder.layer
    if unfreeze_layers:
        for layer in encoder_layers[-unfreeze_layers:]:
            for parameter in layer.parameters():
                parameter.requires_grad = True

    for parameter in model.classifier.parameters():
        parameter.requires_grad = True
    return tokenizer, model


def label_weights(dataset, device, outside_weight: float):
    counts = torch.ones(len(LABELS), dtype=torch.float)
    for item in dataset:
        labels = item["labels"]
        valid = labels[labels != -100]
        counts += torch.bincount(valid, minlength=len(LABELS)).float()
    # Square-root inverse frequency is less aggressive than full inverse
    # frequency and improves precision on highly imbalanced token labels.
    weights = torch.sqrt(counts.sum() / (len(LABELS) * counts))
    weights = weights / weights.mean()
    weights[LABEL2ID["O"]] *= outside_weight
    return weights.to(device)


def train_epoch(model, loader, optimizer, device, class_weights):
    model.train()
    total_loss = 0.0
    criterion = torch.nn.CrossEntropyLoss(weight=class_weights, ignore_index=-100)
    for batch in loader:
        batch = {key: value.to(device) for key, value in batch.items()}
        optimizer.zero_grad()
        labels = batch.pop("labels")
        logits = model(**batch).logits
        loss = criterion(logits.view(-1, len(LABELS)), labels.view(-1))
        loss.backward()
        optimizer.step()
        total_loss += loss.item()
    return total_loss / max(len(loader), 1)


def decode_sequence(probabilities, confidence_threshold):
    predicted_ids = probabilities.argmax(dim=-1).tolist()
    decoded = []
    previous_type = None
    for token_probs, predicted_id in zip(probabilities, predicted_ids):
        label = ID2LABEL[predicted_id]
        confidence = float(token_probs[predicted_id])
        if label != "O" and confidence < confidence_threshold:
            label = "O"
        if label == "O":
            previous_type = None
            decoded.append(label)
            continue
        prefix, entity_type = label.split("-", 1)
        if prefix == "I" and previous_type != entity_type:
            label = f"B-{entity_type}"
        previous_type = entity_type
        decoded.append(label)
    return decoded


def evaluate(model, loader, device, confidence_threshold=0.0):
    model.eval()
    predicted_sequences = []
    target_sequences = []
    with torch.no_grad():
        for batch in loader:
            labels = batch["labels"]
            model_batch = {key: value.to(device) for key, value in batch.items()}
            logits = model(**model_batch).logits.cpu()
            probabilities = logits.softmax(dim=-1)
            for token_probabilities, target in zip(probabilities, labels):
                predicted = decode_sequence(token_probabilities, confidence_threshold)
                predicted_labels = []
                target_labels = []
                for predicted_label, target_id in zip(predicted, target.tolist()):
                    if target_id == -100:
                        continue
                    predicted_labels.append(predicted_label)
                    target_labels.append(ID2LABEL[target_id])
                predicted_sequences.append(predicted_labels)
                target_sequences.append(target_labels)
    return {
        "precision": precision_score(target_sequences, predicted_sequences),
        "recall": recall_score(target_sequences, predicted_sequences),
        "f1": f1_score(target_sequences, predicted_sequences),
    }


def tune_confidence_threshold(model, loader, device):
    candidates = [0.0, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    scored = []
    for threshold in candidates:
        metrics = evaluate(model, loader, device, threshold)
        scored.append((metrics["f1"], metrics["precision"], threshold, metrics))
    _, _, best_threshold, best_metrics = max(scored)
    return best_threshold, best_metrics


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--classifier-learning-rate", type=float, default=5e-4)
    parser.add_argument("--encoder-learning-rate", type=float, default=2e-5)
    parser.add_argument("--unfreeze-layers", type=int, default=0)
    parser.add_argument("--max-length", type=int, default=256)
    parser.add_argument("--outside-weight", type=float, default=0.8)
    args = parser.parse_args()

    random.seed(42)
    torch.manual_seed(42)
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    documents, annotations = read_records()
    split_rows = defaultdict(list)
    for row in documents.values():
        split_rows[row["split"]].append(row)

    tokenizer, model = prepare_model(args.unfreeze_layers)
    model.to(device)

    train_dataset = ClinicalNerDataset(
        split_rows["train"], annotations, tokenizer, max_length=args.max_length
    )
    validation_dataset = ClinicalNerDataset(
        split_rows["validation"], annotations, tokenizer, max_length=args.max_length
    )
    test_dataset = ClinicalNerDataset(
        split_rows["test"], annotations, tokenizer, max_length=args.max_length
    )

    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True)
    validation_loader = DataLoader(validation_dataset, batch_size=args.batch_size)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size)

    classifier_parameters = list(model.classifier.parameters())
    classifier_ids = {id(parameter) for parameter in classifier_parameters}
    encoder_parameters = [
        parameter
        for parameter in model.parameters()
        if parameter.requires_grad and id(parameter) not in classifier_ids
    ]
    parameter_groups = [
        {"params": classifier_parameters, "lr": args.classifier_learning_rate},
    ]
    if encoder_parameters:
        parameter_groups.append(
            {"params": encoder_parameters, "lr": args.encoder_learning_rate}
        )
    optimizer = torch.optim.AdamW(parameter_groups, weight_decay=0.01)
    class_weights = label_weights(train_dataset, device, args.outside_weight)

    best_f1 = -1.0
    best_state = None
    best_threshold = 0.0
    history = []
    for epoch in range(1, args.epochs + 1):
        loss = train_epoch(model, train_loader, optimizer, device, class_weights)
        threshold, metrics = tune_confidence_threshold(
            model, validation_loader, device
        )
        history.append(
            {
                "epoch": epoch,
                "loss": loss,
                "confidence_threshold": threshold,
                **metrics,
            }
        )
        print(
            f"epoch={epoch} loss={loss:.4f} "
            f"precision={metrics['precision']:.4f} "
            f"recall={metrics['recall']:.4f} f1={metrics['f1']:.4f} "
            f"threshold={threshold:.2f}"
        )
        if metrics["f1"] > best_f1:
            best_f1 = metrics["f1"]
            best_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            best_threshold = threshold

    if best_state:
        model.load_state_dict(best_state)
    test_metrics = evaluate(model, test_loader, device, best_threshold)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    report = {
        "base_model": BASE_MODEL,
        "device": str(device),
        "configuration": vars(args),
        "confidence_threshold": best_threshold,
        "validation_history": history,
        "test_metrics": test_metrics,
        "limitations": [
            "Synthetic templated data may produce optimistic metrics.",
            "Results are POC validation metrics, not clinical performance claims.",
        ],
    }
    (OUTPUT_DIR / "training_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"saved_model={OUTPUT_DIR}")
    print(json.dumps(test_metrics, indent=2))


if __name__ == "__main__":
    main()
