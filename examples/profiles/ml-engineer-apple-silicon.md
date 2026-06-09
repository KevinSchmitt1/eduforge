# Learner profile — ML engineer on Apple Silicon

Example of a specialised profile. Pass it with
`forged build --topic "..." --profile examples/profiles/ml-engineer-apple-silicon.md`.

## Who the learner is
An engineer with a solid classical-ML background moving into deep learning and LLMs.
Learns best with theory paired immediately to runnable code, anchored to ML concepts
they already know.

## Already knows well — do NOT re-explain these
- Python, NumPy, Pandas, Matplotlib
- Classical ML: training loops, overfitting, cross-validation, scikit-learn
- Neural network basics: forward pass, backprop, loss functions, softmax
- Linear algebra: dot products, matrix shapes, matrix multiplication

## Still building up — DO explain these carefully
- Transformer architecture and attention internals
- LLM-specific concepts (tokenization, sampling, generation)
- Fine-tuning (LoRA/QLoRA) and the HuggingFace ecosystem

## Environment / prerequisites the material must target
- Apple Silicon Mac. PyTorch device = "mps" if available, else "cpu". No CUDA.
- Prefer CPU/MPS-runnable demos; large model downloads must be called out explicitly.
- Privacy-sensitive context: prefer local/self-hosted options; do not assume it is
  fine to send data to a hosted API in a production framing.
