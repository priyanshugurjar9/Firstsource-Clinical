# BioClinicalBERT NER Evaluation

## Final Result

The clinical entity extraction model was fine-tuned without changing the dataset, labels, or train/validation/test split.

| Metric | Test Score |
|---|---:|
| Precision | 82.69% |
| Recall | 97.50% |
| F1 score | 89.48% |

The previous test F1 was 25.93%. The improvement came from changing the training and decoding strategy, not from modifying the data.

## Training Configuration

```text
Base model: emilyalsentzer/Bio_ClinicalBERT
Epochs: 6
Batch size: 8
Maximum sequence length: 192
Unfrozen encoder layers: 2
Classifier learning rate: 5e-4
Encoder learning rate: 2e-5
Outside-token weight: 0.8
Selected confidence threshold: 0.30
```

## What Improved The Model

1. **Less aggressive class weighting**

   The original inverse-frequency weighting encouraged the model to predict too many entities. Square-root inverse-frequency weighting improved the balance between entity and non-entity tokens.

2. **Partial encoder fine-tuning**

   The final two BioClinicalBERT encoder layers were unfrozen. This allowed the model to adapt its clinical representations while preserving most of its pre-trained knowledge.

3. **Separate learning rates**

   The new classification head used a higher learning rate, while the pre-trained encoder layers used a smaller learning rate to avoid destructive updates.

4. **BIO-consistent decoding**

   Invalid `I-` labels are converted to valid entity starts when they do not follow an entity of the same type.

5. **Validation-selected confidence threshold**

   The confidence threshold was selected on the validation set and applied once to the test set. This reduced low-confidence false positives and improved precision.

## Validation Progress

| Epoch | Precision | Recall | F1 |
|---:|---:|---:|---:|
| 1 | 3.17% | 4.58% | 3.75% |
| 2 | 33.50% | 55.00% | 41.64% |
| 3 | 49.74% | 78.33% | 60.84% |
| 4 | 59.76% | 84.17% | 69.90% |
| 5 | 71.05% | 90.00% | 79.41% |
| 6 | 85.40% | 97.50% | 91.05% |

## Interpretation

These are proof-of-concept metrics measured on the existing synthetic dataset. They show that the model learned the labelled extraction task effectively, but they are not clinical validation results.

The synthetic notes contain repeated scenario patterns. Production evaluation would require de-identified real-world notes, independent annotation, external validation, and clinical review.
