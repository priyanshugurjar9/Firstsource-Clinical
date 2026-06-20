# BioClinicalBERT Checkpoint

The live application requires a fine-tuned token-classification checkpoint in this directory.

Required files:

```text
config.json
model.safetensors
tokenizer.json
tokenizer_config.json
training_report.json
```

`model.safetensors` is approximately 411 MB and is excluded from normal Git tracking because GitHub rejects individual files larger than 100 MB.

Verified local artifact:

```text
Size:   430,942,020 bytes
SHA256: 0157d8ab8f1051f6948a8c8d0a4f5478b7bb642b626fd929037210e9189cd10b
```

For submission, provide the weight file through one of these routes:

1. Attach it to a GitHub Release and place it here after cloning.
2. Track it with Git LFS.
3. Include it in the private submission archive used for the demo.

The application deliberately stops if this file is absent or the checkpoint cannot load. It does not silently switch to rule-only extraction.

Verify the artifact before the demo:

```bash
python scripts/verify_model_checkpoint.py
python scripts/verify_cross_format_bioclinicalbert.py
```
