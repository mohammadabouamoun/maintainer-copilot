import os
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

def main():
    model_dir = "models/classifier"
    print("Loading tokenizer from:", model_dir)
    tokenizer = AutoTokenizer.from_pretrained(model_dir)
    
    print("Loading PyTorch model from:", model_dir)
    model = AutoModelForSequenceClassification.from_pretrained(model_dir)
    model.eval()

    # Create sample dynamic input to trace operations graph
    dummy_text = "how do I configure the pipeline?"
    inputs = tokenizer(dummy_text, return_tensors="pt", truncation=True, max_length=512)
    
    # Define output ONNX graph target file
    onnx_path = os.path.join(model_dir, "model.onnx")
    print("Exporting PyTorch model to ONNX...")
    
    # Export using PyTorch ONNX engine
    torch.onnx.export(
        model,
        args=(inputs["input_ids"], inputs["attention_mask"]),
        f=onnx_path,
        input_names=["input_ids", "attention_mask"],
        output_names=["logits"],
        dynamic_axes={
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "logits": {0: "batch_size"}
        },
        opset_version=14
    )
    print("Successfully exported ONNX model to:", onnx_path)

if __name__ == "__main__":
    main()
