#!/usr/bin/env python3
import subprocess
import datetime
import time
import curses
import os
import json
import sys

# ================== CONFIG ==================
CLUSTER_NAME = "eks-ray-llm"
REGION = "us-east-1"
CONTROL_PLANE_RATE = 0.10  # $ per hour fixed
UPDATE_INTERVAL = 30       # seconds
LOG_DIR = "cost_logs"      # Directory for session logs
# ===========================================

INSTANCE_PRICES = {
    "g5.xlarge": 1.006,
    "g5.2xlarge": 1.212,
    "g4dn.xlarge": 0.526,
    "p3.2xlarge": 3.06,
    "m5.large": 0.096,
    "m5.xlarge": 0.192,
    "m6i.2xlarge": 0.384,
    # Add more as needed
}

def run_cmd(cmd):
    # Insert the profile at the beginning of the command
    full_cmd = ["aws", "--profile", "terraform-local"] + cmd
    try:
        return subprocess.run(full_cmd, capture_output=True, text=True, check=True).stdout.strip()
    except:
        return None

def get_cluster_creation_time():
    return run_cmd(["eks", "describe-cluster", "--name", CLUSTER_NAME, "--region", REGION, "--query", "cluster.createdAt", "--output", "text"])

def get_instance_type():
    return run_cmd(["eks", "describe-nodegroup", "--cluster-name", CLUSTER_NAME, "--nodegroup-name", "gpu", "--region", REGION, "--query", "nodegroup.instanceTypes[0]", "--output", "text"]) or "unknown"

def get_node_rate(instance_type):
    return INSTANCE_PRICES.get(instance_type, 0.45)  # fallback average

def main(stdscr):
    curses.curs_set(0)
    curses.start_color()
    curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
    curses.init_pair(2, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(3, curses.COLOR_RED, curses.COLOR_BLACK)

    creation_time = None
    instance_type = None

    try:
        while True:
            stdscr.clear()
            stdscr.addstr(0, 0, "═" * 60, curses.A_BOLD)
            stdscr.addstr(1, 0, " LIVE EKS COST ESTIMATOR ", curses.A_BOLD | curses.color_pair(1))
            stdscr.addstr(2, 0, f" Cluster: {CLUSTER_NAME} | Region: {REGION}", curses.A_BOLD)
            stdscr.addstr(3, 0, "═" * 60, curses.A_BOLD)

            if not creation_time:
                creation_time = get_cluster_creation_time()
            if not instance_type:
                instance_type = get_instance_type()

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
            node_rate = get_node_rate(instance_type)
            gpu_cost = hours_running * node_rate
            total_cost = control_cost + gpu_cost

            stdscr.addstr(5, 0, f"⏱  Running: {hours_running:.3f} hours")
            stdscr.addstr(7, 0, f"💻 Node type: {instance_type} @ ${node_rate:.4f}/hr")
            stdscr.addstr(10, 0, "📊 SESSION TOTAL COST", curses.A_BOLD)
            stdscr.addstr(11, 2, f"${total_cost:.4f}", curses.color_pair(1) if total_cost < 5.0 else curses.color_pair(3) | curses.A_BOLD)

            stdscr.addstr(19, 0, f"🔄 Last update: {datetime.datetime.now().strftime('%H:%M:%S')} | Ctrl+C to exit")

            stdscr.refresh()
            time.sleep(UPDATE_INTERVAL)
    except KeyboardInterrupt:
        # On Ctrl+C, save session summary to dated JSON in log dir
        if creation_time:
            now = datetime.datetime.now()
            os.makedirs(LOG_DIR, exist_ok=True)
            file_name = f"eks_session_{now.strftime('%Y-%m-%d_%H-%M-%S')}.json"
            file_path = os.path.join(LOG_DIR, file_name)
            data = {
                "session_end": now.isoformat(),
                "creation_time": creation_time,
                "hours_running": round(hours_running, 3),
                "instance_type": instance_type,
                "control_cost": round(control_cost, 4),
                "gpu_cost": round(gpu_cost, 4),
                "total_cost": round(total_cost, 4)
            }
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
            stdscr.addstr(22, 0, f"Session saved to {file_path}. Exiting...", curses.A_BOLD)
        else:
            stdscr.addstr(22, 0, "No session data to save. Exiting...", curses.A_BOLD)
        stdscr.refresh()
        time.sleep(1)

if __name__ == "__main__":
    curses.wrapper(main)