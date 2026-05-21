"""
app/api/routes/system.py

System monitoring endpoints for the UI dashboard.
"""
import psutil
import subprocess
from fastapi import APIRouter

router = APIRouter()

def _get_gpu_stats():
    """Use nvidia-smi to fetch GPU stats natively on Windows/Linux without heavy libs."""
    try:
        # returns: utilization.gpu [%], memory.used [MiB], memory.total [MiB], temperature.gpu
        # e.g.: 15, 4500, 8192, 45
        output = subprocess.check_output([
            "nvidia-smi",
            "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
            "--format=csv,noheader,nounits"
        ], text=True).strip().split('\n')[0]
        
        parts = [p.strip() for p in output.split(",")]
        return {
            "gpu_util_percent": float(parts[0]),
            "vram_used_mb": float(parts[1]),
            "vram_total_mb": float(parts[2]),
            "gpu_temp_c": float(parts[3])
        }
    except Exception:
        return None

@router.get("/stats")
def get_system_stats():
    # CPU
    cpu_util = psutil.cpu_percent(interval=0.1)
    
    # RAM
    ram = psutil.virtual_memory()
    
    # GPU
    gpu = _get_gpu_stats()
    
    return {
        "cpu": {
            "utilization_percent": cpu_util,
            "cores": psutil.cpu_count(logical=True),
        },
        "ram": {
            "used_gb": round(ram.used / (1024**3), 1),
            "total_gb": round(ram.total / (1024**3), 1),
            "utilization_percent": ram.percent,
        },
        "gpu": gpu
    }
