# fpga-builder

This repo contains utilities to ease fpga building

Entry point is `builder.py`, other repositories should include this and extend it for their needs

Use `source go_fpga_builder.sh` to set up python path for importing the modules.

Alternatively, add a line like this to the top of your build script if a startfile is not part of your build flow
```python
THIS_DIR = Path(__file__).parent.absolute()
FPGA_BUILDER_DIR = THIS_DIR / "some/relative/path"
sys.path.append(FPGA_BUILDER_DIR)
```

# Installing dependencies

Dependencies are listed in `requirements.txt` and can be installed with the following:

```python
pip install -r requirements.txt
```

# Integrating with other projects

Add a `run.py` script similar to `example/run.py`. Point to the project TCL build script to auto build the project. Point to the SDK hardware platform for deploying.

To build a device:

`python run.py build device_a`

To build a device with commit:

`python run.py deploy device_a -c`

To see all options:

`python run.py -h`