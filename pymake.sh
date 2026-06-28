#!/usr/bin/env bash
# Pass all arguments to the Python script located in the same directory
ENV_PATH=$(cat "$(dirname "$0")/.env_path" | tr -d '[:space:]')

if command -v mamba &> /dev/null; then
    mamba run -p "$ENV_PATH" python "$(dirname "$0")/pymakefile.py" "$@"
else
    conda run -p "$ENV_PATH" python "$(dirname "$0")/pymakefile.py" "$@"
fi
