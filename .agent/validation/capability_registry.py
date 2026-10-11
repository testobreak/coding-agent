# validation/capability_registry.py
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

class CapabilityStatus(Enum):
    AVAILABLE = "available"
    MISSING = "missing"
    BROKEN = "broken"

@dataclass
class Capability:
    tool: str
    status: CapabilityStatus
    version: str | None
    binary_path: str | None
    error: str | None

class CapabilityRegistry:
    def __init__(self, repo_root=None):
        self.repo_root = Path(repo_root) if repo_root else Path(".")
        self.manifest_path = self.repo_root / ".agent" / "capabilities.json"
        self.capabilities = {}
        self.scan_workspace(self.repo_root)

    def scan_workspace(self, repo_root):
        self.repo_root = Path(repo_root)
        self.manifest_path = self.repo_root / ".agent" / "capabilities.json"
        self.load_or_detect()

    def load_or_detect(self):
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                # Check for standard workspace capability manifest structure
                if "java" in data or "node" in data or "python" in data:
                    if "java" in data:
                        java_info = data["java"]
                        if "maven" in java_info and java_info["maven"]:
                            self.capabilities["maven"] = Capability(
                                tool="maven",
                                status=CapabilityStatus.AVAILABLE,
                                version=java_info.get("version"),
                                binary_path=java_info["maven"],
                                error=None
                            )
                        if "java" in java_info and java_info["java"]:
                            self.capabilities["java"] = Capability(
                                tool="java",
                                status=CapabilityStatus.AVAILABLE,
                                version=java_info.get("version"),
                                binary_path=java_info["java"],
                                error=None
                            )
                    if "node" in data:
                        node_info = data["node"]
                        if "npm" in node_info and node_info["npm"]:
                            self.capabilities["npm"] = Capability(
                                tool="npm",
                                status=CapabilityStatus.AVAILABLE,
                                version=node_info.get("version"),
                                binary_path=node_info["npm"],
                                error=None
                            )
                        if "node" in node_info and node_info["node"]:
                            self.capabilities["node"] = Capability(
                                tool="node",
                                status=CapabilityStatus.AVAILABLE,
                                version=node_info.get("version"),
                                binary_path=node_info["node"],
                                error=None
                            )
                    if "python" in data:
                        py_info = data["python"]
                        if "python" in py_info and py_info["python"]:
                            self.capabilities["python"] = Capability(
                                tool="python",
                                status=CapabilityStatus.AVAILABLE,
                                version=py_info.get("version"),
                                binary_path=py_info["python"],
                                error=None
                            )
                        if "pytest" in py_info and py_info["pytest"]:
                            self.capabilities["pytest"] = Capability(
                                tool="pytest",
                                status=CapabilityStatus.AVAILABLE,
                                version=py_info.get("version"),
                                binary_path=py_info["pytest"],
                                error=None
                            )
                    
                    # Fill missing tools with autodetect
                    for t in ["maven", "npm", "java", "node", "pytest", "python"]:
                        if t not in self.capabilities or self.capabilities[t].status != CapabilityStatus.AVAILABLE:
                            detected = self._detect_tool(t)
                            if detected.status == CapabilityStatus.AVAILABLE:
                                self.capabilities[t] = detected
                else:
                    # Direct Capability mapping
                    for k, v in data.items():
                        self.capabilities[k] = Capability(
                            tool=k,
                            status=CapabilityStatus(v.get("status", "missing")),
                            version=v.get("version"),
                            binary_path=v.get("binary_path"),
                            error=v.get("error")
                        )
                
                # Check that all 6 required tools are present
                for t in ["maven", "npm", "java", "node", "pytest", "python"]:
                    if t not in self.capabilities:
                        self.capabilities[t] = self._detect_tool(t)
                return
            except Exception as e:
                print(f"[CapabilityRegistry] Error loading capabilities manifest: {e}")

        # If not loaded successfully, run full detect
        self.detect()

    def detect(self):
        for t in ["maven", "npm", "java", "node", "pytest", "python"]:
            self.capabilities[t] = self._detect_tool(t)
        self.save_manifest()

    def _detect_tool(self, tool_name: str) -> Capability:
        import sys
        python_bin = sys.executable or "python"
        
        binary_map = {
            "maven": ("mvn", ["mvn", "-v"]),
            "npm": ("npm", ["npm", "-v"]),
            "java": ("java", ["java", "-version"]),
            "node": ("node", ["node", "-v"]),
            "pytest": ("pytest", ["pytest", "--version"]),
            "python": (python_bin, [python_bin, "--version"])
        }
        
        if tool_name not in binary_map:
            return Capability(tool=tool_name, status=CapabilityStatus.MISSING, version=None, binary_path=None, error="Unknown tool")
            
        binary, version_cmd = binary_map[tool_name]
        path = shutil.which(binary)

        if not path:
            return Capability(
                tool=tool_name,
                status=CapabilityStatus.MISSING,
                version=None,
                binary_path=None,
                error="Binary not found in PATH"
            )

        try:
            result = subprocess.run(
                version_cmd,
                capture_output=True,
                text=True,
                timeout=5
            )
            version = result.stdout or result.stderr
            version_str = version.strip() if version else None

            # Verify usable tool health check: if it fails with JAVA_HOME warning or has exit error
            if "JAVA_HOME" in (version_str or "") or result.returncode != 0:
                return Capability(
                    tool=tool_name,
                    status=CapabilityStatus.BROKEN,
                    version=version_str,
                    binary_path=path,
                    error="Tool health check failed"
                )

            return Capability(
                tool=tool_name,
                status=CapabilityStatus.AVAILABLE,
                version=version_str,
                binary_path=path,
                error=None
            )

        except Exception as e:
            return Capability(
                tool=tool_name,
                status=CapabilityStatus.BROKEN,
                version=None,
                binary_path=path,
                error=str(e)
            )

    def save_manifest(self):
        try:
            data = {
                "java": {
                    "maven": self.capabilities["maven"].binary_path if self.capabilities["maven"].status == CapabilityStatus.AVAILABLE else None,
                    "java": self.capabilities["java"].binary_path if self.capabilities["java"].status == CapabilityStatus.AVAILABLE else None,
                    "version": self.capabilities["maven"].version if self.capabilities["maven"].status == CapabilityStatus.AVAILABLE else (
                        self.capabilities["java"].version if self.capabilities["java"].status == CapabilityStatus.AVAILABLE else None
                    )
                },
                "node": {
                    "npm": self.capabilities["npm"].binary_path if self.capabilities["npm"].status == CapabilityStatus.AVAILABLE else None,
                    "node": self.capabilities["node"].binary_path if self.capabilities["node"].status == CapabilityStatus.AVAILABLE else None,
                    "version": self.capabilities["node"].version if self.capabilities["node"].status == CapabilityStatus.AVAILABLE else None
                },
                "python": {
                    "pytest": self.capabilities["pytest"].binary_path if self.capabilities["pytest"].status == CapabilityStatus.AVAILABLE else None,
                    "python": self.capabilities["python"].binary_path if self.capabilities["python"].status == CapabilityStatus.AVAILABLE else None,
                    "version": self.capabilities["pytest"].version if self.capabilities["pytest"].status == CapabilityStatus.AVAILABLE else (
                        self.capabilities["python"].version if self.capabilities["python"].status == CapabilityStatus.AVAILABLE else None
                    )
                }
            }
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.manifest_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[CapabilityRegistry] Failed saving manifest: {e}")
