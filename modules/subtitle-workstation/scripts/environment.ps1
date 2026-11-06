# Dot-source inside a child PowerShell process only. No persistent environment changes.
$WorkbenchRoot = Split-Path -Parent $PSScriptRoot
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONPATH = $null
$env:PYTHONHOME = $null
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$env:HF_HOME = Join-Path $WorkbenchRoot 'cache\huggingface'
$env:HF_HUB_CACHE = Join-Path $env:HF_HOME 'hub'
$env:HF_ASSETS_CACHE = Join-Path $env:HF_HOME 'assets'
$env:TRANSFORMERS_CACHE = Join-Path $env:HF_HOME 'transformers'
$env:TORCH_HOME = Join-Path $WorkbenchRoot 'cache\torch'
$env:XDG_CACHE_HOME = Join-Path $WorkbenchRoot 'cache\xdg'
$env:NLTK_DATA = Join-Path $WorkbenchRoot 'cache\nltk'
$env:NUMBA_CACHE_DIR = Join-Path $WorkbenchRoot 'cache\numba'
$env:MPLCONFIGDIR = Join-Path $WorkbenchRoot 'cache\matplotlib'
$env:PIP_CACHE_DIR = Join-Path $WorkbenchRoot 'cache\pip'
$env:PIP_CONFIG_FILE = 'NUL'
$env:UV_CACHE_DIR = Join-Path $WorkbenchRoot 'cache\uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $WorkbenchRoot 'runtime\python'
$env:UV_PYTHON_CACHE_DIR = Join-Path $WorkbenchRoot 'cache\python'
$env:UV_PYTHON_BIN_DIR = Join-Path $WorkbenchRoot 'runtime\python-bin'
$env:UV_PYTHON_INSTALL_BIN = '0'
$env:UV_PYTHON_INSTALL_REGISTRY = '0'
$env:UV_PYTHON_NO_REGISTRY = '1'
$env:UV_NO_MODIFY_PATH = '1'
$env:UV_NO_CONFIG = '1'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_LINK_MODE = 'copy'
$env:UV_HTTP_TIMEOUT = '180'
$env:UV_HTTP_RETRIES = '3'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:DO_NOT_TRACK = '1'
$env:TEMP = Join-Path $WorkbenchRoot 'temp'
$env:TMP = $env:TEMP
$env:VIRTUAL_ENV = Join-Path $WorkbenchRoot 'envs\subtitle'

# Legacy aliases must not redirect cache writes or inject package sources.
$env:HUGGINGFACE_HUB_CACHE = $env:HF_HUB_CACHE
$env:HUGGINGFACE_ASSETS_CACHE = $env:HF_ASSETS_CACHE
$env:UV_TOOL_DIR = Join-Path $WorkbenchRoot 'runtime\uv-tools'
$env:UV_TOOL_BIN_DIR = Join-Path $WorkbenchRoot 'runtime\uv-tools-bin'
foreach ($key in @('PIP_INDEX_URL','PIP_EXTRA_INDEX_URL','PIP_FIND_LINKS','UV_INDEX','UV_DEFAULT_INDEX','UV_INDEX_URL','UV_EXTRA_INDEX_URL','UV_FIND_LINKS','UV_INSECURE_HOST','UV_NO_VERIFY_HASHES')) {
    Remove-Item -LiteralPath ('Env:\' + $key) -ErrorAction SilentlyContinue
}


$env:UV_PYTHON_CPYTHON_BUILD = '20261026'

# Explicit project-local model transport caches; no persistent configuration.
$env:HF_XET_CACHE = Join-Path $WorkbenchRoot 'cache\huggingface\xet'
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = '1'
$env:HF_HUB_ENABLE_HF_TRANSFER = '0'

# GPU/JIT caches must also stay private to the workstation.
$env:CUDA_CACHE_PATH = Join-Path $WorkbenchRoot 'cache\cuda'
$env:PYTORCH_KERNEL_CACHE_PATH = Join-Path $WorkbenchRoot 'cache\pytorch-kernels'
$env:TORCHINDUCTOR_CACHE_DIR = Join-Path $WorkbenchRoot 'cache\torchinductor'
$env:TORCH_EXTENSIONS_DIR = Join-Path $WorkbenchRoot 'cache\torch-extensions'
$env:HF_DATASETS_CACHE = Join-Path $WorkbenchRoot 'cache\huggingface\datasets'
$env:JOBLIB_TEMP_FOLDER = Join-Path $WorkbenchRoot 'temp\joblib'
