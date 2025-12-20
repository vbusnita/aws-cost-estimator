#!/usr/bin/env python3
import subprocess
import datetime
import time
import curses
import os
import json
import sys

# ================== CONFIG ==================
CLUSTER_NAME = "ray-llm-demo"
REGION = "us-east-1"
CONTROL_PLANE_RATE = 0.10  # $/hour fixed
LOG_FILE = "eks-cost-log.json"
MAX_TOTAL_COST = 5.0       # $ threshold for auto-destroy
IDLE_THRESHOLD_SECONDS = 1800  # 30 mins idle before enforcing destroy
INFRA_DIR = os.path.expanduser("/Users/alex/Documents/projects/eks-ray-llm/infra")  # Change if your infra folder is elsewhere
UPDATE_INTERVAL = 30       # seconds
AWS_PROFILE_FOR_DESTROY = "terraform-local"  # Your existing profile with destroy access
# ===========================================

# On-demand prices us-east-1 (Dec 2025 — update if needed)
INSTANCE_PRICES = {
    "g5.xlarge": 1.006,
    "g5.2xlarge": 1.212,
    "g4dn.xlarge": 0.526,
    "p3.2xlarge": 3.06,
    "m5.large": 0.096,
    # Add more as needed
}

def run_cmd(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip()
    except subprocess.CalledProcessError:
        return None

def get_cluster_creation_time():
    return run_cmd([
        "aws", "eks", "describe-cluster", "--name", CLUSTER_NAME,
        "--region", REGION, "--query", "cluster.createdAt", "--output", "text"
    ])

def get_instance_type():
    it = run_cmd([
        "aws", "eks", "describe-nodegroup", "--cluster-name", CLUSTER_NAME,
        "--nodegroup-name", "gpu", "--region", REGION,
        "--query", "nodegroup.instanceTypes[0]", "--output", "text"
    ])
    return it or "unknown"

def get_node_rate(instance_type):
    return INSTANCE_PRICES.get(instance_type, 0.45)  # fallback average

def get_idle_seconds():
    try:
        output = subprocess.check_output(["w", "-h"], text=True)
        lines = output.splitlines()
        if not lines:
            return 0

        # Find the line containing the script name (active one)
        active_line = None
        for line in lines:
            if "live_eks_cost_watcher.py" in line or "python" in line.lower():
                active_line = line
                break

        if not active_line:
            # Fallback to second line
            active_line = lines[1] if len(lines) > 1 else lines[0]

        parts = active_line.split()
        if len(parts) < 5:
            return 0

        idle_str = parts[4]

        if idle_str == "-" or "s" in idle_str:
            return 0

        if "days" in idle_str:
            return 999999

        if ":" in idle_str:
            try:
                h, m = map(int, idle_str.split(":"))
                return h * 3600 + m * 60
            except:
                return 0

        # Plain minutes "27" or "10m"
        try:
            if "m" in idle_str:
                return int(idle_str.replace("m", "")) * 60
            return int(idle_str) * 60
        except ValueError:
            return 0

    except:
        return 0

def log_cost(entry):
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)
    logs.append(entry)
    with open(LOG_FILE, "w") as f:
        json.dump(logs, f, indent=2)

def auto_destroy(total_cost, idle_seconds):
    if total_cost > MAX_TOTAL_COST and idle_seconds > IDLE_THRESHOLD_SECONDS:
        print("\n🚨 DEAD-MAN SWITCH TRIGGERED: Cost > $5 and idle > 30 mins")
        print("Running terraform destroy...")
        os.chdir(INFRA_DIR)
        os.environ["AWS_PROFILE"] = AWS_PROFILE_FOR_DESTROY
        subprocess.run(["terraform", "destroy", "-auto-approve"], check=True)
        sys.exit(0)

def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)

    instance_type = get_instance_type()
    node_rate = get_node_rate(instance_type)

    while True:
        stdscr.clear()
        stdscr.addstr(0, 0, "═" * 60, curses.A_BOLD)
        stdscr.addstr(1, 0, " LIVE EKS COST ESTIMATOR ", curses.A_BOLD | curses.color_pair(1))
        stdscr.addstr(2, 0, f" Cluster: {CLUSTER_NAME} | Region: {REGION}", curses.A_BOLD)
        stdscr.addstr(3, 0, "═" * 60, curses.A_BOLD)

        creation_time = get_cluster_creation_time()
        if not creation_time:
            stdscr.addstr(5, 0, "❌ Cluster not found — waiting for creation...", curses.color_pair(3))
            stdscr.refresh()
            time.sleep(UPDATE_INTERVAL)
            continue

        # Parse time
        try:
            dt = datetime.datetime.fromisoformat(creation_time.replace("Z", "+00:00"))
            hours_running = (time.time() - dt.timestamp()) / 3600
        except:
            stdscr.addstr(5, 0, "⚠️ Timestamp parse error", curses.color_pair(2))
            hours_running = 0

        control_cost = hours_running * CONTROL_PLANE_RATE
        gpu_cost = hours_running * node_rate
        total_cost = control_cost + gpu_cost

        idle_seconds = get_idle_seconds()

        # Dead-man check
        if total_cost > MAX_TOTAL_COST and idle_seconds > IDLE_THRESHOLD_SECONDS:
            auto_destroy(total_cost, idle_seconds)

        # Display
        stdscr.addstr(5, 0, f"⏱  Running: {hours_running:.3f} hours | Idle: {idle_seconds // 60}m")
        stdscr.addstr(7, 0, f"💻 Node type: {instance_type} @ ${node_rate:.4f}/hr")
        stdscr.addstr(9, 0, "📊 Costs so far:", curses.A_BOLD)
        stdscr.addstr(10, 2, f"Control plane: ${control_cost:.4f}")
        stdscr.addstr(11, 2, f"GPU node:      ${gpu_cost:.4f}")
        stdscr.addstr(12, 2, f"TOTAL:         ${total_cost:.4f}", curses.color_pair(1) if total_cost < MAX_TOTAL_COST else curses.color_pair(3) | curses.A_BOLD)
        stdscr.addstr(14, 0, f"🛡️  Dead-man: >${MAX_TOTAL_COST} + {IDLE_THRESHOLD_SECONDS//60}m idle → auto destroy")
        stdscr.addstr(15, 0, f"📄 Log: {LOG_FILE}")
        stdscr.addstr(17, 0, f"🔄 Last update: {datetime.datetime.now().strftime('%H:%M:%S')} | Ctrl+C to exit")

        # Log entry
        log_cost({
            "timestamp": datetime.datetime.now().isoformat(),
            "hours_running": round(hours_running, 3),
            "instance_type": instance_type,
            "control_cost": round(control_cost, 4),
            "gpu_cost": round(gpu_cost, 4),
            "total_cost": round(total_cost, 4),
            "idle_minutes": round(idle_seconds / 60, 1)
        })

        stdscr.refresh()
        time.sleep(UPDATE_INTERVAL)
            
if __name__ == "__main__":
    curses.wrapper(main)