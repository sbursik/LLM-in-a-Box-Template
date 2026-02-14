import json
import logging
import os
import platform
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class LocalEngine:
    def __init__(self):
        self.loaded_models = set()
        self.loading_models = set()  # Track models currently being loaded
        self.model_errors = {}  # Track loading errors {model_id: error_message}
        self.model_catalog = {}
        self.llama_servers = {}
        self.repo_root = Path(__file__).resolve().parents[2]
        self.allow_remote = os.environ.get("LLM_BOX_ALLOW_REMOTE", "0") == "1"

    def set_model_catalog(self, models):
        self.model_catalog = {model["id"]: model for model in models}

    def sync_loaded(self, model_ids):
        self.loaded_models = set(model_ids)

    def get_model_status(self, model_id):
        """Get the current status of a model: loading, loaded, error, or available."""
        if model_id in self.loading_models:
            return "loading"
        elif model_id in self.loaded_models:
            return "loaded"
        elif model_id in self.model_errors:
            return "error"
        else:
            return "available"
    
    def get_model_error(self, model_id):
        """Get the error message for a model that failed to load."""
        return self.model_errors.get(model_id)

    def load_model(self, model_id):
        self.loading_models.add(model_id)
        self.model_errors.pop(model_id, None)  # Clear any previous errors
        
        try:
            model = self._get_model(model_id)
            runtime = model.get("runtime", "ollama")
            logger.info("Loading model %s with runtime %s...", model_id, runtime)
            
            if runtime == "llamacpp":
                self._ensure_llama_server(model_id, model)
            
            self.loaded_models.add(model_id)
            logger.info("Model %s loaded successfully", model_id)
        except Exception as e:
            error_msg = str(e)
            self.model_errors[model_id] = error_msg
            logger.error("ERROR loading model %s: %s", model_id, error_msg)
            raise
        finally:
            self.loading_models.discard(model_id)

    def unload_model(self, model_id):
        self.loaded_models.discard(model_id)
        server = self.llama_servers.pop(model_id, None)
        if server:
            server["process"].terminate()
            try:
                server["process"].wait(timeout=5)
            except subprocess.TimeoutExpired:
                server["process"].kill()
                server["process"].wait(timeout=5)

    def reply(self, model_id, message):
        if model_id not in self.loaded_models and self.loaded_models:
            raise ValueError("Requested model is not loaded.")

        model = self._get_model(model_id)
        runtime = model.get("runtime", "ollama")

        if runtime == "llamacpp":
            self._ensure_llama_server(model_id, model)
            return self._llama_completion(model_id, model, message)
        if runtime == "ollama":
            return self._ollama_completion(model, message)

        raise ValueError(f"Unsupported runtime: {runtime}")

    def _get_model(self, model_id):
        if not self.model_catalog:
            raise ValueError("Model catalog is not initialized.")
        model = self.model_catalog.get(model_id)
        if model is None:
            raise ValueError("Unknown model id")
        return model

    def _pick_free_port(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def _ensure_llama_server(self, model_id, model):
        if model_id in self.llama_servers:
            return

        server_path = self._resolve_llama_server(model)
        model_path = self._resolve_model_path(model)
        port = int(model.get("port", 0)) or self._pick_free_port()

        logger.debug("Loading model %s", model_id)
        logger.debug("Server path: %s", server_path)
        logger.debug("Server exists: %s", server_path.exists())
        logger.debug("Model path: %s", model_path)
        logger.debug("Model exists: %s", model_path.exists())

        args = [
            str(server_path),
            "--model",
            str(model_path),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ]

        if "n_ctx" in model:
            args.extend(["--ctx-size", str(model["n_ctx"])])
        if "n_gpu_layers" in model:
            args.extend(["--n-gpu-layers", str(model["n_gpu_layers"])])
        for extra_arg in model.get("server_args", []):
            args.append(str(extra_arg))

        # Suppress llama-server output to keep console clean
        process = subprocess.Popen(
            args,
            cwd=str(self.repo_root),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.llama_servers[model_id] = {
            "process": process,
            "base_url": f"http://127.0.0.1:{port}",
        }

        time.sleep(0.5)

    def _resolve_llama_server(self, model):
        def _log_selection(path, reason):
            logger.info("llama.cpp server selected (%s): %s", reason, path)

        override = os.environ.get("LLM_BOX_LLAMA_CPP_SERVER_PATH")
        if override:
            selected = Path(override)
            _log_selection(selected, "override")
            return selected

        config_path = model.get("server_path")
        if config_path:
            resolved = Path(config_path)
            if not resolved.is_absolute():
                resolved = self.repo_root / resolved
            _log_selection(resolved, "model config")
            return resolved

        base_dir = self.repo_root / "app" / "backend" / "runtimes" / "llama.cpp"

        if os.name == "nt":
            binary_name = "llama-server.exe"
        else:
            binary_name = "llama-server"

        # Check flat structure first
        if (base_dir / binary_name).exists():
            selected = base_dir / binary_name
            _log_selection(selected, "flat layout")
            return selected

        system = platform.system().lower()
        machine = platform.machine().lower()
        is_arm = machine in {"arm64", "aarch64"}

        if system == "windows":
            pattern_order = ["*-bin-win-cpu-x64"]
        elif system == "darwin":
            if is_arm:
                pattern_order = ["*-bin-macos-arm64", "*-bin-macos-x64"]
            else:
                pattern_order = ["*-bin-macos-x64", "*-bin-macos-arm64"]
        elif system == "linux":
            pattern_order = ["*-bin-ubuntu-x64"]
        else:
            pattern_order = []

        for pattern in pattern_order:
            for build_dir in sorted(base_dir.glob(pattern)):
                matches = list(build_dir.glob(f"**/{binary_name}"))
                if matches:
                    selected = matches[0]
                    _log_selection(selected, f"build match {build_dir.name}")
                    return selected

        # Recursively search subdirectories as a fallback
        matching = list(base_dir.glob(f"**/{binary_name}"))
        if matching:
            selected = matching[0]
            _log_selection(selected, "fallback scan")
            return selected

        # Return default path (will fail with clear error if not found)
        return base_dir / binary_name

    def _resolve_model_path(self, model):
        artifact = model.get("artifact")
        if not artifact:
            raise ValueError("Model artifact is not configured.")
        resolved = Path(artifact)
        if not resolved.is_absolute():
            resolved = self.repo_root / resolved
        return resolved

    def _ollama_completion(self, model, message):
        base_url = model.get("base_url", "http://127.0.0.1:11434")
        self._assert_local_url(base_url)
        payload = {
            "model": model.get("artifact"),
            "prompt": message,
            "stream": False,
        }
        response = self._post_json(f"{base_url}/api/generate", payload)
        return response.get("response", "").strip()

    def _llama_completion(self, model_id, model, message):
        server = self.llama_servers.get(model_id)
        if server is None:
            raise ValueError("Model server is not running.")
        base_url = server["base_url"]
        
        # Format prompt for instruction-following models
        formatted_prompt = self._format_prompt(model, message)
        
        payload = {
            "prompt": formatted_prompt,
            "n_predict": int(model.get("n_predict", 512)),
            "temperature": float(model.get("temperature", 0.7)),
            "stop": model.get("stop_sequences", ["</s>", "<|im_end|>", "\n\nUser:", "\n\nQuestion:"]),
        }
        
        # Use longer timeout for reasoning models
        timeout = int(model.get("timeout", 120))
        response = self._post_json(f"{base_url}/completion", payload, timeout=timeout)
        content = response.get("content")
        if content is not None:
            return self._strip_reasoning_tags(content.strip())
        choices = response.get("choices")
        if choices:
            return self._strip_reasoning_tags(choices[0].get("text", "").strip())
        return ""
    
    def _format_prompt(self, model, message):
        """Format the user message into the model's expected prompt template."""
        template = model.get("prompt_template", "chatml")
        is_reasoning = model.get("is_reasoning_model", False)
        
        if template == "chatml":
            # ChatML format (used by dolphin, phi-3, qwen)
            if is_reasoning:
                system_msg = "You are a helpful assistant. Answer the question directly and concisely. Do not show your thinking process or reasoning steps. Only provide the final answer."
            else:
                system_msg = "You are a helpful assistant. Provide clear, concise answers."
            return f"<|im_start|>system\n{system_msg}<|im_end|>\n<|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n"
        elif template == "llama3":
            # Llama 3 format
            system_msg = "You are a helpful assistant. Provide clear, concise answers."
            return f"<|begin_of_text|><|start_header_id|>system<|end_header_id|>\n\n{system_msg}<|eot_id|><|start_header_id|>user<|end_header_id|>\n\n{message}<|eot_id|><|start_header_id|>assistant<|end_header_id|>\n\n"
        else:
            # Fallback: simple instruct format
            return f"### Instruction:\n{message}\n\n### Response:\n"
    
    def _strip_reasoning_tags(self, text):
        """Remove reasoning model <think> tags and extract only the final answer."""
        import re
        # Remove everything between <think> and </think> tags (reasoning steps)
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    def _post_json(self, url, payload, timeout=30):
        body = json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise ValueError(f"Runtime request failed: {exc}") from exc

    def _assert_local_url(self, url):
        if self.allow_remote:
            return
        parsed = urlparse(url)
        if parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise ValueError("Remote runtimes are disabled by default.")
