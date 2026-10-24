"""Step 0: check the training machine before anything else.

    python -m ml.detection.check_env

Prints Python, PyTorch, CUDA, GPU name and memory, and which packages are installed.
"""
import importlib
import platform
import sys


def main() -> None:
    print(f"Python      {sys.version.split()[0]} ({platform.system()})")
    try:
        import torch
    except ImportError:
        print("PyTorch     NOT INSTALLED -> see ml/detection/README.md, step 0")
        return
    print(f"PyTorch     {torch.__version__}")
    if torch.cuda.is_available():
        p = torch.cuda.get_device_properties(0)
        print(f"GPU         {p.name}, {p.total_memory / 1024**3:.1f} GB  (CUDA {torch.version.cuda})")
        x = torch.randn(1024, 1024, device="cuda")
        print(f"GPU test    OK (matrix sum {float((x @ x).sum()):.1f})")
    else:
        print("GPU         NOT AVAILABLE. Training on CPU would take many hours.")
        print("            Reinstall PyTorch with CUDA (README step 0) and update the NVIDIA driver.")
    for name in ["rfdetr", "transformers", "PIL", "cv2", "yaml", "supervision"]:
        try:
            mod = importlib.import_module(name)
            print(f"{name:<11} {getattr(mod, '__version__', 'installed')}")
        except ImportError:
            print(f"{name:<11} not installed")


if __name__ == "__main__":
    main()
